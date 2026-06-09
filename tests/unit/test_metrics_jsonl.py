from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from runtime.harness.metrics import JSONLinesMetricsSink, MetricEvent, MetricsHub
from runtime.orchestrator import Orchestrator


class _FailSink:
    def emit(self, *, event: dict[str, Any]) -> None:
        raise RuntimeError("sink failed")


class MetricsJSONLinesTests(unittest.TestCase):
    def test_jsonl_sink_writes_one_event_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "metrics.jsonl"
            hub = MetricsHub(
                sinks=[JSONLinesMetricsSink(out_path=out_path)],
                default_tags={"stage": "stage-2-harness-stability", "schema_version": "v1"},
            )
            hub.emit_event(
                event=MetricEvent.now(
                    task_id="t1",
                    agent="coding",
                    metric="avg_response_time",
                    value=123,
                    unit="ms",
                    tags={"k": "v"},
                )
            )

            lines = out_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            obj = json.loads(lines[0])
            self.assertEqual(obj["task_id"], "t1")
            self.assertEqual(obj["agent"], "coding")
            self.assertEqual(obj["metric"], "avg_response_time")
            self.assertEqual(obj["unit"], "ms")
            self.assertEqual((obj.get("tags") or {}).get("k"), "v")
            self.assertEqual((obj.get("tags") or {}).get("stage"), "stage-2-harness-stability")

    def test_best_effort_sink_failure_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "metrics.jsonl"
            hub = MetricsHub(sinks=[_FailSink(), JSONLinesMetricsSink(out_path=out_path)])
            hub.emit_event(
                event=MetricEvent.now(
                    task_id="t1",
                    agent="orchestrator",
                    metric="retry_count",
                    value=0,
                    unit="count",
                )
            )
            lines = out_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

    def test_orchestrator_emits_required_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "metrics.jsonl"
            orch = Orchestrator.load()
            orch.metrics = MetricsHub(sinks=[JSONLinesMetricsSink(out_path=out_path)])

            hello = (orch.repo_root / "demo_workspace" / "hello.txt").resolve()
            old = hello.read_text(encoding="utf-8") if hello.exists() else None

            try:
                orch.run_demo_task(instruction="emit metrics")
            finally:
                if old is None:
                    if hello.exists():
                        hello.unlink()
                else:
                    hello.write_text(old, encoding="utf-8")

            events = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            metrics = {e.get("metric") for e in events}
            self.assertTrue(
                {"task_success_rate", "retry_count", "review_pass_rate", "token_usage", "avg_response_time"}.issubset(metrics)
            )

            for e in events:
                self.assertTrue(isinstance(e.get("task_id"), str) and e.get("task_id"))
                self.assertTrue(isinstance(e.get("agent"), str) and e.get("agent"))


if __name__ == "__main__":
    unittest.main()

