from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.agents.base import AgentContext
from runtime.llm.client import LLMClient

logger = logging.getLogger(__name__)

TESTING_SYSTEM_PROMPT = """You are a professional test engineer. Your job is to generate
high-quality test cases for code that has been written.

Guidelines:
1. Cover happy path, edge cases, error handling, and boundary conditions
2. Prefer pytest (Python), Go testing (Go), Jest (JS/TS) depending on the language
3. Include both unit tests and integration tests where appropriate
4. Use descriptive test names that explain what is being tested
5. Include setup/teardown logic (fixtures) where needed
6. Output ONLY the test code, no explanations or markdown wrapping
7. Each test file should be self-contained and runnable"""


def _build_testing_user_prompt(
    *,
    source_path: str,
    source_content: str,
    instruction: str,
    language: str | None,
) -> str:
    return f"""## Source File
Path: {source_path}
Language: {language or 'unknown'}

```{language or ''}
{source_content}
```

## Original Task
{instruction}

## Request
Generate comprehensive tests for the source file above.
Include: unit tests, edge case tests, error handling tests, and integration tests where appropriate.

Output the complete test file content."""


def _comment_for(language: str | None) -> str:
    if language in ("python", "py", "ruby", "rb", "sh", "bash", "yaml", "yml"):
        return "#"
    if language in ("go", "c", "cpp", "c++", "java", "js", "ts", "tsx", "jsx", "rust", "rs", "swift"):
        return "//"
    if language in ("sql", "lua"):
        return "--"
    return "#"


def _test_suffix_for(language: str | None) -> str:
    """Return the conventional test file suffix for a language."""
    mapping = {
        "python": "_test.py", "py": "_test.py",
        "go": "_test.go",
        "java": "Test.java",
        "js": ".test.js", "ts": ".test.ts",
        "jsx": ".test.jsx", "tsx": ".test.tsx",
        "rust": "_test.rs", "rs": "_test.rs",
        "c": "_test.c", "cpp": "_test.cpp", "c++": "_test.cpp",
    }
    return mapping.get(language or "", "_test.py")


def _derive_test_path(source_path: str, language: str | None) -> str:
    """Derive a test file path from the source file path."""
    suffix = _test_suffix_for(language)
    # Insert _test before the extension
    if "." in source_path:
        base, ext = source_path.rsplit(".", 1)
        return f"{base}{suffix}"
    return f"{source_path}{suffix}"


@dataclass(frozen=True)
class TestAgent:
    """Generate test cases for code that was written in the coding stage.

    Uses LLM to generate real test code, outputting changes that the
    Orchestrator can apply via the workspace.
    """

    agent_id: str = "testing"
    role: str = "testing"

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        logger.info(f"[TestAgent] Starting testing task: {ctx.task_id}")

        task = payload.get("task") or {}
        instruction = task.get("instruction") or ""
        language = task.get("language")
        content_samples = payload.get("content_samples") or {}
        applied_changes = payload.get("applied_changes") or []

        changes: list[dict[str, Any]] = []
        plan: list[str] = [
            "解析 coding 阶段产出的源代码文件",
            "为每个源文件生成测试代码",
            "输出 changes 供 Orchestrator 写入工作区",
        ]

        # 从 content_samples 和 applied_changes 获取源文件
        source_files: dict[str, str] = {}
        for path, content in (content_samples or {}).items():
            if isinstance(path, str) and isinstance(content, str):
                source_files[path] = content

        # 也用 applied_changes 补全
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
                "summary": "no source files to test",
            }

        for source_path, source_content in source_files.items():
            test_path = _derive_test_path(source_path, language)

            try:
                llm = LLMClient.from_env()
                messages = [
                    {"role": "system", "content": TESTING_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_testing_user_prompt(
                        source_path=source_path,
                        source_content=source_content,
                        instruction=instruction,
                        language=language,
                    )},
                ]
                response = llm.chat(messages=messages, temperature=0.3, max_tokens=8192)
                test_content = llm.extract_content(response).strip()

                # 清理 markdown 围栏
                if test_content.startswith("```") and test_content.endswith("```"):
                    lines = test_content.split("\n")[1:-1]
                    test_content = "\n".join(lines)
                elif test_content.startswith("```"):
                    lines = test_content.split("\n")[1:]
                    test_content = "\n".join(lines)
                elif test_content.endswith("```"):
                    lines = test_content.split("\n")[:-1]
                    test_content = "\n".join(lines)

                logger.info(f"[TestAgent] Generated test for {source_path} → {test_path} ({len(test_content)} bytes)")
            except Exception as e:
                logger.error(f"[TestAgent] LLM failed for {source_path}: {e}")
                test_content = (
                    f"{_comment_for(language)} Auto-generated test placeholder\n"
                    f"{_comment_for(language)} source: {source_path}\n"
                    f"{_comment_for(language)} task_id: {ctx.task_id}\n\n"
                    f"# TODO: write tests for {source_path}\n"
                )

            changes.append({
                "action": "create",
                "path": test_path,
                "content": test_content,
            })

        logger.info(f"[TestAgent] Testing task completed, generated {len(changes)} test files")
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
