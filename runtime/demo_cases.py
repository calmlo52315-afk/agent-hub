from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from runtime.orchestrator import Orchestrator, OrchestratorError


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    title: str
    instruction: str


CASES: tuple[DemoCase, ...] = (
    DemoCase(
        case_id="demo-1-go-gin-api",
        title="生成 Go Gin API",
        instruction="请生成一个使用 Go 和 Gin 的最小 API 服务，包含 health check 和 todo 列表接口，并给出清晰的文件结构。",
    ),
    DemoCase(
        case_id="demo-2-react-todo-page",
        title="生成 React Todo 页面",
        instruction="请生成一个 React Todo 页面，支持新增、完成、删除任务，并提供清晰的组件结构与样式建议。",
    ),
    DemoCase(
        case_id="demo-3-modify-existing-api",
        title="修改已有代码并新增接口",
        instruction="请在现有服务中新增一个获取任务统计信息的接口，返回总任务数、已完成数和未完成数，并补充必要的返回结构说明。",
    ),
)


def _build_case_report(case: DemoCase, result: dict[str, Any]) -> dict[str, Any]:
    artifact_payload = (result.get("result") or {}).get("artifact") or {}
    task_plan = (result.get("result") or {}).get("task_plan") or {}
    # approval_pending 状态时 task_plan 在顶层
    if not task_plan:
        task_plan = result.get("task_plan") or {}
    if not artifact_payload:
        artifact_payload = result.get("artifact") or {}
    diagnostics = result.get("diagnostics") or []
    diagnostic_kinds = [item.get("kind") for item in diagnostics if isinstance(item, dict)]
    return {
        "case": asdict(case),
        "ok": bool(result.get("ok", True)),
        "task_id": result.get("task_id"),
        "trace_id": result.get("trace_id"),
        "status": result.get("status", "completed"),
        "execution_model": (result.get("result") or {}).get("execution_model"),
        "plan_targets": (task_plan.get("targets") or []),
        "artifact_dir": artifact_payload.get("artifact_dir"),
        "created_files": artifact_payload.get("created_files") or [],
        "diagnostic_kinds": diagnostic_kinds,
        "note": "当前报告验证的是流程闭环，不代表已生成真实语义代码。",
    }


def run_cases() -> list[dict[str, Any]]:
    os.environ.setdefault("AGENTHUB_DISABLE_EXTERNAL_CLI", "1")
    reports: list[dict[str, Any]] = []
    for case in CASES:
        orch = Orchestrator.load()
        try:
            result = orch.run_task(instruction=case.instruction)
        except OrchestratorError as exc:
            reports.append(
                {
                    "case": asdict(case),
                    "ok": False,
                    "error": str(exc),
                    "note": "当前案例执行失败。",
                }
            )
            continue

        # ── Human Approval: auto-resume modify tasks for demo ──
        if result.get("status") == "approval_pending":
            approval_result = orch.resume_task(
                task_id=result["task_id"],
                trace_id=result["trace_id"],
                approval_decision="approved",
                task_plan_dict=result["task_plan"],
                coding_output=result["coding_output"],
                review_output=result["review_output"],
                messages=result["messages"],
                diagnostics=result["diagnostics"],
            )
            reports.append(_build_case_report(case=case, result=approval_result))
            continue

        reports.append(_build_case_report(case=case, result=result))
    return reports


def _write_report(output: str, reports: list[dict[str, Any]]) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Stage 6 demo cases against current runtime.")
    parser.add_argument("--output", help="Write JSON report to file.")
    args = parser.parse_args(argv)

    reports = run_cases()
    sys.stdout.write(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    if args.output:
        _write_report(output=args.output, reports=reports)
    return 0 if all(bool(report.get("ok")) for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
