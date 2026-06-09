from __future__ import annotations

import fnmatch
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator


class OwnershipError(RuntimeError):
    pass


class OwnershipDenied(PermissionError):
    pass


class LockTimeout(TimeoutError):
    pass


def _rel_posix(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as e:
        raise OwnershipError(f"path out of repo_root: {path}") from e


@dataclass
class _FileLock:
    lock: threading.Lock
    owner_role: str | None = None


@dataclass(frozen=True)
class LockReservation:
    """Describe one scheduler-level lease on a repository path.
    用于调度器提前判断文件是否被占用
    带租期，会自动过期，防止死锁
    """

    task_id: str
    subtask_id: str
    role: str
    mode: str
    acquired_at_monotonic: float
    lease_seconds: float # 自动过期时间


@dataclass(frozen=True)
class LockWaitRequest:
    """Describe one queued lock request waiting for conflicting paths."""

    task_id: str
    subtask_id: str
    role: str
    mode: str
    priority_rank: int
    queued_at_monotonic: float


@dataclass(frozen=True)
class OwnershipManager:
    repo_root: Path
    policy: dict[str, Any]
    _locks: dict[str, _FileLock]
    _locks_guard: threading.Lock
    _reservations: dict[str, list[LockReservation]]
    _wait_queues: dict[str, list[LockWaitRequest]]
    _reservation_guard: threading.Lock

    @classmethod
    def from_rules(cls, *, repo_root: Path, ownership_policy: dict[str, Any]) -> "OwnershipManager":
        return cls(
            repo_root=repo_root,
            policy=ownership_policy,
            _locks={},
            _locks_guard=threading.Lock(),
            _reservations={},
            _wait_queues={},
            _reservation_guard=threading.Lock(),
        )

    def resolve_owner(self, *, path: Path) -> dict[str, Any]:
        rules = (self.policy.get("rules") or {}).get("owners") or []
        rel_posix = _rel_posix(self.repo_root, path)
        for entry in rules:
            glob = entry.get("glob")
            if isinstance(glob, str) and fnmatch.fnmatch(rel_posix, glob):
                return entry
        raise OwnershipError(f"no owner rule matched: {rel_posix}")

    def assert_write_allowed(self, *, role: str, path: Path) -> None:
        entry = self.resolve_owner(path=path)
        write_roles = entry.get("write_roles") or []
        if role not in write_roles:
            rel_posix = _rel_posix(self.repo_root, path)
            raise OwnershipDenied(f"role not allowed to write: role={role} path={rel_posix}")

    def _get_lock(self, rel_posix: str) -> _FileLock:
        with self._locks_guard:
            lock = self._locks.get(rel_posix)
            if lock is None:
                lock = _FileLock(lock=threading.Lock(), owner_role=None)
                self._locks[rel_posix] = lock
            return lock

    def _default_lease_seconds(self) -> float:
        """Return the default scheduler lease duration."""

        raw = ((self.policy.get("rules") or {}).get("locking") or {}).get("lease_seconds")
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        return 30.0

    def _wait_age_boost_seconds(self) -> float:
        """Return the age interval used to reduce starvation in wait queues."""

        raw = ((self.policy.get("rules") or {}).get("locking") or {}).get("wait_age_boost_seconds")
        if isinstance(raw, (int, float)) and raw > 0:
            return float(raw)
        return 5.0

    def _wait_sort_key(self, request: LockWaitRequest) -> tuple[float, float, str]:
        """Return the fairness-aware ordering key for one queued waiter."""

        age_seconds = max(0.0, time.monotonic() - request.queued_at_monotonic)
        age_boost = int(age_seconds // self._wait_age_boost_seconds())
        effective_priority = max(-10, request.priority_rank - age_boost)
        return (float(effective_priority), request.queued_at_monotonic, request.subtask_id)

    def _dedupe_waiters_locked(self) -> None:
        """Remove duplicate waiter records while holding the reservation guard."""

        for rel_path, waiters in self._wait_queues.items():
            seen: set[tuple[str, str]] = set()
            deduped: list[LockWaitRequest] = []
            for waiter in waiters:
                key = (waiter.task_id, waiter.subtask_id)
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(waiter)
            self._wait_queues[rel_path] = deduped

    def _top_waiter_locked(self, rel_path: str) -> LockWaitRequest | None:
        """Return the current best waiter for one path while holding the lock."""

        waiters = self._wait_queues.get(rel_path) or []
        if not waiters:
            return None
        return sorted(waiters, key=self._wait_sort_key)[0]

    def enqueue_waiting_subtask(
        self,
        *,
        task_id: str,
        subtask_id: str,
        role: str,
        paths: list[Path],
        mode: str,
        priority_rank: int,
    ) -> None:
        """Register a blocked subtask in per-path wait queues."""

        rel_paths = sorted({_rel_posix(self.repo_root, path) for path in paths})
        request = LockWaitRequest(
            task_id=task_id,
            subtask_id=subtask_id,
            role=role,
            mode=mode,
            priority_rank=priority_rank,
            queued_at_monotonic=time.monotonic(),
        )
        with self._reservation_guard:
            for rel_path in rel_paths:
                bucket = self._wait_queues.setdefault(rel_path, [])
                if any(waiter.task_id == task_id and waiter.subtask_id == subtask_id for waiter in bucket):
                    continue
                bucket.append(request)
            self._dedupe_waiters_locked()

    def remove_waiting_subtask(self, *, task_id: str, subtask_id: str) -> None:
        """Remove one subtask from all wait queues."""

        with self._reservation_guard:
            empty_keys: list[str] = []
            for rel_path, waiters in self._wait_queues.items():
                kept = [
                    waiter
                    for waiter in waiters
                    if not (waiter.task_id == task_id and waiter.subtask_id == subtask_id)
                ]
                self._wait_queues[rel_path] = kept
                if not kept:
                    empty_keys.append(rel_path)
            for rel_path in empty_keys:
                self._wait_queues.pop(rel_path, None)

    def active_waiters(self, *, task_id: str | None = None) -> list[dict[str, str]]:
        """Return a snapshot of queued waiters for diagnostics and tests."""

        snapshot: list[dict[str, str]] = []
        with self._reservation_guard:
            self._dedupe_waiters_locked()
            for rel_path, waiters in self._wait_queues.items():
                for waiter in sorted(waiters, key=self._wait_sort_key):
                    if task_id is not None and waiter.task_id != task_id:
                        continue
                    snapshot.append(
                        {
                            "path": rel_path,
                            "task_id": waiter.task_id,
                            "subtask_id": waiter.subtask_id,
                            "role": waiter.role,
                            "mode": waiter.mode,
                            "priority_rank": str(waiter.priority_rank),
                        }
                    )
        return snapshot

    def _purge_expired_reservations_locked(self) -> list[dict[str, str | float]]:
        """Remove expired reservations while holding the reservation guard."""

        now = time.monotonic()
        expired_events: list[dict[str, str | float]] = []
        empty_keys: list[str] = []
        for rel_path, reservations in self._reservations.items():
            kept: list[LockReservation] = []
            for reservation in reservations:
                expires_at = reservation.acquired_at_monotonic + reservation.lease_seconds
                if now >= expires_at:
                    expired_events.append(
                        {
                            "path": rel_path,
                            "task_id": reservation.task_id,
                            "subtask_id": reservation.subtask_id,
                            "role": reservation.role,
                            "mode": reservation.mode,
                            "lease_seconds": reservation.lease_seconds,
                        }
                    )
                else:
                    kept.append(reservation)
            self._reservations[rel_path] = kept
            if not kept:
                empty_keys.append(rel_path)
        for rel_path in empty_keys:
            self._reservations.pop(rel_path, None)
        return expired_events

    def purge_expired_reservations(self) -> list[dict[str, str | float]]:
        """Remove expired scheduler-level leases and return expiration events."""

        with self._reservation_guard:
            return self._purge_expired_reservations_locked()
    #写锁互斥，读锁共享；一写全阻塞
    #从根源避免多 Agent 并发修改文件导致的代码冲突和脏数据。
    def try_acquire_subtask_locks(
        self,
        *,
        task_id: str,
        subtask_id: str,
        role: str,
        paths: list[Path],
        mode: str,
        lease_seconds: float | None = None,
    ) -> list[str]:
        """Try to reserve scheduler-level leases for one subtask.

        Returns the conflicting relative paths when the lease cannot be granted.
        An empty list means the reservation succeeded.
        """

        if mode not in ("read", "write"):
            raise OwnershipError(f"unsupported reservation mode: {mode}")

        rel_paths = sorted({_rel_posix(self.repo_root, path) for path in paths})
        if mode == "write":
            for path in paths:
                self.assert_write_allowed(role=role, path=path)
        lease = lease_seconds if isinstance(lease_seconds, (int, float)) and lease_seconds > 0 else self._default_lease_seconds()

        conflicts: list[str] = []
        with self._reservation_guard:
            self._purge_expired_reservations_locked()
            self._dedupe_waiters_locked()
            for rel_path in rel_paths:
                existing = self._reservations.get(rel_path) or []
                for reservation in existing:
                    if reservation.subtask_id == subtask_id:
                        continue
                    if reservation.mode == "write" or mode == "write":
                        conflicts.append(rel_path)
                        break
                if rel_path in conflicts:
                    continue
                top_waiter = self._top_waiter_locked(rel_path)
                if top_waiter is not None and top_waiter.subtask_id != subtask_id:
                    conflicts.append(rel_path)
            if conflicts:
                return conflicts

            for rel_path in rel_paths:
                bucket = self._reservations.setdefault(rel_path, [])
                bucket.append(
                    LockReservation(
                        task_id=task_id,
                        subtask_id=subtask_id,
                        role=role,
                        mode=mode,
                        acquired_at_monotonic=time.monotonic(),
                        lease_seconds=lease,
                    )
                )
            for rel_path in rel_paths:
                waiters = self._wait_queues.get(rel_path) or []
                kept = [waiter for waiter in waiters if waiter.subtask_id != subtask_id]
                self._wait_queues[rel_path] = kept
            empty_wait_keys = [rel_path for rel_path, waiters in self._wait_queues.items() if not waiters]
            for rel_path in empty_wait_keys:
                self._wait_queues.pop(rel_path, None)
        return []

    def release_subtask_locks(self, *, task_id: str, subtask_id: str) -> None:
        """Release all scheduler-level leases owned by one subtask."""

        with self._reservation_guard:
            empty_keys: list[str] = []
            for rel_path, reservations in self._reservations.items():
                kept = [
                    reservation
                    for reservation in reservations
                    if not (reservation.task_id == task_id and reservation.subtask_id == subtask_id)
                ]
                self._reservations[rel_path] = kept
                if not kept:
                    empty_keys.append(rel_path)
            for rel_path in empty_keys:
                self._reservations.pop(rel_path, None)
        self.remove_waiting_subtask(task_id=task_id, subtask_id=subtask_id)

    def active_reservations(self, *, task_id: str | None = None) -> list[dict[str, str]]:
        """Return a snapshot of active scheduler-level leases for diagnostics/context."""

        snapshot: list[dict[str, str]] = []
        with self._reservation_guard:
            for rel_path, reservations in self._reservations.items():
                for reservation in reservations:
                    if task_id is not None and reservation.task_id != task_id:
                        continue
                    snapshot.append(
                        {
                            "path": rel_path,
                            "task_id": reservation.task_id,
                            "subtask_id": reservation.subtask_id,
                            "role": reservation.role,
                            "mode": reservation.mode,
                            "lease_seconds": f"{reservation.lease_seconds:.3f}",
                        }
                    )
        snapshot.sort(key=lambda item: (item["path"], item["subtask_id"], item["mode"]))
        return snapshot

    #真正的操作系统锁
    @contextmanager
    def acquire_write_lock(self, *, role: str, path: Path, timeout_seconds: float | None = None) -> Generator[None, None, None]:
        rules = (self.policy.get("rules") or {}).get("locking") or {}
        required_ops = set(rules.get("required_for_ops") or [])
        mode = rules.get("mode")
        if mode != "per_file_write_lock":
            raise OwnershipError(f"unsupported lock mode: {mode}")

        if "write" not in required_ops and "delete" not in required_ops:
            yield
            return

        rel_posix = _rel_posix(self.repo_root, path)
        lock = self._get_lock(rel_posix)
        timeout = timeout_seconds
        if timeout is None:
            timeout = float(rules.get("default_timeout_seconds") or 30)

        start = time.monotonic()
        while True:
            acquired = lock.lock.acquire(timeout=0.05)
            if acquired:
                lock.owner_role = role
                break
            if time.monotonic() - start >= timeout:
                raise LockTimeout(f"lock timeout: {rel_posix}")

        try:
            yield
        finally:
            lock.owner_role = None
            lock.lock.release()
