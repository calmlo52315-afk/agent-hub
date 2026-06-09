from __future__ import annotations

"""
Agent 执行器 — 从 Orchestrator 剥离的 Agent 调用/重试/失败分类逻辑。

AgentExecutor 封装了：
1. 消息包装（task → agent / agent → orchestrator）
2. Agent 同步调用 + 超时控制 + 权限强控
3. 重试策略 + 失败分类
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from runtime.agents.base import Agent, AgentContext
from runtime.config.rules_loader import Ruleset
from runtime.harness.forbidden_actions import ForbiddenActionError, enforce_changes_allowed
from runtime.harness.metrics import MetricsHub
from runtime.harness.ownership import OwnershipManager
from runtime.harness.permissions import PermissionDenied, PermissionManager
from runtime.harness.replay import SQLiteReplayStore
from runtime.harness.retry import FailureCategory, FailureInfo, RetryPolicy, run_with_retry
from runtime.harness.validator import RuntimeValidationError, RuntimeValidator
from runtime.messages import Envelope, make_envelope
from runtime.skills.external_cli import (
    ExternalCLIError,
    ExternalCLIModelError,
    ExternalCLIProcessError,
    ExternalCLITimeoutError,
    ExternalCLIValidationError,
)


# ── 内部错误 (不暴露给外部，由 orchestrator 包装) ─────────────

class _AgentExecutorError(RuntimeError):
    """Internal error raised by AgentExecutor, caught and wrapped by Orchestrator."""

    def __init__(self, message: str):
        super().__init__(message)


class _AgentTimeoutError(TimeoutError):
    """Internal agent timeout."""
    pass


# ── 重试策略 & 失败分类 ──────────────────────────────────────

def build_retry_policy(ruleset: Ruleset) -> RetryPolicy:
    """从 ruleset 构建重试策略。"""
    rules = (ruleset.execution.get("rules") or {}).get("retry") or {}
    max_attempts = rules.get("max_attempts")
    backoff_seconds = rules.get("backoff_seconds")
    if not isinstance(max_attempts, int):
        max_attempts = 1
    if not isinstance(backoff_seconds, list):
        backoff_seconds = []
    parsed_backoff: list[float] = []
    for v in backoff_seconds:
        try:
            parsed_backoff.append(float(v))
        except Exception:
            pass
    return RetryPolicy(retry_limit=max_attempts, backoff_seconds=parsed_backoff, min_backoff_seconds=1.0)


def timeout_seconds_for_agent(ruleset: Ruleset, agent_id: str) -> float | None:
    """从 ruleset 读取 agent 超时配置。"""
    timeouts = (ruleset.execution.get("rules") or {}).get("timeouts") or {}
    key = f"{agent_id}_seconds"
    v = timeouts.get(key)
    if isinstance(v, int) and v > 0:
        return float(v)
    return None


def classify_failure(exc: BaseException) -> FailureCategory:
    """遍历异常链，归类为 FailureCategory。"""
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, RuntimeValidationError):
            return FailureCategory.schema_invalid
        if isinstance(cur, (PermissionDenied, PermissionError)):
            return FailureCategory.permission_denied
        if isinstance(cur, (_AgentTimeoutError, TimeoutError, FuturesTimeoutError, ExternalCLITimeoutError)):
            return FailureCategory.timeout
        if isinstance(cur, ExternalCLIModelError):
            return FailureCategory.schema_invalid  # ⭐ API 余额/配额问题 → 不重试
        if isinstance(cur, ExternalCLIValidationError):
            return FailureCategory.schema_invalid
        if isinstance(cur, ExternalCLIProcessError):
            return FailureCategory.unknown
        if isinstance(cur, ExternalCLIError):
            return FailureCategory.unknown
        cur = cur.__cause__
    return FailureCategory.unknown


def is_retryable_category(category: FailureCategory) -> bool:
    return category in (FailureCategory.timeout, FailureCategory.unknown)


# ── Agent 执行器 ─────────────────────────────────────────────

class AgentExecutor:
    """Agent 调用 + 重试的封装。

    所有 Orchestrator 依赖通过构造函数注入，不再持有 Orchestrator 引用。
    """

    def __init__(
        self,
        *,
        agents: dict[str, Agent],
        repo_root: Path,
        ruleset: Ruleset,
        permission: PermissionManager,
        ownership: OwnershipManager,
        replay: SQLiteReplayStore | None = None,
        metrics: MetricsHub | None = None,
        envelope_version: str = "1.0",
        max_payload_bytes: int = 256_000,
        validator: RuntimeValidator | None = None,
        on_validation_error: Callable[[str, str, RuntimeValidationError, dict[str, Any]], None] | None = None,
    ):
        self.agents = agents
        self.repo_root = repo_root
        self.ruleset = ruleset
        self.permission = permission
        self.ownership = ownership
        self.replay = replay
        self.metrics = metrics
        self._envelope_version = envelope_version
        self._max_payload_bytes = max_payload_bytes
        self._validator = validator if validator is not None else RuntimeValidator(expected_envelope_schema_version=envelope_version)
        self._on_validation_error = on_validation_error

    # ── 消息包装 ──────────────────────────────────────────────

    def wrap_task_to_agent(self, *, task_id: str, trace_id: str, agent_id: str, payload: dict[str, Any]) -> Envelope:
        env = make_envelope(
            schema_version=self._envelope_version,
            task_id=task_id,
            trace_id=trace_id,
            sender_type="orchestrator",
            sender_id="orchestrator",
            receiver_type="agent",
            receiver_id=agent_id,
            kind="task",
            status="running",
            payload=payload,
        )
        if env.payload_bytes() > self._max_payload_bytes:
            raise _AgentExecutorError("payload too large")
        return env

    def wrap_result_to_orchestrator(
        self, *, task_id: str, trace_id: str, agent_id: str, in_reply_to: str, payload: dict[str, Any]
    ) -> Envelope:
        env = make_envelope(
            schema_version=self._envelope_version,
            task_id=task_id,
            trace_id=trace_id,
            sender_type="agent",
            sender_id=agent_id,
            receiver_type="orchestrator",
            receiver_id="orchestrator",
            kind="result",
            status="success",
            payload=payload,
            in_reply_to=in_reply_to,
        )
        if env.payload_bytes() > self._max_payload_bytes:
            raise _AgentExecutorError("payload too large")
        return env

    # ── Agent 调用 ────────────────────────────────────────────

    def call_agent(
        self,
        *,
        agent_id: str,
        env: Envelope,
        shared_state: dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> Envelope:
        """Validate, invoke and normalize one concrete agent execution."""
        logger.info(f"[AgentExecutor] Calling agent: {agent_id}, Task ID: {env.task_id}")

        agent = self.agents.get(agent_id)
        if agent is None:
            raise _AgentExecutorError(f"unknown agent: {agent_id}")

        t0 = time.perf_counter()
        try:
            self._validator.validate_envelope(envelope=env.to_dict(), direction="outbound")
        except RuntimeValidationError as e:
            if self._on_validation_error is not None:
                self._on_validation_error(env.task_id, env.trace_id, e, env.to_dict())
            raise _AgentExecutorError(f"invalid outbound envelope: {e.context}") from e

        if self.replay is not None:
            try:
                self.replay.append_message(envelope=env.to_dict())
            except Exception:
                pass

        ctx = AgentContext(task_id=env.task_id, trace_id=env.trace_id, shared_state=shared_state)
        try:
            if timeout_seconds is None:
                payload = agent.handle(payload=env.payload, ctx=ctx)
            else:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(agent.handle, payload=env.payload, ctx=ctx)
                    payload = fut.result(timeout=float(timeout_seconds))
        except FuturesTimeoutError as e:
            raise _AgentTimeoutError(f"agent timeout: {agent_id} ({timeout_seconds}s)") from e

        if not isinstance(payload, dict):
            raise _AgentExecutorError(f"agent returned non-object payload: {agent_id}")

        try:
            self._validator.validate_agent_output(agent_id=agent_id, payload=payload)
        except RuntimeValidationError as e:
            if self._on_validation_error is not None:
                self._on_validation_error(env.task_id, env.trace_id, e, payload)
            raise _AgentExecutorError(f"invalid agent output: {e.context}") from e

        # 编码 agent 的 forbidden-action 检查
        if agent_id == "coding":
            changes = payload.get("changes") or []
            if isinstance(changes, list):
                try:
                    enforce_changes_allowed(
                        repo_root=self.repo_root,
                        permission=self.permission,
                        ownership=self.ownership,
                        role=str(getattr(agent, "role", agent_id)),
                        changes=changes,
                    )
                except ForbiddenActionError as e:
                    diagnostics = shared_state.get("diagnostic_events")
                    if isinstance(diagnostics, list):
                        diagnostics.append({
                            "kind": "forbidden_action",
                            "agent_id": agent_id,
                            "message": str(e),
                            "violations": [v.__dict__ for v in e.violations],
                        })
                    raise

        result_env = self.wrap_result_to_orchestrator(
            task_id=env.task_id,
            trace_id=env.trace_id,
            agent_id=agent_id,
            in_reply_to=env.message_id,
            payload=payload,
        )

        self._validator.validate_envelope(envelope=result_env.to_dict(), direction="inbound")

        if self.replay is not None:
            try:
                self.replay.append_message(envelope=result_env.to_dict())
            except Exception:
                pass

        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(f"[AgentExecutor] Agent {agent_id} completed in {dt_ms}ms")

        if self.metrics is not None:
            try:
                self.metrics.emit(task_id=env.task_id, agent=agent_id, metric="avg_response_time", value=dt_ms, unit="ms")
                self.metrics.emit(task_id=env.task_id, agent=agent_id, metric="token_usage", value=0, unit="token")
            except Exception:
                pass

        diagnostics = shared_state.get("diagnostic_events")
        if isinstance(diagnostics, list):
            diagnostics.append({"kind": "agent_finished", "agent_id": agent_id, "latency_ms": dt_ms})

        return result_env

    # ── Agent + 重试 ─────────────────────────────────────────

    def call_agent_with_retry(
        self,
        *,
        stage: str,
        task_id: str,
        trace_id: str,
        agent_id: str,
        payload: dict[str, Any],
        shared_state: dict[str, Any],
        messages: list[dict[str, Any]],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> tuple[Envelope | None, FailureInfo | None, int]:
        """Execute one agent call with retry classification and backoff policy."""
        timeout_sec = timeout_seconds_for_agent(self.ruleset, agent_id)
        policy = build_retry_policy(self.ruleset)

        def op() -> Envelope:
            env = self.wrap_task_to_agent(task_id=task_id, trace_id=trace_id, agent_id=agent_id, payload=payload)
            messages.append(env.to_dict())
            result = self.call_agent(agent_id=agent_id, env=env, shared_state=shared_state, timeout_seconds=timeout_sec)
            messages.append(result.to_dict())
            return result

        outcome = run_with_retry(
            stage=stage,
            policy=policy,
            is_retryable=is_retryable_category,
            classify_error=classify_failure,
            op=op,
            sleep_fn=sleep_fn,
        )
        if outcome.ok:
            return outcome.value, None, max(0, outcome.attempts - 1)
        return None, outcome.failure, max(0, outcome.attempts - 1)
