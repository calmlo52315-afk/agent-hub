from __future__ import annotations

"""
Skill 注册表负责把 runtime/specs/skills.registry.json 转成可消费对象。
当前只实现最小查询能力，避免过早把编排层做成复杂 DAG。
"""

from dataclasses import dataclass

from runtime.config.spec_loader import Spec
from runtime.skills.base import SkillDefinition


class SkillRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillRegistry:
    definitions: dict[str, SkillDefinition]

    @classmethod
    def from_spec(cls, spec: Spec) -> "SkillRegistry":
        definitions: dict[str, SkillDefinition] = {}
        for key, raw in (spec.skills or {}).items():
            if not isinstance(raw, dict):
                raise SkillRegistryError(f"invalid skill entry: {key}")
            skill_name = raw.get("skill_name")
            version = raw.get("version")
            agent_binding = raw.get("agent_binding")
            workflow_stage = raw.get("workflow_stage")
            if not all(isinstance(v, str) and v for v in (skill_name, version, agent_binding, workflow_stage)):
                raise SkillRegistryError(f"invalid skill metadata: {key}")
            allowed_invokers = raw.get("allowed_invokers") or []
            if not isinstance(allowed_invokers, list):
                raise SkillRegistryError(f"invalid allowed_invokers: {key}")
            timeout_seconds = raw.get("timeout_seconds")
            if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
                raise SkillRegistryError(f"invalid timeout_seconds: {key}")
            command = raw.get("command")
            args_template = raw.get("args_template")
            mode = raw.get("mode")
            output_format = raw.get("output_format")
            permission_mode = raw.get("permission_mode")
            definitions[key] = SkillDefinition(
                key=key,
                skill_name=skill_name,
                version=version,
                status=str(raw.get("status") or "active"),
                owner=str(raw.get("owner") or "runtime"),
                entrypoint=str(raw.get("entrypoint") or "agent"),
                agent_binding=agent_binding,
                workflow_stage=workflow_stage,
                input_schema_ref=str(raw.get("input_schema_ref") or ""),
                output_schema_ref=str(raw.get("output_schema_ref") or ""),
                error_schema_ref=str(raw.get("error_schema_ref") or ""),
                timeout_seconds=timeout_seconds,
                allowed_invokers=tuple(str(v) for v in allowed_invokers if isinstance(v, str) and v),
                permission_scope=(raw.get("permission_scope") if isinstance(raw.get("permission_scope"), dict) else {}),
                command=str(command) if isinstance(command, str) and command else "",
                args_template=str(args_template) if isinstance(args_template, str) and args_template else "",
                mode=str(mode) if isinstance(mode, str) and mode else "interactive",
                output_format=str(output_format) if isinstance(output_format, str) and output_format else "text",
                permission_mode=str(permission_mode) if isinstance(permission_mode, str) and permission_mode else "default",
            )
        return cls(definitions=definitions)

    def get(self, key: str) -> SkillDefinition:
        skill = self.definitions.get(key)
        if skill is None:
            raise SkillRegistryError(f"unknown skill: {key}")
        return skill

    def resolve_active(self, skill_name: str) -> SkillDefinition:
        matches = [
            skill
            for skill in self.definitions.values()
            if skill.skill_name == skill_name and skill.status == "active"
        ]
        if not matches:
            raise SkillRegistryError(f"active skill not found: {skill_name}")
        if len(matches) > 1:
            raise SkillRegistryError(f"multiple active versions found: {skill_name}")
        return matches[0]

    def resolve_stage(self, workflow_stage: str, *, prefer_entrypoint: str | None = None) -> SkillDefinition:
        """Return the active skill for *workflow_stage*.

        When *prefer_entrypoint* is set, skills with that entrypoint are favored.
        ⭐ Stage 9: Default preference is ``"agent"`` — built-in agents are preferred
        over external CLI tools for speed and reliability.
        """
        matches = [
            skill
            for skill in self.definitions.values()
            if skill.workflow_stage == workflow_stage and skill.status == "active"
        ]
        if not matches:
            raise SkillRegistryError(f"active stage skill not found: {workflow_stage}")

        if len(matches) == 1:
            return matches[0]

        # 多匹配时按 entrypoint 优先级选择
        effective_preference = prefer_entrypoint or "agent"
        preferred = [s for s in matches if s.entrypoint == effective_preference]
        if preferred:
            return preferred[0]

        # 无匹配的 entrypoint 时，优先 agent，其次 external_cli
        for entrypoint in ("agent", "external_cli", "tool", "workflow"):
            candidates = [s for s in matches if s.entrypoint == entrypoint]
            if candidates:
                return candidates[0]

        raise SkillRegistryError(f"no suitable entrypoint among {len(matches)} skills for stage: {workflow_stage}")
