from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, cast

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


class SQLiteReplayStore:
    def __init__(
        self,
        *,
        db_path: Path,
        retain_days: int = 30,
        max_records: int = 5000,
    ) -> None:
        self.db_path = db_path
        self.retain_days = int(retain_days)
        self.max_records = int(max_records)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._init_schema(conn)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS replay_records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id TEXT NOT NULL,
              trace_id TEXT,
              record_type TEXT NOT NULL,
              ts_ms INTEGER NOT NULL,
              timestamp TEXT NOT NULL,
              payload_json TEXT NOT NULL,

              message_id TEXT,
              msg_kind TEXT,
              msg_status TEXT,
              sender_type TEXT,
              sender_id TEXT,
              receiver_type TEXT,
              receiver_id TEXT,
              in_reply_to TEXT,

              event_type TEXT,

              artifact_id TEXT,
              artifact_dir TEXT
            )
            """,
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_task_ts ON replay_records(task_id, ts_ms, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_ts ON replay_records(ts_ms, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_type_ts ON replay_records(record_type, ts_ms, id)")

    def append_message(self, *, envelope: dict[str, Any]) -> None:
        task_id = cast(str, envelope.get("task_id"))
        trace_id = cast(str | None, envelope.get("trace_id"))
        timestamp = cast(str, envelope.get("timestamp"))
        dt = _parse_iso(timestamp)
        ts_ms = _dt_to_ms(dt)

        sender = envelope.get("sender") or {}
        receiver = envelope.get("receiver") or {}

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO replay_records (
                  task_id, trace_id, record_type, ts_ms, timestamp, payload_json,
                  message_id, msg_kind, msg_status, sender_type, sender_id, receiver_type, receiver_id, in_reply_to
                ) VALUES (
                  ?, ?, 'message', ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    task_id,
                    trace_id,
                    ts_ms,
                    timestamp,
                    json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
                    envelope.get("message_id"),
                    envelope.get("kind"),
                    envelope.get("status"),
                    (sender.get("type") if isinstance(sender, dict) else None),
                    (sender.get("id") if isinstance(sender, dict) else None),
                    (receiver.get("type") if isinstance(receiver, dict) else None),
                    (receiver.get("id") if isinstance(receiver, dict) else None),
                    envelope.get("in_reply_to"),
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
        ts_iso = dt.isoformat()
        obj = {"task_id": task_id, "trace_id": trace_id, "event_type": event_type, "timestamp": ts_iso, "payload": payload or {}}

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO replay_records (
                  task_id, trace_id, record_type, ts_ms, timestamp, payload_json, event_type
                ) VALUES (
                  ?, ?, 'event', ?, ?, ?, ?
                )
                """,
                (
                    task_id,
                    trace_id,
                    ts_ms,
                    ts_iso,
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    event_type,
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
        ts_iso = dt.isoformat()
        obj = {
            "task_id": task_id,
            "trace_id": trace_id,
            "artifact_id": artifact_id,
            "artifact_dir": artifact_dir,
            "timestamp": ts_iso,
            "payload": payload or {},
        }

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO replay_records (
                  task_id, trace_id, record_type, ts_ms, timestamp, payload_json, artifact_id, artifact_dir
                ) VALUES (
                  ?, ?, 'artifact', ?, ?, ?, ?, ?
                )
                """,
                (
                    task_id,
                    trace_id,
                    ts_ms,
                    ts_iso,
                    json.dumps(obj, ensure_ascii=False, separators=(",", ":")),
                    artifact_id,
                    artifact_dir,
                ),
            )
            self._enforce_retention(conn=conn, now=dt)

    def list_records(self, *, task_id: str | None = None, limit: int | None = None) -> list[ReplayRecord]:
        where = ""
        args: list[Any] = []
        if task_id is not None:
            where = "WHERE task_id = ?"
            args.append(task_id)

        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT ?"
            args.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id, task_id, trace_id, record_type, ts_ms, timestamp, payload_json FROM replay_records {where} ORDER BY ts_ms ASC, id ASC {limit_sql}"
                ,
                tuple(args),
            ).fetchall()

        out: list[ReplayRecord] = []
        for r in rows:
            out.append(
                ReplayRecord(
                    id=int(r["id"]),
                    task_id=str(r["task_id"]),
                    trace_id=(str(r["trace_id"]) if r["trace_id"] is not None else None),
                    record_type=cast(ReplayRecordType, str(r["record_type"])),
                    ts_ms=int(r["ts_ms"]),
                    timestamp=str(r["timestamp"]),
                    payload=cast(dict[str, Any], json.loads(str(r["payload_json"]))),
                )
            )
        return out

    def count_records(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM replay_records").fetchone()
            return int(row["c"] if row is not None else 0)

    def enforce_retention(self, *, now: datetime | None = None) -> None:
        dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self._connect() as conn:
            self._enforce_retention(conn=conn, now=dt)

    def _enforce_retention(self, *, conn: sqlite3.Connection, now: datetime) -> None:
        cutoff = now - timedelta(days=self.retain_days)
        cutoff_ms = _dt_to_ms(cutoff)

        conn.execute("DELETE FROM replay_records WHERE ts_ms < ?", (cutoff_ms,))

        row = conn.execute("SELECT COUNT(*) AS c FROM replay_records").fetchone()
        total = int(row["c"] if row is not None else 0)
        if total <= self.max_records:
            return

        excess = total - self.max_records
        conn.execute(
            """
            DELETE FROM replay_records
            WHERE id IN (
              SELECT id FROM replay_records
              ORDER BY ts_ms ASC, id ASC
              LIMIT ?
            )
            """,
            (excess,),
        )

