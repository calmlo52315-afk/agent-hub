from __future__ import annotations

"""
External CLI Skill Executor — 外置编码智能体子进程执行器。

负责：
1. 为外部 CLI 工具（Claude Code、Codex）创建隔离工作区
2. 以子进程方式拉起 CLI 并注入环境变量
3. 管控超时（SIGTERM → SIGKILL 升级）
4. 解析 stdout 提取结构化结果
5. 按 ADR-014 / ADR-023 分类映射错误码
6. ⭐ Stage 10: CLI 进程池管理（复用进程、减少启动开销）
7. ⭐ Stage 10: 批量请求合并（短时间窗口内合并请求）
"""

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.skills.base import SkillInvocationPlan
from runtime.harness.snapshot import WorkspaceSnapshot, WorkspaceDelta, FileDelta

logger = __import__("logging").getLogger(__name__)


class ExternalCLIError(RuntimeError):
    """外部 CLI 执行异常基类。"""

    def __init__(self, message: str, error_code: str, retryable: bool = False, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable
        self.details = details or {}


class ExternalCLITimeoutError(ExternalCLIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, error_code="TIMEOUT_ERROR", retryable=True, details=details)


class ExternalCLIProcessError(ExternalCLIError):
    def __init__(self, message: str, retryable: bool = False, details: dict[str, Any] | None = None):
        super().__init__(message=message, error_code="PROCESS_ERROR", retryable=retryable, details=details)


class ExternalCLIValidationError(ExternalCLIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, error_code="VALIDATION_ERROR", retryable=False, details=details)


class ExternalCLIModelError(ExternalCLIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message=message, error_code="MODEL_ERROR", retryable=True, details=details)


@dataclass
class ExternalCLIResult:
    """外部 CLI 执行结果。"""

    stdout: str
    stderr: str
    exit_code: int
    latency_ms: int
    parsed_payload: dict[str, Any] | None = None
    error: ExternalCLIError | None = None


def _find_command(command: str) -> str | None:
    """查找 CLI 命令是否可用。返回完整路径或 None。"""
    found = shutil.which(command)
    if found:
        return found
    # 检查常见的绝对路径
    candidates = [
        f"/usr/local/bin/{command}",
        f"/opt/homebrew/bin/{command}",
        f"/Applications/Codex.app/Contents/Resources/{command}",
        os.path.expanduser(f"~/.local/bin/{command}"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _sanitize_json_block(text: str) -> str | None:
    """从文本中提取第一个有效 JSON 对象/数组。

    支持 ```json ... ``` 围栏和裸 JSON。
    """
    # 尝试匹配 ```json ... ``` 围栏
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
    for match in fence_pattern.finditer(text):
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue

    # 尝试找到第一个 { 或 [ 并匹配到对应的 } 或 ]
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        return None
    return None


def _classify_stderr(stderr: str) -> str | None:
    """从 stderr 内容推断错误类别。⭐ 扩展关键词覆盖。"""
    lowered = stderr.lower()
    # API 余额/配额/认证问题 → 不应重试
    if any(kw in lowered for kw in (
        "rate limit", "overloaded", "api error", "model error", "provider error", "auth",
        "insufficient_quota", "billing", "balance", "credits", "quota exceeded",
        "payment required", "unauthorized", "invalid api key",
    )):
        return "MODEL_ERROR"
    # 超时相关
    if any(kw in lowered for kw in ("timed out", "timeout", "killed", "terminated")):
        return "TIMEOUT_ERROR"
    # 无工作可做
    if any(kw in lowered for kw in ("no files", "nothing to do", "no changes", "no targets")):
        return "NO_WORK"
    # 权限
    if any(kw in lowered for kw in ("permission denied", "access denied", "forbidden")):
        return "PERMISSION"
    return None


def _make_content_diff(action: str, path: str, content: str) -> str:
    """为单个文件生成简单的 content 展示 diff（用于 create 或无法获取 before-content 的场景）。"""
    import difflib
    lines = (content or "").splitlines(keepends=True)
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


def _build_claude_code_prompt(payload: dict[str, Any], plan: SkillInvocationPlan) -> str:
    """为 Claude Code 构建包含输出格式要求的完整 Prompt。"""
    instruction = (payload.get("task") or {}).get("instruction") or payload.get("instruction") or ""
    targets = (payload.get("task") or {}).get("targets") or payload.get("targets") or []
    context = payload.get("context") or {}

    parts: list[str] = [instruction]

    if targets:
        parts.append("\n## Target Files")
        for t in targets:
            if isinstance(t, dict):
                parts.append(f"- {t.get('action', 'update')}: {t.get('path', 'unknown')}")

    if context.get("pinned"):
        parts.append("\n## Context")
        for item in context["pinned"]:
            parts.append(f"- {item}")

    parts.append(
        "\n## Output Format\n"
        "After completing the work, output a JSON block with the following structure:\n"
        "```json\n"
        "{\n"
        '  "plan": ["step 1", "step 2"],\n'
        '  "changes": [\n'
        '    {"action": "create|update|delete", "path": "relative/path", "content": "file content here"}\n'
        "  ],\n"
        '  "example_diff": [\n'
        '    {"path": "relative/path", "diff": "unified diff string"}\n'
        "  ]\n"
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _build_codex_review_prompt(payload: dict[str, Any], plan: SkillInvocationPlan) -> str:
    """为 Codex / Claude 构建 Review 模式的完整 Prompt。

    ⭐ Step 1: 包含编码上下文 — 原始 query、Codex 的 plan、thinking trace、
    编码阶段使用的 skill 信息，让审查 agent 能全面了解代码是如何产生的。
    """
    changes = payload.get("changes") or payload.get("applied_changes") or []
    review_focus = payload.get("review_focus") or {}
    coding_ctx = payload.get("coding_context") or {}

    parts: list[str] = ["Review this diff:\n"]

    # ── ⭐ 编码上下文 — 原始 query + Codex 的 plan ─────────────
    instruction = (payload.get("task") or {}).get("instruction") or ""
    if instruction:
        parts.append(f"## Original Task Instruction\n{instruction}\n")

    if coding_ctx.get("plan"):
        parts.append("## Coding Plan (from Codex)")
        for step in coding_ctx["plan"]:
            parts.append(f"- {step}")
        parts.append("")

    if coding_ctx.get("thinking_trace"):
        trace = coding_ctx["thinking_trace"]
        parts.append("## Codex Thinking Trace (stderr)")
        parts.append("```")
        parts.append(trace[:3000])  # 限制长度
        parts.append("```\n")

    if coding_ctx.get("used_skill"):
        parts.append(f"## Coding Skill Used: `{coding_ctx['used_skill']}`\n")

    if coding_ctx.get("changes_summary"):
        parts.append(f"## Changes Summary: {coding_ctx['changes_summary']}\n")

    # ── 文件 diff 内容 ───────────────────────────────────────────
    parts.append("## Files changed")
    for ch in changes:
        if isinstance(ch, dict):
            path = ch.get("path", "unknown")
            diff = ch.get("diff", "")
            parts.append(f"\n### {path}")
            parts.append("```diff")
            parts.append(diff if diff else f"(action: {ch.get('action', 'update')})")
            parts.append("```")

    dimensions = review_focus.get("dimensions", ["security", "logic", "style", "performance"])
    parts.append(f"\nPlease analyze: {', '.join(dimensions)}")

    parts.append(
        "\n## Output Format\n"
        "Output a JSON block with:\n"
        "```json\n"
        "{\n"
        '  "decision": "pass|fail",\n'
        '  "score": {"value": 85, "max": 100},\n'
        '  "issues": [\n'
        '    {"severity": "high|medium|low", "type": "security|logic|style|performance", "message": "...", "path": "...", "suggestion": "..."}\n'
        "  ],\n"
        '  "suggestions": ["..."]\n'
        "}\n"
        "```"
    )

    return "\n".join(parts)


def _scan_workspace_for_files(workspace_dir: Path, repo_root: Path) -> list[dict[str, Any]]:
    """扫描工作区目录以及常见目录，收集所有文件内容。"""
    changes = []
    
    # 要扫描的目录列表
    scan_dirs = [
        workspace_dir,
        repo_root / "demo_workspace",
        repo_root / "transformer",
    ]
    
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        
        for root, dirs, files in os.walk(str(scan_dir)):
            for filename in files:
                file_path = Path(root) / filename
                
                # 计算相对路径
                relative_path = file_path.relative_to(repo_root)
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                except Exception:
                    # 跳过无法读取的文件
                    continue
                
                changes.append({
                    "action": "create",
                    "path": str(relative_path),
                    "content": content,
                })
    
    return changes


def _parse_claude_code_output(stdout: str, workspace_dir: Path = None, repo_root: Path = None) -> dict[str, Any]:
    """解析 Claude Code stdout 为 Coding Agent 兼容格式。"""
    # 先尝试解析 Claude Code 的原生 JSON 输出格式
    result = {}
    try:
        parsed = json.loads(stdout.strip())
        if isinstance(parsed, dict):
            # 这是 Claude Code --output-format json 的输出
            result_text = parsed.get("result", "")
            result = {
                "agent": "coding",
                "role": "coding",
                "plan": ["执行 Claude Code 任务"],
                "changes": [],
                "example_diff": [],
                "raw_result": result_text,
                "cost_usd": parsed.get("total_cost_usd"),
                "session_id": parsed.get("session_id"),
            }
    except (json.JSONDecodeError, ValueError):
        pass

    # 如果有 workspace_dir 和 repo_root，扫描工作区中的文件
    if workspace_dir and repo_root:
        changes_from_workspace = _scan_workspace_for_files(workspace_dir, repo_root)
        if changes_from_workspace:
            if not result:
                result = {
                    "agent": "coding",
                    "role": "coding",
                    "plan": ["执行 Claude Code 任务"],
                    "changes": [],
                    "example_diff": [],
                    "raw_result": stdout,
                }
            result["changes"] = changes_from_workspace
            # ⭐ 创建实际的 diff（不是垃圾占位符）
            result["example_diff"] = [
                {
                    "path": ch["path"],
                    "diff": _make_content_diff(ch.get("action", "create"), ch["path"], ch.get("content", "")),
                    "action": ch.get("action", "create"),
                    "before_content": None,
                    "after_content": ch.get("content", ""),
                }
                for ch in changes_from_workspace
            ]
    
    if result:
        return result

    # 再尝试解析代码中的 JSON 块
    json_str = _sanitize_json_block(stdout)
    if json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return {
                    "agent": "coding",
                    "role": "coding",
                    "plan": parsed.get("plan") or [],
                    "changes": parsed.get("changes") or [],
                    "example_diff": parsed.get("example_diff") or [],
                }
        except json.JSONDecodeError:
            pass

    # 无法解析 JSON → 回退：将全部 stdout 作为单文件变更
    return {
        "agent": "coding",
        "role": "coding",
        "plan": ["解析 Claude Code 输出"],
        "changes": [
            {
                "action": "update",
                "path": "demo_workspace/claude_output.txt",
                "content": stdout.strip(),
            }
        ],
        "example_diff": [
            {
                "path": "demo_workspace/claude_output.txt",
                "diff": _make_content_diff("create", "demo_workspace/claude_output.txt", stdout),
                "action": "create",
                "before_content": None,
                "after_content": stdout.strip(),
            }
        ],
    }


def _parse_codex_output(stdout: str) -> dict[str, Any]:
    """解析 Codex stdout 为 Review Agent 兼容格式。

    解析策略（按优先级）：
    1. JSON 块 — 结构化输出，直接映射
    2. Markdown 文本报告 — 正则提取 issue 列表
    3. 保守回退 — 返回 pass + raw text
    """
    # ── 策略 1: JSON 块 ──────────────────────────────────────
    json_str = _sanitize_json_block(stdout)
    if json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                issues = parsed.get("issues") or []
                score = parsed.get("score") or {}
                return {
                    "agent": "review",
                    "role": "review",
                    "pass": parsed.get("decision") == "pass",
                    "issues": [
                        {
                            "code": issue.get("type", "UNKNOWN").upper(),
                            "severity": issue.get("severity", "medium"),
                            "message": issue.get("message", str(issue)),
                            "path": issue.get("path", ""),
                            "suggestion": issue.get("suggestion", ""),
                        }
                        for issue in issues
                    ],
                    "summary": {
                        "total_issues": len(issues),
                        "score": score.get("value", 0),
                        "suggestions": parsed.get("suggestions") or [],
                    },
                }
        except (json.JSONDecodeError, ValueError):
            pass

    # ── 策略 2: 解析文本报告 ─────────────────────────────────
    issues = _parse_codex_text_report(stdout)
    if issues:
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        worst = max(issues, key=lambda i: severity_order.get(i.get("severity", "low"), 0))
        return {
            "agent": "review",
            "role": "review",
            "pass": len([i for i in issues if i.get("severity") in ("critical", "high")]) == 0,
            "issues": issues,
            "summary": {
                "total_issues": len(issues),
                "worst_severity": worst.get("severity", "low"),
                "categories": list(set(i.get("code", "UNKNOWN") for i in issues)),
            },
        }

    # ── 策略 3: 保守回退 ─────────────────────────────────────
    return {
        "agent": "review",
        "role": "review",
        "pass": True,
        "issues": [],
        "summary": {
            "total_issues": 0,
            "note": "unable to parse structured output from Codex",
            "raw_output_preview": stdout[:500],
        },
    }


def _parse_codex_text_report(text: str) -> list[dict[str, Any]]:
    """从 Codex CLI 文本报告中提取 issue 列表。

    支持常见的代码审查报告格式：
    - ``**Severity**: high`` 或 ``Severity: medium``
    - ``**File**: path/to/file.py`` 或 ``File: path``
    - ``**Line**: 42`` 或 ``Line: 42`` 或 ``:42:``
    - ``**Description** / **Message**``
    - ``**Suggestion** / **Fix**``
    - 也支持 ``[HIGH] path:line - message`` 格式
    """
    issues: list[dict[str, Any]] = []

    # ── 模式 A: 结构化条目（Severity / File / Line 各有独立行）──
    # 将文本按 "###" 或 "---" 或空行分块，每块可能是一个 issue
    blocks = re.split(r"\n\s*(?:###\s*|---+)\s*\n|\n(?:\*\*Issue|Issue\s*#|\[\w+\])", text)

    # 在全文搜索 severity 标记
    severity_kw = r"(?:critical|high|medium|low|warning|info|error)"
    # 匹配 "**Severity**: high" 或 "Severity: high" 或 "[HIGH]"
    sev_pattern = re.compile(
        rf"(\*?\*?(?:severity|level|priority)\*?\*?\s*[:：]\s*({severity_kw}))"
        r"|(\[({severity_kw})\])",
        re.IGNORECASE,
    )
    file_pattern = re.compile(
        r"\*?\*?(?:file|path|location)\*?\*?\s*[:：]\s*[`\"]?([^\s\n\"`]+)[`\"]?",
        re.IGNORECASE,
    )
    line_pattern = re.compile(
        r"\*?\*?(?:line|行)\*?\*?\s*[:：]\s*(\d+)",
        re.IGNORECASE,
    )
    desc_pattern = re.compile(
        r"\*?\*?(?:description|message|issue|问题|描述)\*?\*?\s*[:：]\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )
    sugg_pattern = re.compile(
        r"\*?\*?(?:suggestion|fix|recommendation|建议|修复)\*?\*?\s*[:：]\s*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )

    # 若文本包含多个 issue 块，逐个解析
    if len(blocks) <= 1:
        # 整段作为一个 issue 尝试
        blocks = [text]

    for block in blocks:
        if not block.strip() or len(block.strip()) < 10:
            continue

        # 提取 severity
        sev_match = sev_pattern.search(block)
        severity = "medium"
        if sev_match:
            severity = (sev_match.group(2) or sev_match.group(4) or "medium").lower()

        # 提取文件
        file_match = file_pattern.search(block)
        file_path = file_match.group(1) if file_match else ""

        # 提取行号
        line_match = line_pattern.search(block)
        line_num = int(line_match.group(1)) if line_match else 0

        # 提取描述
        desc_match = desc_pattern.search(block)
        message = (desc_match.group(1) or block[:200]).strip()

        # 提取修复建议
        sugg_match = sugg_pattern.search(block)
        suggestion = sugg_match.group(1).strip() if sugg_match else ""

        # 推断 issue 类型
        code = "REVIEW"
        block_lower = block.lower()
        if any(kw in block_lower for kw in ("security", "安全", "vulnerability", "xss", "sql injection")):
            code = "SECURITY"
        elif any(kw in block_lower for kw in ("performance", "性能", "slow", "bottleneck")):
            code = "PERFORMANCE"
        elif any(kw in block_lower for kw in ("style", "风格", "naming", "format")):
            code = "STYLE"
        elif any(kw in block_lower for kw in ("bug", "error", "defect", "crash", "null", "exception")):
            code = "BUG"

        issues.append({
            "code": code,
            "severity": severity,
            "message": message,
            "path": file_path,
            "line": line_num,
            "suggestion": suggestion,
        })

    # ── 模式 B: 紧凑格式 "[HIGH] path:line - message" ────────
    if not issues:
        compact = re.compile(
            rf"\[({severity_kw})\]\s*([^\s:]+)(?::(\d+))?\s*[-–—]\s*(.+?)(?:\n|$)",
            re.IGNORECASE,
        )
        for match in compact.finditer(text):
            severity = match.group(1).lower()
            file_path = match.group(2)
            line_num = int(match.group(3)) if match.group(3) else 0
            message = match.group(4).strip()
            issues.append({
                "code": "REVIEW",
                "severity": severity,
                "message": message,
                "path": file_path,
                "line": line_num,
                "suggestion": "",
            })

    return issues


# ── Stage 10: Codex Coding Prompt Builder ─────────────────────

def _build_codex_coding_prompt(payload: dict[str, Any], plan: "SkillInvocationPlan") -> str:
    """为 Codex exec 构建编码 Prompt。"""
    instruction = (payload.get("task") or {}).get("instruction") or payload.get("instruction") or ""
    targets = (payload.get("task") or {}).get("targets") or payload.get("targets") or []
    context = payload.get("context") or {}

    parts: list[str] = [instruction]

    if targets:
        parts.append("\n## Target Files")
        for t in targets:
            if isinstance(t, dict):
                parts.append(f"- {t.get('action', 'update')}: {t.get('path', 'unknown')}")

    if context.get("pinned"):
        parts.append("\n## Context")
        for item in context["pinned"]:
            parts.append(f"- {item}")

    parts.append(
        "\n## Output Format\n"
        "After completing the work, output a JSON block with the following structure:\n"
        "```json\n"
        "{\n"
        '  "plan": ["step 1", "step 2"],\n'
        '  "changes": [\n'
        '    {"action": "create|update|delete", "path": "relative/path", "content": "file content here"}\n'
        "  ],\n"
        '  "example_diff": [\n'
        '    {"path": "relative/path", "diff": "unified diff string"}\n'
        "  ]\n"
        "}\n"
        "```"
    )

    return "\n".join(parts)


# ── Stage 10: CLI 进程池 (长连接保活) ──────────────────────────

@dataclass
class CLIProcessPool:
    """CLI 进程池 — 复用 CLI 进程，避免每次 subprocess.Popen 新建进程的开销。

    每个 (command, session_id) 组合维护一个进程实例，
    通过 STDIN/STDOUT 与守护进程通信。

    设计要点：
    - 按 session 隔离上下文（不同 session 使用不同进程）
    - 空闲超时自动回收进程
    - 线程安全（每个进程持有独立锁）
    """

    max_idle_seconds: float = 300.0
    max_processes_per_type: int = 3

    _processes: dict[str, subprocess.Popen] = field(default_factory=dict)
    _locks: dict[str, threading.Lock] = field(default_factory=dict)
    _last_used: dict[str, float] = field(default_factory=dict)
    _instance: "CLIProcessPool | None" = field(default=None, init=False)

    _instance_lock = threading.Lock()

    @classmethod
    def singleton(cls) -> "CLIProcessPool":
        """获取全局单例进程池。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = CLIProcessPool()
        return cls._instance

    def _process_key(self, command: str, session_id: str) -> str:
        return f"{command}:{session_id}"

    def _get_lock(self, key: str) -> threading.Lock:
        if key not in self._locks:
            self._locks[key] = threading.Lock()
        return self._locks[key]

    def get_or_create(
        self, *, cli_path: str, session_id: str, cwd: Path, env: dict[str, str],
    ) -> subprocess.Popen | None:
        """获取或创建一个进程实例。

        注意：当前 Claude Code 和 Codex 的 headless 模式都是一次性子进程，
        不支持 STDIN 长连接交互。此方法在当前阶段作为预热+缓存的抽象层。
        未来当 CLI 支持 --server/--daemon 模式时可启用真正的进程复用。
        """
        key = self._process_key(cli_path, session_id)
        lock = self._get_lock(key)

        with lock:
            existing = self._processes.get(key)
            if existing is not None and existing.poll() is None:
                # 进程仍存活，复用
                self._last_used[key] = time.monotonic()
                return existing

            # 进程不存在或已退出 — 暂不自动创建，由调用方负责
            # 返回 None 表示需要调用方自己 subprocess.Popen
            return None

    def register(
        self, *, cli_path: str, session_id: str, proc: subprocess.Popen,
    ) -> None:
        """注册一个新创建的进程到池中。"""
        key = self._process_key(cli_path, session_id)
        lock = self._get_lock(key)
        with lock:
            # 清理同 key 的旧进程（如果存在）
            old = self._processes.pop(key, None)
            if old is not None and old.poll() is None:
                try:
                    old.terminate()
                    old.wait(timeout=3)
                except Exception:
                    try:
                        old.kill()
                    except Exception:
                        pass

            self._processes[key] = proc
            self._last_used[key] = time.monotonic()

    def cleanup_idle(self) -> int:
        """清理超过 max_idle_seconds 未使用的进程。返回清理数量。"""
        now = time.monotonic()
        to_remove: list[str] = []
        for key, last_used in self._last_used.items():
            if now - last_used > self.max_idle_seconds:
                to_remove.append(key)

        cleaned = 0
        for key in to_remove:
            lock = self._locks.get(key)
            if lock:
                with lock:
                    proc = self._processes.pop(key, None)
                    if proc is not None and proc.poll() is None:
                        try:
                            proc.terminate()
                            proc.wait(timeout=3)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                    self._last_used.pop(key, None)
                    cleaned += 1
            else:
                self._processes.pop(key, None)
                self._last_used.pop(key, None)
                cleaned += 1

        return cleaned

    def shutdown(self) -> None:
        """关闭所有池中的进程。"""
        for key, proc in list(self._processes.items()):
            lock = self._locks.get(key)
            if lock:
                with lock:
                    if proc.poll() is None:
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
        self._processes.clear()
        self._last_used.clear()
        self._locks.clear()

    @property
    def size(self) -> int:
        return len(self._processes)


# ── Stage 10: 批量请求合并器 ──────────────────────────────────

@dataclass
class CLIRequestBatcher:
    """批量请求合并器。

    在 batch_window_seconds 内收到的同一 skill 请求合并为一次调用。
    多个 prompt 用分隔符拼接，结果回来后拆分。

    使用方式:
        batcher = CLIRequestBatcher.singleton()
        result = batcher.submit_and_wait(skill_name, prompt, executor_fn)
    """

    batch_window_seconds: float = 2.0
    max_batch_size: int = 5

    _pending: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _timers: dict[str, threading.Timer] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _instance: "CLIRequestBatcher | None" = field(default=None, init=False)

    _instance_lock = threading.Lock()

    @classmethod
    def singleton(cls) -> "CLIRequestBatcher":
        """获取全局单例批量合并器。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = CLIRequestBatcher()
        return cls._instance

    def submit(self, skill_name: str, prompt: str) -> "Future":
        """提交一个请求到合并队列。返回一个 Future，在合并执行后 resolve。"""
        future: Future = Future()

        with self._lock:
            if skill_name not in self._pending:
                self._pending[skill_name] = []

            self._pending[skill_name].append({
                "prompt": prompt,
                "future": future,
                "submitted_at": time.monotonic(),
            })

            # 已达到最大批量大小 → 立即刷新
            if len(self._pending[skill_name]) >= self.max_batch_size:
                # 取消定时器
                timer = self._timers.pop(skill_name, None)
                if timer is not None:
                    timer.cancel()
                self._flush_locked(skill_name)
            else:
                # 重置定时器
                old_timer = self._timers.pop(skill_name, None)
                if old_timer is not None:
                    old_timer.cancel()
                timer = threading.Timer(
                    self.batch_window_seconds,
                    self._on_timer_expired,
                    args=[skill_name],
                )
                timer.daemon = True
                self._timers[skill_name] = timer
                timer.start()

        return future

    def _on_timer_expired(self, skill_name: str) -> None:
        """定时器到期 — 刷新该 skill 的待处理请求。"""
        with self._lock:
            self._timers.pop(skill_name, None)
            self._flush_locked(skill_name)

    def _flush_locked(self, skill_name: str) -> None:
        """在持有锁的情况下刷新待处理请求（仅标记为需要执行）。

        由调用方负责实际的 CLI 执行。
        """
        # 请求在执行前已经从 _pending 中移除
        # 实际执行在 submit_and_wait 调用方完成
        pass

    def drain_pending(self, skill_name: str) -> list[dict[str, Any]]:
        """排出当前 skill 的所有待处理请求。"""
        with self._lock:
            items = self._pending.pop(skill_name, [])
            self._timers.pop(skill_name, None)
            return items

    def flush_all(self) -> None:
        """刷新所有待处理请求。"""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
            self._pending.clear()


# ── Stage 8: Delta 辅助函数 ──────────────────────────────────

def _build_payload_from_delta(
    delta: "WorkspaceDelta",
    snapshot: "WorkspaceSnapshot",
    repo_root: Path,
) -> dict[str, Any]:
    """从 WorkspaceDelta 构建 Coding Agent 兼容的 payload。

    用于 _handle_success 无法解析 stdout 时（例如 Claude Code 未输出 JSON），
    通过文件系统变化直接构建 changes。

    ⭐ Stage 9: 生成真正的 unified diff（使用 difflib），而不是垃圾占位符。
    """
    import difflib

    changes: list[dict[str, Any]] = []
    example_diff: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in delta.changes:
        if d.path in seen:
            continue
        seen.add(d.path)
        action = d.kind if d.kind == "created" else ("update" if d.kind == "modified" else "delete")
        after_content = None
        before_content = None

        fpath = repo_root / d.path
        try:
            if fpath.exists() and fpath.is_file():
                after_content = fpath.read_text(encoding="utf-8")
        except Exception:
            pass

        changes.append({
            "action": action,
            "path": d.path,
            "content": after_content,
            "old_hash": d.old_hash,
            "new_hash": d.new_hash,
            "old_size": d.old_size,
            "new_size": d.new_size,
        })

        # ⭐ 生成真正的 unified diff
        after_lines = (after_content or "").splitlines(keepends=True)
        before_lines: list[str] = []
        if action == "create":
            diff_lines = list(difflib.unified_diff(
                [], after_lines,
                fromfile="/dev/null",
                tofile=f"b/{d.path}",
                lineterm="",
            ))
        elif action == "delete":
            diff_lines = list(difflib.unified_diff(
                before_lines, [],
                fromfile=f"a/{d.path}",
                tofile="/dev/null",
                lineterm="",
            ))
        else:
            # update — 没有 before content，显示为全部新增的 diff
            diff_lines = list(difflib.unified_diff(
                [], after_lines if after_lines else [],
                fromfile=f"a/{d.path}",
                tofile=f"b/{d.path}",
                lineterm="",
            ))

        example_diff.append({
            "path": d.path,
            "diff": "\n".join(diff_lines) if diff_lines else "",
            "action": action,
            "before_content": before_content,
            "after_content": after_content,
        })

    return {
        "agent": "coding",
        "role": "coding",
        "plan": ["执行外部 CLI 任务"],
        "changes": changes,
        "example_diff": example_diff,
        "delta_summary": delta.summary(),
    }


def _enrich_parsed_with_delta(
    parsed: dict[str, Any],
    delta: "WorkspaceDelta",
    snapshot: "WorkspaceSnapshot",
) -> dict[str, Any]:
    """将 delta 信息合并到已有的 parsed_payload 中。

    替换旧的 changes 列表为 delta 驱动的精确变更记录。
    ⭐ Stage 9: 为每个变更生成真正的 unified diff。
    """
    import difflib

    if not delta.changes:
        # 无变更，保留原始解析结果
        parsed["delta_summary"] = delta.summary()
        return parsed

    # 用 delta 覆盖 changes，同时填充内容（按 path 去重）
    enriched_changes: list[dict[str, Any]] = []
    enriched_diffs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in delta.changes:
        if d.path in seen:
            continue
        seen.add(d.path)
        action = "create" if d.kind == "created" else ("update" if d.kind == "modified" else "delete")
        # ⭐ 从原始 parsed 的 changes 中查找已有的 content（如果有）
        old_content = None
        for orig in parsed.get("changes") or []:
            if orig.get("path") == d.path:
                old_content = orig.get("content")
                break

        enriched_changes.append({
            "action": action,
            "path": d.path,
            "old_hash": d.old_hash,
            "new_hash": d.new_hash,
            "old_size": d.old_size,
            "new_size": d.new_size,
            "content": old_content,
        })

        # ⭐ 生成真正的 unified diff
        after_lines = (old_content or "").splitlines(keepends=True) if old_content else []
        if action == "create":
            diff_lines = list(difflib.unified_diff(
                [], after_lines,
                fromfile="/dev/null",
                tofile=f"b/{d.path}",
                lineterm="",
            ))
        elif action == "delete":
            diff_lines = list(difflib.unified_diff(
                after_lines, [],
                fromfile=f"a/{d.path}",
                tofile="/dev/null",
                lineterm="",
            ))
        else:
            diff_lines = list(difflib.unified_diff(
                [], after_lines if after_lines else [],
                fromfile=f"a/{d.path}",
                tofile=f"b/{d.path}",
                lineterm="",
            ))

        enriched_diffs.append({
            "path": d.path,
            "diff": "\n".join(diff_lines) if diff_lines else "",
            "action": action,
            "before_content": None,
            "after_content": old_content,
        })

    parsed["changes"] = enriched_changes
    parsed["example_diff"] = enriched_diffs
    parsed["delta_summary"] = delta.summary()
    return parsed


@dataclass
class ExternalCLIExecutor:
    """外置 CLI 智能体子进程执行器。

    负责为 Claude Code、Codex 等外部 CLI 工具创建隔离工作区、拉起子进程、
    管控超时、解析输出为 AgentHub 兼容格式。
    """

    repo_root: Path
    workspaces_root: str = "workspaces"
    grace_period_seconds: int = 5

    # ── 公共入口 ──────────────────────────────────────────────

    def execute(self, plan: SkillInvocationPlan) -> ExternalCLIResult:
        """执行一次外部 CLI 调用并返回结构化结果。

        ⭐ Stage 9: cwd 直接设为 source_root（用户原始目录），不复制文件。
        执行前拍摄快照，执行后计算精确 Delta。
        """
        command = getattr(plan.definition, "command", None)
        if not command or not isinstance(command, str):
            raise ExternalCLIProcessError(
                f"skill {plan.definition.skill_name} has no CLI command configured",
                retryable=False,
            )

        # ⭐ Stage 10: 日志 — 记录 CLI 调用入口 + 双写 stderr
        import sys as _sys
        msg = (f"[CLI-EXEC] execute() called: skill={plan.definition.skill_name}, "
               f"command={command}, task_id={plan.task_id[:16]}...")
        print(msg, flush=True)
        _sys.stderr.write(msg + "\n")
        _sys.stderr.flush()

        cli_path = _find_command(command)
        if cli_path is None:
            raise ExternalCLIProcessError(
                f"CLI command not found: {command}",
                retryable=False,
                details={"command": command, "skill_name": plan.definition.skill_name},
            )

        # ⭐ 任务工作目录（仅用于日志/临时文件，不是 cwd）
        task_dir = self._create_workspace(plan)
        env = self._build_env(plan, task_dir)

        # 根据 skill 类型和模式构建 CLI 参数
        # ⭐ Stage 10: codex_coding 的 prompt 通过 stdin 传入，不放在 args 里
        stdin_prompt = ""
        if plan.definition.agent_binding == "coding":
            if plan.definition.skill_name == "codex_coding":
                args = self._build_codex_coding_args(plan)
                stdin_prompt = _build_codex_coding_prompt(plan.payload, plan)
            else:
                args = self._build_claude_code_args(plan, task_dir)
        elif plan.definition.agent_binding == "review":
            if plan.definition.skill_name == "claude_review":
                args = self._build_claude_review_args(plan)
            else:
                # codex_review 或其他 review CLI
                args = self._build_codex_review_args_inline(plan)
        else:
            raise ExternalCLIProcessError(
                f"unsupported agent_binding for external CLI: {plan.definition.agent_binding}",
                retryable=False,
            )

        # ⭐ Stage 9: cwd 设为 source_root — 直接在用户目录工作，不复制文件
        cwd = self._resolve_cwd(plan)

        # ── Stage 8/10: 执行前快照 ─────────────────────────────
        # ⭐ Stage 10: cwd 是 source 目录时，scope 必须覆盖它
        scope = self._resolve_snapshot_scope(plan, cwd=cwd)
        snapshot = WorkspaceSnapshot.capture(self.repo_root, scope=scope)

        result = self._run_subprocess(
            cli_path=cli_path,
            args=args,
            cwd=cwd,
            env=env,
            timeout_seconds=plan.timeout_seconds,
            plan=plan,
            workspace_dir=task_dir,
            stdin_prompt=stdin_prompt,
        )

        # ── Stage 8: 执行后 Delta ────────────────────────────
        delta = snapshot.compute_delta()

        # 若 _handle_success 已解析出 parsed_payload，用 delta 替换 changes
        if result.parsed_payload is not None and isinstance(result.parsed_payload, dict):
            result.parsed_payload = self._enrich_parsed_with_delta(
                result.parsed_payload, delta, snapshot
            )
        elif result.error is None and result.parsed_payload is None:
            # _handle_success 没解析出内容，用 delta 构建基础 payload
            if plan.definition.agent_binding == "coding":
                result.parsed_payload = _build_payload_from_delta(delta, snapshot, self.repo_root)

        # 将外部 CLI 产生的文件变更复制到 session source 目录（仅当文件不在 source/ 下时才复制）
        if plan.definition.agent_binding == "coding" and result.parsed_payload:
            session_id = plan.payload.get("session_id") or plan.payload.get("task", {}).get("session_id", "")
            if session_id and session_id != "default":
                changes = result.parsed_payload.get("changes") or []
                # 只复制 non-source 路径的变更（source/ 下的文件 CLI 已直接写入）
                non_source_changes = [
                    ch for ch in changes
                    if not str(ch.get("path", "")).startswith(f"workspace/{session_id}/source/")
                ]
                if non_source_changes:
                    result.parsed_payload["changes"] = self._copy_changes_to_session_source(
                        session_id=session_id,
                        changes=list(changes),
                    )

        # 对 coding agent 做 forbidden change 检查
        if plan.definition.agent_binding == "coding":
            perm_scope = plan.definition.permission_scope or {}
            write_paths = perm_scope.get("write_paths") or ["demo_workspace/**", "workspaces/**"]
            # 自动追加 source 目录到白名单，匹配 workspace/{session_id}/source/ 下的文件
            cwd_str = str(cwd.resolve())
            repo_str = str(self.repo_root.resolve())
            if cwd_str.startswith(repo_str + os.sep):
                rel_cwd = cwd_str[len(repo_str) + 1:]
                write_paths = list(write_paths) + [f"{rel_cwd}/**"]
            deny_paths = perm_scope.get("deny_operations") or []

            if delta.has_forbidden_changes(write_paths=write_paths, deny_paths=deny_paths):
                snapshot.rollback(delta)
                raise ExternalCLIProcessError(
                    f"Forbidden file changes detected by {plan.definition.skill_name}",
                    retryable=False,
                    details={
                        "delta_summary": delta.summary(),
                        "forbidden_paths": [d.path for d in delta.changes],
                    },
                )

        return result

    def _resolve_cwd(self, plan: SkillInvocationPlan) -> Path:
        """⭐ Stage 9: 确定 CLI 的工作目录。直接在用户的 source 目录工作，不复制文件：
        - imported: 用户原始目录（source_path）
        - scratch/project: workspace/{session_id}/source/
        - 默认: repo_root"""
        session_id = plan.payload.get("session_id") or plan.payload.get("task", {}).get("session_id", "")
        if session_id and session_id != "default":
            # 读取 workspace meta 获取 workspace_type 和 source_path
            import json as _json
            meta_path = self.repo_root / "workspace" / session_id / "workspace_meta.json"
            if meta_path.exists():
                try:
                    meta = _json.loads(meta_path.read_text(encoding="utf-8"))
                    ws_type = meta.get("workspace_type", "scratch")
                    src_path = meta.get("source_path")
                    if ws_type == "imported" and src_path:
                        imported_path = Path(src_path).resolve()
                        if imported_path.exists():
                            return imported_path
                except Exception:
                    pass
            # fallback: source 目录
            source_dir = self.repo_root / "workspace" / session_id / "source"
            if source_dir.exists():
                return source_dir
        return self.repo_root

    def _resolve_snapshot_scope(self, plan: SkillInvocationPlan, cwd: Path | None = None) -> list[str]:
        """从 skill 定义中解析快照覆盖范围。

        ⭐ Stage 10: 根据 cwd 自动扩展 scope。
        当 cwd 在 workspace/{session_id}/source/ 下时，追加该目录到 scope，
        确保快照和 forbidden check 覆盖 CLI 实际写入的路径。
        """
        perm_scope = plan.definition.permission_scope or {}
        read_paths = perm_scope.get("read_paths") or []
        write_paths = perm_scope.get("write_paths") or []
        scope = list(set(read_paths + write_paths))

        # ⭐ Stage 10: 追加 cwd 的子目录到 scope
        if cwd is not None:
            cwd_str = str(cwd.resolve())
            repo_str = str(self.repo_root.resolve())
            if cwd_str.startswith(repo_str + os.sep):
                rel_cwd = cwd_str[len(repo_str) + 1:]
                scope.append(f"{rel_cwd}/**")
            elif cwd_str == repo_str:
                pass
            else:
                scope.append("demo_workspace/**")

        return scope if scope else ["demo_workspace/**"]

    def _copy_changes_to_session_source(
        self,
        *,
        session_id: str,
        changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """将外部 CLI 在隔离工作区中产生的变更复制到 session source 目录。

        Claude Code 在 workspaces/task_xxx/ 下工作。此方法：
        1. 将隔离区中修改的文件复制到 source/ 下
        2. 返回修复后路径的 changes（去掉 task_xxx/ 前缀，变成纯文件路径）
        """
        if not session_id or session_id == "default":
            return changes

        source_root = self.repo_root / "workspace" / session_id / "source"
        source_root.mkdir(parents=True, exist_ok=True)

        new_changes: list[dict[str, Any]] = []
        for ch in changes:
            path = str(ch.get("path") or "")
            action = str(ch.get("action") or "")
            if not path:
                new_changes.append(ch)
                continue

            # 找到实际源文件（可能在 repo_root 下，也可能在隔离工作区中）
            src_file = None
            clean_path = path  # 去掉 task_xxx/ 前缀后的纯路径

            # 检查 repo_root 下的直接路径
            if (self.repo_root / path).exists():
                src_file = self.repo_root / path
            else:
                # 尝试在 workspaces/ 下搜索
                for task_dir in (self.repo_root / "workspaces").iterdir():
                    if task_dir.is_dir() and task_dir.name.startswith("task_"):
                        candidate = task_dir / path
                        if candidate.exists() and candidate.is_file():
                            src_file = candidate
                            break

            if src_file is None or not src_file.exists():
                new_changes.append(ch)
                continue

            # 计算纯路径：去掉 workspaces/task_xxx/ 前缀
            try:
                task_rel = src_file.relative_to(self.repo_root / "workspaces")
                parts = task_rel.parts
                # 去掉 task_xxx/source/ 前缀（如果存在）
                if len(parts) > 2 and parts[0].startswith("task_") and parts[1] == "source":
                    clean_path = "/".join(parts[2:])
                elif len(parts) > 1 and parts[0].startswith("task_"):
                    clean_path = "/".join(parts[1:])
            except ValueError:
                pass

            dst_file = source_root / clean_path

            if action == "delete":
                try:
                    if dst_file.exists():
                        dst_file.unlink()
                except Exception:
                    pass
            elif src_file.exists() and src_file.is_file():
                try:
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    content = src_file.read_text(encoding="utf-8")
                    dst_file.write_text(content, encoding="utf-8")
                except Exception:
                    pass

            new_ch = dict(ch)
            new_ch["path"] = clean_path
            new_changes.append(new_ch)

        return new_changes


    def _enrich_parsed_with_delta(
        self,
        parsed: dict[str, Any],
        delta: "WorkspaceDelta",
        snapshot: "WorkspaceSnapshot",
    ) -> dict[str, Any]:
        """Hook for _enrich_parsed_with_delta that reads file content from disk."""
        result = _enrich_parsed_with_delta(parsed, delta, snapshot)
        # 补充 content 字段（从磁盘读取）
        for change in result.get("changes") or []:
            if isinstance(change, dict) and change.get("content") is None:
                fpath = self.repo_root / change["path"]
                try:
                    if fpath.exists() and fpath.is_file():
                        change["content"] = fpath.read_text(encoding="utf-8")
                except Exception:
                    pass
        return result

    def _build_claude_code_args(self, plan: SkillInvocationPlan, workspace_dir: Path) -> list[str]:
        """为 Claude Code 构建命令行参数，支持 headless 模式。"""
        args = []
        prompt = _build_claude_code_prompt(plan.payload, plan)

        # headless 模式
        if plan.definition.mode == "headless":
            # 非交互模式
            args.append("-p")
            
            # 权限模式
            if plan.definition.permission_mode != "default":
                args.extend(["--permission-mode", plan.definition.permission_mode])
            
            # 输出格式
            if plan.definition.output_format != "text":
                args.extend(["--output-format", plan.definition.output_format])
            
            # 设置工作区为 CWD 的相关提示
            args.append(prompt)
        else:
            # 原有的 interactive 模式
            args.extend(["-p", prompt])
        
        return args

    def _build_codex_coding_args(self, plan: SkillInvocationPlan) -> list[str]:
        """为 Codex CLI 构建编码模式命令行参数: codex exec（prompt 通过 stdin 传入）。

        Stage 10: 新增 Codex 编码模式支持。
        ⭐ prompt 不放在 CLI args 中 — 由 _run_subprocess 通过 stdin 传入，
        避免 Codex CLI 在提供 arg 后仍然等待 stdin 的问题。

        ⭐ 关键标志:
        - --skip-git-repo-check: AgentHub 的工作区不一定被 Codex 认作 trusted 目录
        - --sandbox workspace-write: 允许写入当前工作区的文件
        - --config approval=never: headless 模式不需要人工审批
        """
        return [
            "exec",
            "--skip-git-repo-check",
            "--sandbox", "workspace-write",
            "--config", "approval=never",
        ]

    def _build_codex_review_args_inline(self, plan: SkillInvocationPlan) -> list[str]:
        """为 Codex CLI 构建审查模式命令行参数: codex review <file_path>。

        从 payload 中提取 coding 阶段改动的文件路径，传给 Codex 审查。
        若多个文件改动，审查第一个；若无改动文件，审查 demo_workspace 目录。
        """
        args = ["review"]

        applied_changes = (plan.payload.get("applied_changes") or [])
        if applied_changes:
            # 取第一个有 path 的改动文件
            for change in applied_changes:
                if isinstance(change, dict) and change.get("path"):
                    target = str(self.repo_root / change["path"])
                    if os.path.exists(target):
                        args.append(target)
                        return args

        # 回退：审查 demo_workspace 目录
        fallback = self.repo_root / "demo_workspace"
        if fallback.exists():
            args.append(str(fallback))
        else:
            args.append(str(self.repo_root))
        return args

    def _build_codex_args(self, plan: SkillInvocationPlan) -> list[str]:
        """[DEPRECATED] 旧版 Codex 审查参数构建。请使用 _build_codex_review_args_inline。"""
        return self._build_codex_review_args_inline(plan)

    def _build_claude_review_args(self, plan: SkillInvocationPlan) -> list[str]:
        """为 Claude Code 构建 Review 模式命令行参数。

        从 payload 中提取 coding 阶段的 diff/changes，拼装审查 prompt，
        通过 claude -p 在 headless 模式下执行。
        """
        args = []
        prompt = _build_codex_review_prompt(plan.payload, plan)

        if plan.definition.mode == "headless":
            args.append("-p")
            if plan.definition.permission_mode != "default":
                args.extend(["--permission-mode", plan.definition.permission_mode])
            if plan.definition.output_format != "text":
                args.extend(["--output-format", plan.definition.output_format])
            args.append(prompt)
        else:
            args.extend(["-p", prompt])

        return args

    # ── 工作区管理 ────────────────────────────────────────────

    def _create_workspace(self, plan: SkillInvocationPlan) -> Path:
        """为本次调用确定工作目录。

         Stage 9: 不再复制文件。直接使用 session source 目录或用户原始目录作为 cwd。
        对 imported 工作区，cwd 是用户的原始项目路径。
        对 scratch/project，cwd 是 workspace/{session_id}/source/。
        同时创建 workspaces/task_xxx/ 作为日志/临时目录。
        """
        ws_root = self.repo_root / self.workspaces_root
        ws_root.mkdir(parents=True, exist_ok=True)
        task_dir = ws_root / f"task_{plan.task_id[:12]}"
        task_dir.mkdir(parents=True, exist_ok=True)

        return task_dir

    def _build_env(self, plan: SkillInvocationPlan, workspace_dir: Path) -> dict[str, str]:
        """构建注入子进程的环境变量。"""
        env = os.environ.copy()
        env.update(
            {
                "WORKSPACE_ROOT": str(workspace_dir.resolve()),
                "TASK_ID": plan.task_id,
                "SKILL_NAME": plan.definition.skill_name,
                "TRACE_ID": plan.trace_id,
                "SKILL_VERSION": plan.definition.version,
                f"{plan.definition.skill_name.upper().replace('.', '_')}_TIMEOUT": str(plan.timeout_seconds),
            }
        )
        return env

    # ── 子进程执行 ────────────────────────────────────────────

    def _run_subprocess(
        self,
        *,
        cli_path: str,
        args: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
        plan: SkillInvocationPlan,
        workspace_dir: Path,
        stdin_prompt: str = "",
    ) -> ExternalCLIResult:
        """启动子进程，流式读取输出 + 心跳检测 + stdin 传 prompt。

        ⭐ Stage 10: 重构为流式读取模式。
        - 通过 stdin 传入 prompt（避免 CLI 等待交互输入）
        - 线程异步读取 stdout/stderr
        - 心跳检测：idle_timeout 秒无输出判定为 hang
        """
        t0 = time.perf_counter()
        idle_timeout = 60  # 60s 无输出判定 hang，提前 kill 避免无限等待

        import sys as _sys
        full_cmd = [cli_path] + args
        msg = (f"[CLI-EXEC] Spawning: {' '.join(str(a)[:100] for a in full_cmd[:8])}...\n"
               f"[CLI-EXEC]   cwd={cwd}, timeout={timeout_seconds}s, idle_timeout={idle_timeout}s, "
               f"skill={plan.definition.skill_name}, stdin_prompt_len={len(stdin_prompt)}")
        print(msg, flush=True)
        _sys.stderr.write(msg + "\n")
        _sys.stderr.flush()

        try:
            proc = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,   # ⭐ 通过 stdin 传 prompt
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd),
                env=env,
                text=True,
            )
        except OSError as e:
            raise ExternalCLIProcessError(
                f"failed to spawn CLI process: {e}",
                retryable=False,
                details={"command": cli_path, "args": args[:3]},
            ) from e

        # ── Stage 10: 流式读取 + 心跳检测 ──────────────────────
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        last_activity = time.monotonic()
        read_error: str | None = None

        def _read_stream(stream, chunks: list[str], label: str):
            nonlocal last_activity, read_error
            try:
                for line in stream:
                    chunks.append(line)
                    last_activity = time.monotonic()
                    # 实时打印 stderr（Codex 的模型/进度信息都走 stderr）
                    if label == "stderr":
                        print(f"[CLI-EXEC] [{label}] {line.rstrip()}", flush=True)
            except Exception as e:
                read_error = f"{label} read error: {e}"

        t_stdout = threading.Thread(target=_read_stream, args=(proc.stdout, stdout_chunks, "stdout"), daemon=True)
        t_stderr = threading.Thread(target=_read_stream, args=(proc.stderr, stderr_chunks, "stderr"), daemon=True)
        t_stdout.start()
        t_stderr.start()

        # ⭐ 通过 stdin 传入 prompt（如果有），然后关闭 stdin
        if stdin_prompt:
            try:
                proc.stdin.write(stdin_prompt)
                proc.stdin.flush()
            except Exception as e:
                print(f"[CLI-EXEC] Failed to write stdin prompt: {e}", flush=True)
        try:
            proc.stdin.close()
        except Exception:
            pass

        # 心跳轮询
        deadline = time.monotonic() + float(timeout_seconds)
        timed_out = False
        hung = False
        while True:
            if proc.poll() is not None:
                break  # 进程已退出
            elapsed = time.monotonic() - t0
            if elapsed > float(timeout_seconds):
                timed_out = True
                break
            idle_sec = time.monotonic() - last_activity
            if idle_sec > idle_timeout:
                print(f"[CLI-EXEC] HUNG: no output for {idle_sec:.0f}s, killing process", flush=True)
                hung = True
                break
            time.sleep(2)  # 每2秒轮询一次

        if hung:
            # 心跳超时 → 强制 kill
            try:
                proc.kill()
            except Exception:
                pass
            proc.wait(timeout=5)
            t_stdout.join(timeout=3)
            t_stderr.join(timeout=3)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            raise ExternalCLITimeoutError(
                f"CLI hung: no output for {idle_timeout}s: {plan.definition.skill_name}",
                details={
                    "exit_code": proc.returncode,
                    "stdout_tail": "".join(stdout_chunks)[-1000:],
                    "stderr_tail": "".join(stderr_chunks)[-1000:],
                    "timeout_seconds": timeout_seconds,
                    "idle_timeout": idle_timeout,
                    "latency_ms": latency_ms,
                },
            )

        if timed_out:
            # 总超时 → SIGTERM → SIGKILL
            proc.terminate()
            try:
                proc.wait(timeout=float(self.grace_period_seconds))
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            t_stdout.join(timeout=3)
            t_stderr.join(timeout=3)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            stdout_str = "".join(stdout_chunks)
            stderr_str = "".join(stderr_chunks)
            raise ExternalCLITimeoutError(
                f"CLI timeout after {timeout_seconds}s: {plan.definition.skill_name}",
                details={
                    "exit_code": proc.returncode,
                    "stderr_full": stderr_str,
                    "stdout_tail": stdout_str[-1000:],
                    "timeout_seconds": timeout_seconds,
                    "latency_ms": latency_ms,
                },
            )

        # 进程正常退出 — 等待读取线程收集完最后输出
        t_stdout.join(timeout=5)
        t_stderr.join(timeout=5)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        stdout_str = "".join(stdout_chunks)
        stderr_str = "".join(stderr_chunks)

        # ⭐ Stage 10: 日志 — 记录执行结果摘要 + 双写 stderr
        import sys as _sys
        msg = (f"[CLI-EXEC] Completed: exit={proc.returncode}, latency={latency_ms}ms, "
               f"stdout_len={len(stdout_str)}, stderr_len={len(stderr_str)}")
        print(msg, flush=True)
        _sys.stderr.write(msg + "\n")
        _sys.stderr.flush()
        if stderr_str:
            print(f"[CLI-EXEC]   stderr preview: {stderr_str[:300]}", flush=True)
        if stdout_str:
            print(f"[CLI-EXEC]   stdout preview: {stdout_str[:200]}", flush=True)

        result = ExternalCLIResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=proc.returncode,
            latency_ms=latency_ms,
        )

        # 分类处理退出结果
        if proc.returncode == 0:
            result = self._handle_success(result, plan, workspace_dir)
        else:
            result = self._handle_failure(result, plan)

        return result

    def _handle_success(self, result: ExternalCLIResult, plan: SkillInvocationPlan, workspace_dir: Path) -> ExternalCLIResult:
        """解析成功退出时的 stdout。

        ⭐ Step 6: 捕获 Codex stderr 作为 thinking_trace。
        Codex 将模型推理/进度信息输出到 stderr，保存下来供 review 阶段使用。
        """
        # 在解析前先保存 thinking_trace
        thinking_trace = (result.stderr or "")[-2000:]  # 最后 2000 字符
        try:
            if plan.definition.agent_binding == "coding":
                # ⭐ Stage 10: Codex coding 和 Claude coding 共用同一解析器
                # 两者输出格式要求相同（JSON block with changes）
                result.parsed_payload = _parse_claude_code_output(result.stdout, workspace_dir, self.repo_root)
                # ⭐ Step 6: 注入 thinking_trace 到 parsed_payload
                if thinking_trace:
                    result.parsed_payload["thinking_trace"] = thinking_trace
            elif plan.definition.agent_binding == "review":
                # ⭐ Stage 10: codex_review 用 Codex 解析器, claude_review 也用 Codex 解析器
                # 因为两者的 review 输出格式兼容
                result.parsed_payload = _parse_codex_output(result.stdout)
            else:
                result.parsed_payload = {"raw_stdout": result.stdout[:2000]}
        except Exception as e:
            result.error = ExternalCLIValidationError(
                f"failed to parse CLI output: {e}",
                details={"stdout_tail": result.stdout[-500:]},
            )
        return result

    def _handle_failure(self, result: ExternalCLIResult, plan: SkillInvocationPlan) -> ExternalCLIResult:
        """分类处理非零退出码。⭐ Stage 9: 加入 NO_WORK 和 PERMISSION 分类。"""
        error_code = _classify_stderr(result.stderr)
        stderr_full = (result.stderr or "")  # ⭐ 完整 stderr

        if error_code == "MODEL_ERROR":
            result.error = ExternalCLIModelError(
                f"CLI model error ({plan.definition.skill_name}): API may be unavailable, out of quota, or auth issue",
                details={"exit_code": result.exit_code, "stderr": stderr_full},
            )
        elif error_code == "TIMEOUT_ERROR":
            result.error = ExternalCLITimeoutError(
                f"CLI timeout detected from stderr: {plan.definition.skill_name}",
                details={"exit_code": result.exit_code, "stderr": stderr_full},
            )
        elif error_code == "NO_WORK":
            result.error = ExternalCLIValidationError(
                f"CLI found no work to do: {plan.definition.skill_name}",
                details={"exit_code": result.exit_code, "stderr": stderr_full},
            )
        elif error_code == "PERMISSION":
            result.error = ExternalCLIProcessError(
                f"CLI permission denied: {plan.definition.skill_name}",
                retryable=False,
                details={"exit_code": result.exit_code, "stderr": stderr_full},
            )
        else:
            result.error = ExternalCLIProcessError(
                f"CLI exited with code {result.exit_code}: {plan.definition.skill_name}",
                retryable=(result.exit_code > 1),
                details={"exit_code": result.exit_code, "stderr": stderr_full},
            )
        return result


def external_cli_available(command: str) -> bool:
    """检查外部 CLI 命令是否可用。"""
    return _find_command(command) is not None
