from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from runtime.harness.workspace import Workspace
from runtime.core.types import TaskComplexity
logger = logging.getLogger(__name__)


class PlannerError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlanTarget:
    path: str
    action: str
    language: str
    reason: str
    base_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "action": self.action,
            "language": self.language,
            "reason": self.reason,
            "base_hash": self.base_hash,
        }


@dataclass(frozen=True)
class PlanArtifact:
    type: str
    title: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "title": self.title}


@dataclass(frozen=True)
class PlanRisk:
    severity: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "summary": self.summary}


@dataclass(frozen=True)
class LinearPlan:
    task_id: str
    summary: str
    language: str | None
    task_type: str
    execution_model: str
    planner: str
    planner_strategy: str
    instruction: str
    targets: list[PlanTarget]
    artifacts: list[PlanArtifact]
    risks: list[PlanRisk]
    # 新的领域模型字段
    interaction_mode: str = "orchestrated"  # "direct_agent" or "orchestrated"
    execution_mode: str = "task"             # "task" or "project"
    chat_mode: str = "single"                # "single" or "group"
    review_required: bool = False  # ⭐ Stage 10: 默认跳过 review
    package_strategy: str = "none"           # "none", "zip", "docker", "deploy"
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    workspace_type: str = "scratch"  # "scratch" | "project" | "imported"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "language": self.language,
            "task_type": self.task_type,
            "execution_model": self.execution_model,
            "planner": self.planner,
            "planner_strategy": self.planner_strategy,
            "instruction": self.instruction,
            "targets": [item.to_dict() for item in self.targets],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "risks": [item.to_dict() for item in self.risks],
            "interaction_mode": self.interaction_mode,
            "execution_mode": self.execution_mode,
            "chat_mode": self.chat_mode,
            "workspace_type": self.workspace_type,
            "review_required": self.review_required,
            "package_strategy": self.package_strategy,
            "complexity": self.complexity.value if hasattr(self, "complexity") else "medium",
        }


@dataclass(frozen=True)
class RulePlanner:
    workspace: Workspace

    def plan(self, *, task_id: str, instruction: str) -> LinearPlan:
        lowered = instruction.lower()

        # ⭐ Stage 10: 只在用户显式要求时才开启 review
        # ⭐ 扩展检测：@security_reviewer、审查、review 等关键词
        review_wanted = any(agent in lowered for agent in (
            "@review", "@claude_review", "@claude code",
            "@security_reviewer", "审查", "review", "@qa_engineer",
        ))

        if "gin" in lowered or "go" in lowered:
            plan = self._plan_go_gin_api(task_id=task_id, instruction=instruction)
            return LinearPlan(
                task_id=plan.task_id, summary=plan.summary, language=plan.language,
                task_type=plan.task_type, execution_model=plan.execution_model,
                planner=plan.planner, planner_strategy=plan.planner_strategy,
                instruction=plan.instruction, targets=plan.targets,
                artifacts=plan.artifacts, risks=plan.risks,
                interaction_mode=plan.interaction_mode, execution_mode=plan.execution_mode,
                chat_mode=plan.chat_mode,
                review_required=review_wanted,
                package_strategy=plan.package_strategy, complexity=plan.complexity,
            )
        if "react" in lowered or "todo" in lowered:
            plan = self._plan_react_todo(task_id=task_id, instruction=instruction)
            return LinearPlan(
                task_id=plan.task_id, summary=plan.summary, language=plan.language,
                task_type=plan.task_type, execution_model=plan.execution_model,
                planner=plan.planner, planner_strategy=plan.planner_strategy,
                instruction=plan.instruction, targets=plan.targets,
                artifacts=plan.artifacts, risks=plan.risks,
                interaction_mode=plan.interaction_mode, execution_mode=plan.execution_mode,
                chat_mode=plan.chat_mode,
                review_required=review_wanted,
                package_strategy=plan.package_strategy, complexity=plan.complexity,
            )
        if any(token in lowered for token in ("新增接口", "统计", "api", "existing", "modify", "接口")):
            plan = self._plan_modify_api(task_id=task_id, instruction=instruction)
            return LinearPlan(
                task_id=plan.task_id, summary=plan.summary, language=plan.language,
                task_type=plan.task_type, execution_model=plan.execution_model,
                planner=plan.planner, planner_strategy=plan.planner_strategy,
                instruction=plan.instruction, targets=plan.targets,
                artifacts=plan.artifacts, risks=plan.risks,
                interaction_mode=plan.interaction_mode, execution_mode=plan.execution_mode,
                chat_mode=plan.chat_mode,
                review_required=review_wanted,
                package_strategy=plan.package_strategy, complexity=plan.complexity,
            )
        plan = self._plan_default(task_id=task_id, instruction=instruction)
        return LinearPlan(
            task_id=plan.task_id, summary=plan.summary, language=plan.language,
            task_type=plan.task_type, execution_model=plan.execution_model,
            planner=plan.planner, planner_strategy=plan.planner_strategy,
            instruction=plan.instruction, targets=plan.targets,
            artifacts=plan.artifacts, risks=plan.risks,
            interaction_mode=plan.interaction_mode, execution_mode=plan.execution_mode,
            chat_mode=plan.chat_mode,
            review_required=review_wanted,
            package_strategy=plan.package_strategy, complexity=plan.complexity,
        )

    def _target(self, *, path: str, language: str, reason: str) -> PlanTarget:
        base_hash = self.workspace.file_hash(rel_path=path)
        action = "update" if base_hash is not None else "create"
        return PlanTarget(path=path, action=action, language=language, reason=reason, base_hash=base_hash)

    def _base_artifacts(self) -> list[PlanArtifact]:
        return [
            PlanArtifact(type="diff", title="Code Diff"),
            PlanArtifact(type="review", title="Review Report"),
            PlanArtifact(type="bundle", title="Artifact Bundle"),
        ]

    def _plan_go_gin_api(self, *, task_id: str, instruction: str) -> LinearPlan:
        targets = [
            self._target(path="workspace/go_gin_api/go.mod", language="go", reason="定义 Go module 与依赖"),
            self._target(path="workspace/go_gin_api/main.go", language="go", reason="Gin 入口：注册路由并启动服务"),
            self._target(path="workspace/go_gin_api/router/router.go", language="go", reason="集中管理路由注册"),
            self._target(path="workspace/go_gin_api/handlers/health.go", language="go", reason="health check 处理器"),
            self._target(path="workspace/go_gin_api/handlers/todo.go", language="go", reason="todo CRUD 处理器"),
            self._target(path="workspace/go_gin_api/README.md", language="markdown", reason="说明接口路径与运行方式"),
        ]
        return LinearPlan(
            task_id=task_id,
            summary="生成一个完整的 Go Gin API 服务，含 router/handler 分层与 health/todo 接口。",
            language="go",
            task_type="generate_api",
            execution_model="linear_pipeline",
            planner="rule_planner",
            planner_strategy="fallback",
            instruction=instruction,
            targets=targets,
            artifacts=self._base_artifacts(),
            risks=[PlanRisk(severity="medium", summary="当前为规则规划，文件结构为骨架级输出。")],
            interaction_mode="orchestrated",
            execution_mode="project",
            chat_mode="single",
            review_required=False,  # ⭐ Stage 10: 默认跳过 review，除非用户显式要求
            package_strategy="zip",
            complexity=TaskComplexity.PROJECT,  # 项目级复杂度
        )

    def _plan_react_todo(self, *, task_id: str, instruction: str) -> LinearPlan:
        targets = [
            self._target(path="workspace/react_todo/package.json", language="json", reason="定义前端依赖与脚本"),
            self._target(path="workspace/react_todo/src/main.tsx", language="tsx", reason="React 入口，挂载 App"),
            self._target(path="workspace/react_todo/src/App.tsx", language="tsx", reason="Todo 页面主体与状态管理"),
            self._target(path="workspace/react_todo/src/components/TodoList.tsx", language="tsx", reason="任务列表组件"),
            self._target(path="workspace/react_todo/src/components/TodoItem.tsx", language="tsx", reason="单条任务组件"),
            self._target(path="workspace/react_todo/src/styles/index.css", language="css", reason="页面样式"),
        ]
        return LinearPlan(
            task_id=task_id,
            summary="生成一个组件化 React Todo 页面，含列表/条目/样式拆分。",
            language="tsx",
            task_type="generate_frontend",
            execution_model="linear_pipeline",
            planner="rule_planner",
            planner_strategy="fallback",
            instruction=instruction,
            targets=targets,
            artifacts=self._base_artifacts() + [PlanArtifact(type="preview", title="Preview Entry")],
            risks=[PlanRisk(severity="medium", summary="当前为规则规划，页面预览仍需后续真实渲染链。")],
            interaction_mode="orchestrated",
            execution_mode="project",
            chat_mode="single",
            review_required=False,  # ⭐ Stage 10: 默认跳过 review
            package_strategy="zip",
            complexity=TaskComplexity.PROJECT,  # 项目级复杂度
        )

    def _plan_modify_api(self, *, task_id: str, instruction: str) -> LinearPlan:
        targets = [
            self._target(
                path="workspace/existing_api/models.py",
                language="python",
                reason="定义 TaskStats 等数据模型",
            ),
            self._target(
                path="workspace/existing_api/router.py",
                language="python",
                reason="注册新增统计接口路由",
            ),
            self._target(
                path="workspace/existing_api/service.py",
                language="python",
                reason="在既有服务中新增 get_task_stats 统计逻辑",
            ),
            self._target(
                path="workspace/existing_api/README.md",
                language="markdown",
                reason="补充新增接口的路径与返回结构说明",
            ),
        ]
        return LinearPlan(
            task_id=task_id,
            summary="对现有 Python API 做增量修改：新增 models/router，在 service 中增加统计接口。",
            language="python",
            task_type="modify_existing_code",
            execution_model="linear_pipeline",
            planner="rule_planner",
            planner_strategy="fallback",
            instruction=instruction,
            targets=targets,
            artifacts=self._base_artifacts(),
            risks=[PlanRisk(severity="high", summary="该任务属于修改既有代码，适合后续接入人工审批门控。")],
            interaction_mode="orchestrated",
            execution_mode="task",
            chat_mode="single",
            review_required=False,  # ⭐ Stage 10: 默认跳过 review
            package_strategy="none",
            complexity=TaskComplexity.PROJECT,  # 项目级复杂度
        )

    def _plan_default(self, *, task_id: str, instruction: str) -> LinearPlan:
        # ⭐ Stage 9: 根据 instruction 关键词推断语言和路径
        # 避免所有任务都生成 output.txt
        lowered = instruction.lower()
        if any(kw in lowered for kw in ("c++", "cpp", "cplusplus")):
            lang, ext = "cpp", "cpp"
        elif any(kw in lowered for kw in ("python", "py", "python3")):
            lang, ext = "python", "py"
        elif any(kw in lowered for kw in ("react", "tsx", "typescript", "component", "组件")):
            lang, ext = "tsx", "tsx"
        elif any(kw in lowered for kw in ("javascript", "js", "node", "nodejs")):
            lang, ext = "javascript", "js"
        elif any(kw in lowered for kw in ("go", "golang")):
            lang, ext = "go", "go"
        elif any(kw in lowered for kw in ("rust", "rs")):
            lang, ext = "rust", "rs"
        elif any(kw in lowered for kw in ("java",)):
            lang, ext = "java", "java"
        elif any(kw in lowered for kw in ("html",)):
            lang, ext = "html", "html"
        elif any(kw in lowered for kw in ("css",)):
            lang, ext = "css", "css"
        elif any(kw in lowered for kw in ("sql",)):
            lang, ext = "sql", "sql"
        elif any(kw in lowered for kw in ("shell", "bash", "sh")):
            lang, ext = "bash", "sh"
        elif any(kw in lowered for kw in ("c", "c语言")):
            lang, ext = "c", "c"
        elif any(kw in lowered for kw in ("文档", "doc", "documentation", "markdown", "readme", "md")):
            lang, ext = "markdown", "md"
        else:
            lang, ext = "text", "txt"

        # ⭐ 用 task_id 前缀确保同会话多任务不会互相覆盖
        prefix = task_id[:8] if task_id else "task"
        path = f"workspace/general/{prefix}_task.{ext}"

        targets = [
            self._target(
                path=path,
                language=lang,
                reason=f"默认输出路径（推断语言={lang}），task={prefix}",
            )
        ]
        return LinearPlan(
            task_id=task_id,
            summary=f"默认规则规划任务（{lang}）。",
            language=lang,
            task_type="generic",
            execution_model="linear_pipeline",
            planner="rule_planner",
            planner_strategy="fallback",
            instruction=instruction,
            targets=targets,
            artifacts=self._base_artifacts(),
            risks=[PlanRisk(severity="low", summary="当前未命中特定模板，使用默认保底规划。")],
            interaction_mode="orchestrated",
            execution_mode="task",
            chat_mode="single",
            review_required=False,  # ⭐ Stage 10: 默认跳过 review，加速完成
            package_strategy="none",
            complexity=TaskComplexity.SIMPLE,
        )


@dataclass(frozen=True)
class LLMPlanner:
    """Call the configured LLM to produce a structured :class:`LinearPlan`.

    Reads ``ORCHESTRATOR_BASE_URL``, ``ORCHESTRATOR_API_KEY`` and
    ``ORCHESTRATOR_MODEL`` from the environment.  On any failure a
    :class:`PlannerError` is raised so that the caller can fall back to the
    rule-based planner.
    """

    workspace: Workspace | None = None
    workspace_type: str = "scratch"

    def plan(self, *, task_id: str, instruction: str) -> LinearPlan:
        logger.info(f"[LLMPlanner] Starting planning for task: {task_id}, instruction: {instruction[:100]}...")
        
        # ── 1. build the client ──────────────────────────────────
        try:
            from runtime.llm.client import LLMClient, LLMClientError, LLMTimeoutError, LLMResponseError
        except ImportError as exc:
            logger.error(f"[LLMPlanner] LLM client unavailable: {exc}")
            raise PlannerError(f"llm client unavailable: {exc}") from exc

        try:
            client = LLMClient.from_env(model_env_key="PLANNER_MODEL")
        except LLMClientError as exc:
            logger.error(f"[LLMPlanner] LLM client config error: {exc}")
            raise PlannerError(f"llm client config error: {exc}") from exc

        # ── 2. build prompts ─────────────────────────────────────
        from runtime.llm.prompts import PLANNER_SYSTEM_PROMPT, build_planner_user_prompt

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": build_planner_user_prompt(task_id=task_id, instruction=instruction)},
        ]

        # ── 3. call the model ────────────────────────────────────
        try:
            logger.info(f"[LLMPlanner] Calling LLM for planning...")
            body = client.chat(
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            raw = client.extract_content(body)
            logger.info(f"[LLMPlanner] Received LLM response")
        except LLMTimeoutError as exc:
            logger.error(f"[LLMPlanner] Timed out: {exc}")
            raise PlannerError(f"llm_planner timed out: {exc}") from exc
        except LLMResponseError as exc:
            logger.error(f"[LLMPlanner] Response error: {exc}")
            raise PlannerError(f"llm_planner response error: {exc}") from exc
        except LLMClientError as exc:
            logger.error(f"[LLMPlanner] Error: {exc}")
            raise PlannerError(f"llm_planner error: {exc}") from exc

        # ── 4. parse the JSON output ─────────────────────────────
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            # 模型有时会包在 markdown 代码块里，做一次简单清洗
            cleaned = _strip_markdown_fence(raw)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                raise PlannerError(f"llm_planner returned unparseable JSON: {raw[:300]}") from exc

        if not isinstance(parsed, dict):
            raise PlannerError(f"llm_planner output must be a JSON object, got {type(parsed).__name__}")

        # ── 5. validate required fields ──────────────────────────
        summary = parsed.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise PlannerError("llm_planner output missing 'summary' field")

        language = parsed.get("language")
        task_type = parsed.get("task_type")
        if not isinstance(task_type, str) or not task_type.strip():
            raise PlannerError("llm_planner output missing 'task_type' field")

        # 复杂度 - 由 planner 直接输出, 不再依赖关键词匹配
        raw_complexity = parsed.get("complexity", "medium")
        if not isinstance(raw_complexity, str):
            raw_complexity = "medium"
        if raw_complexity not in ("simple", "medium", "project"):
            raw_complexity = "medium"
        complexity_val = TaskComplexity(raw_complexity)

        # 新的领域模型字段
        interaction_mode = parsed.get("interaction_mode", "orchestrated")
        if not isinstance(interaction_mode, str):
            interaction_mode = "orchestrated"
        if interaction_mode not in ("orchestrated", "direct_agent"):
            interaction_mode = "orchestrated"

        execution_mode = parsed.get("execution_mode", "task")
        if not isinstance(execution_mode, str):
            execution_mode = "task"
        if execution_mode not in ("task", "project"):
            execution_mode = "task"

        chat_mode = parsed.get("chat_mode", "single")
        if not isinstance(chat_mode, str):
            chat_mode = "single"
        if chat_mode not in ("single", "group"):
            chat_mode = "single"

        review_required = parsed.get("review_required")
        if review_required is None or not isinstance(review_required, bool):
            # ⭐ Stage 10: 默认不需要 review — 用户没明确要求时跳过审查阶段，节省时间
            review_required = False

        # ⭐ Stage 10: 用户显式要求 review（@claude_review/@review）时才开启审查
        mentioned = instruction.lower()
        if any(agent in mentioned for agent in ("@claude_review", "@review", "@claude code")):
            review_required = True

        package_strategy = parsed.get("package_strategy", "none")
        if not isinstance(package_strategy, str):
            package_strategy = "none"
        if package_strategy not in ("none", "zip", "docker", "deploy"):
            package_strategy = "none"

        raw_targets = parsed.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise PlannerError("llm_planner output missing or empty 'targets' list")

        raw_artifacts = parsed.get("artifacts") or []
        raw_risks = parsed.get("risks") or []

        # ── 6. build targets with base_hash ──────────────────────
        targets: list[PlanTarget] = []
        for t in raw_targets:
            if not isinstance(t, dict):
                continue
            path = t.get("path")
            if not isinstance(path, str) or not path.strip():
                continue
            target_lang = t.get("language", language)
            reason = t.get("reason", "generated by llm_planner")
            if not isinstance(reason, str):
                reason = "generated by llm_planner"

            # base_hash 决定真实 action（覆盖 LLM 的 action 以避免 VersionMismatch）
            base_hash: str | None = None
            if self.workspace is not None:
                base_hash = self.workspace.file_hash(rel_path=path)
            action = "update" if base_hash is not None else "create"

            targets.append(
                PlanTarget(
                    path=path,
                    action=action,
                    language=str(target_lang) if target_lang else "text",
                    reason=str(reason),
                    base_hash=base_hash,
                )
            )

        if not targets:
            raise PlannerError("llm_planner produced no valid targets")

        # ── 7. build artifacts ───────────────────────────────────
        artifacts: list[PlanArtifact] = []
        for a in raw_artifacts:
            if not isinstance(a, dict):
                continue
            artifacts.append(
                PlanArtifact(
                    type=str(a.get("type") or "bundle"),
                    title=str(a.get("title") or "Artifact"),
                )
            )
        if not artifacts:
            artifacts = [
                PlanArtifact(type="diff", title="Code Diff"),
                PlanArtifact(type="review", title="Review Report"),
                PlanArtifact(type="bundle", title="Artifact Bundle"),
            ]

        # ── 8. build risks ───────────────────────────────────────
        risks: list[PlanRisk] = []
        for r in raw_risks:
            if not isinstance(r, dict):
                continue
            severity = r.get("severity", "medium")
            if severity not in ("low", "medium", "high"):
                severity = "medium"
            risks.append(
                PlanRisk(
                    severity=str(severity),
                    summary=str(r.get("summary") or "unknown risk"),
                )
            )

        # ── 9. correct complexity with workspace context ───────────
        # complexity 由 LLM 输出决定 (line 7+), 此处只做修正:
        #   - workspace_type == imported -> PROJECT
        #   - execution_mode == project -> PROJECT
        from runtime.core.task_classifier import TaskClassifier
        classifier = TaskClassifier()
        classification = classifier.classify(
            complexity=complexity_val,
            execution_mode=execution_mode,
            workspace_type=self.workspace_type,
            task_type=task_type,
        )
        complexity = classification.complexity
        logger.info(f"[LLMPlanner] Complexity: {complexity}, reason={classification.reason}")

        # ── 10. assemble the plan ─────────────────────────────────
        return LinearPlan(
            task_id=task_id,
            summary=str(summary).strip(),
            language=str(language) if isinstance(language, str) and language else None,
            task_type=str(task_type).strip(),
            execution_model="linear_pipeline",
            planner="llm_planner",
            planner_strategy="primary",
            instruction=instruction,
            targets=targets,
            artifacts=artifacts,
            risks=risks,
            interaction_mode=interaction_mode,
            execution_mode=execution_mode,
            chat_mode=chat_mode,
            review_required=review_required,
            package_strategy=package_strategy,
            complexity=complexity,
            workspace_type=self.workspace_type,
        )


def _strip_markdown_fence(raw: str) -> str:
    """Remove a surrounding ```json ... ``` code fence if present."""
    text = raw.strip()
    if text.startswith("```"):
        # find the first newline after the opening fence
        nl = text.find("\n")
        if nl >= 0:
            text = text[nl + 1 :]
    if text.endswith("```"):
        text = text[: -3].rstrip()
    return text.strip()


@dataclass(frozen=True)
class LinearPlanner:
    workspace: Workspace

    def plan(self, *, task_id: str, instruction: str) -> tuple[LinearPlan, str]:
        import sys as _sys
        _sys.stderr.write(f"[PLANNER] plan() called: ws_type={getattr(self.workspace, 'workspace_type', 'scratch')}, task={task_id[:12]}..., instruction='{instruction[:80]}...'\n")
        _sys.stderr.flush()

        logger.info(f"[LinearPlanner] Starting planning process for task: {task_id}")
        ws_type = getattr(self.workspace, "workspace_type", "scratch")

        # ⭐ Stage 9: scratch 工作区简单任务直接用 RulePlanner，跳过 LLM 规划
        if ws_type == "scratch":
            logger.info(f"[LinearPlanner] Scratch workspace — using RulePlanner directly (fast path)")
            rule_plan = RulePlanner(workspace=self.workspace).plan(task_id=task_id, instruction=instruction)
            _sys.stderr.write(f"[PLANNER] RulePlanner done: complexity={rule_plan.complexity}, targets={len(rule_plan.targets)}, ws_type={rule_plan.workspace_type}\n")
            _sys.stderr.flush()
            return rule_plan, "rule_planner"

        llm_planner = LLMPlanner(workspace=self.workspace, workspace_type=ws_type)
        try:
            logger.info(f"[LinearPlanner] Trying LLM planner first...")
            plan = llm_planner.plan(task_id=task_id, instruction=instruction)
            logger.info(f"[LinearPlanner] Successfully generated plan with LLM planner")
            return plan, "llm_planner"
        except PlannerError as e:
            logger.warning(f"[LinearPlanner] LLM planner failed: {e}, falling back to rule planner")
            rule_plan = RulePlanner(workspace=self.workspace).plan(task_id=task_id, instruction=instruction)
            logger.info(f"[LinearPlanner] Successfully generated plan with rule planner")
            return rule_plan, "rule_planner"
