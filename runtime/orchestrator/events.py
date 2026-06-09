from __future__ import annotations

"""
事件发射器 — 从 Orchestrator 剥离的诊断/Replay 事件记录逻辑。

通过 EventEmitter 封装，注入 replay store 即可，不再依赖 Orchestrator 实例。
"""

from typing import Any

from runtime.harness.replay import SQLiteReplayStore, PostgresReplayStore

ReplayStore = SQLiteReplayStore | PostgresReplayStore


class EventEmitter:
    """统一的事件/诊断/Replay 发射器。

    所有 emit_* 方法都会同步写入 shared diagnostics 列表（若提供），
    同时异步写入 replay store（若配置）。
    """

    def __init__(self, replay: ReplayStore | None = None):
        self.replay = replay

    def emit_diagnostic(
        self,
        *,
        task_id: str,
        trace_id: str,
        diagnostics: list[dict[str, Any]],
        event_type: str,
        payload: dict[str, Any] | None = None,
        shared_diag: list[dict[str, Any]] | None = None,
    ) -> None:
        """发射一条诊断事件到 diagnostics 列表和 replay store。

        如果 shared_diag 与 diagnostics 不是同一个列表（由外部轮询者提供），
        也会同步写入 shared_diag 以便外部实时读取进度。
        """
        event_payload = payload or {}
        entry = {"kind": event_type, **event_payload}
        diagnostics.append(entry)

        if shared_diag is not None and shared_diag is not diagnostics:
            shared_diag.append(dict(entry))

        if self.replay is not None:
            try:
                self.replay.append_event(
                    task_id=task_id,
                    trace_id=trace_id,
                    event_type=event_type,
                    payload=event_payload,
                )
            except Exception:
                pass

    def replay_artifact(
        self,
        *,
        task_id: str,
        trace_id: str,
        artifact_dir: str,
        payload: dict[str, Any],
    ) -> None:
        """写入一条 artifact replay 记录。"""
        if self.replay is None:
            return
        try:
            self.replay.append_artifact(
                task_id=task_id,
                trace_id=trace_id,
                artifact_id=task_id,
                artifact_dir=artifact_dir,
                payload=payload,
            )
        except Exception:
            pass
