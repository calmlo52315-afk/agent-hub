"use client";

import { CheckCircle2, Loader2, Circle } from "lucide-react";
import { useTaskStore } from "@/stores/taskStore";
import type { RealtimeMessage, TaskUpdatedPayload } from "@/types";
import { cn } from "@/lib/utils";

/**
 * ⭐ Step 4: 格式化耗时
 */
const formatLatency = (ms: number | undefined): string => {
  if (!ms || ms <= 0) return "";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
};

/**
 * 步骤类型定义
 */
interface TimelineStep {
  id: string;
  label: string;
  status: "pending" | "current" | "completed";
  latencyMs?: number;
}

    // 转换消息为可读的步骤标签
const getStepLabel = (payload: TaskUpdatedPayload): string => {
  const { summary, agent } = payload;

  if (summary) {
    const lower = summary.toLowerCase();

    // 更友好的标签
    if (lower.includes("gateway accepted")) return "Gateway accepted user instruction";
    if (lower.includes("task created")) return "Task created";
    if (lower.includes("planning")) return "Planning...";
    if (lower.includes("coding")) return "Coding...";
    if (lower.includes("review")) return "Reviewing...";
    if (lower.includes("artifact")) return "Packaging...";
    if (lower.includes("completed")) return "Completed";

    return summary;
  }

  // Fallback 基于 agent 类型
  const agentStr = agent as string | undefined;
  if (agentStr === "orchestrator" || agentStr === "planning" || agentStr === "planner") return "Planning...";
  if (agentStr === "coding") return "Coding...";
  if (agentStr === "review") return "Reviewing...";
  if (agentStr === "artifact") return "Packaging...";

  return "Processing...";
};

/**
 * ⭐ Step 4: 根据 label 推断耗时类型
 */
const getLatencyForStep = (label: string): number | undefined => {
  const tasks = useTaskStore.getState().tasks;
  if (tasks.length === 0) return undefined;
  const task = tasks[0];
  const lower = label.toLowerCase();
  if (lower.includes("coding") || lower.includes("code gen") || lower.includes("generate")) {
    return task.coding_latency_ms;
  }
  if (lower.includes("review")) {
    return task.review_latency_ms;
  }
  return undefined;
};

/**
 * 从多个消息中聚合出时间线步骤
 * 我们需要为每个任务聚合步骤，保持顺序
 */
const aggregateSteps = (messages: RealtimeMessage[]): TimelineStep[] => {
  const stepsMap = new Map<string, TimelineStep>();
  
  // 过滤并处理任务相关消息
  const taskMessages = messages.filter(msg => 
    msg.type === "task.created" || msg.type === "task.updated" || msg.type === "task.completed"
  );
  
  // 先收集所有可能的步骤（基于消息顺序）
  taskMessages.forEach((msg, index) => {
    const payload = msg.payload as unknown as TaskUpdatedPayload;
    const label = getStepLabel(payload);
    const status = payload.status;
    
    // 使用 label 作为 id，避免重复
    const stepId = label;
    
    if (!stepsMap.has(stepId)) {
      // ⭐ Step 4: 推断耗时
      const latencyMs = getLatencyForStep(label);
      // 新步骤
      stepsMap.set(stepId, {
        id: stepId,
        label,
        latencyMs,
        status: status === "completed" ? "completed" :
                status === "running" || status === "retrying" ? "current" : "current"
      });
    } else {
      // 更新现有步骤状态
      const existingStep = stepsMap.get(stepId)!;
      if (status === "completed") {
        existingStep.status = "completed";
        // ⭐ Step 4: 完成时更新耗时
        const latencyMs = getLatencyForStep(label);
        if (latencyMs) {
          existingStep.latencyMs = latencyMs;
        }
      }
    }
  });
  
  // 转换为数组并确保正确的顺序
  const steps = Array.from(stepsMap.values());
  
  // 确保只有一个步骤标记为 current
  let foundCurrent = false;
  for (let i = steps.length - 1; i >= 0; i--) {
    if (!foundCurrent && steps[i].status !== "completed") {
      steps[i].status = "current";
      foundCurrent = true;
    } else if (steps[i].status !== "completed") {
      steps[i].status = "completed"; // 如果不是最后一个，标记为完成
    }
  }
  
  return steps;
};

interface MinimalTimelineProps {
  messages: RealtimeMessage[];
}

export function MinimalTimeline({ messages }: MinimalTimelineProps) {
  const steps = aggregateSteps(messages);
  
  if (steps.length === 0) return null;
  
  return (
    <div className="flex justify-center py-4">
      <div className="flex flex-col items-start gap-0">
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          const hasNext = index < steps.length - 1;
          
          return (
            <div key={step.id} className="flex items-start gap-3">
              {/* 图标 */}
              <div className="flex flex-col items-center">
                {step.status === "completed" ? (
                  <CheckCircle2 className="h-5 w-5 text-[#10B981] shrink-0" />
                ) : step.status === "current" ? (
                  <div className="relative flex items-center justify-center">
                    <Loader2 className="h-5 w-5 text-[#6B7280] shrink-0 animate-spin" />
                  </div>
                ) : (
                  <Circle className="h-5 w-5 text-[#9CA3AF] shrink-0" />
                )}
                
                {/* 连接线 */}
                {hasNext && (
                  <div className={cn(
                    "w-0.5 h-6 mt-1",
                    steps[index + 1].status === "completed" ? "bg-[#10B981]" : "bg-[#E5E7EB]"
                  )} />
                )}
              </div>
              
              {/* 文字 + 耗时 */}
              <div className="pt-0.5">
                <span className={cn(
                  "text-sm leading-tight",
                  step.status === "completed" ? "text-[#4B5563]" : "text-[#374151]"
                )}>
                  {step.label}
                  {step.status === "completed" && step.latencyMs && step.latencyMs > 0 && (
                    <span className="text-[11px] text-[#9CA3AF] ml-1">
                      ({formatLatency(step.latencyMs)})
                    </span>
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
