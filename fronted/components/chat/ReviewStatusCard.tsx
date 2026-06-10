"use client";

import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";

interface ReviewStatusCardProps {
  status: "reviewing" | "completed" | "failed";
  timestamp: string;
  issueCount?: number;
  latencyMs?: number;
}

/**
 * ⭐ Step 3: Review 状态卡片 — 在代码渲染后显示 Review 进行中/完成/失败的状态。
 * 设计为内联显示，位于代码卡片和 review 结果之间。
 */
export function ReviewStatusCard({
  status,
  issueCount,
  latencyMs,
}: ReviewStatusCardProps) {
  const formatLatency = (ms: number): string => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
    const minutes = Math.floor(ms / 60_000);
    const seconds = Math.round((ms % 60_000) / 1000);
    return `${minutes}m ${seconds}s`;
  };

  if (status === "reviewing") {
    return (
      <div className="px-6 py-2">
        <div className="rounded-[8px] border border-[#F59E0B]/30 bg-[#FFFBEB] px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-[#F59E0B]" />
            <span className="text-[13px] font-medium text-[#92400E]">
              🔍 Reviewing code...
            </span>
          </div>
          <p className="text-[11px] text-[#6B7280] mt-1 ml-6">
            Analyzing changes for security, logic, style, and performance issues
          </p>
        </div>
      </div>
    );
  }

  if (status === "completed") {
    const latencyStr = latencyMs ? formatLatency(latencyMs) : null;
    const hasIssues = issueCount && issueCount > 0;
    return (
      <div className="px-6 py-2">
        <div
          className={`rounded-[8px] border px-4 py-2.5 ${
            hasIssues
              ? "border-[#F59E0B]/30 bg-[#FFFBEB]"
              : "border-[#10B981]/30 bg-[#ECFDF5]"
          }`}
        >
          <div className="flex items-center gap-2">
            {hasIssues ? (
              <Clock className="h-4 w-4 text-[#F59E0B]" />
            ) : (
              <CheckCircle2 className="h-4 w-4 text-[#10B981]" />
            )}
            <span
              className={`text-[13px] font-medium ${
                hasIssues ? "text-[#92400E]" : "text-[#065F46]"
              }`}
            >
              {hasIssues
                ? `✅ Review Complete · ${issueCount} issue${issueCount !== 1 ? "s" : ""} found`
                : "✅ Review Passed · No issues found"}
            </span>
            {latencyStr && (
              <span className="text-[11px] text-[#6B7280]">· {latencyStr}</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // failed
  return (
    <div className="px-6 py-2">
      <div className="rounded-[8px] border border-[#DC2626]/30 bg-[#FEF2F2] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <XCircle className="h-4 w-4 text-[#DC2626]" />
          <span className="text-[13px] font-medium text-[#991B1B]">
            ❌ Review Failed
          </span>
        </div>
        <p className="text-[11px] text-[#6B7280] mt-1 ml-6">
          The review process encountered an error. Check the artifacts panel for
          details.
        </p>
      </div>
    </div>
  );
}
