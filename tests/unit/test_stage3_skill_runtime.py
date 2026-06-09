from __future__ import annotations

import unittest
from pathlib import Path

from runtime.config.rules_loader import load_ruleset
from runtime.config.spec_loader import load_spec
from runtime.harness.permissions import PermissionDenied
from runtime.orchestrator import Orchestrator
from runtime.skills import SkillRegistry, SkillRuntime


class Stage3SkillRuntimeTests(unittest.TestCase):
    def test_skill_runtime_plans_invocation_from_rules_and_registry(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec = load_spec(repo_root)
        ruleset = load_ruleset(repo_root)

        registry = SkillRegistry.from_spec(spec)
        runtime = SkillRuntime(
            execution_policy=ruleset.execution,
            permission_policy=ruleset.permission,
            registry=registry,
        )

        plan = runtime.plan_invocation(
            skill_name="coding.generate_patch",
            task_id="task_001",
            trace_id="trace_001",
            payload={"task": {"instruction": "x", "targets": []}},
            shared_state={"workflow_state": "coding", "diagnostic_events": []},
        )

        self.assertEqual(plan.definition.agent_binding, "coding")
        self.assertEqual(plan.timeout_seconds, 600)
        self.assertEqual(plan.budget_tokens, 50000)
        self.assertEqual(plan.budget_cost_usd, 5.0)
        self.assertEqual(plan.context["workflow_state"], "coding")

    def test_skill_runtime_rejects_skill_for_wrong_role(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec = load_spec(repo_root)
        ruleset = load_ruleset(repo_root)

        registry = SkillRegistry.from_spec(spec)
        runtime = SkillRuntime(
            execution_policy=ruleset.execution,
            permission_policy=ruleset.permission,
            registry=registry,
        )

        with self.assertRaises(PermissionDenied):
            runtime.assert_skill_allowed(
                role="review",
                skill_name="coding.generate_patch",
                invoker="orchestrator",
            )

    def test_orchestrator_run_demo_task_records_skill_dispatch(self) -> None:
        orch = Orchestrator.load()

        result = orch.run_demo_task(instruction="generate hello file")

        self.assertTrue(result["ok"])
        diagnostics = result.get("diagnostics") or []
        kinds = [item.get("kind") for item in diagnostics if isinstance(item, dict)]
        self.assertIn("skill_dispatch", kinds)


if __name__ == "__main__":
    unittest.main()
