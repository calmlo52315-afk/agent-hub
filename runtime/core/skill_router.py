from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.core.types import (
    TaskComplexity,
    SkillType,
)

logger = logging.getLogger(__name__)


@dataclass
class SkillDecision:
    """Skill Router 的决策结果"""
    skill_type: SkillType
    skill_name: str
    reason: str


class SkillRouter:
    """
    技能路由器 (Stage 10 重构版)

    Stage 10: 智能分流策略 —
    - 编码：SIMPLE/MEDIUM → Codex（速度快），PROJECT/imported → Claude Code（质量优先）
    - 审查：SIMPLE → 内置 LLM（轻量），MEDIUM+/PROJECT → Claude Code（深度审查）
    - 每层都有 CLI 可用性回退链
    """

    def __init__(self):
        pass

    def select_coding_skill(self, plan: Any) -> SkillDecision:
        """
        根据 plan 选择编码技能

        Stage 10 分流策略：scratch 工作区 → 内置 LLM，project/imported → Codex
        """
        from runtime.skills.external_cli import external_cli_available

        complexity = getattr(plan, "complexity", TaskComplexity.MEDIUM)
        workspace_type = getattr(plan, "workspace_type", "scratch")
        execution_mode = getattr(plan, "execution_mode", "task")

        print(f"[TRACE] [SkillRouter] select_coding_skill: complexity={complexity} workspace_type={workspace_type} execution_mode={execution_mode}")

        # scratch(demo) 工作区用内置 LLM，project/imported 用 Codex
        if workspace_type == "scratch":
            print(f"[TRACE] [SkillRouter] -> NATIVE_CODEGEN (scratch workspace, built-in LLM)")
            return SkillDecision(
                skill_type=SkillType.NATIVE_CODEGEN,
                skill_name="coding.generate_patch",
                reason="demo 工作区，内置 LLM 更简单高效",
            )

        if workspace_type == "imported" or execution_mode == "project":
            if external_cli_available("codex"):
                print(f"[TRACE] [SkillRouter] -> CODEX_CODING (workspace_type={workspace_type})", flush=True)
                return SkillDecision(
                    skill_type=SkillType.CODEX_CODING,
                    skill_name="codex_coding",
                    reason=f"workspace_type={workspace_type}, use Codex for direct coding",
                )

        if complexity == TaskComplexity.SIMPLE:
            # 简单任务 → Codex (速度快)
            if external_cli_available("codex"):
                print(f"[TRACE] [SkillRouter] -> CODEX_CODING (simple task, speed-first)")
                return SkillDecision(
                    skill_type=SkillType.CODEX_CODING,
                    skill_name="codex_coding",
                    reason=f"简单任务 (simple)，使用 Codex 快速生成",
                )
            # Codex 不可用 → 内置 LLM
            print(f"[TRACE] [SkillRouter] -> NATIVE_CODEGEN (codex not available)")
            return SkillDecision(
                skill_type=SkillType.NATIVE_CODEGEN,
                skill_name="coding.generate_patch",
                reason="Codex not available, fallback to built-in LLM",
            )

        if complexity == TaskComplexity.PROJECT:
            # 项目级任务 → Codex (速度快，能处理多文件)
            print(f"[TRACE] [SkillRouter] -> CODEX_CODING (project, Codex handles multi-file)")
            if external_cli_available("codex"):
                return SkillDecision(
                    skill_type=SkillType.CODEX_CODING,
                    skill_name="codex_coding",
                    reason=f"项目级任务 (project)，使用 Codex 处理多文件",
                )
            # Codex 不可用 → Claude Code
            if external_cli_available("claude"):
                print(f"[TRACE] [SkillRouter] -> CLAUDE_CODE (codex not available)")
                return SkillDecision(
                    skill_type=SkillType.CLAUDE_CODE,
                    skill_name="claude_code",
                    reason="Codex not available, fallback to Claude Code",
                )
            # 都不可用 → 内置 LLM
            print(f"[TRACE] [SkillRouter] -> NATIVE_CODEGEN (no external CLI available)")
            return SkillDecision(
                skill_type=SkillType.NATIVE_CODEGEN,
                skill_name="coding.generate_patch",
                reason="No external CLI available, fallback to built-in",
            )

        # MEDIUM (默认) → Codex (速度优先)
        if external_cli_available("codex"):
            print(f"[TRACE] [SkillRouter] -> CODEX_CODING (medium task, speed-first)")
            return SkillDecision(
                skill_type=SkillType.CODEX_CODING,
                skill_name="codex_coding",
                reason=f"中等任务 (medium)，默认使用 Codex 快速生成",
            )
        # Codex 不可用 → 内置 LLM
        print(f"[TRACE] [SkillRouter] -> NATIVE_CODEGEN (codex not available, fallback)")
        return SkillDecision(
            skill_type=SkillType.NATIVE_CODEGEN,
            skill_name="coding.generate_patch",
            reason="Codex not available, fallback to built-in LLM",
        )

    def select_review_skill(self, plan: Any) -> SkillDecision:
        """
        根据 plan 选择审查技能

        ⭐ Stage 10 分流策略 (角色标注):
        - SIMPLE → review.analyze_changes (内置 LLM/doubao，轻量快速) — simple_reviewer
        - MEDIUM/PROJECT → claude_review (Claude Code，深度审查，适合大项目) — deep_reviewer
        - Claude 不可用 → codex_review (Codex，快速开发周期) — quick_reviewer
        - 都不可用 → review.analyze_changes (内置 LLM 兜底)

        设计原则:
        - Claude Code: 适合大项目的深度审查修改，能利用 coding 阶段的完整上下文
        - Codex: 适合快速开发出项目，速度优先
        - Built-in LLM (doubao): 简单任务的快速审查
        """
        from runtime.skills.external_cli import external_cli_available

        complexity = getattr(plan, "complexity", TaskComplexity.MEDIUM)

        print(f"[TRACE] [SkillRouter] select_review_skill: complexity={complexity}")

        if complexity == TaskComplexity.SIMPLE:
            print(f"[TRACE] [SkillRouter] -> REVIEW (simple task, built-in doubao LLM — simple_reviewer)")
            return SkillDecision(
                skill_type=SkillType.REVIEW,
                skill_name="review.analyze_changes",
                reason=f"简单任务，使用内置 LLM (doubao simple_reviewer) 快速审查",
            )

        # MEDIUM/PROJECT → Claude Review (深度审查，大项目)
        if external_cli_available("claude"):
            print(f"[TRACE] [SkillRouter] -> CLAUDE_REVIEW (deep review — deep_reviewer)")
            return SkillDecision(
                skill_type=SkillType.CLAUDE_REVIEW,
                skill_name="claude_review",
                reason=f"{complexity} 任务，使用 Claude Code (deep_reviewer) 深度审查 — 适合大项目",
            )

        # Claude 不可用 → Codex Review 备选 (快速审查)
        if external_cli_available("codex"):
            print(f"[TRACE] [SkillRouter] -> CODEX_REVIEW (quick review — quick_reviewer)")
            return SkillDecision(
                skill_type=SkillType.CODEX_REVIEW,
                skill_name="codex_review",
                reason="Claude Code not available, fallback to Codex (quick_reviewer) — 适合快速开发",
            )

        # 都不可用 → 内置 LLM
        print(f"[TRACE] [SkillRouter] -> REVIEW (no external CLI, fallback to built-in)")
        return SkillDecision(
            skill_type=SkillType.REVIEW,
            skill_name="review.analyze_changes",
            reason="No external CLI available, fallback to built-in LLM (simple_reviewer)",
        )
