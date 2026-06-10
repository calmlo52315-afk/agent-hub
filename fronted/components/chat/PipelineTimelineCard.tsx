"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, Loader2, Circle, XCircle } from "lucide-react";

interface PipelineStep {
  key: string;
  label: string;
}

const PIPELINE_STEPS: PipelineStep[] = [
  { key: "received", label: "Received" },
  { key: "planning", label: "Planning" },
  { key: "coding", label: "Coding" },
  { key: "review", label: "Review" },
  { key: "bundle", label: "Bundle" },
];

type StepStatus = "completed" | "running" | "failed" | "pending";

interface PipelineTimelineCardProps {
  currentStep?: string;
  stepStatuses?: Record<string, StepStatus>;
}

const statusConfig: Record<StepStatus, {
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  lineColor: string;
}> = {
  completed: { icon: CheckCircle2, color: "text-[#6B7280]", lineColor: "bg-[#D1D5DB]" },
  running: { icon: Loader2, color: "text-[#111827]", lineColor: "bg-[#D1D5DB]" },
  failed: { icon: XCircle, color: "text-[#DC2626]", lineColor: "bg-[#FECACA]" },
  pending: { icon: Circle, color: "text-[#D1D5DB]", lineColor: "bg-[#E5E7EB]" },
};

export function PipelineTimelineCard({
  currentStep,
  stepStatuses = {},
}: PipelineTimelineCardProps) {
  const getStepStatus = (stepKey: string, index: number): StepStatus => {
    if (stepStatuses[stepKey]) return stepStatuses[stepKey];

    const currentIdx = PIPELINE_STEPS.findIndex((s) => s.key === currentStep);
    if (currentIdx >= 0) {
      if (index < currentIdx) return "completed";
      if (index === currentIdx) return "running";
    }
    return "pending";
  };

  return (
    <div className="px-4 py-3">
      <div className="rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] px-4 py-3">
        <p className="text-xs font-medium text-[#9CA3AF] mb-3">
          Pipeline
        </p>

        <div className="flex items-center w-full">
          {PIPELINE_STEPS.map((step, idx) => {
            const status = getStepStatus(step.key, idx);
            const config = statusConfig[status];
            const Icon = config.icon;
            const isLast = idx === PIPELINE_STEPS.length - 1;

            return (
              <div key={step.key} className="flex items-center flex-1 min-w-0">
                <div className="flex flex-col items-center shrink-0">
                  <Icon
                    className={cn(
                      "h-5 w-5",
                      config.color,
                      status === "running" && "animate-spin"
                    )}
                  />
                  <span
                    className={cn(
                      "text-[10px] mt-1 text-center whitespace-nowrap",
                      status === "pending" ? "text-[#D1D5DB]" : "text-[#111827]"
                    )}
                  >
                    {step.label}
                  </span>
                </div>

                {!isLast && (
                  <div className="flex-1 h-0.5 mx-1 min-w-[12px]">
                    <div
                      className={cn(
                        "h-full rounded-full transition-colors duration-500",
                        status === "completed" ? "bg-[#D1D5DB]" : "bg-[#E5E7EB]"
                      )}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
