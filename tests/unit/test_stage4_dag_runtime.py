from __future__ import annotations

import unittest

from runtime.orchestrator import Orchestrator
from runtime.orchestrator.task_graph import Subtask, TaskPlan, TaskPlanError, TaskPlanner


class Stage4DagRuntimeTests(unittest.TestCase):
    def test_task_plan_ready_semantics_and_conflict_detection(self) -> None:
        plan = TaskPlan(
            task_id="task_001",
            trace_id="trace_001",
            instruction="stage4",
            subtasks=[
                Subtask(
                    subtask_id="coding_a",
                    title="A",
                    workflow_stage="coding",
                    agent="coding",
                    skill_name="coding.generate_patch",
                    target_files=["demo/a.txt"],
                    order=0,
                ),
                Subtask(
                    subtask_id="coding_b",
                    title="B",
                    workflow_stage="coding",
                    agent="coding",
                    skill_name="coding.generate_patch",
                    target_files=["demo/b.txt"],
                    order=1,
                ),
                Subtask(
                    subtask_id="review_a",
                    title="Review",
                    workflow_stage="review",
                    agent="review",
                    skill_name="review.analyze_changes",
                    target_files=["demo/a.txt", "demo/b.txt"],
                    dependency_ids=["coding_a", "coding_b"],
                    order=2,
                ),
            ],
        )
        plan.validate()

        ready = plan.ready_subtasks(running_target_files=set())
        self.assertEqual([item.subtask_id for item in ready], ["coding_a", "coding_b"])

        plan.mark_running("coding_a")
        ready = plan.ready_subtasks(running_target_files={"demo/a.txt"})
        self.assertEqual([item.subtask_id for item in ready], ["coding_b"])

        plan.mark_success("coding_a", output={"ok": True})
        plan.mark_success("coding_b", output={"ok": True})
        ready = plan.ready_subtasks(running_target_files=set())
        self.assertEqual([item.subtask_id for item in ready], ["review_a"])

    def test_task_plan_rejects_cycle(self) -> None:
        plan = TaskPlan(
            task_id="task_cycle",
            trace_id="trace_cycle",
            instruction="cycle",
            subtasks=[
                Subtask(
                    subtask_id="a",
                    title="A",
                    workflow_stage="coding",
                    agent="coding",
                    skill_name="coding.generate_patch",
                    target_files=["demo/a.txt"],
                    dependency_ids=["b"],
                ),
                Subtask(
                    subtask_id="b",
                    title="B",
                    workflow_stage="review",
                    agent="review",
                    skill_name="review.analyze_changes",
                    target_files=["demo/b.txt"],
                    dependency_ids=["a"],
                ),
            ],
        )

        with self.assertRaises(TaskPlanError):
            plan.validate()

    def test_task_planner_builds_parallel_fanout_plan(self) -> None:
        planner = TaskPlanner()
        plan = planner.build_demo_plan(
            task_id="task_stage4",
            trace_id="trace_stage4",
            instruction="parallel stage4",
            targets=[
                {"path": "demo_workspace/hello.txt", "action": "create", "base_hash": None},
                {"path": "demo_workspace/hello_parallel.txt", "action": "create", "base_hash": None},
            ],
            artifact_root="artifacts",
        )

        self.assertEqual(len(plan.subtasks), 4)
        self.assertEqual([subtask.workflow_stage for subtask in plan.subtasks], ["coding", "coding", "review", "artifact"])
        self.assertEqual(plan.get_subtask("review-001").dependency_ids, ["coding-001", "coding-002"])
        self.assertEqual(plan.get_subtask("artifact-001").dependency_ids, ["review-001"])

    def test_task_planner_parses_explicit_agent_clauses(self) -> None:
        planner = TaskPlanner()
        plan = planner.build_plan(
            task_id="task_generic",
            trace_id="trace_generic",
            instruction="@coding 修改 api/todo.py 和 tests/test_todo.py；@review 审核 todo 改动；@artifact 归档结果",
            default_targets=[{"path": "demo_workspace/hello.txt", "action": "create", "base_hash": None}],
            artifact_root="artifacts",
        )

        self.assertEqual([subtask.workflow_stage for subtask in plan.subtasks], ["coding", "review", "artifact"])
        self.assertEqual(plan.get_subtask("coding-001").target_files, ["api/todo.py", "tests/test_todo.py"])
        self.assertEqual(plan.get_subtask("review-001").dependency_ids, ["coding-001"])
        self.assertEqual(plan.get_subtask("artifact-001").dependency_ids, ["review-001"])

    def test_task_planner_auto_appends_review_and_artifact(self) -> None:
        planner = TaskPlanner()
        plan = planner.build_plan(
            task_id="task_auto",
            trace_id="trace_auto",
            instruction="开发 web/login.tsx 和 web/login.css",
            default_targets=[{"path": "web/login.tsx", "action": "create", "base_hash": None}],
            artifact_root="artifacts",
        )

        self.assertEqual([subtask.workflow_stage for subtask in plan.subtasks], ["coding", "review", "artifact"])
        self.assertEqual(plan.get_subtask("review-001").dependency_ids, ["coding-001"])
        self.assertEqual(plan.get_subtask("artifact-001").dependency_ids, ["review-001"])

    def test_task_planner_chunks_coding_files_by_granularity(self) -> None:
        planner = TaskPlanner()
        plan = planner.build_plan(
            task_id="task_chunk",
            trace_id="trace_chunk",
            instruction="@coding 修改 a.py、b.py、c.py、d.py；@review 审核改动",
            default_targets=[{"path": "a.py", "action": "create", "base_hash": None}],
            artifact_root="artifacts",
        )

        coding_subtasks = [subtask for subtask in plan.subtasks if subtask.workflow_stage == "coding"]
        self.assertEqual(len(coding_subtasks), 2)
        self.assertEqual(coding_subtasks[0].target_files, ["a.py", "b.py", "c.py"])
        self.assertEqual(coding_subtasks[1].target_files, ["d.py"])
        self.assertEqual(plan.get_subtask("review-001").dependency_ids, ["coding-001", "coding-002"])

    def test_scheduler_level_lock_reservations_conflict_and_release(self) -> None:
        orch = Orchestrator.load()
        path = orch.workspace._abs("demo_workspace/hello.txt")

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_lock",
            subtask_id="coding-001",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, [])

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_lock",
            subtask_id="coding-002",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, ["demo_workspace/hello.txt"])

        orch.ownership.release_subtask_locks(task_id="task_lock", subtask_id="coding-001")
        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_lock",
            subtask_id="coding-002",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, [])

    def test_scheduler_level_lock_reservations_expire(self) -> None:
        orch = Orchestrator.load()
        path = orch.workspace._abs("demo_workspace/hello.txt")

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_expire",
            subtask_id="coding-001",
            role="coding",
            paths=[path],
            mode="write",
            lease_seconds=0.01,
        )
        self.assertEqual(conflicts, [])

        import time

        time.sleep(0.03)
        expired = orch.ownership.purge_expired_reservations()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["path"], "demo_workspace/hello.txt")

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_expire",
            subtask_id="coding-002",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, [])

    def test_wait_queue_prevents_bypass_after_release(self) -> None:
        orch = Orchestrator.load()
        path = orch.workspace._abs("demo_workspace/hello.txt")

        self.assertEqual(
            orch.ownership.try_acquire_subtask_locks(
                task_id="task_wait",
                subtask_id="holder",
                role="coding",
                paths=[path],
                mode="write",
            ),
            [],
        )
        orch.ownership.enqueue_waiting_subtask(
            task_id="task_wait",
            subtask_id="waiter-old",
            role="coding",
            paths=[path],
            mode="write",
            priority_rank=2,
        )
        orch.ownership.release_subtask_locks(task_id="task_wait", subtask_id="holder")

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_wait",
            subtask_id="new-high",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, ["demo_workspace/hello.txt"])

        conflicts = orch.ownership.try_acquire_subtask_locks(
            task_id="task_wait",
            subtask_id="waiter-old",
            role="coding",
            paths=[path],
            mode="write",
        )
        self.assertEqual(conflicts, [])

    def test_wait_queue_aging_reduces_starvation(self) -> None:
        orch = Orchestrator.load()
        orch.ownership.policy.setdefault("rules", {}).setdefault("locking", {})["wait_age_boost_seconds"] = 0.01
        path = orch.workspace._abs("demo_workspace/hello.txt")

        orch.ownership.enqueue_waiting_subtask(
            task_id="task_starve",
            subtask_id="low-old",
            role="coding",
            paths=[path],
            mode="write",
            priority_rank=2,
        )

        import time

        time.sleep(0.03)
        orch.ownership.enqueue_waiting_subtask(
            task_id="task_starve",
            subtask_id="high-new",
            role="coding",
            paths=[path],
            mode="write",
            priority_rank=0,
        )

        waiters = orch.ownership.active_waiters(task_id="task_starve")
        self.assertGreaterEqual(len(waiters), 2)
        self.assertEqual(waiters[0]["subtask_id"], "low-old")

    def test_context_budget_trims_recent_events_and_dependency_summaries(self) -> None:
        orch = Orchestrator.load()
        orch._context_budget_bytes = lambda: 420  # type: ignore[method-assign]

        planner = TaskPlanner()
        plan = planner.build_demo_plan(
            task_id="task_budget",
            trace_id="trace_budget",
            instruction="parallel budget",
            targets=[
                {"path": "demo_workspace/hello.txt", "action": "create", "base_hash": None},
                {"path": "demo_workspace/hello_parallel.txt", "action": "create", "base_hash": None},
            ],
            artifact_root="artifacts",
        )
        plan.get_subtask("coding-001").status = "success"
        plan.get_subtask("coding-001").output = {
            "applied_changes": [{"path": "a.txt"} for _ in range(10)],
            "content_samples": {f"path_{idx}.txt": "hello" for idx in range(10)},
        }
        plan.get_subtask("coding-002").status = "success"
        plan.get_subtask("coding-002").output = {
            "applied_changes": [{"path": "b.txt"} for _ in range(10)],
            "content_samples": {f"other_{idx}.txt": "hello" for idx in range(10)},
        }

        diagnostics = [
            {"kind": "diagnostic", "message": f"event-{idx}-" + ("x" * 80)}
            for idx in range(20)
        ]
        review_subtask = plan.get_subtask("review-001")
        context = orch._build_subtask_context(plan=plan, subtask=review_subtask, diagnostics=diagnostics)

        self.assertLessEqual(context["budget"]["actual_bytes"], 420)
        self.assertTrue(context["budget"]["trimmed"])
        self.assertLess(len(context["recent_events"]), 10)

    def test_blocked_subtask_can_be_requeued_after_release(self) -> None:
        orch = Orchestrator.load()
        planner = TaskPlanner()
        plan = planner.build_demo_plan(
            task_id="task_requeue",
            trace_id="trace_requeue",
            instruction="parallel stage4",
            targets=[
                {"path": "demo_workspace/hello.txt", "action": "create", "base_hash": None},
                {"path": "demo_workspace/hello_parallel.txt", "action": "create", "base_hash": None},
            ],
            artifact_root="artifacts",
        )
        blocked = plan.get_subtask("review-001")
        blocked.status = "blocked"
        for dep_id in blocked.dependency_ids:
            dep = plan.get_subtask(dep_id)
            dep.status = "success"
            dep.output = {"ok": True}

        diagnostics: list[dict[str, str]] = []
        orch._requeue_blocked_subtasks(plan=plan, diagnostics=diagnostics)

        self.assertEqual(blocked.status, "pending")
        self.assertTrue(any(item.get("kind") == "subtask_requeued" for item in diagnostics))

    def test_orchestrator_run_demo_task_uses_stage4_task_plan(self) -> None:
        orch = Orchestrator.load()

        result = orch.run_demo_task(instruction="parallel smoke stage4")

        self.assertTrue(result["ok"])
        diagnostics = result.get("diagnostics") or []
        kinds = [item.get("kind") for item in diagnostics if isinstance(item, dict)]
        self.assertIn("task_planned", kinds)
        self.assertIn("subtask_dispatched", kinds)

        task_plan = ((result.get("result") or {}).get("task_plan") or {})
        subtasks = task_plan.get("subtasks") or []
        self.assertGreaterEqual(len(subtasks), 4)

        artifact_payload = (result.get("result") or {}).get("artifact") or {}
        self.assertIsInstance(artifact_payload.get("artifact_dir"), str)


if __name__ == "__main__":
    unittest.main()
