"use client";

import { cn, formatTime } from "@/lib/utils";
import { Boxes, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessagePayload } from "@/types";

interface SystemMessageCardProps {
  payload: ChatMessagePayload;
  timestamp: string;
  status?: string;
}

export function SystemMessageCard({ payload, timestamp, status }: SystemMessageCardProps) {
  const isRunning = status === "running" || status === "streaming";

  return (
    <div className="px-4 py-3 group">
      <div className="rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] px-4 py-3.5">
        {/* Header */}
        <div className="flex items-center gap-2.5 mb-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#111827] text-white">
            <Boxes className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <span className="text-sm font-medium text-[#111827]">Orchestrator</span>
            {isRunning && (
              <span className="inline-flex items-center gap-1 ml-2 text-xs text-[#6B7280]">
                <Loader2 className="h-3 w-3 animate-spin" />
                Running
              </span>
            )}
          </div>
          <span className="text-[10px] text-[#9CA3AF]">
            {formatTime(timestamp)}
          </span>
        </div>

        {/* Content */}
        {payload.format === "markdown" ? (
          <div className="prose prose-sm max-w-none text-sm text-[#6B7280] [&_p]:leading-[1.6] [&_li]:leading-[1.6]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {payload.content}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-[#6B7280] whitespace-pre-wrap break-words leading-relaxed">
            {payload.content}
          </p>
        )}
      </div>
    </div>
  );
}
