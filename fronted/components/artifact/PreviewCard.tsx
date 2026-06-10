"use client";

import type { PreviewContent } from "@/types";
import { Monitor, Smartphone, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface PreviewCardProps {
  content: PreviewContent;
  title: string;
  summary?: string;
}

export function PreviewCard({ content, title, summary }: PreviewCardProps) {
  const Icon = content.viewport === "mobile" ? Smartphone : Monitor;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2" style={{ padding: 16 }}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Icon className="h-4 w-4 text-[#6B7280]" />
            {title}
          </CardTitle>
          {content.framework && (
            <Badge variant="secondary" className="text-[10px] px-2">
              {content.framework}
            </Badge>
          )}
        </div>
        {summary && (
          <p className="text-xs text-[#9CA3AF] mt-0.5">{summary}</p>
        )}
      </CardHeader>
      <CardContent style={{ padding: "0 16px 16px" }}>
        <div className="rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] overflow-hidden">
          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-[#E5E7EB] bg-white">
            <div className="flex gap-1">
              <div className="h-2.5 w-2.5 rounded-full bg-[#FF5F57]" />
              <div className="h-2.5 w-2.5 rounded-full bg-[#FFBD2E]" />
              <div className="h-2.5 w-2.5 rounded-full bg-[#28C840]" />
            </div>
            <span className="text-[10px] text-[#9CA3AF] ml-2 font-mono truncate">
              {content.preview_url || content.entry_path || "Preview URL"}
            </span>
          </div>
          <div className="aspect-video flex items-center justify-center bg-[#F3F4F6]">
            {content.preview_url ? (
              <div className="text-center">
                <p className="text-xs text-[#9CA3AF] mb-2">
                  Preview ready
                </p>
                <a
                  href={content.preview_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-[#111827] hover:underline transition-colors font-medium"
                >
                  <ExternalLink className="h-3 w-3" />
                  Open preview
                </a>
              </div>
            ) : (
              <div className="text-center">
                <Monitor className="h-8 w-8 text-[#D1D5DB] mx-auto mb-2" />
                <p className="text-xs text-[#9CA3AF]">
                  Preview area (pending)
                </p>
                <p className="text-[10px] text-[#9CA3AF]">
                  Waiting for build...
                </p>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
