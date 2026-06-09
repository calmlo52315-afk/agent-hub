from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


@dataclass
class PostgresMetricsSink:
    """PostgreSQL 实现 MetricsSink，写入 metric_events 表。

    与 JSONLinesMetricsSink 保持相同的 emit 接口。
    """

    dsn: str | None = None

    def __post_init__(self) -> None:
        if not HAS_PSYCOPG2:
            raise ImportError(
                "psycopg2 is required for PostgresMetricsSink. "
                "Install it with: pip install psycopg2-binary"
            )
        self.dsn = self.dsn or os.getenv(
            "METRICS_POSTGRES_DSN",
            os.getenv(
                "REPLAY_POSTGRES_DSN",
                "postgres://postgres:123456@localhost:5432/AgentHub?sslmode=disable",
            ),
        )

    def emit(self, *, event: dict[str, Any]) -> None:
        """写入一条 metric event 到 PostgreSQL。"""
        try:
            conn = psycopg2.connect(self.dsn)
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO metric_events (task_id, agent, metric, value, unit, tags)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.get("task_id", ""),
                        event.get("agent", ""),
                        event.get("metric", ""),
                        event.get("value", 0),
                        event.get("unit", "count"),
                        psycopg2.extras.Json(event.get("tags", {})),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Metrics 写入失败不抛异常，静默丢弃
            pass
