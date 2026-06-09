from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from runtime.orchestrator import Orchestrator
from runtime.demo_cases import CASES


class LinearDemoCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("AGENTHUB_DISABLE_EXTERNAL_CLI", "1")

    def test_demo_cases_run_end_to_end(self) -> None:
        for case in CASES:
            with self.subTest(case=case.case_id):
                orch = Orchestrator.load()
                result = orch.run_task(instruction=case.instruction)

                # ── Handle approval gate ──────────────────────
                if result.get("status") == "approval_pending":
                    result = orch.resume_task(
                        task_id=result["task_id"],
                        trace_id=result["trace_id"],
                        approval_decision="approved",
                        task_plan_dict=result["task_plan"],
                        coding_output=result["coding_output"],
                        review_output=result["review_output"],
                        messages=result["messages"],
                        diagnostics=result["diagnostics"],
                    )

                self.assertTrue(result.get("ok", True))
                self.assertIsInstance(result.get("task_id"), str)
                self.assertIsInstance(result.get("trace_id"), str)
                self.assertEqual((result.get("result") or {}).get("execution_model"), "linear_pipeline")

                artifact_payload = (result.get("result") or {}).get("artifact") or {}
                artifact_dir = artifact_payload.get("artifact_dir")
                self.assertIsInstance(artifact_dir, str)

                artifact_path = (orch.repo_root / str(artifact_dir)).resolve()
                self.assertTrue(artifact_path.is_dir())

                metadata_path = artifact_path / "metadata.json"
                self.assertTrue(metadata_path.is_file())
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata.get("task_id"), result.get("task_id"))
                self.assertEqual(metadata.get("version"), "v1")

                created_files = artifact_payload.get("created_files") or []
                self.assertTrue(any(str(item).endswith("/metadata.json") for item in created_files))

                task_plan = (result.get("result") or {}).get("task_plan") or {}
                targets = task_plan.get("targets") or []
                self.assertGreaterEqual(len(targets), 1)
                for target in targets:
                    target_path = str((target or {}).get("path") or "")
                    self.assertTrue(target_path)
                    snapshot_path = artifact_path / "workspace" / Path(target_path)
                    self.assertTrue(snapshot_path.is_file(), f"missing snapshot for {target_path}")


if __name__ == "__main__":
    unittest.main()
