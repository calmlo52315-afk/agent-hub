"use client";

import { cn } from "@/lib/utils";
import { Bot } from "lucide-react";

interface AgentTagProps {
  agent: string;
  className?: string;
  showIcon?: boolean;
}

/**
 * Minimal agent tag — light gray pill, no colors
 */
export function AgentTag({
  agent,
  className,
  showIcon = false,
}: AgentTagProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-[#E5E7EB] bg-[#F3F4F6] px-2 py-0.5 text-[11px] font-medium text-[#374151]",
        className
      )}
    >
      {showIcon && <Bot className="h-3 w-3" />}
      {agent}
    </span>
  );
}
