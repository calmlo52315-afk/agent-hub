from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generic, TypeVar


class FailureCategory(str, Enum):
    schema_invalid = "schema_invalid"
    review_failed = "review_failed"
    timeout = "timeout"
    permission_denied = "permission_denied"
    unknown = "unknown"


@dataclass(frozen=True)
class FailureInfo:
    category: FailureCategory
    stage: str
    message: str
    attempts: int
    retry_limit: int
    exception_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "kind": "failure",
            "category": self.category.value,
            "stage": self.stage,
            "message": self.message,
            "attempts": self.attempts,
            "retry_limit": self.retry_limit,
            "exception_type": self.exception_type,
            "created_at": time.time(),
        }


@dataclass(frozen=True)
class RetryPolicy:
    retry_limit: int
    backoff_seconds: list[float]
    min_backoff_seconds: float = 1.0

    def max_attempts(self) -> int:
        if self.retry_limit <= 0:
            return 1
        return self.retry_limit

    def backoff_for_attempt(self, *, attempt_index: int) -> float:
        if attempt_index < 0:
            return self.min_backoff_seconds
        if not self.backoff_seconds:
            return self.min_backoff_seconds
        idx = min(attempt_index, len(self.backoff_seconds) - 1)
        raw = float(self.backoff_seconds[idx])
        if raw < self.min_backoff_seconds:
            return self.min_backoff_seconds
        return raw


T = TypeVar("T")


@dataclass(frozen=True)
class RetryOutcome(Generic[T]):
    ok: bool
    value: T | None
    failure: FailureInfo | None
    attempts: int
    slept_seconds: list[float]


def run_with_retry(
    *,
    stage: str,
    policy: RetryPolicy,
    is_retryable: Callable[[FailureCategory], bool],
    classify_error: Callable[[BaseException], FailureCategory],
    op: Callable[[], T],
    sleep_fn: Callable[[float], None] = time.sleep,
) -> RetryOutcome[T]:
    slept: list[float] = []
    last_exc: BaseException | None = None

    for attempt in range(1, policy.max_attempts() + 1):
        try:
            value = op()
            return RetryOutcome(ok=True, value=value, failure=None, attempts=attempt, slept_seconds=slept)
        except BaseException as e:
            last_exc = e
            category = classify_error(e)
            if attempt >= policy.max_attempts() or not is_retryable(category):
                return RetryOutcome(
                    ok=False,
                    value=None,
                    failure=FailureInfo(
                        category=category,
                        stage=stage,
                        message=str(e),
                        attempts=attempt,
                        retry_limit=policy.max_attempts(),
                        exception_type=type(e).__name__,
                    ),
                    attempts=attempt,
                    slept_seconds=slept,
                )

            backoff = policy.backoff_for_attempt(attempt_index=attempt - 1)
            slept.append(backoff)
            sleep_fn(backoff)

    return RetryOutcome(
        ok=False,
        value=None,
        failure=FailureInfo(
            category=FailureCategory.unknown,
            stage=stage,
            message=str(last_exc) if last_exc is not None else "unknown error",
            attempts=policy.max_attempts(),
            retry_limit=policy.max_attempts(),
            exception_type=type(last_exc).__name__ if last_exc is not None else None,
        ),
        attempts=policy.max_attempts(),
        slept_seconds=slept,
    )
