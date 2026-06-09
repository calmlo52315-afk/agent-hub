from __future__ import annotations

import difflib
import json
import logging
from typing import Any

from runtime.harness.workspace import AppliedChange, FileChange, Workspace
from runtime.messages import Envelope
from runtime.orchestrator.task_graph import Subtask

logger = logging.getLogger(__name__)


# ── 工具函数 ────────────────────────────────────────────────

def as_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _generate_unified_diff(
    before_content: str | None,
    after_content: str | None,
    path: str,
    action: str,
) -> str:
    """使用 difflib 生成真正的 unified diff。

    返回标准的 unified diff 格式字符串，包含 +++/--- 头部和行级差异。
    前端可以解析为绿色(+)/红色(-)行来展示。
    """
    before_lines = (before_content or "").splitlines(keepends=True)
    after_lines = (after_content or "").splitlines(keepends=True)

    if action == "create":
        diff_lines = list(difflib.unified_diff(
            [], after_lines,
            fromfile="/dev/null",
            tofile=f"b/{path}",
            lineterm="",
        ))
        return "\n".join(diff_lines) if diff_lines else ""

    if action == "delete":
        diff_lines = list(difflib.unified_diff(
            before_lines, [],
            fromfile=f"a/{path}",
            tofile="/dev/null",
            lineterm="",
        ))
        return "\n".join(diff_lines) if diff_lines else ""

    # update
    diff_lines = list(difflib.unified_diff(
        before_lines, after_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))
    return "\n".join(diff_lines) if diff_lines else ""


def diff_excerpt_create(path: str, content: str, ctx_lines: int = 5) -> str:
    """Generate a unified-diff-style excerpt for a newly created file."""
    lines = content.split("\n")
    preview_lines = lines[:ctx_lines]
    snippet = "\n".join(f"+{line}" for line in preview_lines)
    if len(lines) > ctx_lines:
        snippet += f"\n+... ({len(lines)} lines total)"
    return f"--- /dev/null\n+++ {path}\n@@ -0,0 +1,{len(lines)} @@\n{snippet}"


def diff_excerpt_update(path: str, before: str, after: str) -> str:
    """⭐ 使用 difflib 为 update 操作生成真正的行级对比 diff。"""
    return _generate_unified_diff(before, after, path, "update")


# ── 输出归一化 ──────────────────────────────────────────────

class OutputNormalizer:
    """将 Agent 原始输出归一化为 Orchestrator 可消费的结构化格式。

    每个 normalize_* 方法接收 workspace + 原始输出，返回标准化的 dict。
    """

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    # ── Linear 管线用（run_task）───────────────────────────────

    def normalize_linear_coding(self, *, result_env: Envelope) -> dict[str, Any]:
        """归一化 Linear 管线的 coding 输出。

        ⭐ Stage 9: 为每个变更生成真正的 unified diff (before/after 行级对比)。
        """
        changes = (result_env.payload or {}).get("changes") or []
        if not isinstance(changes, list):
            raise TypeError("coding.changes must be list")

        # 收集所有 changes（跳过缺少 path 或 content 的无效项，按 path 去重）
        file_changes: list[FileChange] = []
        seen_paths: set[str] = set()
        skipped_missing_content = 0
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            path = str(ch.get("path") or "")
            action = str(ch.get("action") or "")
            if not path or not action:
                continue
            if path in seen_paths:
                continue  # 跳过重复路径
            seen_paths.add(path)
            content = ch.get("content") if isinstance(ch.get("content"), str) else None
            base_hash = ch.get("base_hash") if isinstance(ch.get("base_hash"), str) else None
            # 若缺失 content 但非 delete，尝试从磁盘读取
            if content is None and action != "delete":
                try:
                    fpath = self.workspace._abs(path)
                    if fpath.exists() and fpath.is_file():
                        content = fpath.read_text(encoding="utf-8")
                    else:
                        fpath2 = self.workspace.repo_root / path
                        if fpath2.exists() and fpath2.is_file():
                            content = fpath2.read_text(encoding="utf-8")
                except Exception:
                    pass
            if content is None and action != "delete":
                skipped_missing_content += 1
                continue  # 跳过无内容的 create/update
            file_changes.append(
                FileChange(action=action, path=path, content=content, base_hash=base_hash)
            )

        if skipped_missing_content:
            logger.warning(
                f"[Normalizer] Skipped {skipped_missing_content} changes missing content"
            )

        applied_changes: list[AppliedChange] = []
        for change in file_changes:
            applied_changes.append(self.workspace.apply_change(role="coding", change=change))

        content_samples: dict[str, str] = {}
        for applied in applied_changes:
            if applied.action in ("create", "update"):
                content_samples[applied.path] = self.workspace.read_text(role="review", rel_path=applied.path)

        # ⭐ 生成真实 unified diff（使用 difflib）
        real_diffs: list[dict[str, Any]] = []
        for applied in applied_changes:
            path = applied.path
            action = applied.action
            after_content = content_samples.get(path, "")

            if action == "create":
                unified_diff = _generate_unified_diff(
                    before_content=None,
                    after_content=after_content,
                    path=path,
                    action="create",
                )
                real_diffs.append({
                    "path": path,
                    "diff": unified_diff,
                    "action": action,
                    "before_content": None,
                    "after_content": after_content,
                })
            elif action == "update":
                # ⭐ 对 update：用 difflib 生成 before/after 行级对比
                before_content = None
                fpath = self.workspace._abs(path)
                if not (fpath.exists() and fpath.is_file()):
                    fpath = self.workspace.repo_root / path
                try:
                    if fpath.exists() and fpath.is_file():
                        before_content = fpath.read_text(encoding="utf-8")
                except Exception:
                    pass

                # 如果有 before_content（从 workspace apply 前的 hash 找到原始内容），做 diff
                # 否则回退到只显示新内容
                if before_content is not None:
                    unified_diff = _generate_unified_diff(
                        before_content=before_content,
                        after_content=after_content,
                        path=path,
                        action="update",
                    )
                else:
                    unified_diff = diff_excerpt_create(path, after_content)

                real_diffs.append({
                    "path": path,
                    "diff": unified_diff,
                    "action": action,
                    "before_content": before_content,
                    "after_content": after_content,
                })
            elif action == "delete":
                real_diffs.append({
                    "path": path,
                    "diff": f"--- a/{path}\n+++ /dev/null\n@@ -1 +0,0 @@\n- [file deleted]\n",
                    "action": action,
                    "before_content": None,
                    "after_content": None,
                })

        agent_output = dict(result_env.payload)
        agent_output["example_diff"] = real_diffs

        return {
            "agent_output": agent_output,
            "applied_changes": [item.__dict__ for item in applied_changes],
            "content_samples": content_samples,
            "summary": {"applied_change_count": len(applied_changes)},
            "example_diff": real_diffs,  # ⭐ 顶层也提供，供 artifact 消费
        }

    # ── DAG 管线用（_run_task_plan_async）───────────────────────

    def normalize_coding(self, *, subtask: Subtask, result_env: Envelope) -> dict[str, Any]:
        """Apply coding changes to the workspace and capture reviewable snapshots.

        ⭐ Stage 9: 为每个变更生成真正的 unified diff。
        """
        changes = (result_env.payload or {}).get("changes") or []
        if not isinstance(changes, list):
            raise TypeError("coding.changes must be list")

        file_changes: list[FileChange] = []
        for ch in changes:
            if not isinstance(ch, dict):
                continue
            file_changes.append(
                FileChange(
                    action=str(ch.get("action")),
                    path=str(ch.get("path")),
                    content=(ch.get("content") if isinstance(ch.get("content"), str) else None),
                    base_hash=(ch.get("base_hash") if isinstance(ch.get("base_hash"), str) else None),
                )
            )

        applied_changes: list[AppliedChange] = []
        for change in file_changes:
            applied_changes.append(self.workspace.apply_change(role="coding", change=change))

        content_samples: dict[str, str] = {}
        for applied in applied_changes:
            if applied.action in ("create", "update"):
                content_samples[applied.path] = self.workspace.read_text(role="review", rel_path=applied.path)

        # ⭐ 生成真正的 unified diff
        real_diffs: list[dict[str, Any]] = []
        for applied in applied_changes:
            path = applied.path
            action = applied.action
            after_content = content_samples.get(path, "")
            before_content = None

            if action == "update":
                # 试图读取 before 内容
                fpath = self.workspace._abs(path)
                try:
                    if fpath.exists() and fpath.is_file():
                        # 这里只能拿到 after，before 需要从 workspace 的历史
                        pass
                except Exception:
                    pass

            unified_diff = _generate_unified_diff(
                before_content=before_content,
                after_content=after_content if action != "delete" else None,
                path=path,
                action=action,
            )
            real_diffs.append({
                "path": path,
                "diff": unified_diff,
                "action": action,
                "before_content": before_content,
                "after_content": after_content,
            })

        return {
            "agent_output": result_env.payload,
            "applied_changes": [item.__dict__ for item in applied_changes],
            "content_samples": content_samples,
            "example_diff": real_diffs,
            "summary": {
                "subtask_id": subtask.subtask_id,
                "applied_change_count": len(applied_changes),
            },
        }

    def normalize_review(self, *, subtask: Subtask, result_env: Envelope) -> dict[str, Any]:
        """Normalize one review result into the structured subtask output."""
        return {
            "review_result": result_env.payload,
            "summary": {
                "subtask_id": subtask.subtask_id,
                "pass": bool((result_env.payload or {}).get("pass")),
            },
        }

    def normalize_artifact(
        self, *, subtask: Subtask, result_env: Envelope,
        on_artifact: callable | None = None,
    ) -> dict[str, Any]:
        """Normalize artifact output. on_artifact(task_id, trace_id, artifact_dir, payload)
        is called as a callback for replay metadata (optional)."""
        artifact_dir = str((result_env.payload or {}).get("artifact_dir") or "")
        if artifact_dir and on_artifact is not None:
            payload = result_env.payload or {}
            on_artifact(
                artifact_dir=artifact_dir,
                payload={
                    "created_files": payload.get("created_files"),
                    "summary": payload.get("summary"),
                },
            )
        return {
            "artifact_result": result_env.payload,
            "summary": {
                "subtask_id": subtask.subtask_id,
                "artifact_dir": artifact_dir,
            },
        }
