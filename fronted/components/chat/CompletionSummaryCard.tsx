"use client";

import { CheckCircle2, Code2, ShieldCheck, Package } from "lucide-react";
import type { RealtimeMessage } from "@/types";

interface CompletionSummaryCardProps {
  message: RealtimeMessage;
  taskSummary?: {
    coding?: { files: number; additions: number; deletions: number };
    review?: { decision: string; score: number; issues: number };
    bundle?: { items: number };
  };
}

export function CompletionSummaryCard({ message, taskSummary }: CompletionSummaryCardProps) {
  const payload = message.payload as Record<string, unknown>;

  return (
    <div className="px-4 py-3">
      <div className="rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] px-4 py-4">
        {/* Header */}
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#111827] text-white">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <div>
            <span className="text-sm font-semibold text-[#111827]">
              Task Complete
            </span>
            <p className="text-xs text-[#9CA3AF]">
              All phases finished, summary below
            </p>
          </div>
        </div>

        {/* Pipeline Steps Summary */}
        <div className="grid grid-cols-3 gap-2">
          {/* Coding Step */}
          <div className="rounded-[6px] bg-white border border-[#E5E7EB] px-3 py-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <Code2 className="h-3.5 w-3.5 text-[#6B7280]" />
              <span className="text-xs font-medium text-[#111827]">Code Gen</span>
            </div>
            {taskSummary?.coding ? (
              <div className="text-[10px] text-[#9CA3AF] space-y-0.5">
                <p>{taskSummary.coding.files} files</p>
                <p className="text-[#6B7280]">+{taskSummary.coding.additions}</p>
                <p className="text-[#DC2626]">-{taskSummary.coding.deletions}</p>
              </div>
            ) : (
              <p className="text-[10px] text-[#9CA3AF]">Complete</p>
            )}
          </div>

          {/* Review Step */}
          <div className="rounded-[6px] bg-white border border-[#E5E7EB] px-3 py-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <ShieldCheck className="h-3.5 w-3.5 text-[#6B7280]" />
              <span className="text-xs font-medium text-[#111827]">Review</span>
            </div>
            {taskSummary?.review ? (
              <div className="text-[10px] text-[#9CA3AF] space-y-0.5">
                <p className={taskSummary.review.decision === "pass" ? "text-[#6B7280]" : "text-[#DC2626]"}>
                  {taskSummary.review.decision === "pass" ? "✓ PASS" : "✗ FAIL"}
                </p>
                <p>Score: {taskSummary.review.score}/100</p>
                <p>{taskSummary.review.issues} issues</p>
              </div>
            ) : (
              <p className="text-[10px] text-[#9CA3AF]">Complete</p>
            )}
          </div>

          {/* Bundle Step */}
          <div className="rounded-[6px] bg-white border border-[#E5E7EB] px-3 py-2.5">
            <div className="flex items-center gap-1.5 mb-1">
              <Package className="h-3.5 w-3.5 text-[#6B7280]" />
              <span className="text-xs font-medium text-[#111827]">Bundle</span>
            </div>
            {taskSummary?.bundle ? (
              <div className="text-[10px] text-[#9CA3AF] space-y-0.5">
                <p>{taskSummary.bundle.items} items</p>
              </div>
            ) : (
              <p className="text-[10px] text-[#9CA3AF]">Complete</p>
            )}
          </div>
        </div>

        {/* Summary text from payload */}
        {(payload.summary as string) && (
          <p className="text-xs text-[#9CA3AF] mt-3 border-t border-[#E5E7EB] pt-2">
            {(payload.summary as string)}
          </p>
        )}
      </div>
    </div>
  );
}
