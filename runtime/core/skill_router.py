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

        ⭐ Stage 10 分流策略 (速度优先 — 比赛场景):
        - 默认 → review.analyze_changes (内置 LLM/doubao，轻量快速 <5s)
        - SIMPLE/MEDIUM → review.analyze_changes (内置 LLM)
        - ~~PROJECT → claude_review~~ (太慢，比赛不用)
        - Claude Code 不可用 → codex_review
        - 都不可用 → review.analyze_changes (内置 LLM 兜底)

        设计原则:
        - 内置 LLM (doubao-seed-code): 快速审查，<5s 完成，适合比赛展示
        - Codex: 适中速度，适合日常开发
        - Claude Code: 深度慢速审查 (~60-300s)，仅在用户显式 @Claude Code review 时使用
        """
        from runtime.skills.external_cli import external_cli_available

        complexity = getattr(plan, "complexity", TaskComplexity.MEDIUM)

        print(f"[TRACE] [SkillRouter] select_review_skill: complexity={complexity}")

        # ⭐ 默认使用内置 LLM (doubao) — 快速、可靠、适合比赛
        if complexity in (TaskComplexity.SIMPLE, TaskComplexity.MEDIUM):
            print(f"[TRACE] [SkillRouter] -> REVIEW (built-in LLM doubao — fast <5s)")
            return SkillDecision(
                skill_type=SkillType.REVIEW,
                skill_name="review.analyze_changes",
                reason=f"{complexity} 任务，使用内置 LLM (doubao) 快速审查 — 适合比赛",
            )

        # PROJECT 复杂项目 — 优先 Codex review (比 Claude Code 快很多)
        if external_cli_available("codex"):
            print(f"[TRACE] [SkillRouter] -> CODEX_REVIEW (project, faster than Claude Code)")
            return SkillDecision(
                skill_type=SkillType.CODEX_REVIEW,
                skill_name="codex_review",
                reason=f"项目级任务 (project)，使用 Codex 审查 — 速度适中",
            )

        # 没有外部 CLI → 内置 LLM
        print(f"[TRACE] [SkillRouter] -> REVIEW (no external CLI, fallback to built-in)")
        return SkillDecision(
            skill_type=SkillType.REVIEW,
            skill_name="review.analyze_changes",
            reason="使用内置 LLM (doubao) 审查",
        )
