from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from runtime.harness.forbidden_actions import ForbiddenActionError
from runtime.harness.permissions import PermissionDenied
from runtime.orchestrator import Orchestrator


def _make_tmp_repo_root() -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    src_root = Path(__file__).resolve().parents[2]
    tmp_dir = tempfile.TemporaryDirectory()
    tmp_root = Path(tmp_dir.name)

    shutil.copytree((src_root / "rules").resolve(), (tmp_root / "rules").resolve())
    (tmp_root / "runtime" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp_root / "runtime" / "specs" / "index.json").write_text(
        json.dumps(
            json.loads((src_root / "runtime" / "specs" / "index.json").read_text(encoding="utf-8")),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_root / "demo_workspace").mkdir(parents=True, exist_ok=True)
    return tmp_root, tmp_dir


class _ForbiddenDeleteCodingAgent:
    agent_id: str = "coding"
    role: str = "coding"

    def __init__(self, *, target_path: str):
        self.target_path = target_path
        self.calls = 0

    def handle(self, *, payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "agent": "coding",
            "role": "coding",
            "plan": ["x"],
            "changes": [{"action": "delete", "path": self.target_path, "content": None, "base_hash": None}],
            "example_diff": None,
        }


class _ForbiddenWriteCodingAgent:
    agent_id: str = "coding"
    role: str = "coding"

    def __init__(self, *, target_path: str):
        self.target_path = target_path
        self.calls = 0

    def handle(self, *, payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "agent": "coding",
            "role": "coding",
            "plan": ["x"],
            "changes": [{"action": "create", "path": self.target_path, "content": "x\n", "base_hash": None}],
            "example_diff": None,
        }


class Stage2ForbiddenActionsTests(unittest.TestCase):
    def test_forbidden_delete_denied_at_runtime_boundary(self) -> None:
        repo_root, tmp_dir = _make_tmp_repo_root()
        self.addCleanup(tmp_dir.cleanup)
        forbidden_rel = "demo_workspace/forbidden.md"
        (repo_root / forbidden_rel).write_text("x\n", encoding="utf-8")

        orch = Orchestrator.load(repo_root=repo_root)
        agent = _ForbiddenDeleteCodingAgent(target_path=forbidden_rel)
        orch.agents["coding"] = agent
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["max_attempts"] = 3
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["backoff_seconds"] = [0, 0, 0]

        diagnostics: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        result, failure, retries = orch._call_agent_with_retry(
            stage="coding",
            task_id="t",
            trace_id="tr",
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
            shared_state={"workflow_state": "coding", "diagnostic_events": diagnostics},
            messages=messages,
            sleep_fn=lambda _: None,
        )
        self.assertIsNone(result)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.category.value, "permission_denied")
        self.assertEqual(retries, 0)
        self.assertEqual(agent.calls, 1)
        self.assertTrue((repo_root / forbidden_rel).exists())
        self.assertTrue(any(d.get("kind") == "forbidden_action" for d in diagnostics))

    def test_cross_ownership_write_denied_at_runtime_boundary(self) -> None:
        repo_root, tmp_dir = _make_tmp_repo_root()
        self.addCleanup(tmp_dir.cleanup)
        forbidden_rel = "artifacts/should_not_write.txt"

        orch = Orchestrator.load(repo_root=repo_root)
        agent = _ForbiddenWriteCodingAgent(target_path=forbidden_rel)
        orch.agents["coding"] = agent

        diagnostics: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        result, failure, retries = orch._call_agent_with_retry(
            stage="coding",
            task_id="t",
            trace_id="tr",
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
            shared_state={"workflow_state": "coding", "diagnostic_events": diagnostics},
            messages=messages,
            sleep_fn=lambda _: None,
        )
        self.assertIsNone(result)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.category.value, "permission_denied")
        self.assertEqual(retries, 0)
        self.assertEqual(agent.calls, 1)
        self.assertFalse((repo_root / forbidden_rel).exists())

    def test_deny_shell_flag_blocks_dangerous_operation(self) -> None:
        repo_root, tmp_dir = _make_tmp_repo_root()
        self.addCleanup(tmp_dir.cleanup)
        orch = Orchestrator.load(repo_root=repo_root)
        with self.assertRaises(PermissionDenied):
            orch.permission.check_dangerous(role="coding", op="shell")

    def test_forbidden_action_error_contains_violations(self) -> None:
        repo_root, tmp_dir = _make_tmp_repo_root()
        self.addCleanup(tmp_dir.cleanup)
        forbidden_rel = "demo_workspace/forbidden.md"
        (repo_root / forbidden_rel).write_text("x\n", encoding="utf-8")

        orch = Orchestrator.load(repo_root=repo_root)
        orch.agents["coding"] = _ForbiddenDeleteCodingAgent(target_path=forbidden_rel)

        env = orch._wrap_task_to_agent(
            task_id="t",
            trace_id="tr",
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
        )
        with self.assertRaises(ForbiddenActionError) as ctx:
            orch._call_agent(agent_id="coding", env=env, shared_state={"workflow_state": "coding", "diagnostic_events": []})
        self.assertGreaterEqual(len(ctx.exception.violations), 1)


if __name__ == "__main__":
    unittest.main()
