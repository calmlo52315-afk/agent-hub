"use client";

import { cn } from "@/lib/utils";
import { Loader2, Check } from "lucide-react";

interface ThinkBarProps {
  status: string;
  visible: boolean;
}

const STATUS_MAP: Record<string, string> = {
  planning: "Planning...",
  coding: "Generating code...",
  review: "Reviewing...",
  bundle: "Packaging...",
  completed: "Completed",
  creating: "Creating...",
  running: "Executing...",
};

export function ThinkBar({ status, visible }: ThinkBarProps) {
  if (!visible) return null;

  const isComplete = status === "completed";
  const displayText = STATUS_MAP[status] || status || "Processing...";

  return (
    <div className="flex items-center justify-center py-2 px-4 select-none">
      <div
        className={cn(
          "inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-[12px] font-medium transition-all duration-300",
          isComplete 
            ? "bg-[#10B981] text-white" 
            : "bg-[#F3F4F6] text-[#6B7280]"
        )}
      >
        {isComplete ? (
          <Check className="h-3.5 w-3.5" />
        ) : (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        )}
        {displayText}
      </div>
    </div>
  );
}
