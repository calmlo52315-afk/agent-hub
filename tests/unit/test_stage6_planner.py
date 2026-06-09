from __future__ import annotations

import os
import unittest
from pathlib import Path

from runtime.config.rules_loader import load_ruleset
from runtime.config.spec_loader import load_spec
from runtime.harness.ownership import OwnershipManager
from runtime.harness.permissions import PermissionManager
from runtime.harness.workspace import Workspace
from runtime.planner import LinearPlanner


class LinearPlannerTests(unittest.TestCase):
    def _workspace(self) -> Workspace:
        repo_root = Path(__file__).resolve().parents[2]
        ruleset = load_ruleset(repo_root)
        _ = load_spec(repo_root)
        permission = PermissionManager(repo_root=repo_root, policy=ruleset.permission)
        ownership = OwnershipManager.from_rules(repo_root=repo_root, ownership_policy=ruleset.ownership)
        return Workspace(
            repo_root=repo_root,
            permission=permission,
            ownership=ownership,
            ruleset_ownership=ruleset.ownership,
        )

    def test_linear_planner_falls_back_to_rule_planner_when_llm_unconfigured(self) -> None:
        # 设空值阻止 load_dotenv() 重新加载，同时让 LLMClient.from_env() 报错 → fallback
        for key in ("OPENAI_API_KEY", "ORCHESTRATOR_BASE_URL", "ORCHESTRATOR_API_KEY", "ORCHESTRATOR_MODEL"):
            os.environ[key] = ""
        planner = LinearPlanner(workspace=self._workspace())

        plan, planner_used = planner.plan(task_id="task_linear_planner", instruction="请生成一个使用 Go 和 Gin 的最小 API 服务")

        self.assertEqual(planner_used, "rule_planner")
        self.assertEqual(plan.execution_model, "linear_pipeline")
        self.assertEqual(plan.task_type, "generate_api")
        self.assertGreaterEqual(len(plan.targets), 1)
        self.assertTrue(any(target.path.endswith("main.go") for target in plan.targets))


if __name__ == "__main__":
    unittest.main()
