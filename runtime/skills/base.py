from __future__ import annotations

"""
Skill 基础协议与数据对象。
Stage 3 先把“能力”抽象成可注册、可路由的最小单元。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillDefinition:
    key: str
    skill_name: str
    version: str
    status: str
    owner: str
    entrypoint: str
    agent_binding: str
    workflow_stage: str
    input_schema_ref: str
    output_schema_ref: str
    error_schema_ref: str
    timeout_seconds: int
    allowed_invokers: tuple[str, ...]
    permission_scope: dict[str, Any]
    command: str = ""           # 外部 CLI 命令（如 claude, codex），仅 entrypoint=external_cli 时有效
    args_template: str = ""     # CLI 参数模板，{instruction} 等占位符在运行时替换
    mode: str = "interactive"   # 运行模式: interactive 或 headless
    output_format: str = "text" # 输出格式: text 或 json
    permission_mode: str = "default" # 权限模式: default, bypassPermissions, auto, dontAsk, plan


@dataclass(frozen=True)
class SkillInvocationPlan:
    definition: SkillDefinition
    invoker: str
    role: str
    task_id: str
    trace_id: str
    payload: dict[str, Any]
    context: dict[str, Any]
    timeout_seconds: int
    budget_tokens: int
    budget_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "skill_name": self.definition.skill_name,
            "version": self.definition.version,
            "invoker": {"type": "orchestrator", "id": self.invoker},
            "context": self.context,
            "payload": self.payload,
            "constraints": {
                "timeout_seconds": self.timeout_seconds,
                "budget_tokens": self.budget_tokens,
                "budget_cost_usd": self.budget_cost_usd,
            },
        }
