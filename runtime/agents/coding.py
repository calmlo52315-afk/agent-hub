from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.agents.base import AgentContext
from runtime.llm.client import LLMClient
from runtime.llm.prompts import CODING_SYSTEM_PROMPT, build_coding_user_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodingAgent:
    """Generate the smallest reviewable change set for a coding subtask.

    Uses LLM to generate real code instead of templates.
    """

    agent_id: str = "coding"
    role: str = "coding"

    def _render_content_with_llm(
        self,
        *,
        path: str,
        instruction: str,
        task_type: str,
        language: str | None,
        review_feedback: dict[str, Any],
        ctx: AgentContext,
    ) -> str:
        """Render code content using LLM."""
        try:
            llm = LLMClient.from_env(model_env_key="CODING_MODEL")
            logger.info(f"Calling LLM to generate code for: {path}")

            messages = [
                {"role": "system", "content": CODING_SYSTEM_PROMPT},
                {"role": "user", "content": build_coding_user_prompt(
                    path=path,
                    instruction=instruction,
                    language=language,
                    task_type=task_type
                )},
            ]

            response = llm.chat(messages=messages, temperature=0.3, max_tokens=8192)
            content = llm.extract_content(response)

            # Clean up any extra whitespace or markdown
            content = content.strip()

            # Remove any markdown code fences if present
            if content.startswith("```") and content.endswith("```"):
                lines = content.split("\n")[1:-1]
                content = "\n".join(lines)
            elif content.startswith("```"):
                lines = content.split("\n")[1:]
                content = "\n".join(lines)
            elif content.endswith("```"):
                lines = content.split("\n")[:-1]
                content = "\n".join(lines)

            logger.info(f"Successfully generated code for: {path} ({len(content)} bytes)")
            return content

        except Exception as e:
            logger.error(f"Failed to generate code via LLM: {e}")
            # Fallback to a simple template if LLM fails
            return self._render_fallback_template(path, instruction, language, ctx)

    def _render_fallback_template(
        self,
        path: str,
        instruction: str,
        language: str | None,
        ctx: AgentContext,
    ) -> str:
        """Simple fallback template if LLM fails."""
        comment = _comment_for(language)
        return (
            f"{comment} {instruction}\n"
            f"{comment} task_id: {ctx.task_id}\n\n"
            "# TODO: implement the logic described above\n"
        )

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        """Convert a task payload into a minimal patch proposal.

        Uses LLM to generate real code for each target file.
        """
        logger.info(f"[CodingAgent] Starting coding task: {ctx.task_id}")
        task = payload.get("task") or {}
        instruction = task.get("instruction") or ""
        targets = task.get("targets") or []
        task_type = str(task.get("task_type") or "generic")
        language = task.get("language")
        review_feedback = payload.get("review_feedback") or {}
        logger.info(f"[CodingAgent] Task details - instruction: {instruction[:100]}..., targets: {len(targets)}")

        changes: list[dict[str, Any]] = []
        plan: list[str] = []

        plan.append("解析任务目标与目标文件列表")
        plan.append("使用 LLM 为每个目标文件生成代码")
        plan.append("输出 changes（含 base_hash）供 Orchestrator 应用并做版本检查")

        if not isinstance(targets, list) or not targets:
            targets = [
                {
                    "path": "demo_workspace/hello.txt",
                    "action": "create",
                    "base_hash": None,
                }
            ]

        for t in targets:
            if not isinstance(t, dict):
                continue
            path = t.get("path")
            action = t.get("action")
            base_hash = t.get("base_hash")
            if not isinstance(path, str) or action not in ("create", "update"):
                continue

            content = self._render_content_with_llm(
                path=path,
                instruction=instruction,
                task_type=task_type,
                language=(language if isinstance(language, str) else None),
                review_feedback=(review_feedback if isinstance(review_feedback, dict) else {}),
                ctx=ctx,
            )

            changes.append(
                {
                    "action": action,
                    "path": path,
                    "base_hash": base_hash,
                    "content": content,
                }
            )

        logger.info(f"[CodingAgent] Coding task completed, generated {len(changes)} changes")
        
        return {
            "agent": self.agent_id,
            "role": self.role,
            "plan": plan,
            "changes": changes,
            "example_diff": [
                {
                    "path": (changes[0]["path"] if changes else "demo_workspace/hello.txt"),
                    "diff": _diff_snippet(changes[0]) if changes else "",
                }
            ],
        }


def _diff_snippet(change: dict[str, Any]) -> str:
    """从单个 change 生成真正的 unified diff（作为 CodingAgent 的默认 example_diff）。"""
    import difflib

    path = str(change.get("path", "")) if isinstance(change, dict) else ""
    content = str(change.get("content", "")) if isinstance(change, dict) else ""
    action = str(change.get("action", "create")) if isinstance(change, dict) else "create"

    lines = content.splitlines(keepends=True)
    if action == "create":
        diff_lines = list(difflib.unified_diff(
            [], lines,
            fromfile="/dev/null",
            tofile=f"b/{path}",
            lineterm="",
        ))
    elif action == "delete":
        diff_lines = list(difflib.unified_diff(
            lines, [],
            fromfile=f"a/{path}",
            tofile="/dev/null",
            lineterm="",
        ))
    else:
        diff_lines = list(difflib.unified_diff(
            [], lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        ))
    return "\n".join(diff_lines) if diff_lines else ""


def _comment_for(language: str | None) -> str:
    """根据语言返回对应的注释前缀。"""
    if language in ("python", "py", "ruby", "rb", "sh", "bash", "yaml", "yml"):
        return "#"
    if language in ("go", "c", "cpp", "c++", "java", "js", "ts", "tsx", "jsx", "rust", "rs", "swift"):
        return "//"
    if language in ("sql"):
        return "--"
    if language in ("lua"):
        return "--"
    return "#"
