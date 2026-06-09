from __future__ import annotations

"""
Persona 模块 — User-Defined Agent 的 Prompt Builder。

实现了 ADR-029 的核心设计：Agent Definition = 数据，通过 PersonaLoader 加载，
通过 AgentPromptBuilder 组装 System Prompt → 注入 payload。

架构：
    mentioned_agent ("backend_architect")
        │
        ▼
    PersonaLoader.load(id)
        │  ┌─ 优先从内置 definition 加载
        │  └─ 回退到 Gateway API (future)
        ▼
    AgentPromptBuilder.build(agent_def, task_ctx)
        │
        ▼
    组装后的 prompt → 注入 payload["system_prompt"]
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── 内置 Agent Definitions ────────────────────────────────────

_BUILTIN_AGENTS: dict[str, dict[str, Any]] = {
    "backend_architect": {
        "id": "backend_architect",
        "name": "Backend Architect",
        "avatar": "🏗️",
        "description": "Go 后端架构专家，擅长 Gin + GORM",
        "system_prompt": (
            "你是一名资深 Go 后端架构师。\n"
            "你擅长：\n"
            "- Gin 框架的 API 设计（路由、中间件、请求验证）\n"
            "- GORM 数据模型设计与迁移\n"
            "- 微服务架构与 gRPC 通信\n"
            "- 清晰的分层架构（handler → service → repository）\n"
            "- 完善的错误处理与日志\n"
            "你的代码风格：函数短小精悍、错误处理明确、变量命名有意义。\n"
            "输出代码时优先使用 Go 标准库，其次使用社区主流库。"
        ),
        "allowed_skills": ["coding", "review", "read_file", "write_file"],
        "preferred_provider": "claude_code",
        "visibility": "public",
    },
    "frontend_engineer": {
        "id": "frontend_engineer",
        "name": "Frontend Engineer",
        "avatar": "🎨",
        "description": "React 前端工程师，擅长组件化开发",
        "system_prompt": (
            "你是一名资深 React 前端工程师。\n"
            "你擅长：\n"
            "- React 18+ 函数组件与 Hooks\n"
            "- TypeScript 类型系统\n"
            "- Next.js App Router\n"
            "- TailwindCSS 样式方案\n"
            "- 组件化设计与可复用性\n"
            "你的代码风格：组件单一职责、Props 类型明确、状态管理清晰。\n"
            "输出代码时优先使用 TypeScript + React + TailwindCSS。"
        ),
        "allowed_skills": ["coding", "review", "read_file", "write_file"],
        "preferred_provider": "claude_code",
        "visibility": "public",
    },
    "devops_engineer": {
        "id": "devops_engineer",
        "name": "DevOps Engineer",
        "avatar": "🚀",
        "description": "DevOps 部署运维专家",
        "system_prompt": (
            "你是一名资深 DevOps 工程师。\n"
            "你擅长：\n"
            "- Dockerfile 和 docker-compose 编写\n"
            "- CI/CD 流水线配置（GitHub Actions / GitLab CI）\n"
            "- Kubernetes 部署文件\n"
            "- 基础设施即代码（Terraform）\n"
            "- 监控与日志方案（Prometheus + Grafana）\n"
            "你的原则：安全优先、可重复部署、最小权限原则。"
        ),
        "allowed_skills": ["coding", "run_command", "git_diff", "read_file", "write_file"],
        "preferred_provider": "claude_code",
        "visibility": "public",
    },
    "qa_engineer": {
        "id": "qa_engineer",
        "name": "QA Engineer",
        "avatar": "🧪",
        "description": "质量保证工程师，擅长测试与审查",
        "system_prompt": (
            "你是一名资深 QA 工程师。\n"
            "你擅长：\n"
            "- 为代码编写全面的测试用例\n"
            "- 审查代码中的 Bug、逻辑错误和边界条件\n"
            "- 评估代码的可测试性和可维护性\n"
            "- 设计集成测试和端到端测试方案\n"
            "你的审查维度：功能正确性、边界条件、错误处理、安全性。\n"
            "每个发现的问题需要包含：严重级别、位置、原因、修复建议。"
        ),
        "allowed_skills": ["review", "read_file", "search_code"],
        "preferred_provider": "claude_code",
        "visibility": "public",
    },
    "security_reviewer": {
        "id": "security_reviewer",
        "name": "Security Reviewer",
        "avatar": "🔒",
        "description": "安全审查专家，专注代码安全",
        "system_prompt": (
            "你是一名资深安全审查专家。\n"
            "你擅长：\n"
            "- OWASP Top 10 漏洞检测\n"
            "- SQL 注入、XSS、CSRF 防护\n"
            "- 认证与授权安全\n"
            "- 敏感数据保护\n"
            "- 依赖供应链安全\n"
            "你的审查维度：注入攻击、认证漏洞、敏感数据暴露、\n"
            "访问控制缺陷、不安全的依赖、日志安全。\n"
            "每个发现需要包含：CWE 编号（如适用）、严重级别、\n"
            "影响范围、利用条件、修复方案。"
        ),
        "allowed_skills": ["review", "read_file", "search_code"],
        "preferred_provider": "claude_code",
        "visibility": "public",
    },
}


# ── Agent Definition 数据类 ────────────────────────────────────

@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    avatar: str = ""
    description: str = ""
    system_prompt: str = ""
    allowed_skills: tuple[str, ...] = ()
    preferred_provider: str = "claude_code"
    visibility: str = "private"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    import_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "allowed_skills": list(self.allowed_skills),
            "preferred_provider": self.preferred_provider,
            "visibility": self.visibility,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "import_url": self.import_url,
        }


# ── PersonaLoader ──────────────────────────────────────────────

class PersonaLoader:
    """加载 Agent Definition。

    优先级：
    1. 内置 Agent（_BUILTIN_AGENTS）
    2. 用户自定义 Agent（user_agents.json）
    3. Gateway API（future）
    """

    _user_agents: dict[str, dict[str, Any]] | None = None
    _user_agents_loaded_at: float = 0.0

    def __init__(self, gateway_base_url: str | None = None, gateway_token: str | None = None):
        self._gateway_url = gateway_base_url
        self._gateway_token = gateway_token
        self._repo_root = Path.cwd()

    def load(self, agent_id: str) -> AgentDefinition | None:
        """根据 agent_id 加载 Agent Definition。"""
        # 优先查内置
        raw = _BUILTIN_AGENTS.get(agent_id)
        if raw:
            return self._from_dict(raw)

        # ⭐ 查用户自定义 agent
        raw = self._user_agent_raw(agent_id)
        if raw:
            return self._from_dict(raw)

        # Future: 从 Gateway API 加载
        # if self._gateway_url:
        #     return self._load_from_gateway(agent_id)

        return None

    def list_all(self) -> list[AgentDefinition]:
        """列出所有可用的 Agent（内置 + 用户自定义）。"""
        builtins = self.list_builtin()
        user_agents = self.list_user_agents()
        return builtins + user_agents

    def list_builtin(self) -> list[AgentDefinition]:
        return [self._from_dict(raw) for raw in _BUILTIN_AGENTS.values()]

    def list_user_agents(self) -> list[AgentDefinition]:
        """列出所有用户自定义 Agent。"""
        self._ensure_user_agents_loaded()
        if not self._user_agents:
            return []
        return [self._from_dict(raw) for raw in self._user_agents.values()]

    def resolve(self, mentioned_agent: str | None) -> AgentDefinition | None:
        """解析 mentioned_agent 为 AgentDefinition。

        - 若为 None → 返回 None（使用默认 coding agent persona）
        - 若命中内置 → 返回对应 definition
        - 若命中用户自定义 → 返回对应 definition
        - 若未命中 → 返回 None
        """
        if mentioned_agent is None:
            return None
        # 去掉 @ 前缀（如果用户 @Backend Architect 格式输入）
        agent_id = mentioned_agent.lstrip("@").strip().lower().replace(" ", "_")
        return self.load(agent_id)

    def add_user_agent(self, raw: dict[str, Any]) -> AgentDefinition:
        """添加一个用户自定义 Agent 并持久化。"""
        import json as _json
        from datetime import datetime, timezone

        agent_id = raw.get("id") or raw.get("name", "").lower().replace(" ", "_")
        now = datetime.now(timezone.utc).isoformat()

        entry = {
            "id": agent_id,
            "name": raw.get("name", agent_id),
            "avatar": raw.get("avatar", ""),
            "description": raw.get("description", ""),
            "system_prompt": raw.get("system_prompt", ""),
            "allowed_skills": raw.get("allowed_skills") or [],
            "preferred_provider": raw.get("preferred_provider", "claude_code"),
            "visibility": raw.get("visibility", "private"),
            "created_by": raw.get("created_by", "user"),
            "created_at": raw.get("created_at") or now,
            "updated_at": now,
            "import_url": raw.get("import_url", ""),
        }

        self._ensure_user_agents_loaded()
        if self._user_agents is None:
            self._user_agents = {}
        self._user_agents[agent_id] = entry
        self._persist_user_agents()
        return self._from_dict(entry)

    def delete_user_agent(self, agent_id: str) -> bool:
        """删除一个用户自定义 Agent 并持久化。返回是否成功。"""
        self._ensure_user_agents_loaded()
        if not self._user_agents or agent_id not in self._user_agents:
            return False
        del self._user_agents[agent_id]
        self._persist_user_agents()
        return True

    # ── 内部 ──────────────────────────────────────────────────

    def _user_agent_raw(self, agent_id: str) -> dict[str, Any] | None:
        self._ensure_user_agents_loaded()
        if not self._user_agents:
            return None
        return self._user_agents.get(agent_id)

    def _user_agents_path(self) -> Path:
        return self._repo_root / "runtime" / "specs" / "registries" / "user_agents.json"

    def _ensure_user_agents_loaded(self):
        """惰性加载 user_agents.json，每 5 秒检查一次更新。"""
        import json as _json, time as _time
        now = _time.time()
        if self._user_agents is not None and (now - self._user_agents_loaded_at) < 5.0:
            return
        path = self._user_agents_path()
        if not path.exists():
            self._user_agents = {}
            self._user_agents_loaded_at = now
            return
        try:
            data = _json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._user_agents = {item["id"]: item for item in data if isinstance(item, dict) and "id" in item}
            else:
                self._user_agents = {}
        except Exception:
            self._user_agents = {}
        self._user_agents_loaded_at = now

    def _persist_user_agents(self):
        """将用户 agent 列表写回 user_agents.json。"""
        import json as _json
        path = self._user_agents_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        agents_list = list((self._user_agents or {}).values())
        path.write_text(_json.dumps(agents_list, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Prompt Builder ─────────────────────────────────────────────

class AgentPromptBuilder:
    """将 AgentDefinition + TaskContext 组装为发送给 Provider 的完整 prompt。"""

    @staticmethod
    def _from_dict(raw: dict[str, Any]) -> AgentDefinition:
        """从字典构建 AgentDefinition（静态方法）。"""
        return AgentDefinition(
            id=raw["id"],
            name=raw.get("name", raw["id"]),
            avatar=raw.get("avatar", ""),
            description=raw.get("description", ""),
            system_prompt=raw.get("system_prompt", ""),
            allowed_skills=tuple(raw.get("allowed_skills") or []),
            preferred_provider=raw.get("preferred_provider", "claude_code"),
            visibility=raw.get("visibility", "public"),
            created_by=raw.get("created_by", ""),
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
            import_url=raw.get("import_url", ""),
        )

    @staticmethod
    def build_coding_prompt(
        *,
        agent_def: AgentDefinition | None,
        instruction: str,
        targets: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """构建 coding 阶段的 prompt。

        若 agent_def 不为 None，将其 system_prompt 前置。
        """
        parts: list[str] = []

        if agent_def is not None and agent_def.system_prompt:
            parts.append(agent_def.system_prompt)
            parts.append("")

        parts.append(instruction)

        if targets:
            parts.append("\n## Target Files")
            for t in targets:
                if isinstance(t, dict):
                    parts.append(f"- {t.get('action', 'update')}: {t.get('path', 'unknown')}")

        if context and context.get("pinned"):
            parts.append("\n## Context")
            for item in context["pinned"]:
                parts.append(f"- {item}")

        parts.append(
            "\n## Output Format\n"
            "After completing the work, output a JSON block with:\n"
            "```json\n"
            '{"plan": ["step 1"], "changes": [{"action": "create|update|delete", "path": "relative/path", "content": "..."}], "example_diff": [{"path": "...", "diff": "..."}]}\n'
            "```"
        )

        return "\n".join(parts)

    @staticmethod
    def build_review_prompt(
        *,
        agent_def: AgentDefinition | None,
        changes: list[dict[str, Any]] | None = None,
        review_focus: dict[str, Any] | None = None,
    ) -> str:
        """构建 review 阶段的 prompt。"""
        parts: list[str] = []

        if agent_def is not None and agent_def.system_prompt:
            parts.append(agent_def.system_prompt)
            parts.append("")

        parts.append("Review this diff:\n")

        if changes:
            parts.append("## Files changed")
            for ch in changes:
                if isinstance(ch, dict):
                    path = ch.get("path", "unknown")
                    diff = ch.get("diff", "")
                    parts.append(f"\n### {path}")
                    parts.append("```diff")
                    parts.append(diff if diff else f"(action: {ch.get('action', 'update')})")
                    parts.append("```")

        dimensions = (review_focus or {}).get("dimensions", ["security", "logic", "style", "performance"])
        parts.append(f"\nPlease analyze: {', '.join(dimensions)}")

        parts.append(
            "\n## Output Format\n"
            "Output a JSON block with:\n"
            "```json\n"
            '{"decision": "pass|fail", "score": {"value": 85, "max": 100}, "issues": [{"severity": "high|medium|low", "type": "security|logic|style|performance", "message": "...", "path": "...", "suggestion": "..."}]}\n'
            "```"
        )

        return "\n".join(parts)

    @staticmethod
    def check_skill_allowed(agent_def: AgentDefinition | None, skill_name: str) -> bool:
        """检查 skill 是否在 agent 的白名单中。

        若 agent_def 为 None（默认 coding agent），始终返回 True。
        """
        if agent_def is None:
            return True
        if not agent_def.allowed_skills:
            return True  # 未配置白名单 = 允许所有
        # 去掉版本号再匹配（claude_code@1.0.0 → claude_code）
        base_skill = skill_name.split("@")[0]
        return base_skill in agent_def.allowed_skills
