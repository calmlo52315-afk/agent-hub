from __future__ import annotations

from dataclasses import dataclass, field

from runtime.harness.metrics.events import MetricEvent, MetricName, MetricUnit
from runtime.harness.metrics.jsonl_sink import MetricsSink


@dataclass
class MetricsHub:
    sinks: list[MetricsSink] = field(default_factory=list)
    default_tags: dict[str, str] = field(default_factory=dict)

    def emit_event(self, *, event: MetricEvent) -> None:
        obj = event.to_dict()
        tags = dict(self.default_tags)
        tags.update(obj.get("tags") or {})
        obj["tags"] = tags

        for sink in list(self.sinks):
            try:
                sink.emit(event=obj)
            except Exception:
                pass

    def emit(
        self,
        *,
        task_id: str,
        agent: str,
        metric: MetricName,
        value: int | float,
        unit: MetricUnit,
        tags: dict[str, str] | None = None,
    ) -> None:
        ev = MetricEvent.now(task_id=task_id, agent=agent, metric=metric, value=value, unit=unit, tags=tags)
        self.emit_event(event=ev)
