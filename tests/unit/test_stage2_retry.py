from __future__ import annotations

import unittest
from typing import Any

from runtime.orchestrator import Orchestrator


class _FlakyCodingAgent:
    agent_id: str = "coding"
    role: str = "coding"

    def __init__(self, *, fail_times: int, exc: BaseException) -> None:
        self._fail_times = fail_times
        self._exc = exc
        self.calls = 0

    def handle(self, *, payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self._fail_times:
            raise self._exc
        return {"agent": "coding", "role": "coding", "plan": ["ok"], "changes": []}


class Stage2RetryTests(unittest.TestCase):
    def test_retry_applies_limit_and_min_backoff_then_succeeds(self) -> None:
        orch = Orchestrator.load()
        orch.agents["coding"] = _FlakyCodingAgent(fail_times=2, exc=RuntimeError("transient"))
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["max_attempts"] = 3
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["backoff_seconds"] = [0, 0, 0]

        slept: list[float] = []

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        messages: list[dict[str, Any]] = []
        result, failure, retries = orch._call_agent_with_retry(
            stage="coding",
            task_id="t",
            trace_id="tr",
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
            shared_state={"workflow_state": "coding"},
            messages=messages,
            sleep_fn=fake_sleep,
        )
        self.assertIsNotNone(result)
        self.assertIsNone(failure)
        self.assertEqual(retries, 2)
        self.assertEqual(slept, [1.0, 1.0])
        self.assertEqual(getattr(orch.agents["coding"], "calls"), 3)
        self.assertGreaterEqual(len(messages), 3)

    def test_retry_exhaustion_returns_structured_failure(self) -> None:
        orch = Orchestrator.load()
        orch.agents["coding"] = _FlakyCodingAgent(fail_times=10, exc=TimeoutError("timeout"))
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["max_attempts"] = 2
        (orch.ruleset.execution.get("rules") or {}).setdefault("retry", {})["backoff_seconds"] = [0, 0]

        slept: list[float] = []

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        messages: list[dict[str, Any]] = []
        result, failure, retries = orch._call_agent_with_retry(
            stage="coding",
            task_id="t",
            trace_id="tr",
            agent_id="coding",
            payload={"task": {"instruction": "x", "targets": []}},
            shared_state={"workflow_state": "coding"},
            messages=messages,
            sleep_fn=fake_sleep,
        )
        self.assertIsNone(result)
        self.assertIsNotNone(failure)
        self.assertEqual(failure.category.value, "timeout")
        self.assertEqual(failure.attempts, 2)
        self.assertEqual(retries, 1)
        self.assertEqual(slept, [1.0])


if __name__ == "__main__":
    unittest.main()

