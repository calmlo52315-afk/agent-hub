from __future__ import annotations

"""
Skill Runtime 负责做三件事：
1. 解析 Skill Registry；
2. 按 rules 校验白名单、调用方和预算；
3. 生成可被 Orchestrator 执行的调用计划。
"""

from dataclasses import dataclass
from typing import Any

from runtime.harness.permissions import PermissionDenied
from runtime.skills.base import SkillInvocationPlan
from runtime.skills.registry import SkillRegistry


class SkillRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillRuntime:
    execution_policy: dict[str, Any]
    permission_policy: dict[str, Any]
    registry: SkillRegistry

    def _skill_rules(self) -> dict[str, Any]:
        return ((self.permission_policy.get("rules") or {}).get("skills") or {})

    def _execution_skill_rules(self) -> dict[str, Any]:
        return ((self.execution_policy.get("rules") or {}).get("skills") or {})

    def _timeout_for_skill(self, skill_name: str, default_timeout_seconds: int) -> int:
        skill_rules = self._execution_skill_rules()
        skill_timeouts = skill_rules.get("skill_timeouts") or {}
        if isinstance(skill_timeouts, dict):
            value = skill_timeouts.get(skill_name)
            if isinstance(value, int) and value > 0:
                return value
        return default_timeout_seconds

    def _cost_budget(self) -> tuple[int, float]:
        budget = (self._execution_skill_rules().get("cost_budget") or {})
        max_tokens = budget.get("max_tokens")
        max_cost_usd = budget.get("max_cost_usd")
        if not isinstance(max_tokens, int) or max_tokens < 0:
            max_tokens = 0
        if not isinstance(max_cost_usd, (int, float)) or max_cost_usd < 0:
            max_cost_usd = 0.0
        return max_tokens, float(max_cost_usd)

    def assert_skill_allowed(self, *, role: str, skill_name: str, invoker: str) -> None:
        skill_rules = self._skill_rules()
        if not bool(skill_rules.get("enabled", False)):
            raise PermissionDenied("skill runtime disabled by permission rules")

        allowed_skills = skill_rules.get("allowed_skills") or []
        if skill_name not in allowed_skills:
            raise PermissionDenied(f"skill not allowed: {skill_name}")

        role_skill_whitelist = skill_rules.get("role_skill_whitelist") or {}
        role_allowed = role_skill_whitelist.get(role) or []
        if skill_name not in role_allowed:
            raise PermissionDenied(f"skill not allowed for role={role}: {skill_name}")

        definition = self.registry.resolve_active(skill_name)
        if invoker not in definition.allowed_invokers:
            raise PermissionDenied(f"skill invoker not allowed: {skill_name} <- {invoker}")

    def plan_invocation(
        self,
        *,
        skill_name: str,
        task_id: str,
        trace_id: str,
        payload: dict[str, Any],
        shared_state: dict[str, Any],
        invoker: str = "orchestrator",
    ) -> SkillInvocationPlan:
        definition = self.registry.resolve_active(skill_name)
        self.assert_skill_allowed(role=definition.agent_binding, skill_name=skill_name, invoker=invoker)

        skill_rules = self._execution_skill_rules()
        default_timeout_seconds = skill_rules.get("default_timeout_seconds")
        if not isinstance(default_timeout_seconds, int) or default_timeout_seconds <= 0:
            raise SkillRuntimeError("invalid default_timeout_seconds in execution rules")
        timeout_seconds = self._timeout_for_skill(skill_name, default_timeout_seconds)
        budget_tokens, budget_cost_usd = self._cost_budget()

        workflow_state = shared_state.get("workflow_state")
        context = {
            "workflow_state": str(workflow_state or ""),
            "shared_state_keys": sorted(str(key) for key in shared_state.keys()),
        }
        return SkillInvocationPlan(
            definition=definition,
            invoker=invoker,
            role=definition.agent_binding,
            task_id=task_id,
            trace_id=trace_id,
            payload=payload,
            context=context,
            timeout_seconds=timeout_seconds,
            budget_tokens=budget_tokens,
            budget_cost_usd=budget_cost_usd,
        )
