"use client";

import { AgentTag } from "@/components/chat/AgentTag";
import { cn } from "@/lib/utils";
import type { RealtimeMessage, TaskUpdatedPayload } from "@/types";
import {
  CheckCircle2,
  Loader2,
  Clock,
  AlertCircle,
  Circle,
  Sparkles,
  Code2,
  FileCheck,
  Package,
} from "lucide-react";

const getAgentIcon = (agent?: string) => {
  switch (agent) {
    case "orchestrator":
      return Sparkles;
    case "planning":
    case "planner":
      return Clock;
    case "coding":
      return Code2;
    case "review":
      return FileCheck;
    case "artifact":
      return Package;
    default:
      return Loader2;
  }
};

const getStatusSummary = (summary?: string, agent?: string) => {
  if (summary) {
    const lower = summary.toLowerCase();
    if (lower.includes("planning")) return "Planning...";
    else if (lower.includes("coding")) return "Coding...";
    else if (lower.includes("review")) return "Reviewing...";
    else if (lower.includes("artifact")) return "Packaging...";
    else if (lower.includes("created")) return "Task created";
    else if (lower.includes("completed")) return "Completed";
  }
  return summary || "Running...";
};

const statusConfig: Record<
  string,
  {
    icon: React.ComponentType<{ className?: string }>;
    label: string;
    color: string;
    bgColor: string;
    borderColor: string;
  }
> = {
  created:    { icon: Circle, label: "Created", color: "text-[#9CA3AF]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  planning:   { icon: Clock, label: "Planning", color: "text-[#6B7280]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  scheduled:  { icon: Clock, label: "Scheduled", color: "text-[#9CA3AF]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  running:    { icon: Loader2, label: "Running", color: "text-[#111827]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  blocked:    { icon: AlertCircle, label: "Blocked", color: "text-[#9CA3AF]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  retrying:   { icon: Loader2, label: "Retrying", color: "text-[#6B7280]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
  completed:  { icon: CheckCircle2, label: "Done", color: "text-[#10B981]", bgColor: "bg-[#F0FDF4]", borderColor: "border-[#A7F3D0]" },
  failed:     { icon: AlertCircle, label: "Failed", color: "text-[#DC2626]", bgColor: "bg-[#FEF2F2]", borderColor: "border-[#FECACA]" },
  cancelled:  { icon: AlertCircle, label: "Cancelled", color: "text-[#D1D5DB]", bgColor: "bg-white", borderColor: "border-[#E5E7EB]" },
};

interface TaskTimelineCardProps {
  message: RealtimeMessage;
}

export function TaskTimelineCard({ message }: TaskTimelineCardProps) {
  const payload = message.payload as unknown as TaskUpdatedPayload;
  const status = payload.status || "created";
  const config = statusConfig[status] || statusConfig.created;
  const Icon = payload.agent ? getAgentIcon(payload.agent) : config.icon;
  const displaySummary = getStatusSummary(payload.summary, payload.agent);
  const isCompleted = status === "completed";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-3 rounded-[8px] border px-4 py-3 text-sm max-w-full",
        config.bgColor,
        config.borderColor
      )}
    >
      <div className={cn(
        "flex items-center justify-center h-6 w-6 rounded-full shrink-0",
        isCompleted ? "bg-[#10B981]" : ""
      )}>
        <Icon
          className={cn(
            "h-4 w-4 shrink-0",
            isCompleted ? "text-white" : config.color,
            status === "running" || status === "retrying"
              ? "animate-spin"
              : ""
          )}
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={cn(
            "font-medium text-xs truncate",
            isCompleted ? "text-[#10B981]" : "text-[#111827]"
          )}>
            {displaySummary}
          </span>
          {payload.agent && (
            <AgentTag agent={payload.agent} showIcon={false} />
          )}
        </div>
        {payload.progress && (
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1.5 flex-1 rounded-full bg-[#E5E7EB] overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  isCompleted
                    ? "bg-[#10B981]"
                    : status === "failed"
                      ? "bg-[#DC2626]"
                      : "bg-[#111827]"
                )}
                style={{
                  width: `${Math.round(
                    (payload.progress.current / payload.progress.total) * 100
                  )}%`,
                }}
              />
            </div>
            <span className="text-[10px] text-[#9CA3AF] shrink-0">
              {payload.progress.current}/{payload.progress.total}
            </span>
          </div>
        )}
      </div>

      <span className={cn("text-[10px] font-medium shrink-0", config.color)}>
        {config.label}
      </span>
    </div>
  );
}
