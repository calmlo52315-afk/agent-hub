from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.harness.replay import SQLiteReplayStore


class ReplaySQLiteStoreRetentionTests(unittest.TestCase):
    def test_retain_days_eviction_by_time(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "replay.sqlite3"
            store = SQLiteReplayStore(db_path=db_path, retain_days=30, max_records=5000)

            task_id = uuid.uuid4().hex
            trace_id = uuid.uuid4().hex

            now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
            old = now - timedelta(days=31)

            store.append_event(task_id=task_id, trace_id=trace_id, event_type="old", payload={"n": 1}, timestamp=old)
            store.append_event(task_id=task_id, trace_id=trace_id, event_type="new", payload={"n": 2}, timestamp=now)

            store.enforce_retention(now=now)

            records = store.list_records(task_id=task_id)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].payload.get("event_type"), "new")

    def test_max_records_eviction_keeps_newest_by_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "replay.sqlite3"
            store = SQLiteReplayStore(db_path=db_path, retain_days=30, max_records=2)

            task_id = uuid.uuid4().hex
            trace_id = uuid.uuid4().hex

            base = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
            t1 = base + timedelta(seconds=10)
            t2 = base + timedelta(seconds=20)
            t3 = base + timedelta(seconds=30)
            t4 = base + timedelta(seconds=40)

            store.append_event(task_id=task_id, trace_id=trace_id, event_type="t3", timestamp=t3)
            store.append_event(task_id=task_id, trace_id=trace_id, event_type="t1", timestamp=t1)
            store.append_event(task_id=task_id, trace_id=trace_id, event_type="t4", timestamp=t4)
            store.append_event(task_id=task_id, trace_id=trace_id, event_type="t2", timestamp=t2)

            records = store.list_records(task_id=task_id)
            self.assertEqual(len(records), 2)
            self.assertEqual([r.payload.get("event_type") for r in records], ["t3", "t4"])


if __name__ == "__main__":
    unittest.main()

