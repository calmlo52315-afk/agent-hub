from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

MetricName = Literal["task_success_rate", "retry_count", "review_pass_rate", "token_usage", "avg_response_time"]
MetricUnit = Literal["count", "ms", "token", "ratio"]


@dataclass(frozen=True)
class MetricEvent:
    task_id: str
    agent: str
    metric: MetricName
    value: int | float
    unit: MetricUnit
    timestamp: str
    tags: dict[str, str]

    @classmethod
    def now(
        cls,
        *,
        task_id: str,
        agent: str,
        metric: MetricName,
        value: int | float,
        unit: MetricUnit,
        tags: dict[str, str] | None = None,
    ) -> "MetricEvent":
        ts = datetime.now(timezone.utc).astimezone(timezone.utc).isoformat()
        return cls(
            task_id=task_id,
            agent=agent,
            metric=metric,
            value=value,
            unit=unit,
            timestamp=ts,
            tags=tags or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent": self.agent,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "tags": dict(self.tags),
        }
