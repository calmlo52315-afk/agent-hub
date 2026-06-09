from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.agents.base import AgentContext
from runtime.llm.client import LLMClient

logger = logging.getLogger(__name__)

DOC_SYSTEM_PROMPT = """You are a professional technical writer. Your job is to generate
clear, accurate documentation for code that has been written.

Guidelines:
1. Write in clear, concise language suitable for developers
2. Include: overview, API reference, usage examples, and any caveats
3. Follow the project's existing documentation style if detectable
4. Use Markdown format — output MUST be valid .md content
5. Include code examples where helpful
6. Document public functions, classes, types, and their parameters
7. Note any edge cases, error conditions, or performance considerations
8. Output ONLY the documentation content, no meta-commentary
9. Use proper Markdown headings (##, ###), code fences, tables, and lists"""


def _build_doc_user_prompt(
    *,
    source_path: str,
    source_content: str,
    instruction: str,
    language: str | None,
    doc_type: str = "api",
) -> str:
    type_guides = {
        "api": "Generate API documentation in Markdown format: describe all public functions, classes, their parameters, return types, and usage examples. Output a complete .md document.",
        "readme": "Generate a README in Markdown format: project overview, setup instructions, usage examples, and architecture summary. Output a complete README.md document.",
        "inline": "Add comprehensive docstrings and inline comments to the code. Return the full file with comments added.",
    }
    guide = type_guides.get(doc_type, type_guides["api"])

    return f"""## Source File
Path: {source_path}
Language: {language or 'unknown'}

```{language or ''}
{source_content}
```

## Original Task
{instruction}

## Documentation Type
{doc_type}

## Request
{guide}

Output the complete documentation in Markdown format. Do NOT wrap the output in a top-level markdown code fence — output raw markdown directly."""


def _derive_doc_path(source_path: str, doc_type: str) -> str:
    """Derive a documentation file path from the source file path. Always outputs .md for doc types."""
    if doc_type == "readme":
        base_dir = source_path.rsplit("/", 1)[0] if "/" in source_path else "."
        return f"{base_dir}/README.md" if base_dir != "." else "README.md"
    if doc_type == "inline":
        return source_path  # inline docs modify the original file
    # api docs — always .md
    if "." in source_path:
        base = source_path.rsplit(".", 1)[0]
        return f"docs/{base}.md"
    return f"docs/{source_path}.md"


@dataclass(frozen=True)
class DocAgent:
    """Generate documentation for code produced in the coding stage.

    Uses LLM to generate API docs, READMEs, or inline docstrings,
    outputting changes that the Orchestrator can apply via the workspace.
    """

    agent_id: str = "documentation"
    role: str = "documentation"

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        logger.info(f"[DocAgent] Starting documentation task: {ctx.task_id}")

        task = payload.get("task") or {}
        instruction = task.get("instruction") or ""
        language = task.get("language")
        content_samples = payload.get("content_samples") or {}
        applied_changes = payload.get("applied_changes") or []
        doc_type = payload.get("doc_type") or "api"

        changes: list[dict[str, Any]] = []
        plan: list[str] = [
            "解析 coding 阶段产出的源代码文件",
            f"为每个源文件生成 {doc_type} 文档",
            "输出 changes 供 Orchestrator 写入工作区",
        ]

        # 收集源文件
        source_files: dict[str, str] = {}
        for path, content in (content_samples or {}).items():
            if isinstance(path, str) and isinstance(content, str):
                source_files[path] = content

        for ch in (applied_changes or []):
            if not isinstance(ch, dict):
                continue
            path = ch.get("path", "")
            if path and path not in source_files:
                source_files[path] = ch.get("content") or f"# TODO: read {path}"

        if not source_files:
            return {
                "agent": self.agent_id,
                "role": self.role,
                "plan": plan,
                "changes": [],
                "summary": "no source files to document",
            }

        for source_path, source_content in source_files.items():
            doc_path = _derive_doc_path(source_path, doc_type)

            try:
                llm = LLMClient.from_env()
                messages = [
                    {"role": "system", "content": DOC_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_doc_user_prompt(
                        source_path=source_path,
                        source_content=source_content,
                        instruction=instruction,
                        language=language,
                        doc_type=doc_type,
                    )},
                ]
                response = llm.chat(messages=messages, temperature=0.3, max_tokens=8192)
                doc_content = llm.extract_content(response).strip()

                # 清理 markdown 围栏
                if doc_content.startswith("```") and doc_content.endswith("```"):
                    lines = doc_content.split("\n")[1:-1]
                    doc_content = "\n".join(lines)
                elif doc_content.startswith("```"):
                    lines = doc_content.split("\n")[1:]
                    doc_content = "\n".join(lines)
                elif doc_content.endswith("```"):
                    lines = doc_content.split("\n")[:-1]
                    doc_content = "\n".join(lines)

                logger.info(f"[DocAgent] Generated doc for {source_path} → {doc_path} ({len(doc_content)} bytes)")
            except Exception as e:
                logger.error(f"[DocAgent] LLM failed for {source_path}: {e}")
                doc_content = (
                    f"# Documentation for {source_path}\n\n"
                    f"> Auto-generated placeholder\n\n"
                    f"## Overview\nTODO: document {source_path}\n\n"
                    f"## API Reference\nTODO: add API docs\n"
                )

            action = "update" if doc_type == "inline" else "create"
            changes.append({
                "action": action,
                "path": doc_path,
                "content": doc_content,
            })

        logger.info(f"[DocAgent] Documentation task completed, generated {len(changes)} doc files")
        return {
            "agent": self.agent_id,
            "role": self.role,
            "plan": plan,
            "changes": changes,
            "example_diff": [
                {"path": ch["path"], "diff": f"--- /dev/null\n+++ {ch['path']}\n@@\n+{(ch.get('content') or '')[:200]}"}
                for ch in changes
            ],
        }
