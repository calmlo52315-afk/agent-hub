from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from runtime.core.types import TaskComplexity

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    complexity: TaskComplexity
    reason: str


class TaskClassifier:
    """
    任务分类器 (Stage 9 重构版)

    complexity 不再由关键词匹配决定。
    Planner 是唯一决策源。
    TaskClassifier 只做简单修正:
      1. execution_mode == "project" -> PROJECT
      2. workspace_type == "imported" -> PROJECT
      3. task_type == "modify_existing_code" -> PROJECT
      4. 默认保留 planner 传入的 complexity
    """

    def classify(
        self,
        complexity: TaskComplexity = TaskComplexity.MEDIUM,
        execution_mode: str = "task",
        workspace_type: str = "scratch",
        task_type: str = "generic",
    ) -> ClassificationResult:
        """修正复杂度

        规则(优先级从高到低):
          1. execution_mode == "project" -> PROJECT
          2. workspace_type == "imported" -> PROJECT
          3. task_type == "modify_existing_code" -> PROJECT

        Args:
            complexity: Planner 输出的初始复杂度
            execution_mode: 执行模式 (task/project)
            workspace_type: 工作区类型 (scratch/project/imported)
            task_type: 任务类型

        Returns:
            ClassificationResult
        """
        print(f"[TRACE] [TaskClassifier] classify: complexity={complexity} execution_mode={execution_mode} workspace_type={workspace_type} task_type={task_type}")

        if execution_mode == "project":
            print(f"[TRACE] [TaskClassifier] -> PROJECT (execution_mode=project)", flush=True)
            return ClassificationResult(
                complexity=TaskComplexity.PROJECT,
                reason=f"execution_mode={execution_mode}",
            )

        if workspace_type == "imported":
            print(f"[TRACE] [TaskClassifier] -> PROJECT (workspace_type=imported)", flush=True)
            return ClassificationResult(
                complexity=TaskComplexity.PROJECT,
                reason=f"workspace_type={workspace_type}, 导入工作区视为项目级",
            )

        if task_type == "modify_existing_code":
            print(f"[TRACE] [TaskClassifier] -> PROJECT (task_type=modify_existing_code)", flush=True)
            return ClassificationResult(
                complexity=TaskComplexity.PROJECT,
                reason=f"task_type={task_type}",
            )

        print(f"[TRACE] [TaskClassifier] -> {complexity} (保留 planner 输出)", flush=True)
        return ClassificationResult(
            complexity=complexity,
            reason=f"保留 planner 输出: complexity={complexity}",
        )
