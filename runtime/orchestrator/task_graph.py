from __future__ import annotations

"""Stage 4 task planning and DAG scheduling primitives.

This module introduces structured task and subtask objects so the Orchestrator
can move from a fixed serial chain to dependency-aware scheduling.
"""

import re
from dataclasses import dataclass, field
from typing import Any


class TaskPlanError(RuntimeError):
    """Raised when a task plan is structurally invalid or cannot be scheduled."""


_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_TERMINAL_STATUSES = {"success", "failed", "skipped"}
_FILE_PATTERN = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)")


@dataclass
class Subtask:
    """Represent one executable DAG node owned by a single runtime role.

    Each subtask is intentionally small and explicit about dependencies, target
    files and runtime constraints so Stage 4 can enforce ADR-007 granularity.
    """

    subtask_id: str
    title: str
    workflow_stage: str
    agent: str
    skill_name: str
    target_files: list[str]
    dependency_ids: list[str] = field(default_factory=list)
    priority: str = "medium"
    timeout_seconds: int = 300
    retry_limit: int = 1
    input_payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    attempt: int = 0
    required: bool = True
    order: int = 0
    output: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None

    def priority_rank(self) -> int:
        """Return the comparable priority rank used by the scheduler."""

        return _PRIORITY_ORDER.get(self.priority, _PRIORITY_ORDER["medium"])

    def to_dict(self) -> dict[str, Any]:
        """Serialize the subtask into a review-friendly structured object."""

        return {
            "subtask_id": self.subtask_id,
            "title": self.title,
            "workflow_stage": self.workflow_stage,
            "agent": self.agent,
            "skill_name": self.skill_name,
            "target_files": list(self.target_files),
            "dependency_ids": list(self.dependency_ids),
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "retry_limit": self.retry_limit,
            "status": self.status,
            "attempt": self.attempt,
            "required": self.required,
            "output": self.output,
            "failure": self.failure,
        }


@dataclass
class TaskPlan:
    """Represent the root task and the full subtask DAG for one execution."""

    task_id: str
    trace_id: str
    instruction: str
    subtasks: list[Subtask]

    def subtask_map(self) -> dict[str, Subtask]:
        """Index subtasks by identifier for dependency lookup."""

        return {subtask.subtask_id: subtask for subtask in self.subtasks}

    def get_subtask(self, subtask_id: str) -> Subtask:
        """Return one subtask by id or raise a plan error."""

        subtask = self.subtask_map().get(subtask_id)
        if subtask is None:
            raise TaskPlanError(f"unknown subtask: {subtask_id}")
        return subtask

    def validate(self) -> None:
        """Validate ids, role boundaries, file granularity and DAG acyclicity."""

        mapping = self.subtask_map()
        if len(mapping) != len(self.subtasks):
            raise TaskPlanError("duplicate subtask_id found in task plan")

        for subtask in self.subtasks:
            if subtask.agent not in ("coding", "review", "artifact"):
                raise TaskPlanError(f"invalid subtask agent: {subtask.subtask_id} -> {subtask.agent}")
            if not subtask.workflow_stage:
                raise TaskPlanError(f"missing workflow_stage: {subtask.subtask_id}")
            if len(subtask.target_files) > 3:
                raise TaskPlanError(f"subtask exceeds file granularity limit: {subtask.subtask_id}")
            for dep_id in subtask.dependency_ids:
                if dep_id == subtask.subtask_id:
                    raise TaskPlanError(f"subtask depends on itself: {subtask.subtask_id}")
                if dep_id not in mapping:
                    raise TaskPlanError(f"unknown dependency: {subtask.subtask_id} -> {dep_id}")

        visiting: set[str] = set()
        visited: set[str] = set()

        """
        visiting:当前正在走的路（一条 dag)，当前id 不能和我刚刚走过的节点重复否则认为出现环
        visited:走完的路，不影响当前走的这条路
        """
        def dfs(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise TaskPlanError(f"cycle detected at subtask: {node_id}")
            visiting.add(node_id)
            node = mapping[node_id]
            for dep_id in node.dependency_ids:
                dfs(dep_id)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in mapping:
            dfs(node_id)

    def dependencies_satisfied(self, subtask: Subtask) -> bool:
        """Return whether all direct dependencies have completed successfully."""

        return all(self.get_subtask(dep_id).status == "success" for dep_id in subtask.dependency_ids)

    def has_failed_dependency(self, subtask: Subtask) -> bool:
        """Return whether any dependency has irrecoverably failed."""

        return any(self.get_subtask(dep_id).status in ("failed", "skipped") for dep_id in subtask.dependency_ids)

    def dependency_outputs(self, subtask: Subtask) -> list[dict[str, Any]]:
        """Return structured outputs for all direct dependencies."""

        outputs: list[dict[str, Any]] = []
        for dep_id in subtask.dependency_ids:
            dep = self.get_subtask(dep_id)
            outputs.append(
                {
                    "subtask_id": dep.subtask_id,
                    "workflow_stage": dep.workflow_stage,
                    "status": dep.status,
                    "output": dep.output,
                }
            )
        return outputs

    def ready_subtasks(self, *, running_target_files: set[str]) -> list[Subtask]:
        """Return schedulable nodes ordered by priority and creation order."""

        ready: list[Subtask] = []
        for subtask in self.subtasks:
            if subtask.status in _TERMINAL_STATUSES or subtask.status == "running":
                continue
            if self.has_failed_dependency(subtask):
                subtask.status = "skipped"
                continue
            if not self.dependencies_satisfied(subtask):
                subtask.status = "blocked"
                continue
            if any(path in running_target_files for path in subtask.target_files):
                subtask.status = "blocked"
                continue
            subtask.status = "ready"
            ready.append(subtask)
        ready.sort(key=lambda item: (item.priority_rank(), item.order, item.subtask_id))
        return ready

    def mark_running(self, subtask_id: str) -> Subtask:
        """Move one subtask into the running state and increment its attempt."""

        subtask = self.get_subtask(subtask_id)
        subtask.status = "running"
        subtask.attempt += 1
        return subtask

    def mark_success(self, subtask_id: str, *, output: dict[str, Any]) -> Subtask:
        """Mark one subtask as successful and store its normalized output."""

        subtask = self.get_subtask(subtask_id)
        subtask.status = "success"
        subtask.output = output
        subtask.failure = None
        return subtask

    def mark_failed(self, subtask_id: str, *, failure: dict[str, Any]) -> Subtask:
        """Mark one subtask as failed and store the failure description."""

        subtask = self.get_subtask(subtask_id)
        subtask.status = "failed"
        subtask.failure = failure
        return subtask

    def has_required_failure(self) -> bool:
        """Return whether any required node has permanently failed."""

        return any(subtask.required and subtask.status == "failed" for subtask in self.subtasks)

    def all_required_success(self) -> bool:
        """Return whether all required nodes have completed successfully."""

        return all((not subtask.required) or subtask.status == "success" for subtask in self.subtasks)

    def all_terminal(self) -> bool:
        """Return whether every subtask reached a terminal status."""

        return all(subtask.status in _TERMINAL_STATUSES for subtask in self.subtasks)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full plan for diagnostics, replay and stage documents."""

        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "instruction": self.instruction,
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
        }


@dataclass(frozen=True)
class TaskPlanner:
    """Build deterministic Stage 4 task plans from user instruction and targets."""

    def _split_clauses(self, instruction: str) -> list[str]:
        """Split one instruction into coarse planning clauses."""

        normalized = instruction.replace("\n", "；")
        parts = re.split(r"[；;。]", normalized)
        clauses = [part.strip() for part in parts if part.strip()]
        return clauses or [instruction.strip()]

    def _infer_agent(self, clause: str) -> str:
        """Infer the target agent from explicit tags or clause keywords."""

        lowered = clause.lower()
        if "@coding" in lowered:
            return "coding"
        if "@review" in lowered:
            return "review"
        if "@artifact" in lowered:
            return "artifact"
        if any(token in lowered for token in ("review", "审核", "审查", "检查")):
            return "review"
        if any(token in lowered for token in ("artifact", "归档", "产物", "打包")):
            return "artifact"
        return "coding"

    def _infer_priority(self, clause: str) -> str:
        """Infer a normalized priority from clause wording."""

        lowered = clause.lower()
        if any(token in lowered for token in ("紧急", "critical", "urgent", "high")):
            return "high"
        if any(token in lowered for token in ("低优先级", "low priority", "later", "补充")):
            return "low"
        return "medium"

    def _extract_paths(self, clause: str, *, fallback_paths: list[str]) -> list[str]:
        """Extract repo-relative file paths from one clause."""

        found = [match.group("path") for match in _FILE_PATTERN.finditer(clause)]
        seen: set[str] = set()
        paths: list[str] = []
        for path in found or fallback_paths:
            normalized = path.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            paths.append(normalized)
        return paths

    def _chunk_paths(self, paths: list[str], *, chunk_size: int = 3) -> list[list[str]]:
        """Split file paths into ADR-007-compatible task chunks."""

        if not paths:
            return [[]]
        return [paths[index : index + chunk_size] for index in range(0, len(paths), chunk_size)]

    def _parallel_hint(self, clause: str, *, paths: list[str]) -> bool:
        """Return whether one clause hints that path chunks can run in parallel."""

        lowered = clause.lower()
        return len(paths) > 1 and any(token in lowered for token in ("并行", "parallel", "分别", "fanout"))

    def build_plan(
        self,
        *,
        task_id: str,
        trace_id: str,
        instruction: str,
        default_targets: list[dict[str, Any]],
        artifact_root: str,
    ) -> TaskPlan:
        """Build a generic Stage 4 task plan from instruction clauses.

        The planner uses lightweight heuristics:
        - `@coding/@review/@artifact` or clause keywords determine the agent
        - explicit file paths determine target files
        - coding clauses can fan out by ADR-007-sized file chunks
        - review and artifact clauses fan in over the relevant prior subtasks
        """

        default_paths = [str(item.get("path") or "") for item in default_targets if str(item.get("path") or "")]
        default_target_by_path = {
            str(item.get("path") or ""): {
                "path": str(item.get("path") or ""),
                "action": str(item.get("action") or "create"),
                "base_hash": item.get("base_hash") if isinstance(item.get("base_hash"), str) else None,
            }
            for item in default_targets
            if str(item.get("path") or "")
        }
        clauses = self._split_clauses(instruction)

        subtasks: list[Subtask] = []
        stage_counters = {"coding": 0, "review": 0, "artifact": 0}
        latest_clause_ids: list[str] = []
        coding_ids: list[str] = []
        review_ids: list[str] = []

        for clause in clauses:
            agent = self._infer_agent(clause)
            priority = self._infer_priority(clause)
            paths = self._extract_paths(clause, fallback_paths=(default_paths if agent == "coding" else []))
            path_chunks = self._chunk_paths(paths)
            current_clause_ids: list[str] = []

            if agent == "coding":
                for chunk in path_chunks:
                    stage_counters["coding"] += 1
                    subtask_id = f"coding-{stage_counters['coding']:03d}"
                    target_specs = []
                    for path in chunk:
                        target_specs.append(
                            default_target_by_path.get(
                                path,
                                {"path": path, "action": "create", "base_hash": None},
                            )
                        )
                    subtask = Subtask(
                        subtask_id=subtask_id,
                        title=f"编码子任务 {stage_counters['coding']}",
                        workflow_stage="coding",
                        agent="coding",
                        skill_name="coding.generate_patch",
                        target_files=[spec["path"] for spec in target_specs],
                        dependency_ids=([] if self._parallel_hint(clause, paths=paths) else list(latest_clause_ids)),
                        priority=("high" if priority == "high" else ("medium" if priority == "medium" else "low")),
                        timeout_seconds=600,
                        retry_limit=2,
                        input_payload={
                            "task": {
                                "instruction": clause,
                                "targets": target_specs,
                            }
                        },
                        order=len(subtasks),
                    )
                    subtasks.append(subtask)
                    current_clause_ids.append(subtask_id)
                    coding_ids.append(subtask_id)

            elif agent == "review":
                stage_counters["review"] += 1
                review_dependency_ids = list(coding_ids or latest_clause_ids)
                review_target_files = sorted(
                    {
                        path
                        for item in subtasks
                        if item.subtask_id in review_dependency_ids
                        for path in item.target_files
                    }
                ) or list(default_paths[:3])
                subtask_id = f"review-{stage_counters['review']:03d}"
                subtasks.append(
                    Subtask(
                        subtask_id=subtask_id,
                        title=f"评审子任务 {stage_counters['review']}",
                        workflow_stage="review",
                        agent="review",
                        skill_name="review.analyze_changes",
                        target_files=review_target_files[:3],
                        dependency_ids=review_dependency_ids,
                        priority=("high" if priority == "high" else "medium"),
                        timeout_seconds=300,
                        retry_limit=1,
                        order=len(subtasks),
                    )
                )
                current_clause_ids.append(subtask_id)
                review_ids.append(subtask_id)

            else:
                stage_counters["artifact"] += 1
                artifact_dependency_ids = list(review_ids or coding_ids or latest_clause_ids)
                subtask_id = f"artifact-{stage_counters['artifact']:03d}"
                subtasks.append(
                    Subtask(
                        subtask_id=subtask_id,
                        title=f"归档子任务 {stage_counters['artifact']}",
                        workflow_stage="artifact",
                        agent="artifact",
                        skill_name="artifact.package_result",
                        target_files=[f"{artifact_root.rstrip('/')}/{task_id}/metadata.json"],
                        dependency_ids=artifact_dependency_ids,
                        priority=("medium" if priority != "low" else "low"),
                        timeout_seconds=300,
                        retry_limit=1,
                        input_payload={"artifacts_root": artifact_root},
                        order=len(subtasks),
                    )
                )
                current_clause_ids.append(subtask_id)

            if current_clause_ids:
                latest_clause_ids = current_clause_ids

        if coding_ids and not review_ids:
            stage_counters["review"] += 1
            subtasks.append(
                Subtask(
                    subtask_id=f"review-{stage_counters['review']:03d}",
                    title="自动补齐评审节点",
                    workflow_stage="review",
                    agent="review",
                    skill_name="review.analyze_changes",
                    target_files=sorted(
                        {
                            path
                            for item in subtasks
                            if item.subtask_id in coding_ids
                            for path in item.target_files
                        }
                    )[:3],
                    dependency_ids=list(coding_ids),
                    priority="high",
                    timeout_seconds=300,
                    retry_limit=1,
                    order=len(subtasks),
                )
            )
            review_ids.append(subtasks[-1].subtask_id)
            latest_clause_ids = [subtasks[-1].subtask_id]

        if (coding_ids or review_ids) and not any(item.workflow_stage == "artifact" for item in subtasks):
            stage_counters["artifact"] += 1
            subtasks.append(
                Subtask(
                    subtask_id=f"artifact-{stage_counters['artifact']:03d}",
                    title="自动补齐归档节点",
                    workflow_stage="artifact",
                    agent="artifact",
                    skill_name="artifact.package_result",
                    target_files=[f"{artifact_root.rstrip('/')}/{task_id}/metadata.json"],
                    dependency_ids=list(review_ids or coding_ids or latest_clause_ids),
                    priority="medium",
                    timeout_seconds=300,
                    retry_limit=1,
                    input_payload={"artifacts_root": artifact_root},
                    order=len(subtasks),
                )
            )

        plan = TaskPlan(task_id=task_id, trace_id=trace_id, instruction=instruction, subtasks=subtasks)
        plan.validate()
        return plan

    def build_demo_plan(
        self,
        *,
        task_id: str,
        trace_id: str,
        instruction: str,
        targets: list[dict[str, Any]],
        artifact_root: str,
    ) -> TaskPlan:
        """Create the demo fan-out/fan-in plan with one coding node per target."""

        subtasks: list[Subtask] = []
        coding_ids: list[str] = []

        for index, target in enumerate(targets, start=1):
            path = str(target.get("path") or "")
            action = str(target.get("action") or "create")
            base_hash = target.get("base_hash") if isinstance(target.get("base_hash"), str) else None
            subtask_id = f"coding-{index:03d}"
            coding_ids.append(subtask_id)
            subtasks.append(
                Subtask(
                    subtask_id=subtask_id,
                    title=f"生成代码变更 {index}",
                    workflow_stage="coding",
                    agent="coding",
                    skill_name="coding.generate_patch",
                    target_files=[path],
                    dependency_ids=[],
                    priority="high" if index == 1 else "medium",
                    timeout_seconds=600,
                    retry_limit=2,
                    input_payload={
                        "task": {
                            "instruction": instruction,
                            "targets": [{"path": path, "action": action, "base_hash": base_hash}],
                        }
                    },
                    order=len(subtasks),
                )
            )

        review_id = "review-001"
        subtasks.append(
            Subtask(
                subtask_id=review_id,
                title="聚合评审所有编码结果",
                workflow_stage="review",
                agent="review",
                skill_name="review.analyze_changes",
                target_files=sorted({path for subtask in subtasks for path in subtask.target_files})[:3],
                dependency_ids=list(coding_ids),
                priority="high",
                timeout_seconds=300,
                retry_limit=1,
                order=len(subtasks),
            )
        )

        subtasks.append(
            Subtask(
                subtask_id="artifact-001",
                title="归档 Stage 4 执行产物",
                workflow_stage="artifact",
                agent="artifact",
                skill_name="artifact.package_result",
                target_files=[f"{artifact_root.rstrip('/')}/{task_id}/metadata.json"],
                dependency_ids=[review_id],
                priority="medium",
                timeout_seconds=300,
                retry_limit=1,
                input_payload={"artifacts_root": artifact_root},
                order=len(subtasks),
            )
        )

        plan = TaskPlan(task_id=task_id, trace_id=trace_id, instruction=instruction, subtasks=subtasks)
        plan.validate()
        return plan
