from __future__ import annotations

from enum import Enum
from dataclasses import dataclass
from typing import Any


class TaskComplexity(str, Enum):
    """任务复杂度分类"""
    SIMPLE = "simple"
    MEDIUM = "medium"
    PROJECT = "project"


class SkillType(str, Enum):
    """技能类型"""
    NATIVE_CODEGEN = "native_codegen"
    CLAUDE_CODE = "claude_code"
    CODEX_CODING = "codex_coding"
    CODEX_REVIEW = "codex_review"
    CLAUDE_REVIEW = "claude_review"
    PLANNER = "planner"
    REVIEW = "review"


class AgentType(str, Enum):
    """Agent 类型"""
    PLANNER = "planner"
    CODING = "coding"
    REVIEW = "review"
    CUSTOM = "custom"


@dataclass
class TaskContext:
    """任务上下文，用于 Skill Router 决策

    complexity 由 Planner 输出决定, 不再由 TaskClassifier 关键词推断.
    workspace_type 由前端传入(scratch / project / imported),
    imported 时强制 PROJECT 复杂度.
    """
    complexity: TaskComplexity
    task_type: str
    language: str | None = None
    target_count: int = 1
    execution_mode: str = "task"
    review_required: bool = False
    workspace_type: str = "scratch"

    def is_simple(self) -> bool:
        return self.complexity == TaskComplexity.SIMPLE

    def is_project(self) -> bool:
        return self.complexity == TaskComplexity.PROJECT

