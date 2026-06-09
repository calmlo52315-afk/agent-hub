from __future__ import annotations

"""
Skill 执行器 — 从 Orchestrator 剥离的 Skill 调用/升级/外部 CLI 路由逻辑。

SkillExecutor 封装了：
1. Skill 自动升级（内置 agent → external CLI）
2. Skill 调用 + 重试
3. 外部 CLI（Claude Code / Codex）子进程调度
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── 外部 CLI 执行日志 ──────────────────────────────────────────
# 每次外部 CLI 调用都写入结构化日志文件，便于调试 diff/review 问题。
# 日志路径：workspaces/external_cli_logs/{date}_{task_id}_{skill_name}.json
LOG_DIR: Path | None = None


def _log_dir(repo_root: Path) -> Path:
    global LOG_DIR
    if LOG_DIR is None:
        LOG_DIR = repo_root / "workspaces" / "external_cli_logs"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def _write_cli_log(skill_name: str, task_id: str, log_entry: dict[str, Any]) -> None:
    """将外部 CLI 执行详情写入磁盘日志文件。"""
    import json
    try:
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{now}_{task_id[:12]}_{skill_name}.json"
        path = _log_dir(Path.cwd()) / filename
        path.write_text(json.dumps(log_entry, indent=2, ensure_ascii=False, default=str))
        logger.info(f"[CLI-LOG] Written to {path}")
    except Exception as e:
        logger.warning(f"[CLI-LOG] Failed to write log: {e}")

from runtime.agents.base import Agent
from runtime.harness.forbidden_actions import ForbiddenActionError, enforce_changes_allowed
from runtime.harness.ownership import OwnershipManager
from runtime.harness.permissions import PermissionManager
from runtime.harness.retry import FailureCategory, FailureInfo, RetryPolicy, run_with_retry
from runtime.messages import Envelope
from runtime.orchestrator.agent_executor import (
    AgentExecutor,
    classify_failure,
    is_retryable_category,
)
from runtime.skills import SkillRegistry, SkillRuntime, SkillRegistryError
from runtime.skills.base import SkillInvocationPlan
from runtime.skills.external_cli import (
    ExternalCLIError,
    ExternalCLIExecutor,
    ExternalCLITimeoutError,
    ExternalCLIValidationError,
    external_cli_available,
)


class OrchestratorError(RuntimeError):
    pass


class SkillExecutor:
    """Skill 执行管线。

    组合 AgentExecutor（内置 agent）和 ExternalCLIExecutor（外置 CLI），
    通过 SkillRuntime 做调用计划，自动选择最优执行路径。
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        ruleset: Any,  # Ruleset
        skill_runtime: SkillRuntime,
        agent_executor: AgentExecutor,
        permission: PermissionManager,
        ownership: OwnershipManager,
    ):
        self.repo_root = repo_root
        self.ruleset = ruleset
        self.skill_runtime = skill_runtime
        self.agent_executor = agent_executor

    # ── Skill 升级 ────────────────────────────────────────────

    def resolve_preferred_skill_name(self, skill_name: str, plan: Any = None) -> str:
        """Map a skill name to its external-CLI variant when available.

        Set ``AGENTHUB_DISABLE_EXTERNAL_CLI=1`` to force built-in agents only.

        ⭐ Stage 9: 内置 Agent 优先。外部 CLI（Claude Code）仅在用户显式
        mentioned_agent 或 persona preferred_provider 时使用。
        """
        if os.environ.get("AGENTHUB_DISABLE_EXTERNAL_CLI") == "1":
            return skill_name

        # Review 阶段强制使用内置 Agent
        if "review" in skill_name.lower():
            return skill_name

        # ⭐ Stage 10: 检查是否用户显式指定了外部 CLI
        if plan is not None:
            mentioned = getattr(plan, "mentioned_agent", None)
            if mentioned in ("claude_code", "codex", "claude_review"):
                # 用户显式 @Claude Code 或 @Codex — 尊重用户选择
                return skill_name

        # ⭐ 默认不升级到外部 CLI — 内置 Agent 优先
        # 只有 entrypoint 已经是 external_cli 的才保持
        try:
            definition = self.skill_runtime.registry.resolve_active(skill_name)
        except Exception:
            return skill_name

        if definition.entrypoint == "external_cli":
            return skill_name

        # ⭐ 不再自动升级到 external_cli — 保持内置 agent
        return skill_name

    def _skill_name_for_stage(self, workflow_stage: str) -> str:
        """Return the active skill name for a given workflow stage."""
        try:
            return self.skill_runtime.registry.resolve_stage(workflow_stage).skill_name
        except SkillRegistryError:
            raise OrchestratorError(f"no active skill registered for stage: {workflow_stage}")

    # ── Skill 调用 ────────────────────────────────────────────

    def call_skill(
        self,
        *,
        skill_name: str,
        task_id: str,
        trace_id: str,
        payload: dict[str, Any],
        shared_state: dict[str, Any],
        messages: list[dict[str, Any]],
        plan: Any = None,
    ) -> Envelope:
        """Plan one skill invocation and dispatch to bound agent or external CLI.

        When an external-CLI variant is registered and available, it is used
        automatically in preference to the built-in agent.
        """
        import sys as _sys
        logger.info(f"[SkillExecutor] Calling skill: {skill_name}, Task: {task_id}")
        _sys.stderr.write(f"[SKILL-EXEC] call_skill: {skill_name}, task={task_id[:16]}..., payload_keys={list(payload.keys())}\n")
        _sys.stderr.flush()

        # 自动升级到外部 CLI
        resolved_name = self.resolve_preferred_skill_name(skill_name, plan=plan)
        if resolved_name != skill_name:
            logger.info(f"[SkillExecutor] Upgraded {skill_name} → {resolved_name}")
            diagnostics = shared_state.get("diagnostic_events")
            if isinstance(diagnostics, list):
                diagnostics.append({"kind": "skill_upgraded", "from": skill_name, "to": resolved_name, "reason": "external_cli available"})
            skill_name = resolved_name

        skill_plan = self.skill_runtime.plan_invocation(
            skill_name=skill_name,
            task_id=task_id,
            trace_id=trace_id,
            payload=payload,
            shared_state=shared_state,
        )

        diagnostics = shared_state.get("diagnostic_events")
        if isinstance(diagnostics, list):
            diagnostics.append({
                "kind": "skill_dispatch",
                "skill_name": skill_plan.definition.skill_name,
                "skill_version": skill_plan.definition.version,
                "agent_binding": skill_plan.definition.agent_binding,
                "workflow_stage": skill_plan.definition.workflow_stage,
                "entrypoint": skill_plan.definition.entrypoint,
                "timeout_seconds": skill_plan.timeout_seconds,
            })

        # ── 外部 CLI 分支 ────────────────────────────────────
        if skill_plan.definition.entrypoint == "external_cli":
            return self._call_external_skill(
                plan=skill_plan,
                shared_state=shared_state,
                messages=messages,
            )

        # ── 内置 Agent 分支 ──────────────────────────────────
        logger.info(f"[SkillExecutor] Using built-in agent {skill_plan.definition.agent_binding}")
        env = self.agent_executor.wrap_task_to_agent(
            task_id=task_id, trace_id=task_id,
            agent_id=skill_plan.definition.agent_binding,
            payload=skill_plan.payload,
        )
        messages.append(env.to_dict())
        result = self.agent_executor.call_agent(
            agent_id=skill_plan.definition.agent_binding,
            env=env,
            shared_state=shared_state,
            timeout_seconds=float(skill_plan.timeout_seconds),
        )
        messages.append(result.to_dict())
        return result

    def call_skill_with_retry(
        self,
        *,
        stage: str,
        skill_name: str,
        task_id: str,
        trace_id: str,
        payload: dict[str, Any],
        shared_state: dict[str, Any],
        messages: list[dict[str, Any]],
        plan: Any = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> tuple[Envelope | None, FailureInfo | None, int]:
        """Execute one skill dispatch under the shared retry policy."""
        # 从 ruleset 构建重试策略
        rules = (self.ruleset.execution.get("rules") or {}).get("retry") or {}
        max_attempts = rules.get("max_attempts", 1)
        if not isinstance(max_attempts, int):
            max_attempts = 1
        backoff_seconds = rules.get("backoff_seconds")
        if not isinstance(backoff_seconds, list):
            backoff_seconds = []
        parsed_backoff: list[float] = []
        for v in backoff_seconds:
            try:
                parsed_backoff.append(float(v))
            except Exception:
                pass
        policy = RetryPolicy(retry_limit=max_attempts, backoff_seconds=parsed_backoff, min_backoff_seconds=1.0)

        def op() -> Envelope:
            return self.call_skill(
                skill_name=skill_name,
                task_id=task_id,
                trace_id=trace_id,
                payload=payload,
                shared_state=shared_state,
                messages=messages,
                plan=plan,
            )

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

    # ── 外部 CLI 私有方法 ─────────────────────────────────────

    def _call_external_skill(
        self,
        *,
        plan: SkillInvocationPlan,
        shared_state: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> Envelope:
        """Execute a skill via external CLI (Claude Code / Codex subprocess).

        Falls back to the bound agent if the CLI command is not available.
        """
        import sys as _sys
        diagnostics = shared_state.get("diagnostic_events")
        command = getattr(plan.definition, "command", "")

        _sys.stderr.write(f"[SKILL-EXEC] _call_external_skill: skill={plan.definition.skill_name}, command={command}, available={command and external_cli_available(command)}\n")
        _sys.stderr.flush()

        if command and external_cli_available(command):
            executor = ExternalCLIExecutor(repo_root=self.repo_root)
            try:
                t0 = time.perf_counter()
                cli_result = executor.execute(plan)
                latency_ms = int((time.perf_counter() - t0) * 1000)

                # ── 写入结构化日志文件 ─────────────────────
                _write_cli_log(
                    skill_name=plan.definition.skill_name,
                    task_id=plan.task_id,
                    log_entry={
                        "task_id": plan.task_id,
                        "trace_id": plan.trace_id,
                        "skill_name": plan.definition.skill_name,
                        "agent_binding": plan.definition.agent_binding,
                        "command": command,
                        "latency_ms": latency_ms,
                        "exit_code": cli_result.exit_code,
                        "stdout": cli_result.stdout[-10000:] if cli_result.stdout else "",
                        "stderr": cli_result.stderr[-5000:] if cli_result.stderr else "",
                        "parsed_payload_summary": {
                            "plan": cli_result.parsed_payload.get("plan") if cli_result.parsed_payload else None,
                            "changes_count": len(cli_result.parsed_payload.get("changes") or []) if cli_result.parsed_payload else 0,
                            "changes": cli_result.parsed_payload.get("changes") if cli_result.parsed_payload else None,
                            "pass": cli_result.parsed_payload.get("pass") if cli_result.parsed_payload else None,
                            "issues_count": len(cli_result.parsed_payload.get("issues") or []) if cli_result.parsed_payload else 0,
                        } if cli_result.parsed_payload else None,
                        "error": {
                            "error_code": cli_result.error.error_code,
                            "message": str(cli_result.error),
                            "details": cli_result.error.details,
                        } if cli_result.error else None,
                    },
                )
                # ─────────────────────────────────────────────

                if cli_result.error is not None:
                    raise cli_result.error

                if cli_result.parsed_payload is None:
                    raise ExternalCLIValidationError(
                        f"CLI returned no parsed payload: {plan.definition.skill_name}",
                        details={"stdout_tail": cli_result.stdout[-300:]},
                    )

                agent_id = plan.definition.agent_binding
                result_env = self.agent_executor.wrap_result_to_orchestrator(
                    task_id=plan.task_id,
                    trace_id=plan.trace_id,
                    agent_id=agent_id,
                    in_reply_to=plan.trace_id,
                    payload=cli_result.parsed_payload,
                )
                messages.append(result_env.to_dict())

                if isinstance(diagnostics, list):
                    diagnostics.append({
                        "kind": "external_cli_success",
                        "skill_name": plan.definition.skill_name,
                        "command": command,
                        "latency_ms": cli_result.latency_ms,
                        "exit_code": cli_result.exit_code,
                    })

                # coding 输出的 forbidden-action 检查
                if agent_id == "coding":
                    changes = cli_result.parsed_payload.get("changes") or []
                    if isinstance(changes, list) and changes:
                        try:
                            enforce_changes_allowed(
                                repo_root=self.repo_root,
                                permission=None,  # 由 external_cli 内部处理
                                ownership=None,
                                role=agent_id,
                                changes=changes,
                            )
                        except ForbiddenActionError as e:
                            if isinstance(diagnostics, list):
                                diagnostics.append({
                                    "kind": "forbidden_action",
                                    "agent_id": agent_id,
                                    "message": str(e),
                                    "violations": [v.__dict__ for v in e.violations],
                                })
                            raise

                return result_env

            except ExternalCLIError:
                raise

        # CLI 不可用 → 回退到内置 agent
        logger.warning(f"[SkillExecutor] External CLI not available for {plan.definition.skill_name}, falling back to agent")
        env = self.agent_executor.wrap_task_to_agent(
            task_id=plan.task_id, trace_id=plan.trace_id,
            agent_id=plan.definition.agent_binding,
            payload=plan.payload,
        )
        messages.append(env.to_dict())
        result = self.agent_executor.call_agent(
            agent_id=plan.definition.agent_binding,
            env=env,
            shared_state=shared_state,
            timeout_seconds=float(plan.timeout_seconds),
        )
        messages.append(result.to_dict())
        return result
