from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator, Literal, cast

# psycopg2 是可选依赖，仅在启用 PostgreSQL 后端时需要
try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

ReplayRecordType = Literal["message", "event", "artifact"]


@dataclass(frozen=True)
class ReplayRecord:
    id: int
    task_id: str
    trace_id: str | None
    record_type: ReplayRecordType
    ts_ms: int
    timestamp: str
    payload: dict[str, Any]


def _dt_to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class PostgresReplayStore:
    """PostgreSQL 实现 Replay 存储，写入统一的 events 表。

    与 SQLiteReplayStore 保持相同的方法签名，调用方不需要改动。
    """

    def __init__(
        self,
        *,
        dsn: str | None = None,
        retain_days: int = 30,
        max_records: int = 5000,
    ) -> None:
        if not HAS_PSYCOPG2:
            raise ImportError(
                "psycopg2 is required for PostgresReplayStore. "
                "Install it with: pip install psycopg2-binary"
            )

        dsn = dsn or os.getenv(
            "REPLAY_POSTGRES_DSN",
            "postgres://agenthub:agenthub@localhost:5432/agenthub?sslmode=disable",
        )
        self.dsn = dsn
        self.retain_days = int(retain_days)
        self.max_records = int(max_records)

    @contextmanager
    def _connect(self) -> Iterator[psycopg2.extensions.connection]:
        conn = psycopg2.connect(self.dsn)
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def append_message(self, *, envelope: dict[str, Any]) -> None:
        task_id = cast(str, envelope.get("task_id"))
        trace_id = cast(str | None, envelope.get("trace_id"))
        timestamp = cast(str, envelope.get("timestamp"))
        dt = _parse_iso(timestamp)
        ts_ms = _dt_to_ms(dt)

        sender = envelope.get("sender") or {}
        receiver = envelope.get("receiver") or {}
        session_id = ""
        if isinstance(sender, dict):
            session_id = sender.get("session_id", "")

        role = "agent"
        agent_name = ""
        if isinstance(sender, dict):
            sender_type = sender.get("type", "")
            if sender_type == "user":
                role = "user"
            elif sender_type == "system":
                role = "system"
            else:
                role = "agent"
            agent_name = sender.get("id", "")

        payload = dict(envelope)
        metadata: dict[str, Any] = {
            "message_id": envelope.get("message_id"),
            "msg_kind": envelope.get("kind"),
            "msg_status": envelope.get("status"),
            "sender": sender,
            "receiver": receiver,
            "in_reply_to": envelope.get("in_reply_to"),
        }
        # 清理 None 值
        metadata = {k: v for k, v in metadata.items() if v is not None}

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO events (session_id, task_id, trace_id, seq, event_type,
                                    role, agent_name, payload, metadata, created_at)
                VALUES (%s, %s, %s,
                        COALESCE((SELECT MAX(seq) FROM events WHERE session_id = %s), 0) + 1,
                        'message.agent', %s, %s, %s, %s, %s)
                """,
                (
                    session_id if session_id else None,
                    task_id if task_id else None,
                    trace_id,
                    session_id if session_id else None,
                    role,
                    agent_name if agent_name else None,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
                    dt,
                ),
            )
            self._enforce_retention(conn=conn, now=dt)

    def append_event(
        self,
        *,
        task_id: str,
        trace_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        dt = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        ts_ms = _dt_to_ms(dt)

        obj = {
            "task_id": task_id,
            "trace_id": trace_id,
            "event_type": event_type,
            "timestamp": dt.isoformat(),
            "payload": payload or {},
        }

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO events (session_id, task_id, trace_id, seq, event_type,
                                    payload, created_at)
                VALUES (%s, %s, %s, 0, %s, %s, %s)
                """,
                (
                    None,  # session_id 从 task_id 可推导，暂留空
                    task_id if task_id else None,
                    trace_id,
                    event_type,
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    dt,
                ),
            )
            self._enforce_retention(conn=conn, now=dt)

    def append_artifact(
        self,
        *,
        task_id: str,
        trace_id: str | None,
        artifact_id: str,
        artifact_dir: str,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        dt = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
        ts_ms = _dt_to_ms(dt)

        obj = {
            "task_id": task_id,
            "trace_id": trace_id,
            "artifact_id": artifact_id,
            "artifact_dir": artifact_dir,
            "timestamp": dt.isoformat(),
            "payload": payload or {},
        }

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO events (session_id, task_id, trace_id, seq, event_type,
                                    payload, created_at)
                VALUES (%s, %s, %s, 0, 'artifact.created', %s, %s)
                """,
                (
                    None,
                    task_id if task_id else None,
                    trace_id,
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    dt,
                ),
            )
            self._enforce_retention(conn=conn, now=dt)

    def list_records(
        self, *, task_id: str | None = None, limit: int | None = None
    ) -> list[ReplayRecord]:
        where = ""
        args: list[Any] = []
        if task_id is not None:
            where = "WHERE task_id = %s"
            args.append(task_id)

        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT %s"
            args.append(int(limit))

        query = f"""
            SELECT id, task_id, trace_id, event_type,
                   EXTRACT(EPOCH FROM created_at)::BIGINT * 1000 AS ts_ms,
                   created_at::TEXT AS timestamp,
                   payload
            FROM events
            {where}
            ORDER BY created_at ASC, id ASC
            {limit_sql}
        """

        with self._connect() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, tuple(args))
            rows = cur.fetchall()

        out: list[ReplayRecord] = []
        for r in rows:
            payload = r["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)

            # 从 payload 或 event_type 推导 record_type
            event_type = str(r["event_type"] or "")
            if event_type.startswith("message"):
                record_type: ReplayRecordType = "message"
            elif event_type.startswith("artifact"):
                record_type = "artifact"
            else:
                record_type = "event"

            out.append(
                ReplayRecord(
                    id=int(r["id"]),
                    task_id=str(r["task_id"]) if r["task_id"] else "",
                    trace_id=str(r["trace_id"]) if r["trace_id"] else None,
                    record_type=record_type,
                    ts_ms=int(r["ts_ms"]),
                    timestamp=str(r["timestamp"]),
                    payload=cast(dict[str, Any], payload),
                )
            )
        return out

    def count_records(self) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS c FROM events")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def enforce_retention(self, *, now: datetime | None = None) -> None:
        dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self._connect() as conn:
            self._enforce_retention(conn=conn, now=dt)

    def _enforce_retention(
        self, *, conn: psycopg2.extensions.connection, now: datetime
    ) -> None:
        cutoff = now - timedelta(days=self.retain_days)

        cur = conn.cursor()
        cur.execute("DELETE FROM events WHERE created_at < %s", (cutoff,))

        cur.execute("SELECT COUNT(*) AS c FROM events")
        total = int(cur.fetchone()[0])
        if total <= self.max_records:
            return

        excess = total - self.max_records
        cur.execute(
            """
            DELETE FROM events
            WHERE id IN (
              SELECT id FROM events
              ORDER BY created_at ASC, id ASC
              LIMIT %s
            )
            """,
            (excess,),
        )
