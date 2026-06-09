from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Any

from runtime.config.rules_loader import RulesLoadError, load_ruleset
from runtime.harness.state_machine import IllegalStateTransitionError, WorkflowStateMachine
from runtime.harness.validator import RuntimeValidationError, RuntimeValidator
from runtime.orchestrator import Orchestrator, OrchestratorError


class _BadCodingAgent:
    agent_id: str = "coding"
    role: str = "coding"

    def handle(self, *, payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
        return {"agent": "coding", "role": "coding", "plan": "not-a-list", "changes": []}


class Stage2NegativeTests(unittest.TestCase):
    def test_envelope_schema_invalid_raises(self) -> None:
        v = RuntimeValidator(expected_envelope_schema_version="1.0")
        with self.assertRaises(RuntimeValidationError):
            v.validate_envelope(envelope={"schema_version": "1.0"}, direction="outbound")

    def test_agent_output_schema_invalid_persists_error(self) -> None:
        orch = Orchestrator.load()
        orch.agents["coding"] = _BadCodingAgent()

        task_id = uuid.uuid4().hex
        trace_id = uuid.uuid4().hex

        env = orch._wrap_task_to_agent(
            task_id=task_id,
            trace_id=trace_id,
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
        )

        with self.assertRaises(OrchestratorError):
            orch._call_agent(agent_id="coding", env=env, shared_state={"workflow_state": "coding"})

        err_root = (orch.repo_root / "artifacts" / "validation_errors" / task_id).resolve()
        self.assertTrue(err_root.is_dir())
        files = sorted(p for p in err_root.iterdir() if p.is_file() and p.suffix == ".json")
        self.assertGreaterEqual(len(files), 1)
        obj = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(obj.get("task_id"), task_id)
        self.assertEqual(obj.get("trace_id"), trace_id)
        self.assertEqual((obj.get("context") or {}).get("kind"), "agent_output")

    def test_rules_required_sections_missing_raises(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        src_rules = (repo_root / "rules").resolve()

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            tmp_rules = tmp_root / "rules"
            tmp_rules.mkdir(parents=True, exist_ok=True)

            index = json.loads((src_rules / "index.json").read_text(encoding="utf-8"))
            (tmp_rules / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            for name in (
                "execution-rules.json",
                "permission-rules.json",
                "ownership-rules.json",
                "communication-rules.json",
            ):
                obj = json.loads((src_rules / name).read_text(encoding="utf-8"))
                if name == "execution-rules.json":
                    rules = obj.get("rules") or {}
                    rules.pop("workflow", None)
                    obj["rules"] = rules
                (tmp_rules / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            with self.assertRaises(RulesLoadError):
                load_ruleset(tmp_root)

    def test_state_machine_illegal_transition_emits_diagnostic(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        ruleset = load_ruleset(repo_root)
        sm = WorkflowStateMachine.from_execution_policy(ruleset.execution, initial_state="created")
        diagnostics: list[dict[str, Any]] = []
        with self.assertRaises(IllegalStateTransitionError):
            sm.transition(event="review.pass", diagnostics=diagnostics)
        self.assertGreaterEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[-1].get("kind"), "illegal_transition")


if __name__ == "__main__":
    unittest.main()

