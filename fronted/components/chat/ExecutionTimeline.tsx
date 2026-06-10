"use client";

import { useEffect, useState, useMemo } from "react";
import { useTaskStore } from "@/stores/taskStore";
import {
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronUp,
  ChevronDown,
  Zap
} from "lucide-react";
import { cn } from "@/lib/utils";

export function ExecutionTimeline() {
  const tasks = useTaskStore((s) => s.tasks);
  const [isExpanded, setIsExpanded] = useState(true);

  // 调试日志，查看实际的 task 数据
  if (tasks.length > 0) {
    console.log("ExecutionTimeline: current task", tasks[0]);
  }

  if (tasks.length === 0) return null;

  const task = tasks[0];
  const isSimpleTask = task.complexity === "simple";
  const isCompleted = task.status === "completed";
  const isFailed = task.status === "failed" || task.status === "cancelled";
  const isRunning = task.status === "running" || task.status === "retrying" || task.status === "scheduled";
  const isPlanning = task.status === "created" || task.status === "planning";

  // 当任务完成或失败时，自动折叠
  useEffect(() => {
    if (isCompleted || isFailed) {
      setIsExpanded(false);
    } else {
      setIsExpanded(true);
    }
  }, [isCompleted, isFailed]);

  // 简单任务显示逻辑
  if (isSimpleTask) {
    return (
      <div className="px-5 py-2">
        {/* 折叠状态的小卡片 */}
        {(isCompleted || isFailed) && !isExpanded && (
          <div
            className="rounded-[8px] border border-[#E5E7EB] bg-white p-3 cursor-pointer hover:bg-[#FAFAFA] transition-colors"
            onClick={() => setIsExpanded(true)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {isCompleted ? (
                  <CheckCircle2 className="h-5 w-5 text-[#10B981]" />
                ) : (
                  <XCircle className="h-5 w-5 text-[#DC2626]" />
                )}
                <span className={cn(
                  "text-[13px] font-semibold",
                  isCompleted ? "text-[#10B981]" : "text-[#DC2626]"
                )}>
                  {isCompleted ? "Code Generated" : "Failed"}
                </span>
              </div>
              <ChevronDown className="h-4 w-4 text-[#9CA3AF]" />
            </div>
          </div>
        )}

        {/* 展开状态的内容 */}
        {isExpanded && (
          <div className="rounded-[8px] border border-[#E5E7EB] bg-white p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="flex items-center justify-center h-6 w-6 rounded-full bg-[#F0FDF4]">
                  <Zap className="h-3.5 w-3.5 text-[#10B981]" />
                </div>
                <p className="text-[11px] font-semibold text-[#10B981] uppercase tracking-wider">
                  Quick Code Generation
                </p>
              </div>
              {(isCompleted || isFailed) && (
                <button
                  onClick={() => setIsExpanded(false)}
                  className="flex items-center gap-1 text-[#9CA3AF] hover:text-[#6B7280] transition-colors"
                >
                  <ChevronUp className="h-3.5 w-3.5" />
                  <span className="text-[11px]">Collapse</span>
                </button>
              )}
            </div>

            <div className="space-y-3">
              {/* 状态显示 */}
              <div className="flex items-center gap-2 text-[#6B7280]">
                {isPlanning && (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Thinking...</span>
                  </>
                )}
                {isRunning && (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Generating code...</span>
                  </>
                )}
                {isCompleted && (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-[#10B981]" />
                    <span className="text-[#10B981]">Successfully generated!</span>
                  </>
                )}
                {isFailed && (
                  <>
                    <XCircle className="h-4 w-4 text-[#DC2626]" />
                    <span className="text-[#DC2626]">Failed to generate</span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // 复杂任务的完整 Timeline - 直接使用 agent_flow 动态生成
  const agentLabelMap: Record<string, string> = {
    orchestrator: "Planning",
    coding: "Code Generation",
    review: "Code Review",
    artifact: "Artifact Packaging",
  };

  const phasesWithStatus = useMemo(() => {
    if (tasks.length === 0) return [];
    const task = tasks[0];
    const agentFlow = task.agent_flow || [];
    
    // 直接根据 agent_flow 生成阶段
    return agentFlow.map((agentKey: string, index: number) => {
      let status = "pending";
      const currentAgent = task.current_agent;
      const currentIndex = currentAgent ? agentFlow.indexOf(currentAgent) : -1;
      
      if (task.status === "completed") {
        status = "completed";
      } else if (task.status === "failed" || task.status === "cancelled") {
        if (index < currentIndex) status = "completed";
        else if (index === currentIndex) status = "failed";
        else status = "pending";
      } else {
        if (index < currentIndex) status = "completed";
        else if (index === currentIndex || (!currentAgent && index === 0)) {
          // 如果没有 currentAgent，默认第一个阶段是 in_progress
          status = "in_progress";
        } else status = "pending";
      }
      
      return {
        key: agentKey,
        label: agentLabelMap[agentKey] || agentKey,
        agentKey,
        status,
      };
    });
  }, [tasks]);

  // 只显示已完成和进行中的阶段，不显示 pending 的
  const visiblePhases = useMemo(() => {
    return phasesWithStatus.filter((p) => p.status !== "pending");
  }, [phasesWithStatus]);

  const allCompleted = phasesWithStatus.every((p) => p.status === "completed");
  const allFailed = phasesWithStatus.some((p) => p.status === "failed");

  return (
    <div className="px-5 py-2">
      {/* Collapsed State */}
      {(allCompleted || allFailed) && !isExpanded && (
        <div
          className="rounded-[8px] border border-[#E5E7EB] bg-white p-3 cursor-pointer hover:bg-[#FAFAFA] transition-colors"
          onClick={() => setIsExpanded(true)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {allCompleted ? (
                <CheckCircle2 className="h-5 w-5 text-[#10B981]" />
              ) : (
                <XCircle className="h-5 w-5 text-[#DC2626]" />
              )}
              <span className={cn(
                "text-[13px] font-semibold",
                allCompleted ? "text-[#10B981]" : "text-[#DC2626]"
              )}>
                {allCompleted ? "Task Complete" : "Task Failed"}
              </span>
            </div>
            <ChevronDown className="h-4 w-4 text-[#9CA3AF]" />
          </div>
        </div>
      )}

      {/* Expanded Timeline */}
      {isExpanded && (
        <div className="rounded-[8px] border border-[#E5E7EB] bg-white p-4">
          <div className="flex items-center justify-between mb-4">
            <p className="text-[11px] font-medium text-[#9CA3AF] uppercase tracking-[0.12em]">
              Execution Timeline
            </p>
            {(allCompleted || allFailed) && (
              <button
                onClick={() => setIsExpanded(false)}
                className="flex items-center gap-1 text-[#9CA3AF] hover:text-[#6B7280] transition-colors"
              >
                <ChevronUp className="h-3.5 w-3.5" />
                <span className="text-[11px]">Collapse</span>
              </button>
            )}
          </div>

          <div className="relative">
            {/* Vertical Line - 只在有多个阶段时显示 */}
            {visiblePhases.length > 1 && (
              <div className="absolute left-[11px] top-[24px] bottom-[24px] w-px bg-[#E5E7EB]" />
            )}

            <div className="space-y-4">
              {visiblePhases.map((phase, idx) => (
                <div key={phase.key} className="flex items-start gap-3 relative">
                  {/* Node Circle */}
                  <div className={cn(
                    "z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2",
                    phase.status === "in_progress" && "border-[#111827] bg-[#111827] animate-pulse",
                    phase.status === "completed" && "border-[#10B981] bg-[#10B981]",
                    phase.status === "failed" && "border-[#DC2626] bg-[#DC2626]",
                  )}>
                    {phase.status === "completed" && <CheckCircle2 className="h-3.5 w-3.5 text-white" />}
                    {phase.status === "failed" && <XCircle className="h-3.5 w-3.5 text-white" />}
                    {phase.status === "in_progress" && <Loader2 className="h-3.5 w-3.5 text-white animate-spin" />}
                  </div>

                  {/* Phase Content */}
                  <div className="mt-[2px]">
                    <p className={cn(
                      "text-[13px] font-medium",
                      phase.status === "in_progress" && "text-[#111827]",
                      phase.status === "completed" && "text-[#111827]",
                      phase.status === "failed" && "text-[#DC2626]",
                    )}>
                      {phase.label}
                    </p>
                    {phase.status === "in_progress" && (
                      <p className="text-[11px] text-[#9CA3AF] mt-0.5">In progress...</p>
                    )}
                    {phase.status === "completed" && (
                      <p className="text-[11px] text-[#9CA3AF] mt-0.5">Complete</p>
                    )}
                    {phase.status === "failed" && (
                      <p className="text-[11px] text-[#DC2626] mt-0.5">Failed</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
