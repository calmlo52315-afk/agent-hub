from __future__ import annotations

import json
import unittest
from pathlib import Path

from runtime.orchestrator import Orchestrator


class RuntimeSmokeTest(unittest.TestCase):
    def test_run_one_task_no_crash_no_conflict_outputs_artifact(self) -> None:
        orch = Orchestrator.load()

        target_rel = "demo_workspace/hello.txt"
        hash_before = orch.workspace.file_hash(rel_path=target_rel)

        result = orch.run_demo_task(instruction="smoke test: run one task end-to-end")

        self.assertIsInstance(result.get("task_id"), str)
        self.assertIsInstance(result.get("trace_id"), str)

        messages = result.get("messages")
        self.assertIsInstance(messages, list)
        self.assertGreaterEqual(len(messages), 1)

        first_payload = (messages[0] or {}).get("payload") or {}
        target = ((first_payload.get("task") or {}).get("targets") or [{}])[0] or {}
        base_hash = target.get("base_hash")
        self.assertEqual(base_hash, hash_before)

        artifact_payload = (result.get("result") or {}).get("artifact") or {}
        artifact_dir = artifact_payload.get("artifact_dir")
        self.assertIsInstance(artifact_dir, str)

        created_files = artifact_payload.get("created_files")
        self.assertIsInstance(created_files, list)
        self.assertTrue(any(str(p).endswith("/metadata.json") for p in created_files))
        self.assertTrue(any("/workspace/" in str(p) for p in created_files))

        artifact_path = (orch.repo_root / str(artifact_dir)).resolve()
        self.assertTrue(artifact_path.is_dir())

        metadata_path = artifact_path / "metadata.json"
        self.assertTrue(metadata_path.is_file())
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata.get("task_id"), result.get("task_id"))

        snapshot_path = artifact_path / "workspace" / Path(target_rel)
        self.assertTrue(snapshot_path.is_file())
        snapshot_text = snapshot_path.read_text(encoding="utf-8")
        self.assertIn("Hello, AgentHub!", snapshot_text)


if __name__ == "__main__":
    unittest.main()

