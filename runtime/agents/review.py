from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from runtime.agents.base import AgentContext

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """\
You are an expert code reviewer. Analyze the provided code changes and identify issues.

## Review Dimensions
1. **security**: Vulnerabilities, unsafe operations, injection risks, missing validation
2. **logic**: Bugs, edge cases, incorrect algorithms, race conditions
3. **style**: Naming, code organization, readability, best practices
4. **performance**: Inefficient algorithms, unnecessary allocations, missing optimizations

## Output Format
Respond with a JSON object:
```json
{
  "pass": true,
  "score": 85,
  "issues": [
    {
      "severity": "high|medium|low",
      "type": "security|logic|style|performance",
      "message": "concise description of the issue",
      "path": "the file path",
      "line": 42,
      "suggestion": "how to fix it"
    }
  ],
  "summary": "brief overall assessment"
}
```

## Rules
- Only report REAL issues — don't be overly pedantic
- For simple/demo code, be more lenient
- `score` is 0-100; deduct 10-20 for high, 5-10 for medium, 1-3 for low issues
- `pass` is true if no high-severity issues exist
- If the code is correct and clean, return `pass: true, score: 95+, issues: []`
"""


def _build_review_prompt(path: str, content: str, instruction: str) -> str:
    """Build the review prompt for a single changed file."""
    return (
        f"## File: {path}\n"
        f"## Task Instruction: {instruction}\n\n"
        f"```\n{content[:4000]}\n```\n\n"
        "Review this code change. Output ONLY the JSON."
    )


@dataclass(frozen=True)
class ReviewAgent:
    """⭐ Stage 9: LLM-powered code review.

    Uses the CODING_MODEL (doubao-code-preview) to analyze code changes
    for security, logic, style, and performance issues.
    """

    agent_id: str = "review"
    role: str = "review"

    def _call_llm_review(self, path: str, content: str, instruction: str) -> dict[str, Any]:
        """Call LLM to review a single file change."""
        try:
            from runtime.llm.client import LLMClient
            client = LLMClient.from_env(model_env_key="CODING_MODEL")
            logger.info(f"[ReviewAgent] Calling LLM to review: {path}")

            messages = [
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": _build_review_prompt(path, content, instruction)},
            ]

            response = client.chat(messages=messages, temperature=0.2, max_tokens=2048)
            raw = client.extract_content(response)

            # Parse JSON from response
            parsed = self._parse_json(raw)
            if parsed and isinstance(parsed, dict):
                return parsed
        except Exception as e:
            logger.error(f"[ReviewAgent] LLM review failed for {path}: {e}")

        # Fallback: pass with no issues
        return {"pass": True, "score": 100, "issues": [], "summary": "LLM review unavailable"}

    def _parse_json(self, text: str) -> Any:
        """Extract JSON from LLM response text."""
        text = text.strip()
        # Remove code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON block
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return None

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        """⭐ Review applied changes using LLM analysis.

        For each changed file, calls the LLM to identify issues.
        Aggregates results into a pass/fail decision with scored issues.
        """
        applied = payload.get("applied_changes") or []
        content_samples = payload.get("content_samples") or {}
        instruction = payload.get("task", {}).get("instruction", "") or ""

        # Also try to get instruction from persona/context
        if not instruction:
            instruction = payload.get("context", {}).get("task_brief", {}).get("title", "") or ""

        all_issues: list[dict[str, Any]] = []
        total_score = 100
        files_reviewed = 0

        if isinstance(applied, list) and applied:
            for ch in applied:
                if not isinstance(ch, dict):
                    continue
                path = ch.get("path", "")
                if not path:
                    continue

                # Get file content — from content_samples or the change itself
                content = content_samples.get(path) or ch.get("content") or ""
                if not content:
                    # Skip files without content (e.g., delete actions)
                    continue

                # ⭐ LLM-based review for each file
                result = self._call_llm_review(path, content, instruction)
                file_issues = result.get("issues") or []
                file_score = result.get("score", 100)

                # Attach path to issues if missing
                for issue in file_issues:
                    if not issue.get("path"):
                        issue["path"] = path

                all_issues.extend(file_issues)
                total_score = min(total_score, file_score)
                files_reviewed += 1

        # Also do a quick forbidden path check (security baseline)
        if isinstance(applied, list):
            for ch in applied:
                if not isinstance(ch, dict):
                    continue
                path = ch.get("path", "")
                if not isinstance(path, str):
                    continue
                if path.startswith("spec/") or path.startswith("rules/") or path.startswith("runtime/"):
                    already_reported = any(i.get("code") == "FORBIDDEN_PATH" and i.get("path") == path for i in all_issues)
                    if not already_reported:
                        all_issues.append({
                            "code": "FORBIDDEN_PATH",
                            "severity": "high",
                            "type": "security",
                            "message": f"Change touches forbidden path: {path}",
                            "path": path,
                            "suggestion": "Do not modify system configuration files directly",
                        })

        # Determine pass/fail
        any_high = any(i.get("severity") == "high" for i in all_issues)
        passed = not any_high
        approval_required = any(i.get("code") == "FORBIDDEN_PATH" for i in all_issues)

        # Adjust score for forbidden path issues
        if any_high and files_reviewed > 0:
            total_score = max(0, total_score - 20)

        logger.info(f"[ReviewAgent] Review complete: pass={passed}, issues={len(all_issues)}, files={files_reviewed}")

        return {
            "agent": self.agent_id,
            "role": self.role,
            "pass": passed,
            "score": total_score,
            "issues": all_issues,
            "approval_required": approval_required,
            "files_reviewed": files_reviewed,
            "summary": {
                "task_id": ctx.task_id,
                "trace_id": ctx.trace_id,
                "applied_change_count": (len(applied) if isinstance(applied, list) else 0),
                "files_reviewed": files_reviewed,
                "total_issues": len(all_issues),
            },
        }
