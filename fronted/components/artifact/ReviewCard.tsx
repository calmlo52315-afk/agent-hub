"use client";

import type { ReviewContent, ReviewIssue } from "@/types";
import {
  ShieldCheck,
  ShieldX,
  ShieldAlert,
  AlertTriangle,
  Info,
  Bug,
  Zap,
  Code2,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface ReviewCardProps {
  content: ReviewContent;
  title: string;
  summary?: string;
}

const severityConfig: Record<
  string,
  { icon: React.ComponentType<{ className?: string }>; color: string; bg: string; label: string }
> = {
  high: { icon: AlertTriangle, color: "text-[#DC2626]", bg: "bg-[#FEF2F2] border-[#FECACA]", label: "严重" },
  medium: { icon: Info, color: "text-[#D97706]", bg: "bg-[#FFFBEB] border-[#FDE68A]", label: "中等" },
  low: { icon: Info, color: "text-[#6B7280]", bg: "bg-[#F9FAFB] border-[#E5E7EB]", label: "轻微" },
};

const typeConfig: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string }> = {
  security: { icon: ShieldAlert, label: "安全" },
  logic: { icon: Bug, label: "逻辑" },
  style: { icon: Code2, label: "风格" },
  performance: { icon: Zap, label: "性能" },
};

export function ReviewCard({ content, title, summary }: ReviewCardProps) {
  // ⭐ Skipped state
  if (content.decision === "skipped") {
    return (
      <Card className="overflow-hidden">
        <CardHeader className="pb-2" style={{ padding: 16 }}>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-[#9CA3AF]" />
              {title}
            </CardTitle>
            <Badge variant="outline" className="text-[10px] px-2 text-[#9CA3AF]">
              已跳过
            </Badge>
          </div>
          <p className="text-xs text-[#9CA3AF] mt-1">
            简单任务，已跳过代码审查
          </p>
        </CardHeader>
      </Card>
    );
  }

  const passed = content.decision === "pass";
  const score = content.score ?? 100;
  const issues = content.issues ?? [];

  return (
    <Card
      className={cn(
        "overflow-hidden border-l-4",
        passed ? "border-l-[#10B981]" : "border-l-[#DC2626]"
      )}
    >
      <CardHeader className="pb-2" style={{ padding: 16 }}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            {passed ? (
              <ShieldCheck className="h-4 w-4 text-[#10B981]" />
            ) : (
              <ShieldX className="h-4 w-4 text-[#DC2626]" />
            )}
            {title}
          </CardTitle>
          <Badge
            className={cn(
              "text-[10px] px-2 font-semibold",
              passed
                ? "bg-[#D1FAE5] text-[#065F46]"
                : "bg-[#FEE2E2] text-[#991B1B]"
            )}
          >
            {passed ? "✓ PASS" : "✗ FAIL"}
          </Badge>
        </div>
        {summary && (
          <p className="text-xs text-[#9CA3AF] mt-0.5">{summary}</p>
        )}
        {/* Score bar */}
        <div className="flex items-center gap-2 mt-2">
          <span className={cn(
            "text-lg font-bold",
            score >= 80 ? "text-[#10B981]" : score >= 60 ? "text-[#D97706]" : "text-[#DC2626]"
          )}>
            {score}
          </span>
          <span className="text-xs text-[#9CA3AF]">/ 100</span>
          {content.files_reviewed ? (
            <span className="text-[10px] text-[#9CA3AF] ml-auto">
              {content.files_reviewed} 文件已审查
            </span>
          ) : null}
        </div>
        {/* Score bar visual */}
        <div className="mt-1.5 h-1.5 w-full rounded-full bg-[#F3F4F6] overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              score >= 80 ? "bg-[#10B981]" : score >= 60 ? "bg-[#D97706]" : "bg-[#DC2626]"
            )}
            style={{ width: `${score}%` }}
          />
        </div>
      </CardHeader>

      {issues.length > 0 && (
        <CardContent style={{ padding: "0 16px 16px" }}>
          <p className="text-xs font-medium text-[#374151] mb-2">
            发现问题 ({issues.length})
          </p>
          <div className="space-y-2">
            {issues.map((issue, idx) => {
              const cfg = severityConfig[issue.severity] || severityConfig.low;
              const SIcon = cfg.icon;
              const typeCfg = issue.type ? typeConfig[issue.type] : undefined;
              const TypeIcon = typeCfg?.icon;

              return (
                <div
                  key={idx}
                  className={cn(
                    "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-xs",
                    cfg.bg
                  )}
                >
                  <SIcon className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", cfg.color)} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[#111827] font-medium leading-snug">{issue.message}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {issue.paths && issue.paths.length > 0 && (
                        <span className="text-[10px] text-[#9CA3AF] font-mono bg-[#F3F4F6] px-1 rounded">
                          {issue.paths.join(", ")}
                        </span>
                      )}
                      {issue.line && (
                        <span className="text-[10px] text-[#9CA3AF] font-mono">
                          :{issue.line}
                        </span>
                      )}
                      {typeCfg && TypeIcon && (
                        <span className="inline-flex items-center gap-1 text-[10px] text-[#6B7280]">
                          <TypeIcon className="h-3 w-3" />
                          {typeCfg.label}
                        </span>
                      )}
                    </div>
                    {issue.suggestion && (
                      <p className="text-[10px] text-[#6B7280] mt-1.5 italic">
                        💡 {issue.suggestion}
                      </p>
                    )}
                  </div>
                  <Badge
                    variant="outline"
                    className={cn("text-[10px] px-1.5 h-4 shrink-0", cfg.color)}
                  >
                    {cfg.label}
                  </Badge>
                </div>
              );
            })}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
