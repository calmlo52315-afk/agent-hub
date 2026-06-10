from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from runtime.agents.artifact import ArtifactAgent
from runtime.agents.base import Agent, AgentContext
from runtime.agents.coding import CodingAgent
from runtime.agents.documentation import DocAgent
from runtime.agents.review import ReviewAgent
from runtime.agents.testing import TestAgent
from runtime.config.rules_loader import Ruleset, load_ruleset
from runtime.config.spec_loader import Spec, load_spec
from runtime.harness.ownership import OwnershipManager
from runtime.harness.permissions import PermissionDenied, PermissionManager
from runtime.harness.retry import FailureCategory, FailureInfo, RetryPolicy, run_with_retry
from runtime.harness.replay import SQLiteReplayStore, PostgresReplayStore
from runtime.harness.state_machine import IllegalStateTransitionError, WorkflowStateMachine
from runtime.harness.metrics import JSONLinesMetricsSink, MetricsHub, PostgresMetricsSink
from runtime.harness.forbidden_actions import ForbiddenActionError, enforce_changes_allowed
from runtime.harness.validator import RuntimeValidationError, RuntimeValidator
from runtime.harness.workspace import AppliedChange, FileChange, Workspace
from runtime.messages import Envelope, make_envelope, new_trace_id
from runtime.orchestrator.task_graph import Subtask, TaskPlan, TaskPlanError, TaskPlanner
from runtime.orchestrator.normalizers import OutputNormalizer, as_json, diff_excerpt_create, diff_excerpt_update
from runtime.orchestrator.events import EventEmitter
from runtime.orchestrator.agent_executor import (
    AgentExecutor,
    build_retry_policy,
    classify_failure,
    is_retryable_category,
    timeout_seconds_for_agent,
)
from runtime.orchestrator.skill_executor import SkillExecutor
from runtime.workspace.diff_pipeline import DiffPipeline
from runtime.planner import (
    PlanArtifact,
    PlanRisk,
    PlanTarget,
    LinearPlan,
    LinearPlanner,
)
from runtime.skills import SkillRegistry, SkillRuntime
from runtime.skills.base import SkillInvocationPlan
from runtime.skills.external_cli import (
    ExternalCLIError,
    ExternalCLIExecutor,
    ExternalCLIModelError,
    ExternalCLIProcessError,
    ExternalCLITimeoutError,
    ExternalCLIValidationError,
    external_cli_available,
)


class OrchestratorError(RuntimeError):
    pass


class AgentTimeoutError(TimeoutError):
    pass


def _read_workspace_type(repo_root: Path, session_id: str) -> str:
    """⭐ 从 workspace_meta.json 读取 workspace_type，避免所有工作区默认为 scratch。"""
    import json as _json
    meta_path = repo_root / "workspace" / session_id / "workspace_meta.json"
    if meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            return meta.get("workspace_type", "scratch")
        except Exception:
            pass
    return "scratch"


def _summarize_changes(changes: list[dict[str, Any]]) -> str:
    """⭐ 将 applied_changes 列表浓缩为简短摘要字符串，供 review prompt 使用。"""
    if not changes:
        return "no file changes"
    summaries = []
    for ch in changes[:10]:  # 最多 10 个文件
        if isinstance(ch, dict):
            action = ch.get("action", "update")
            path = ch.get("path", "?")
            summaries.append(f"{action}: {path}")
    if len(changes) > 10:
        summaries.append(f"... and {len(changes) - 10} more files")
    return ", ".join(summaries)

@dataclass
class Orchestrator:
    """Coordinate the full runtime workflow across rules, agents and storage.

    The Orchestrator is the only component allowed to route messages, advance
    workflow state and bridge skills with concrete agent execution.
    """

    repo_root: Path
    ruleset: Ruleset
    spec: Spec
    permission: PermissionManager
    ownership: OwnershipManager
    workspace: Workspace
    agents: dict[str, Agent]
    skill_runtime: SkillRuntime
    task_planner: TaskPlanner
    linear_planner: LinearPlanner
    replay: SQLiteReplayStore | None = None
    metrics: MetricsHub | None = None
    # Stage 8: 提取的子模块
    normalizer: OutputNormalizer | None = None
    events: EventEmitter | None = None
    agent_executor: AgentExecutor | None = None
    skill_executor: SkillExecutor | None = None
    # Stage 8: Session 级 workspace
    session_id: str | None = None

    @classmethod
    def load(cls, repo_root: Path | None = None, session_id: str | None = None) -> "Orchestrator":
        """Build a fully wired runtime instance from repository-local config.

        Args:
            repo_root: Project root directory.
            session_id: Session identifier for session-scoped workspace.
                        When provided, workspace is created/loaded under
                        ``workspace/{session_id}/``.
        """

        root = repo_root or Path(__file__).resolve().parents[2]
        sid = session_id or "default"

        # 自动加载 .env 确保 LLM Planner 可用
        try:
            from dotenv import load_dotenv
            load_dotenv(root / ".env")
        except ImportError:
            pass
        ruleset = load_ruleset(root)
        spec = load_spec(root)
        permission = PermissionManager(repo_root=root, policy=ruleset.permission)
        ownership = OwnershipManager.from_rules(repo_root=root, ownership_policy=ruleset.ownership)
        workspace = Workspace.load(
            repo_root=root,
            session_id=sid,
            permission=permission,
            ownership=ownership,
            ruleset_ownership=ruleset.ownership,
            # ⭐ Stage 9: 从 workspace_meta.json 读取 workspace_type
            # 这样项目工作区不会被默认成 scratch
            workspace_type=_read_workspace_type(root, sid),
        )

        agents: dict[str, Agent] = {
            "coding": CodingAgent(),
            "review": ReviewAgent(),
            "artifact": ArtifactAgent(workspace=workspace),
            "testing": TestAgent(),
            "documentation": DocAgent(),
        }
        # Stage 3: Skill Runtime 负责把“可复用能力”映射到具体 Agent 实现。
        skill_registry = SkillRegistry.from_spec(spec)
        skill_runtime = SkillRuntime(
            execution_policy=ruleset.execution,
            permission_policy=ruleset.permission,
            registry=skill_registry,
        )
        task_planner = TaskPlanner()
        linear_planner = LinearPlanner(workspace=workspace)

        replay_backend = os.getenv("REPLAY_STORE_BACKEND", "postgres")
        if replay_backend == "postgres":
            replay_dsn = os.getenv("REPLAY_POSTGRES_DSN",
                "postgres://postgres:123456@localhost:5432/AgentHub?sslmode=disable")
            replay = PostgresReplayStore(dsn=replay_dsn, retain_days=30, max_records=5000)
        else:
            replay = SQLiteReplayStore(
                db_path=(root / "artifacts" / "replay" / "replay.sqlite3").resolve(),
                retain_days=30,
                max_records=5000,
            )

        metrics_backend = os.getenv("METRICS_STORE_BACKEND", "postgres")
        if metrics_backend == "postgres":
            metrics = MetricsHub(
                sinks=[PostgresMetricsSink()],
                default_tags={"stage": "stage-8-improvement", "schema_version": "v2"},
            )
        else:
            metrics = MetricsHub(
                sinks=[JSONLinesMetricsSink(out_path=(root / "artifacts" / "metrics" / "metrics.jsonl").resolve())],
                default_tags={"stage": "stage-4-orchestrator-upgrade", "schema_version": "v1"},
            )

        # Stage 8: 构建提取的子模块
        normalizer = OutputNormalizer(workspace=workspace)
        events = EventEmitter(replay=replay)

        def _on_validation_error(task_id: str, trace_id: str, err, sample: dict[str, Any]) -> None:
            """Persist validation error to disk (mirrors _persist_validation_error)."""
            from datetime import datetime, timezone
            err_root = (root / "artifacts" / "validation_errors" / task_id).resolve()
            err_root.mkdir(parents=True, exist_ok=True)
            out_path = err_root / f"{uuid.uuid4().hex}.json"
            try:
                out_path.write_text(
                    json.dumps({
                        "schema_version": "1.0",
                        "kind": "validation-error",
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "context": getattr(err, "context", None),
                        "errors": getattr(err, "errors", []),
                        "sample": json.dumps(sample, default=str),
                    }, ensure_ascii=False, indent=2)
                )
            except Exception:
                pass

        agent_executor = AgentExecutor(
            agents=agents,
            repo_root=root,
            ruleset=ruleset,
            permission=permission,
            ownership=ownership,
            replay=replay,
            metrics=metrics,
            on_validation_error=_on_validation_error,
        )
        skill_executor = SkillExecutor(
            repo_root=root,
            ruleset=ruleset,
            skill_runtime=skill_runtime,
            agent_executor=agent_executor,
            permission=permission,
            ownership=ownership,
        )

        return cls(
            repo_root=root,
            ruleset=ruleset,
            spec=spec,
            permission=permission,
            ownership=ownership,
            workspace=workspace,
            agents=agents,
            skill_runtime=skill_runtime,
            task_planner=task_planner,
            linear_planner=linear_planner,
            replay=replay,
            metrics=metrics,
            normalizer=normalizer,
            events=events,
            agent_executor=agent_executor,
            skill_executor=skill_executor,
            session_id=sid,
        )

    def _envelope_version(self) -> str:
        return str((self.spec.message_envelope or {}).get("schema_version") or "1.0")

    def _max_payload_bytes(self) -> int:
        rules = (self.ruleset.communication.get("rules") or {}).get("message_constraints") or {}
        value = rules.get("max_payload_bytes")
        return int(value) if isinstance(value, int) else 262144

    def _validator(self) -> RuntimeValidator:
        return RuntimeValidator(expected_envelope_schema_version=self._envelope_version())

    def _persist_validation_error(
        self,
        *,
        task_id: str,
        trace_id: str,
        err: RuntimeValidationError,
        sample: dict[str, Any],
    ) -> Path:
        root = (self.repo_root / "artifacts" / "validation_errors" / task_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        out_path = root / f"{uuid.uuid4().hex}.json"
        out_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "kind": "validation-error",
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "context": err.context,
                    "errors": err.errors,
                    "sample": sample,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return out_path

    def _wrap_task_to_agent(self, *, task_id: str, trace_id: str, agent_id: str, payload: dict[str, Any]) -> Envelope:
        return self.agent_executor.wrap_task_to_agent(task_id=task_id, trace_id=trace_id, agent_id=agent_id, payload=payload)

    def _wrap_result_to_orchestrator(
        self, *, task_id: str, trace_id: str, agent_id: str, in_reply_to: str, payload: dict[str, Any]
    ) -> Envelope:
        return self.agent_executor.wrap_result_to_orchestrator(task_id=task_id, trace_id=trace_id, agent_id=agent_id, in_reply_to=in_reply_to, payload=payload)

    def _call_agent(
        self, *, agent_id: str, env: Envelope, shared_state: dict[str, Any], timeout_seconds: float | None = None,
    ) -> Envelope:
        try:
            return self.agent_executor.call_agent(
                agent_id=agent_id, env=env, shared_state=shared_state, timeout_seconds=timeout_seconds,
            )
        except TimeoutError as e:
            raise AgentTimeoutError(str(e)) from e
        except RuntimeError as e:
            raise OrchestratorError(str(e)) from e

    def _skill_name_for_stage(self, workflow_stage: str) -> str:
        return self.skill_executor._skill_name_for_stage(workflow_stage)

    def _resolve_preferred_skill_name(self, skill_name: str, plan: Any = None) -> str:
        return self.skill_executor.resolve_preferred_skill_name(skill_name, plan=plan)

    def _call_skill(
        self, *, skill_name: str, task_id: str, trace_id: str, payload: dict[str, Any],
        shared_state: dict[str, Any], messages: list[dict[str, Any]], plan: Any = None,
    ) -> Envelope:
        return self.skill_executor.call_skill(
            skill_name=skill_name, task_id=task_id, trace_id=trace_id,
            payload=payload, shared_state=shared_state, messages=messages, plan=plan,
        )

    def _call_external_skill(
        self, *, plan: "SkillInvocationPlan", shared_state: dict[str, Any], messages: list[dict[str, Any]],
    ) -> Envelope:
        return self.skill_executor._call_external_skill(plan=plan, shared_state=shared_state, messages=messages)

    def _retry_policy(self) -> RetryPolicy:
        return build_retry_policy(self.ruleset)

    def _timeout_seconds_for_agent(self, agent_id: str) -> float | None:
        return timeout_seconds_for_agent(self.ruleset, agent_id)

    def _classify_failure(self, exc: BaseException) -> FailureCategory:
        return classify_failure(exc)

    def _is_retryable_category(self, category: FailureCategory) -> bool:
        return is_retryable_category(category)

    def _call_agent_with_retry(
        self, *, stage: str, task_id: str, trace_id: str, agent_id: str, payload: dict[str, Any],
        shared_state: dict[str, Any], messages: list[dict[str, Any]],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> tuple[Envelope | None, FailureInfo | None, int]:
        return self.agent_executor.call_agent_with_retry(
            stage=stage, task_id=task_id, trace_id=trace_id, agent_id=agent_id,
            payload=payload, shared_state=shared_state, messages=messages, sleep_fn=sleep_fn,
        )

    def _call_skill_with_retry(
        self, *, stage: str, skill_name: str, task_id: str, trace_id: str,
        payload: dict[str, Any], shared_state: dict[str, Any], messages: list[dict[str, Any]],
        plan: Any = None, sleep_fn: Callable[[float], None] = time.sleep,
    ) -> tuple[Envelope | None, FailureInfo | None, int]:
        return self.skill_executor.call_skill_with_retry(
            stage=stage, skill_name=skill_name, task_id=task_id, trace_id=trace_id,
            payload=payload, shared_state=shared_state, messages=messages, plan=plan, sleep_fn=sleep_fn,
        )

    def _replay_event(self, *, task_id: str, trace_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self.replay is None:
            return
        try:
            self.replay.append_event(task_id=task_id, trace_id=trace_id, event_type=event_type, payload=payload)
        except Exception:
            pass

    def _replay_artifact(self, *, task_id: str, trace_id: str, artifact_dir: str, payload: dict[str, Any]) -> None:
        self.events.replay_artifact(task_id=task_id, trace_id=trace_id, artifact_dir=artifact_dir, payload=payload)

    def _emit_event(
        self, *, task_id: str, trace_id: str, diagnostics: list[dict[str, Any]],
        event_type: str, payload: dict[str, Any] | None = None,
    ) -> None:
        shared = getattr(self, "_shared_diag", None)
        self.events.emit_diagnostic(
            task_id=task_id, trace_id=trace_id, diagnostics=diagnostics,
            event_type=event_type, payload=payload, shared_diag=shared,
        )

    def _artifact_root(self) -> str:
        return str(
            (((self.ruleset.permission.get("rules") or {}).get("artifact") or {}).get("artifact_root") or "artifacts")
        )

    def _normalize_linear_coding_output(self, *, result_env: Envelope) -> dict[str, Any]:
        return self.normalizer.normalize_linear_coding(result_env=result_env)

    def _record_task_metrics(
        self, *, task_id: str, task_success: bool, retry_count_total: int, task_t0: float
    ) -> None:
        dt_ms = int((time.perf_counter() - task_t0) * 1000)
        if self.metrics is not None:
            try:
                self.metrics.emit(
                    task_id=task_id,
                    agent="orchestrator",
                    metric="avg_response_time",
                    value=dt_ms,
                    unit="ms",
                )
                self.metrics.emit(
                    task_id=task_id,
                    agent="orchestrator",
                    metric="task_success_rate",
                    value=(1 if task_success else 0),
                    unit="ratio",
                )
                self.metrics.emit(
                    task_id=task_id,
                    agent="orchestrator",
                    metric="retry_count",
                    value=retry_count_total,
                    unit="count",
                )
                self.metrics.emit(
                    task_id=task_id,
                    agent="orchestrator",
                    metric="token_usage",
                    value=0,
                    unit="token",
                )
            except Exception:
                pass

    def _failure_response(
        self,
        *,
        task_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
        failure: FailureInfo,
        task_plan: LinearPlan | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "task_id": task_id,
            "trace_id": trace_id,
            "messages": messages,
            "failure": failure.to_dict(),
            "diagnostics": diagnostics,
        }
        if task_plan is not None:
            payload["task_plan"] = task_plan.to_dict()
        return payload

    def _max_parallel_tasks(self) -> int:
        """Return the Stage 4 in-memory scheduler concurrency limit."""

        raw = ((self.ruleset.execution.get("rules") or {}).get("scheduler") or {}).get("max_parallel_tasks")
        if isinstance(raw, int) and raw > 0:
            return raw
        return 2

    def _context_budget_bytes(self) -> int:
        """Return the maximum serialized context size allowed for one subtask."""

        raw = ((self.ruleset.execution.get("rules") or {}).get("scheduler") or {}).get("context_budget_bytes")
        if isinstance(raw, int) and raw > 0:
            return raw
        return 2048

    def _subtask_lock_mode(self, subtask: Subtask) -> str:
        """Return the scheduler lease mode used by one subtask."""

        if subtask.agent == "review":
            return "read"
        return "write"

    def _subtask_lease_seconds(self, subtask: Subtask) -> float:
        """Return the lease duration assigned to one subtask reservation."""

        timeout_seconds = subtask.timeout_seconds if subtask.timeout_seconds > 0 else 30
        return max(1.0, min(float(timeout_seconds), 300.0))

    def _requeue_blocked_subtasks(self, *, plan: TaskPlan, diagnostics: list[dict[str, Any]]) -> None:
        """Move resource-blocked subtasks back to pending so the scheduler can retry them."""

        for subtask in plan.subtasks:
            if subtask.status != "blocked":
                continue
            if plan.has_failed_dependency(subtask):
                continue
            if not plan.dependencies_satisfied(subtask):
                continue
            subtask.status = "pending"
            diagnostics.append(
                {
                    "kind": "subtask_requeued",
                    "subtask_id": subtask.subtask_id,
                    "workflow_stage": subtask.workflow_stage,
                    "reason": "blocked_resource_recheck",
                }
            )

    def _clear_task_scheduler_state(self, *, plan: TaskPlan) -> None:
        """Remove any remaining waiters and reservations associated with one task plan."""

        for subtask in plan.subtasks:
            self.ownership.release_subtask_locks(task_id=plan.task_id, subtask_id=subtask.subtask_id)
            self.ownership.remove_waiting_subtask(task_id=plan.task_id, subtask_id=subtask.subtask_id)

    def _build_demo_task_plan(self, *, task_id: str, trace_id: str, instruction: str) -> TaskPlan:
        """Build the Stage 4 demo task plan used by the DAG scheduler.

        The default plan contains one coding node, one review node and one
        artifact node. If the instruction explicitly asks for parallel work, an
        additional coding node is added to exercise fan-out/fan-in scheduling.
        """

        targets: list[dict[str, Any]] = []
        for rel_path in ("demo_workspace/hello.txt",):
            current_hash = self.workspace.file_hash(rel_path=rel_path)
            targets.append(
                {
                    "path": rel_path,
                    "action": ("update" if current_hash is not None else "create"),
                    "base_hash": current_hash,
                }
            )

        lowered = instruction.lower()
        if any(token in lowered for token in ("parallel", "fanout")) or "并行" in instruction or "多文件" in instruction:
            rel_path = "demo_workspace/hello_parallel.txt"
            current_hash = self.workspace.file_hash(rel_path=rel_path)
            targets.append(
                {
                    "path": rel_path,
                    "action": ("update" if current_hash is not None else "create"),
                    "base_hash": current_hash,
                }
            )

        artifact_root = (
            ((self.ruleset.permission.get("rules") or {}).get("artifact") or {}).get("artifact_root") or "artifacts"
        )
        return self.task_planner.build_demo_plan(
            task_id=task_id,
            trace_id=trace_id,
            instruction=instruction,
            targets=targets,
            artifact_root=str(artifact_root),
        )

    #精简，压缩上下文
    def _build_subtask_context(
        self, *, plan: TaskPlan, subtask: Subtask, diagnostics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Assemble the Stage 4 structured context passed into one subtask."""

        dependency_outputs: list[dict[str, Any]] = []
        for dep in plan.dependency_outputs(subtask):
            output = dep.get("output") if isinstance(dep, dict) else None
            dependency_outputs.append(
                {
                    "subtask_id": dep.get("subtask_id"),
                    "workflow_stage": dep.get("workflow_stage"),
                    "status": dep.get("status"),
                    "summary": self._summarize_dependency_output(output=output),
                }
            )

        recent_events = []
        #保留最近的十条
        for event in diagnostics[-10:]:
            if not isinstance(event, dict):
                continue
            recent_events.append(
                {
                    "type": str(event.get("kind") or event.get("event_type") or "event"),
                    "summary": str(event.get("message") or event.get("subtask_id") or event.get("stage") or ""),
                }
            )

        context = {
            "task_id": plan.task_id,
            "subtask_id": subtask.subtask_id,
            "system_rules": [
                "ADR-002: 核心角色固定为 coding/review/artifact",
                "ADR-007: 单个子任务目标文件原则上不超过 3 个",
                "ADR-011: Agent 间消息必须使用结构化 JSON",
            ],
            "task_brief": {
                "title": subtask.title,
                "agent": subtask.agent,
                "workflow_stage": subtask.workflow_stage,
                "target_files": list(subtask.target_files),
                "priority": subtask.priority,
                "timeout_seconds": subtask.timeout_seconds,
                "retry_limit": subtask.retry_limit,
            },
            "dependency_outputs": dependency_outputs,
            "workspace_locks": self.ownership.active_reservations(task_id=plan.task_id),
            "recent_events": recent_events,
            "budget": {"max_bytes": self._context_budget_bytes()},
        }
        return self._trim_context_to_budget(context)

    def _summarize_dependency_output(self, *, output: dict[str, Any] | None) -> dict[str, Any]:
        """Compress one dependency output into a bounded summary."""

        if not isinstance(output, dict):
            return {"has_output": False, "output_keys": []}

        output_keys = sorted(output.keys())
        summary: dict[str, Any] = {
            "has_output": True,
            "output_keys": output_keys[:6],
            "truncated": len(output_keys) > 6,
        }
        applied_changes = output.get("applied_changes")
        if isinstance(applied_changes, list):
            summary["applied_change_count"] = len(applied_changes)
        content_samples = output.get("content_samples")
        if isinstance(content_samples, dict):
            summary["content_sample_paths"] = sorted(str(path) for path in content_samples.keys())[:4]
        review_result = output.get("review_result")
        if isinstance(review_result, dict):
            summary["review_pass"] = bool(review_result.get("pass"))
            issues = review_result.get("issues")
            if isinstance(issues, list):
                summary["issue_count"] = len(issues)
        artifact_result = output.get("artifact_result")
        if isinstance(artifact_result, dict):
            summary["artifact_dir"] = str(artifact_result.get("artifact_dir") or "")
        return summary
    #绝对保证 payload 不超限、不超 token、不报错。
    def _trim_context_to_budget(self, context: dict[str, Any]) -> dict[str, Any]:
        """Trim low-priority context fields until the serialized payload fits budget."""

        budget = self._context_budget_bytes()
        trimmed = json.loads(json.dumps(context, ensure_ascii=False))
        was_trimmed = False

        def size_of(obj: dict[str, Any]) -> int:
            return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        while size_of(trimmed) > budget:
            recent_events = trimmed.get("recent_events")
            if isinstance(recent_events, list) and recent_events:
                recent_events.pop(0)
                was_trimmed = True
                continue

            dependency_outputs = trimmed.get("dependency_outputs")
            if isinstance(dependency_outputs, list) and dependency_outputs:
                last = dependency_outputs[-1]
                summary = last.get("summary") if isinstance(last, dict) else None
                if isinstance(summary, dict):
                    sample_paths = summary.get("content_sample_paths")
                    if isinstance(sample_paths, list) and len(sample_paths) > 2:
                        summary["content_sample_paths"] = sample_paths[:2]
                        summary["truncated"] = True
                        was_trimmed = True
                        continue
                    output_keys = summary.get("output_keys")
                    if isinstance(output_keys, list) and len(output_keys) > 3:
                        summary["output_keys"] = output_keys[:3]
                        summary["truncated"] = True
                        was_trimmed = True
                        continue
                if len(dependency_outputs) > 1:
                    dependency_outputs.pop()
                    was_trimmed = True
                    continue
                if isinstance(last, dict):
                    current_summary = last.get("summary") if isinstance(last.get("summary"), dict) else {}
                    minimal_summary = {"has_output": bool(current_summary.get("has_output"))}
                    if current_summary != minimal_summary:
                        last["summary"] = minimal_summary
                        was_trimmed = True
                        continue

            workspace_locks = trimmed.get("workspace_locks")
            if isinstance(workspace_locks, list) and workspace_locks:
                trimmed["workspace_locks"] = workspace_locks[:1] if len(workspace_locks) > 1 else []
                was_trimmed = True
                continue

            task_brief = trimmed.get("task_brief")
            if isinstance(task_brief, dict) and "target_files" in task_brief:
                target_files = task_brief.get("target_files")
                if isinstance(target_files, list):
                    task_brief["target_file_count"] = len(target_files)
                task_brief.pop("target_files", None)
                was_trimmed = True
                continue
            if isinstance(task_brief, dict) and "title" in task_brief:
                task_brief.pop("title", None)
                was_trimmed = True
                continue
            if isinstance(task_brief, dict):
                minimal_brief = {
                    "agent": task_brief.get("agent"),
                    "workflow_stage": task_brief.get("workflow_stage"),
                }
                if task_brief != minimal_brief:
                    trimmed["task_brief"] = minimal_brief
                    was_trimmed = True
                    continue

            system_rules = trimmed.get("system_rules")
            if isinstance(system_rules, list) and len(system_rules) > 1:
                trimmed["system_rules"] = system_rules[:1]
                was_trimmed = True
                continue
            if isinstance(system_rules, list) and system_rules:
                trimmed["system_rules"] = []
                was_trimmed = True
                continue

            dependency_outputs = trimmed.get("dependency_outputs")
            if isinstance(dependency_outputs, list) and dependency_outputs:
                trimmed["dependency_outputs"] = []
                was_trimmed = True
                continue
            break

        trimmed["budget"]["actual_bytes"] = size_of(trimmed)
        trimmed["budget"]["trimmed"] = was_trimmed
        return trimmed

    def _prepare_subtask_payload(
        self, *, plan: TaskPlan, subtask: Subtask, diagnostics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Build the runtime payload for one subtask from plan state and dependencies."""

        context = self._build_subtask_context(plan=plan, subtask=subtask, diagnostics=diagnostics)
        if subtask.workflow_stage == "coding":
            payload = dict(subtask.input_payload)
            payload["context"] = context
            return payload

        if subtask.workflow_stage == "review":
            applied_changes: list[dict[str, Any]] = []
            content_samples: dict[str, str] = {}
            for dep in plan.dependency_outputs(subtask):
                output = dep.get("output") if isinstance(dep, dict) else None
                if not isinstance(output, dict):
                    continue
                for change in output.get("applied_changes") or []:
                    if isinstance(change, dict):
                        applied_changes.append(change)
                for path, content in (output.get("content_samples") or {}).items():
                    if isinstance(path, str) and isinstance(content, str):
                        content_samples[path] = content
            return {
                "applied_changes": applied_changes,
                "content_samples": content_samples,
                "context": context,
            }

        if subtask.workflow_stage == "artifact":
            applied_changes: list[dict[str, Any]] = []
            snapshots: dict[str, str] = {}
            review_result: dict[str, Any] = {}
            for item in plan.subtasks:
                if item.workflow_stage == "coding" and isinstance(item.output, dict):
                    for change in item.output.get("applied_changes") or []:
                        if isinstance(change, dict):
                            applied_changes.append(change)
                    for path, content in (item.output.get("content_samples") or {}).items():
                        if isinstance(path, str) and isinstance(content, str):
                            snapshots[path] = content
                if item.workflow_stage == "review" and isinstance(item.output, dict):
                    review_result = item.output.get("review_result") or {}
            payload = dict(subtask.input_payload)
            payload.update(
                {
                    "applied_changes": applied_changes,
                    "review_result": review_result,
                    "snapshots": snapshots,
                    "context": context,
                }
            )
            return payload

        raise OrchestratorError(f"unsupported workflow_stage: {subtask.workflow_stage}")

    def _normalize_coding_output(self, *, subtask: Subtask, result_env: Envelope) -> dict[str, Any]:
        return self.normalizer.normalize_coding(subtask=subtask, result_env=result_env)

    def _normalize_review_output(self, *, subtask: Subtask, result_env: Envelope) -> dict[str, Any]:
        return self.normalizer.normalize_review(subtask=subtask, result_env=result_env)

    def _normalize_artifact_output(
        self, *, task_id: str, trace_id: str, subtask: Subtask, result_env: Envelope
    ) -> dict[str, Any]:
        def on_artifact(*, artifact_dir: str, payload: dict[str, Any]) -> None:
            self._replay_artifact(task_id=task_id, trace_id=trace_id, artifact_dir=artifact_dir, payload=payload)
        return self.normalizer.normalize_artifact(subtask=subtask, result_env=result_env, on_artifact=on_artifact)

    async def _execute_subtask_async(
        self, *, plan: TaskPlan, subtask: Subtask, diagnostics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute one subtask asynchronously via the existing skill runtime."""

        local_messages: list[dict[str, Any]] = []
        payload = self._prepare_subtask_payload(plan=plan, subtask=subtask, diagnostics=diagnostics)
        shared_state = {
            "workflow_state": subtask.workflow_stage,
            "diagnostic_events": diagnostics,
            "task_id": plan.task_id,
            "subtask_id": subtask.subtask_id,
        }
        result_env, failure, retries = await asyncio.to_thread(
            self._call_skill_with_retry,
            stage=subtask.workflow_stage,
            skill_name=subtask.skill_name,
            task_id=plan.task_id,
            trace_id=plan.trace_id,
            payload=payload,
            shared_state=shared_state,
            messages=local_messages,
        )
        if failure is not None:
            return {
                "subtask_id": subtask.subtask_id,
                "messages": local_messages,
                "retries": retries,
                "failure": failure,
                "output": None,
            }
        if result_env is None:
            failure = FailureInfo(
                category=FailureCategory.unknown,
                stage=subtask.workflow_stage,
                message=f"subtask returned no result: {subtask.subtask_id}",
                attempts=1,
                retry_limit=subtask.retry_limit,
            )
            return {
                "subtask_id": subtask.subtask_id,
                "messages": local_messages,
                "retries": retries,
                "failure": failure,
                "output": None,
            }

        try:
            if subtask.workflow_stage == "coding":
                normalized = await asyncio.to_thread(self._normalize_coding_output, subtask=subtask, result_env=result_env)
            elif subtask.workflow_stage == "review":
                normalized = self._normalize_review_output(subtask=subtask, result_env=result_env)
                if not bool((result_env.payload or {}).get("pass")):
                    failure = FailureInfo(
                        category=FailureCategory.review_failed,
                        stage=subtask.workflow_stage,
                        message=as_json(result_env.payload),
                        attempts=1,
                        retry_limit=subtask.retry_limit,
                    )
                    return {
                        "subtask_id": subtask.subtask_id,
                        "messages": local_messages,
                        "retries": retries,
                        "failure": failure,
                        "output": None,
                    }
            elif subtask.workflow_stage == "artifact":
                normalized = self._normalize_artifact_output(
                    task_id=plan.task_id,
                    trace_id=plan.trace_id,
                    subtask=subtask,
                    result_env=result_env,
                )
            else:
                raise OrchestratorError(f"unsupported workflow_stage: {subtask.workflow_stage}")
        except Exception as exc:
            failure = FailureInfo(
                category=self._classify_failure(exc),
                stage=subtask.workflow_stage,
                message=str(exc),
                attempts=1,
                retry_limit=subtask.retry_limit,
                exception_type=type(exc).__name__,
            )
            return {
                "subtask_id": subtask.subtask_id,
                "messages": local_messages,
                "retries": retries,
                "failure": failure,
                "output": None,
            }

        return {
            "subtask_id": subtask.subtask_id,
            "messages": local_messages,
            "retries": retries,
            "failure": None,
            "output": normalized,
        }

    def _transition_workflow(
        self,
        *,
        sm: WorkflowStateMachine,
        shared_state: dict[str, Any],
        diagnostics: list[dict[str, Any]],
        task_id: str,
        trace_id: str,
        event: str,
    ) -> None:
        """Apply one coarse workflow transition and replay the event."""

        from_state = sm.state
        sm.transition(event=event, diagnostics=diagnostics)
        shared_state["workflow_state"] = sm.state
        self._replay_event(
            task_id=task_id,
            trace_id=trace_id,
            event_type=event,
            payload={"kind": "transition", "from": from_state, "to": sm.state, "event": event},
        )
   #Dag 调度器的真身
    async def _run_task_plan_async(
        self,
        *,
        plan: TaskPlan,
        diagnostics: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        sm: WorkflowStateMachine,
        shared_state: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, FailureInfo | None, int]:
        """Execute a validated task plan with dependency-aware in-memory scheduling."""

        retry_count_total = 0
        running: dict[str, tuple[Subtask, asyncio.Task[dict[str, Any]]]] = {}

        while True:
            expired_reservations = self.ownership.purge_expired_reservations()
            for expired in expired_reservations:
                diagnostics.append(
                    {
                        "kind": "lock_expired",
                        "path": expired.get("path"),
                        "subtask_id": expired.get("subtask_id"),
                        "task_id": expired.get("task_id"),
                    }
                )
                self._replay_event(
                    task_id=plan.task_id,
                    trace_id=plan.trace_id,
                    event_type="lock.expired",
                    payload=dict(expired),
                )
            if expired_reservations:
                self._requeue_blocked_subtasks(plan=plan, diagnostics=diagnostics)

            running_target_files = {
                path
                for subtask, _ in running.values()
                for path in subtask.target_files
            }
            ready = plan.ready_subtasks(running_target_files=running_target_files)
            #启动能跑的任务
            while ready and len(running) < self._max_parallel_tasks():
                next_subtask = ready[0]
                if next_subtask.status != "ready":
                    ready = ready[1:]
                    continue
                #尝试给文件上锁
                reservation_conflicts = self.ownership.try_acquire_subtask_locks(
                    task_id=plan.task_id,
                    subtask_id=next_subtask.subtask_id,
                    role=next_subtask.agent,
                    paths=[self.workspace._abs(path) for path in next_subtask.target_files],
                    mode=self._subtask_lock_mode(next_subtask),
                    lease_seconds=self._subtask_lease_seconds(next_subtask),
                )

                # 锁被占用->blocked
                if reservation_conflicts:
                    self.ownership.enqueue_waiting_subtask(
                        task_id=plan.task_id,
                        subtask_id=next_subtask.subtask_id,
                        role=next_subtask.agent,
                        paths=[self.workspace._abs(path) for path in next_subtask.target_files],
                        mode=self._subtask_lock_mode(next_subtask),
                        priority_rank=next_subtask.priority_rank(),
                    )
                    next_subtask.status = "blocked"
                    diagnostics.append(
                        {
                            "kind": "subtask_blocked",
                            "subtask_id": next_subtask.subtask_id,
                            "workflow_stage": next_subtask.workflow_stage,
                            "reason": "lock_conflict",
                            "conflicts": reservation_conflicts,
                            "lease_seconds": self._subtask_lease_seconds(next_subtask),
                            "queued_waiters": self.ownership.active_waiters(task_id=plan.task_id),
                        }
                    )
                    self._replay_event(
                        task_id=plan.task_id,
                        trace_id=plan.trace_id,
                        event_type="subtask.blocked",
                        payload={
                            "subtask_id": next_subtask.subtask_id,
                            "workflow_stage": next_subtask.workflow_stage,
                            "reason": "lock_conflict",
                            "conflicts": reservation_conflicts,
                            "lease_seconds": self._subtask_lease_seconds(next_subtask),
                            "queued_waiters": self.ownership.active_waiters(task_id=plan.task_id),
                        },
                    )
                    ready = ready[1:]
                    continue
                if next_subtask.workflow_stage == "review" and sm.state == "coding":
                    self._transition_workflow(
                        sm=sm,
                        shared_state=shared_state,
                        diagnostics=diagnostics,
                        task_id=plan.task_id,
                        trace_id=plan.trace_id,
                        event="coding.success",
                    )
                if next_subtask.workflow_stage == "artifact" and sm.state == "reviewing":
                    self._transition_workflow(
                        sm=sm,
                        shared_state=shared_state,
                        diagnostics=diagnostics,
                        task_id=plan.task_id,
                        trace_id=plan.trace_id,
                        event="review.pass",
                    )

                plan.mark_running(next_subtask.subtask_id)
                diagnostics.append(
                    {
                        "kind": "subtask_dispatched",
                        "subtask_id": next_subtask.subtask_id,
                        "workflow_stage": next_subtask.workflow_stage,
                        "agent": next_subtask.agent,
                        "priority": next_subtask.priority,
                    }
                )
                self._replay_event(
                    task_id=plan.task_id,
                    trace_id=plan.trace_id,
                    event_type="subtask.dispatched",
                    payload={
                        "subtask_id": next_subtask.subtask_id,
                        "workflow_stage": next_subtask.workflow_stage,
                        "agent": next_subtask.agent,
                        "priority": next_subtask.priority,
                    },
                )
                #异步启动子任务
                running[next_subtask.subtask_id] = (
                    next_subtask,
                    asyncio.create_task(
                        self._execute_subtask_async(plan=plan, subtask=next_subtask, diagnostics=diagnostics)
                    ),
                )
                running_target_files = {
                    path
                    for subtask, _ in running.values()
                    for path in subtask.target_files
                }
                ready = plan.ready_subtasks(running_target_files=running_target_files)

            if not running:
                if plan.has_required_failure():
                    failed = next(subtask for subtask in plan.subtasks if subtask.required and subtask.status == "failed")
                    failure_obj = failed.failure or {}
                    failure = FailureInfo(
                        category=FailureCategory(str(failure_obj.get("category") or FailureCategory.unknown.value)),
                        stage=str(failure_obj.get("stage") or failed.workflow_stage),
                        message=str(failure_obj.get("message") or f"subtask failed: {failed.subtask_id}"),
                        attempts=int(failure_obj.get("attempts") or failed.attempt or 1),
                        retry_limit=int(failure_obj.get("retry_limit") or failed.retry_limit),
                        exception_type=(
                            str(failure_obj.get("exception_type")) if failure_obj.get("exception_type") is not None else None
                        ),
                    )
                    self._clear_task_scheduler_state(plan=plan)
                    return None, failure, retry_count_total
                if plan.all_required_success():
                    coding_outputs = [
                        subtask.output for subtask in plan.subtasks if subtask.workflow_stage == "coding" and isinstance(subtask.output, dict)
                    ]
                    review_output = next(
                        (
                            subtask.output.get("review_result")
                            for subtask in plan.subtasks
                            if subtask.workflow_stage == "review" and isinstance(subtask.output, dict)
                        ),
                        {},
                    )
                    artifact_output = next(
                        (
                            subtask.output.get("artifact_result")
                            for subtask in plan.subtasks
                            if subtask.workflow_stage == "artifact" and isinstance(subtask.output, dict)
                        ),
                        {},
                    )
                    result = (
                        {
                            "coding": ((coding_outputs[0] or {}).get("agent_output") if coding_outputs else {}),
                            "coding_subtasks": coding_outputs,
                            "review": review_output,
                            "artifact": artifact_output,
                            "task_plan": plan.to_dict(),
                        },
                        None,
                        retry_count_total,
                    )
                    self._clear_task_scheduler_state(plan=plan)
                    return result
                if plan.all_terminal():
                    failure = FailureInfo(
                        category=FailureCategory.unknown,
                        stage="dag",
                        message="task plan terminated without satisfying all required subtasks",
                        attempts=1,
                        retry_limit=1,
                    )
                    self._clear_task_scheduler_state(plan=plan)
                    return None, failure, retry_count_total
                failure = FailureInfo(
                    category=FailureCategory.unknown,
                    stage="dag",
                    message="no runnable subtasks remain",
                    attempts=1,
                    retry_limit=1,
                )
                self._clear_task_scheduler_state(plan=plan)
                return None, failure, retry_count_total

            #高性能并发调度
            done, _ = await asyncio.wait(
                [task for _, task in running.values()],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for finished in done:
                match = next((item for item in running.items() if item[1][1] is finished), None)
                if match is None:
                    continue
                subtask_id, (subtask, task) = match
                del running[subtask_id]
                outcome = await task
                self.ownership.release_subtask_locks(task_id=plan.task_id, subtask_id=subtask_id)
                self._requeue_blocked_subtasks(plan=plan, diagnostics=diagnostics)
                messages.extend(outcome["messages"])
                retry_count_total += int(outcome["retries"])

                failure = outcome["failure"]
                if failure is not None:
                    plan.mark_failed(subtask_id, failure=failure.to_dict())
                    diagnostics.append(
                        {
                            "kind": "subtask_failed",
                            "subtask_id": subtask_id,
                            "workflow_stage": subtask.workflow_stage,
                            "message": failure.message,
                        }
                    )
                    self._replay_event(
                        task_id=plan.task_id,
                        trace_id=plan.trace_id,
                        event_type="subtask.failed",
                        payload={
                            "subtask_id": subtask_id,
                            "workflow_stage": subtask.workflow_stage,
                            "failure": failure.to_dict(),
                        },
                    )
                    if subtask.workflow_stage == "coding" and sm.state == "coding":
                        self._transition_workflow(
                            sm=sm,
                            shared_state=shared_state,
                            diagnostics=diagnostics,
                            task_id=plan.task_id,
                            trace_id=plan.trace_id,
                            event="coding.failed",
                        )
                    elif subtask.workflow_stage == "review" and sm.state == "reviewing":
                        self._transition_workflow(
                            sm=sm,
                            shared_state=shared_state,
                            diagnostics=diagnostics,
                            task_id=plan.task_id,
                            trace_id=plan.trace_id,
                            event="review.fail.hard",
                        )
                    elif subtask.workflow_stage == "artifact" and sm.state == "artifacting":
                        self._transition_workflow(
                            sm=sm,
                            shared_state=shared_state,
                            diagnostics=diagnostics,
                            task_id=plan.task_id,
                            trace_id=plan.trace_id,
                            event="artifact.failed",
                        )
                    continue

                output = outcome["output"] or {}
                plan.mark_success(subtask_id, output=output)
                diagnostics.append(
                    {
                        "kind": "subtask_success",
                        "subtask_id": subtask_id,
                        "workflow_stage": subtask.workflow_stage,
                    }
                )
                self._replay_event(
                    task_id=plan.task_id,
                    trace_id=plan.trace_id,
                    event_type="subtask.success",
                    payload={
                        "subtask_id": subtask_id,
                        "workflow_stage": subtask.workflow_stage,
                    },
                )
                if subtask.workflow_stage == "artifact" and sm.state == "artifacting":
                    self._transition_workflow(
                        sm=sm,
                        shared_state=shared_state,
                        diagnostics=diagnostics,
                        task_id=plan.task_id,
                        trace_id=plan.trace_id,
                        event="artifact.success",
                    )

 
    def run_task(self, *, instruction: str, mentioned_agent: str | None = None, review_agent: str | None = None, _shared_diag: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Run the Stage 6 linear pipeline with structured planning output.

        If *_shared_diag* is provided it MUST be a mutable list — every event
        appended to the internal diagnostics list is also appended to this
        shared list so that an external poller (e.g. the Runtime API) can
        read the intermediate progress without waiting for the task to finish.
        """
        print(f"[TRACE] [Orchestrator] run_task START: instruction='{instruction[:80]}...', mentioned_agent={mentioned_agent}, review_agent={review_agent}", flush=True)

        task_id = uuid.uuid4().hex
        trace_id = new_trace_id()
        diagnostics: list[dict[str, Any]] = []
        # 当外部传入共享列表时，_emit_event 会同步写入
        self._shared_diag = _shared_diag
        messages: list[dict[str, Any]] = []
        task_t0 = time.perf_counter()
        task_success = False
        retry_count_total = 0
        plan: LinearPlan | None = None
        used_skills: list[str] = []

        shared_state: dict[str, Any] = {"workflow_state": "created", "diagnostic_events": diagnostics}
        self._emit_event(task_id=task_id, trace_id=trace_id, diagnostics=diagnostics, event_type="task.created")

        try:
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="planning.started",
            )
            try:
                plan, planner_used = self.linear_planner.plan(task_id=task_id, instruction=instruction)
            except Exception as exc:
                failure = FailureInfo(
                    category=FailureCategory.schema_invalid,
                    stage="planning",
                    message=str(exc),
                    attempts=1,
                    retry_limit=1,
                    exception_type=type(exc).__name__,
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.failed",
                    payload={"stage": "planning", "message": str(exc)},
                )
                return self._failure_response(
                    task_id=task_id,
                    trace_id=trace_id,
                    messages=messages,
                    diagnostics=diagnostics,
                    failure=failure,
                )

            shared_state["workflow_state"] = "planned"
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="planning.completed",
                payload={"planner": planner_used, "summary": plan.summary, "target_count": len(plan.targets)},
            )

            coding_payload = {
                "task": {
                    "instruction": instruction,
                    "task_type": plan.task_type,
                    "language": plan.language,
                    "targets": [target.to_dict() for target in plan.targets],
                },
                "task_plan": plan.to_dict(),
                # 注入 session_id — 让 external_cli 能把文件复制到 source 目录
                "session_id": self.session_id,
            }
            shared_state["workflow_state"] = "coding"
            
            # ── Stage 8: Persona 加载 ──────────────────────────
            from runtime.agents.persona import PersonaLoader, AgentPromptBuilder
            persona_loader = PersonaLoader()
            agent_def = persona_loader.resolve(mentioned_agent)

            # 选择编码技能：如果用户指定了 agent，则使用对应的技能
            # ⭐ Stage 10: 默认使用 SkillRouter 分流
            coding_skill_name = "codex_coding"  # 默认 Codex（最快路径）
            # ⭐ SkillRouter 在 coding 分支之外也定义好，避免 UnboundLocalError
            from runtime.core.skill_router import SkillRouter
            skill_router = SkillRouter()
            if mentioned_agent == "claude_code":
                coding_skill_name = "claude_code"
            elif mentioned_agent == "codex":
                coding_skill_name = "codex_coding"
            elif agent_def is not None:
                preferred = agent_def.preferred_provider or "codex"
                if preferred == "claude_code":
                    coding_skill_name = "claude_code"
                elif preferred == "codex":
                    coding_skill_name = "codex_coding"
                if not AgentPromptBuilder.check_skill_allowed(agent_def, "coding"):
                    coding_skill_name = "coding.generate_patch"
            else:
                # ⭐ 无用户指定时用 SkillRouter 自动选择
                coding_decision = skill_router.select_coding_skill(plan)
                coding_skill_name = coding_decision.skill_name
                print(f"[TRACE] [Orchestrator] SkillRouter coding decision: {coding_skill_name} — {coding_decision.reason}", flush=True)

            # Persona 注入：将 system_prompt 写入 payload
            if agent_def is not None:
                persona_prompt = AgentPromptBuilder.build_coding_prompt(
                    agent_def=agent_def,
                    instruction=instruction,
                    targets=[target.to_dict() for target in plan.targets],
                )
                coding_payload["persona"] = {
                    "agent_id": agent_def.id,
                    "agent_name": agent_def.name,
                    "system_prompt": agent_def.system_prompt,
                    "allowed_skills": list(agent_def.allowed_skills),
                }
                coding_payload["task"]["instruction"] = persona_prompt

            used_skills.append(coding_skill_name)
            print(f"[TRACE] [Orchestrator] Coding skill resolved: {coding_skill_name}, plan.complexity={getattr(plan, 'complexity', 'N/A')}, plan.workspace_type={getattr(plan, 'workspace_type', 'N/A')}")

            # ⭐ Stage 9: 编码阶段开始时发送进度事件
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="coding.started",
                payload={"skill": coding_skill_name, "target_count": len(plan.targets), "using": "builtin" if coding_skill_name == "coding.generate_patch" else "external_cli"},
            )

            # ── Diff Pipeline: before snapshot ────────────────────
            diff_pipeline = DiffPipeline()
            ws_source = getattr(self.workspace, "source_root", None)
            if ws_source and ws_source.exists():
                diff_pipeline.snapshot_before(ws_source)
            # ─────────────────────────────────────────────────────

            # ⭐ Stage 9: 如果使用外部 CLI，发送 cli.started 事件；内置发送 emit 已在上方
            is_external_cli = coding_skill_name in ("claude_code", "codex_coding")
            if is_external_cli:
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="cli.started",
                    payload={"skill": coding_skill_name},
                )
            else:
                # ⭐ 内置 Agent — 直接 emit builtin_started 事件，让前端知道使用内置 LLM
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="builtin.started",
                    payload={"skill": coding_skill_name, "target_count": len(plan.targets)},
                )

            # ⭐ Stage 10: 编码阶段耗时日志 (同时写 stdout+stderr)
            import sys as _sys
            coding_t0 = time.perf_counter()
            msg = (f"[ORCH] Coding stage START: skill={coding_skill_name}, "
                   f"task_id={task_id[:16]}..., plan.complexity={getattr(plan, 'complexity', 'N/A')}, "
                   f"plan.workspace_type={getattr(plan, 'workspace_type', 'N/A')}")
            print(msg, flush=True)
            _sys.stderr.write(msg + "\n")
            _sys.stderr.flush()

            coding_env, coding_failure, coding_retries = self._call_skill_with_retry(
                stage="coding",
                skill_name=coding_skill_name,
                task_id=task_id,
                trace_id=trace_id,
                payload=coding_payload,
                shared_state=shared_state,
                messages=messages,
                plan=plan,
            )
            coding_latency_ms = int((time.perf_counter() - coding_t0) * 1000)
            msg2 = (f"[ORCH] Coding stage END: skill={coding_skill_name}, "
                    f"latency={coding_latency_ms}ms, "
                    f"success={coding_failure is None and coding_env is not None}")
            print(msg2, flush=True)
            _sys.stderr.write(msg2 + "\n")
            _sys.stderr.flush()
            retry_count_total += int(coding_retries)
            if coding_failure is not None or coding_env is None:
                failure = coding_failure or FailureInfo(
                    category=FailureCategory.unknown,
                    stage="coding",
                    message="coding returned no result",
                    attempts=1,
                    retry_limit=1,
                )
                print(f"[ERROR] Coding stage FAILED: {failure.message}", flush=True)
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="coding.failed",
                    payload={"message": failure.message},
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.failed",
                    payload={"stage": "coding", "message": failure.message},
                )
                return self._failure_response(
                    task_id=task_id,
                    trace_id=trace_id,
                    messages=messages,
                    diagnostics=diagnostics,
                    failure=failure,
                    task_plan=plan,
                )
            try:
                coding_output = self._normalize_linear_coding_output(result_env=coding_env)
            except Exception as e:
                print(f"[ERROR] normalize_linear_coding failed: {e}", flush=True)
                import traceback
                traceback.print_exc()
                # 即使 normalizer 失败，也继续——用 agent_output 中的原始 changes
                coding_output = {
                    "agent_output": dict(coding_env.payload) if coding_env else {},
                    "applied_changes": [],
                    "content_samples": {},
                    "summary": {"applied_change_count": 0},
                }
            applied_changes = coding_output.get("applied_changes") or []
            print(f"[TRACE] [Orchestrator] Coding output normalized: {len(applied_changes)} applied_changes, content_samples={len(coding_output.get('content_samples') or {})}")

            # ── Diff Pipeline: after snapshot + compute diff ─────
            diff_changes = []
            if ws_source and ws_source.exists():
                diff_pipeline.snapshot_after(ws_source)
                diff_result = diff_pipeline.diff()
                diff_changes = [c.to_dict() if hasattr(c, 'to_dict') else {"action": c.action, "path": c.path} for c in diff_result.changes]
                if diff_changes:
                    print(f"[TRACE] [DiffPipeline] Detected {len(diff_changes)} file changes")
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="workspace.changed",
                        payload={"changes": diff_changes, "has_git": diff_result.has_git},
                    )
                    # Also inject diff changes into coding_output for artifact creation
                    if "applied_changes" not in coding_output or not coding_output["applied_changes"]:
                        coding_output["applied_changes"] = diff_changes
                    elif diff_changes:
                        existing_paths = {c.get("path") for c in coding_output.get("applied_changes") or []}
                        for dc in diff_changes:
                            if dc.get("path") not in existing_paths:
                                coding_output.setdefault("applied_changes", []).append(dc)
            if not diff_changes:
                print(f"[TRACE] [Orchestrator] Diff Pipeline: no changes detected (source exists={ws_source and ws_source.exists()})")
            # ─────────────────────────────────────────────────────

            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="coding.completed",
                payload={"applied_change_count": len(coding_output.get("applied_changes") or []), "latency_ms": coding_latency_ms},
            )
            
            # 获取新的领域模型字段
            interaction_mode = plan.interaction_mode if hasattr(plan, "interaction_mode") else "orchestrated"
            execution_mode = plan.execution_mode if hasattr(plan, "execution_mode") else "task"
            chat_mode = plan.chat_mode if hasattr(plan, "chat_mode") else "single"
            review_required = plan.review_required if hasattr(plan, "review_required") else False  # ⭐ Stage 10: 默认跳过 review
            # ⭐ Step 5: 用户提及 review 相关 agent 时自动启用
            # ⭐ 多 agent 场景：review_agent 优先（来自 extractReviewAgent）
            if not review_required:
                # ⭐ review_agent 不为空意味着用户明确要求审查
                if review_agent:
                    review_required = True
                elif review_agent in ("claude_review",):
                    review_required = True
                elif mentioned_agent in ("claude_review",):
                    review_required = True
                elif isinstance(mentioned_agent, str) and "review" in mentioned_agent.lower():
                    review_required = True
                # 如果 instruction 中明确包含审查关键词
                elif instruction and any(kw in instruction.lower() for kw in (
                    "@review", "@claude_review", "@claude code",
                    "@security_reviewer", "审查", "@qa_engineer",
                )):
                    review_required = True
            package_strategy = plan.package_strategy if hasattr(plan, "package_strategy") else "none"
            
            # Direct Agent 模式：直接结束，跳过后续阶段
            if interaction_mode == "direct_agent":
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.completed",
                    payload={"execution_model": plan.execution_model, "interaction_mode": interaction_mode},
                )
                task_success = True
                return {
                    "ok": True,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "messages": messages,
                    "diagnostics": diagnostics,
                    "result": {
                        "execution_model": plan.execution_model,
                        "task_plan": plan.to_dict(),
                        "coding": coding_output,
                        "review": None,
                        "artifact": None,
                        "used_skills": used_skills,
                    },
                }
            
            # Orchestrated 模式：继续执行后续阶段
            # ⭐ Stage 10: 默认跳过 Review - 不指定时快速完成编码即可
            review_output = {"pass": True, "skipped": True, "reason": "review_not_required"}
            artifact_output = None

            # Review 阶段（如果需要）
            if review_required:
                _sys.stderr.write(f"[ORCH] Review stage START (review_required=True)\n")
                _sys.stderr.flush()
                review_t0 = time.perf_counter()  # ⭐ Step 4: 记录 review 开始时间
                review_payload = {
                    "task_type": plan.task_type,
                    "applied_changes": coding_output.get("applied_changes") or [],
                    "content_samples": coding_output.get("content_samples") or {},
                    "task_plan": plan.to_dict(),
                    # ⭐ 传递原始 instruction 给 review agent
                    "task": {"instruction": instruction},
                    # ⭐ Step 1: 编码上下文 — 让 review agent 了解 Codex 的思考过程
                    "coding_context": {
                        "plan": coding_output.get("plan") or [],
                        "thinking_trace": coding_output.get("thinking_trace") or "",
                        "changes_summary": _summarize_changes(coding_output.get("applied_changes") or []),
                        "used_skill": coding_skill_name,
                        "coding_latency_ms": coding_latency_ms,
                    },
                }
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="review.started",
                )
                shared_state["workflow_state"] = "reviewing"
                
                # ⭐ Stage 10: 使用 SkillRouter 智能分流审查技能
                review_decision = skill_router.select_review_skill(plan)
                review_skill_name = review_decision.skill_name
                print(f"[TRACE] [Orchestrator] SkillRouter review decision: {review_skill_name} — {review_decision.reason}", flush=True)

                # 用户显式指定 agent 时优先级最高
                # ⭐ review_agent 优先（来自 Gateway extractReviewAgent / 群聊多 agent 文本解析）
                # ⭐ 只对 claude_review 做覆盖；codex 不覆盖（用内置 LLM 更快）
                if review_agent == "claude_review":
                    review_skill_name = "claude_review"
                elif mentioned_agent == "claude_review":
                    review_skill_name = "claude_review"
                # ⭐ 不再把 @Codex 强制映射到 codex_review — 编码用 Codex，审查用内置 LLM
                elif agent_def is not None:
                    # User-Defined Agent：白名单检查 + 使用 claude_review
                    if AgentPromptBuilder.check_skill_allowed(agent_def, "review"):
                        review_skill_name = "claude_review"

                print(f"[TRACE] [Orchestrator] Final review skill: {review_skill_name}", flush=True)

                # 注入 persona 到 review payload
                if agent_def is not None:
                    review_payload["persona"] = {
                        "agent_id": agent_def.id,
                        "agent_name": agent_def.name,
                        "system_prompt": agent_def.system_prompt,
                    }
                used_skills.append(review_skill_name)
                
                review_env, review_failure, review_retries = self._call_skill_with_retry(
                    stage="review",
                    skill_name=review_skill_name,
                    task_id=task_id,
                    trace_id=trace_id,
                    payload=review_payload,
                    shared_state=shared_state,
                    messages=messages,
                    plan=plan,
                )
                retry_count_total += int(review_retries)
                if review_failure is not None or review_env is None:
                    failure = review_failure or FailureInfo(
                        category=FailureCategory.review_failed,
                        stage="review",
                        message="review returned no result",
                        attempts=1,
                        retry_limit=1,
                    )
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="review.failed",
                        payload={"message": failure.message},
                    )
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="task.failed",
                        payload={"stage": "review", "message": failure.message},
                    )
                    return self._failure_response(
                        task_id=task_id,
                        trace_id=trace_id,
                        messages=messages,
                        diagnostics=diagnostics,
                        failure=failure,
                        task_plan=plan,
                    )
                review_output = self._normalize_review_output(
                    subtask=Subtask(
                        subtask_id="linear-review",
                        title="linear review",
                        workflow_stage="review",
                        agent="review",
                        skill_name="review.analyze_changes",
                        target_files=[target.path for target in plan.targets[:3]],
                        dependency_ids=[],
                        order=0,
                    ),
                    result_env=review_env,
                )["review_result"]
                # ⭐ 注入 review_skill 名称，供 Gateway 展示用
                review_output["review_skill"] = review_skill_name
                print(f"[TRACE] [Orchestrator] Review output: pass={review_output.get('pass')}, score={review_output.get('score')}, issues={len(review_output.get('issues') or [])}, skill={review_skill_name}", flush=True)
                # ── Approval gate (checked first, independent of pass/fail) ─
                if bool(review_output.get("approval_required")):
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="approval.required",
                        payload={"issues": review_output.get("issues") or []},
                    )
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="task.paused",
                        payload={"stage": "review", "reason": "approval_required"},
                    )
                    return {
                        "ok": True,
                        "status": "approval_pending",
                        "task_id": task_id,
                        "trace_id": trace_id,
                        "messages": messages,
                        "diagnostics": diagnostics,
                        "task_plan": plan.to_dict(),
                        "coding_output": coding_output,
                        "review_output": review_output,
                    }

                review_latency_ms = int((time.perf_counter() - review_t0) * 1000)  # ⭐ Step 4
                if not bool(review_output.get("pass")):
                    # ── Hard review failure (no approval gate) ──────
                    failure = FailureInfo(
                        category=FailureCategory.review_failed,
                        stage="review",
                        message=as_json(review_output),
                        attempts=1,
                        retry_limit=1,
                    )
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="review.failed",
                        payload={"issues": review_output.get("issues") or [], "latency_ms": review_latency_ms},
                    )
                    self._emit_event(
                        task_id=task_id,
                        trace_id=trace_id,
                        diagnostics=diagnostics,
                        event_type="task.failed",
                        payload={"stage": "review", "message": failure.message},
                    )
                    return self._failure_response(
                        task_id=task_id,
                        trace_id=trace_id,
                        messages=messages,
                        diagnostics=diagnostics,
                        failure=failure,
                        task_plan=plan,
                    )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="review.completed",
                    payload={"issue_count": len(review_output.get("issues") or []), "latency_ms": review_latency_ms},
                )
            
            # 如果不需要 packaging，直接结束
            if package_strategy == "none":
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.completed",
                    payload={"execution_model": plan.execution_model, "interaction_mode": interaction_mode, "execution_mode": execution_mode, "chat_mode": chat_mode},
                )
                task_success = True
                return {
                    "ok": True,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "messages": messages,
                    "diagnostics": diagnostics,
                    "result": {
                        "execution_model": plan.execution_model,
                        "task_plan": plan.to_dict(),
                        "coding": coding_output,
                        # ⭐ review 跳过时返回 skip sentinel，而不是 None
                        "review": review_output if review_output is not None else {"pass": True, "skipped": True, "reason": "review_not_required"},
                        "artifact": None,
                        "used_skills": used_skills,
                    },
                }
            
            # 需要 packaging：继续执行 Packaging (Artifact) 阶段
            artifact_payload = {
                "artifacts_root": self._artifact_root(),
                "version": "v1",
                "applied_changes": coding_output.get("applied_changes") or [],
                "review_result": review_output,
                "snapshots": coding_output.get("content_samples") or {},
                "task_plan": plan.to_dict(),
                "package_strategy": package_strategy,
            }
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="packaging.started",
            )
            shared_state["workflow_state"] = "packaging"
            artifact_env, artifact_failure, artifact_retries = self._call_agent_with_retry(
                stage="packaging",
                task_id=task_id,
                trace_id=trace_id,
                agent_id="artifact",
                payload=artifact_payload,
                shared_state=shared_state,
                messages=messages,
            )
            retry_count_total += int(artifact_retries)
            if artifact_failure is not None or artifact_env is None:
                failure = artifact_failure or FailureInfo(
                    category=FailureCategory.unknown,
                    stage="packaging",
                    message="packaging returned no result",
                    attempts=1,
                    retry_limit=1,
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="packaging.failed",
                    payload={"message": failure.message},
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.failed",
                    payload={"stage": "packaging", "message": failure.message},
                )
                return self._failure_response(
                    task_id=task_id,
                    trace_id=trace_id,
                    messages=messages,
                    diagnostics=diagnostics,
                    failure=failure,
                    task_plan=plan,
                )

            artifact_output = artifact_env.payload
            artifact_dir = str(artifact_output.get("artifact_dir") or "")
            if artifact_dir:
                self._replay_artifact(
                    task_id=task_id,
                    trace_id=trace_id,
                    artifact_dir=artifact_dir,
                    payload={
                        "created_files": artifact_output.get("created_files"),
                        "summary": artifact_output.get("summary"),
                        "version": artifact_output.get("version"),
                    },
                )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="packaging.completed",
                payload={"artifact_dir": artifact_dir, "version": artifact_output.get("version")},
            )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="task.completed",
                payload={"execution_model": plan.execution_model, "interaction_mode": interaction_mode, "execution_mode": execution_mode},
            )

            task_success = True
            return {
                "ok": True,
                "task_id": task_id,
                "trace_id": trace_id,
                "messages": messages,
                "diagnostics": diagnostics,
                "result": {
                    "execution_model": plan.execution_model,
                    "task_plan": plan.to_dict(),
                    "coding": coding_output.get("agent_output", coding_output),
                    "review": review_output.get("review_result", review_output),
                    "artifact": artifact_output,
                    "used_skills": used_skills,
                },
            }
        finally:
            self._shared_diag = None
            self._record_task_metrics(
                task_id=task_id,
                task_success=task_success,
                retry_count_total=retry_count_total,
                task_t0=task_t0,
            )

    def resume_task(
        self,
        *,
        task_id: str,
        trace_id: str,
        approval_decision: str,
        task_plan_dict: dict[str, Any],
        coding_output: dict[str, Any],
        review_output: dict[str, Any],
        messages: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Resume a Stage 6 task that was paused for human approval.

        *approval_decision* must be ``"approved"`` or ``"rejected"``.

        On approval the pipeline continues to the Artifact stage.  On rejection
        the task is failed with an ``approval_denied`` event.
        """
        task_t0 = time.perf_counter()
        task_success = False
        retry_count_total = 0

        # ── Reconstruct plan ────────────────────────────────────
        targets_data = task_plan_dict.get("targets") or []
        plan = LinearPlan(
            task_id=task_id,
            summary=str(task_plan_dict.get("summary") or ""),
            language=task_plan_dict.get("language"),
            task_type=str(task_plan_dict.get("task_type") or "generic"),
            execution_model=str(task_plan_dict.get("execution_model") or "linear_pipeline"),
            planner=str(task_plan_dict.get("planner") or "rule_planner"),
            planner_strategy=str(task_plan_dict.get("planner_strategy") or "fallback"),
            instruction=str(task_plan_dict.get("instruction") or ""),
            targets=[
                PlanTarget(
                    path=str(t.get("path") or ""),
                    action=str(t.get("action") or "create"),
                    language=str(t.get("language") or "text"),
                    reason=str(t.get("reason") or ""),
                    base_hash=t.get("base_hash"),
                )
                for t in targets_data
                if isinstance(t, dict)
            ],
            artifacts=[
                PlanArtifact(
                    type=str(a.get("type") or "bundle"),
                    title=str(a.get("title") or "Artifact"),
                )
                for a in (task_plan_dict.get("artifacts") or [])
                if isinstance(a, dict)
            ],
            risks=[
                PlanRisk(
                    severity=str(r.get("severity") or "medium"),
                    summary=str(r.get("summary") or ""),
                )
                for r in (task_plan_dict.get("risks") or [])
                if isinstance(r, dict)
            ],
            interaction_mode=str(task_plan_dict.get("interaction_mode") or "orchestrated"),
            execution_mode=str(task_plan_dict.get("execution_mode") or "task"),
            chat_mode=str(task_plan_dict.get("chat_mode") or "single"),
            review_required=task_plan_dict.get("review_required", True),
            complexity=TaskComplexity(task_plan_dict.get("complexity", "medium"))
                if task_plan_dict.get("complexity") in ("simple", "medium", "project")
                else TaskComplexity.MEDIUM,
            workspace_type=str(task_plan_dict.get("workspace_type") or "scratch"),
            package_strategy=str(task_plan_dict.get("package_strategy") or "none"),
        )

        shared_state: dict[str, Any] = {"workflow_state": "reviewing", "diagnostic_events": diagnostics}

        # ── Approval decision gate ──────────────────────────────
        decision = approval_decision.strip().lower()
        if decision == "rejected":
            failure = FailureInfo(
                category=FailureCategory.review_failed,
                stage="review",
                message="approval denied by human operator",
                attempts=1,
                retry_limit=1,
            )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="approval.denied",
                payload={"decision": approval_decision},
            )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="task.failed",
                payload={"stage": "review", "message": failure.message},
            )
            return self._failure_response(
                task_id=task_id,
                trace_id=trace_id,
                messages=messages,
                diagnostics=diagnostics,
                failure=failure,
                task_plan=plan,
            )

        if decision != "approved":
            failure = FailureInfo(
                category=FailureCategory.review_failed,
                stage="review",
                message=f"invalid approval decision: {approval_decision}",
                attempts=1,
                retry_limit=1,
            )
            return self._failure_response(
                task_id=task_id,
                trace_id=trace_id,
                messages=messages,
                diagnostics=diagnostics,
                failure=failure,
                task_plan=plan,
            )

        # ── Approved: continue to packaging ──────────────────────
        self._emit_event(
            task_id=task_id,
            trace_id=trace_id,
            diagnostics=diagnostics,
            event_type="approval.approved",
            payload={"decision": approval_decision},
        )
        self._emit_event(
            task_id=task_id,
            trace_id=trace_id,
            diagnostics=diagnostics,
            event_type="review.completed",
            payload={"issue_count": len(review_output.get("issues") or [])},
        )

        try:
            artifact_payload = {
                "artifacts_root": self._artifact_root(),
                "version": "v1",
                "applied_changes": coding_output.get("applied_changes") or [],
                "review_result": review_output,
                "snapshots": coding_output.get("content_samples") or {},
                "task_plan": plan.to_dict(),
            }
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="packaging.started",
            )
            shared_state["workflow_state"] = "packaging"
            artifact_env, artifact_failure, artifact_retries = self._call_agent_with_retry(
                stage="packaging",
                task_id=task_id,
                trace_id=trace_id,
                agent_id="artifact",
                payload=artifact_payload,
                shared_state=shared_state,
                messages=messages,
            )
            retry_count_total += int(artifact_retries)
            if artifact_failure is not None or artifact_env is None:
                failure = artifact_failure or FailureInfo(
                    category=FailureCategory.unknown,
                    stage="packaging",
                    message="packaging returned no result",
                    attempts=1,
                    retry_limit=1,
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="packaging.failed",
                    payload={"message": failure.message},
                )
                self._emit_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    diagnostics=diagnostics,
                    event_type="task.failed",
                    payload={"stage": "packaging", "message": failure.message},
                )
                return self._failure_response(
                    task_id=task_id,
                    trace_id=trace_id,
                    messages=messages,
                    diagnostics=diagnostics,
                    failure=failure,
                    task_plan=plan,
                )

            artifact_output = artifact_env.payload
            artifact_dir = str(artifact_output.get("artifact_dir") or "")
            if artifact_dir:
                self._replay_artifact(
                    task_id=task_id,
                    trace_id=trace_id,
                    artifact_dir=artifact_dir,
                    payload={
                        "created_files": artifact_output.get("created_files"),
                        "summary": artifact_output.get("summary"),
                        "version": artifact_output.get("version"),
                    },
                )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="packaging.completed",
                payload={"artifact_dir": artifact_dir, "version": artifact_output.get("version")},
            )
            self._emit_event(
                task_id=task_id,
                trace_id=trace_id,
                diagnostics=diagnostics,
                event_type="task.completed",
                payload={"execution_model": plan.execution_model, "interaction_mode": plan.interaction_mode, "execution_mode": plan.execution_mode},
            )

            task_success = True
            return {
                "ok": True,
                "task_id": task_id,
                "trace_id": trace_id,
                "messages": messages,
                "diagnostics": diagnostics,
                "result": {
                    "execution_model": plan.execution_model,
                    "task_plan": plan.to_dict(),
                    "coding": coding_output,
                    "review": review_output,
                    "artifact": artifact_output,
                    "used_skills": used_skills,
                },
            }
        finally:
            self._record_task_metrics(
                task_id=task_id,
                task_success=task_success,
                retry_count_total=retry_count_total,
                task_t0=task_t0,
            )

    def run_demo_task(self, *, instruction: str) -> dict[str, Any]:
        """Run the Stage 4 demo workflow through task splitting and DAG scheduling."""

        task_id = uuid.uuid4().hex
        trace_id = new_trace_id()
        diagnostics: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        sm = WorkflowStateMachine.from_execution_policy(self.ruleset.execution, initial_state="created")
        shared_state: dict[str, Any] = {"workflow_state": sm.state, "diagnostic_events": diagnostics}
        task_t0 = time.perf_counter()
        task_success = False
        retry_count_total = 0
        failure: FailureInfo | None = None

        try:
            try:
                plan = self._build_demo_task_plan(task_id=task_id, trace_id=trace_id, instruction=instruction)
            except TaskPlanError as exc:
                failure = FailureInfo(
                    category=FailureCategory.schema_invalid,
                    stage="planning",
                    message=str(exc),
                    attempts=1,
                    retry_limit=1,
                    exception_type=type(exc).__name__,
                )
                return {
                    "ok": False,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "messages": messages,
                    "failure": failure.to_dict(),
                    "diagnostics": diagnostics,
                }

            diagnostics.append({"kind": "task_planned", "task_id": task_id, "subtask_count": len(plan.subtasks)})
            self._replay_event(
                task_id=task_id,
                trace_id=trace_id,
                event_type="task.planned",
                payload={
                    "subtask_count": len(plan.subtasks),
                    "subtasks": [
                        {
                            "subtask_id": subtask.subtask_id,
                            "workflow_stage": subtask.workflow_stage,
                            "agent": subtask.agent,
                            "dependency_ids": list(subtask.dependency_ids),
                            "target_files": list(subtask.target_files),
                        }
                        for subtask in plan.subtasks
                    ],
                },
            )

            try:
                self._transition_workflow(
                    sm=sm,
                    shared_state=shared_state,
                    diagnostics=diagnostics,
                    task_id=task_id,
                    trace_id=trace_id,
                    event="start",
                )
            except IllegalStateTransitionError as exc:
                failure = FailureInfo(
                    category=FailureCategory.unknown,
                    stage="workflow",
                    message=str(exc),
                    attempts=1,
                    retry_limit=1,
                    exception_type=type(exc).__name__,
                )
                return {
                    "ok": False,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "messages": messages,
                    "failure": failure.to_dict(),
                    "diagnostics": diagnostics,
                }

            result_payload, failure, retry_count_total = asyncio.run(
                self._run_task_plan_async(
                    plan=plan,
                    diagnostics=diagnostics,
                    messages=messages,
                    sm=sm,
                    shared_state=shared_state,
                )
            )
            if failure is not None:
                return {
                    "ok": False,
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "messages": messages,
                    "failure": failure.to_dict(),
                    "diagnostics": diagnostics,
                    "task_plan": plan.to_dict(),
                }

            task_success = True
            return {
                "ok": True,
                "task_id": task_id,
                "trace_id": trace_id,
                "messages": messages,
                "diagnostics": diagnostics,
                "result": result_payload,
            }
        finally:
            self._record_task_metrics(
                task_id=task_id,
                task_success=task_success,
                retry_count_total=retry_count_total,
                task_t0=task_t0,
            )
