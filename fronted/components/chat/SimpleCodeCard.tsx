"use client";

import type { FileContent } from "@/types";
import { Download, ArrowRightCircle, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/artifact/CodeBlock";
import { MarkdownPreview } from "@/components/artifact/MarkdownPreview";
import { useWorkspacePanelStore } from "@/stores/workspacePanelStore";
import { useMemo } from "react";

interface SimpleCodeCardProps {
  content: FileContent;
  title?: string;
  summary?: string;
}

const langMap: Record<string, string> = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  py: "python", go: "go", rs: "rust", json: "json", yaml: "yaml",
  yml: "yaml", md: "markdown", css: "css", html: "html", sql: "sql",
  sh: "bash", bash: "bash",
};

function detectLang(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "text";
  return langMap[ext] || ext;
}

export function SimpleCodeCard({ content, title }: SimpleCodeCardProps) {
  const lang = detectLang(content.path);
  const displayTitle = title || content.path.split("/").pop() || "File";
  const showPanel = useWorkspacePanelStore((s) => s.showPanel);
  const isPanelForced = useWorkspacePanelStore((s) => s.forceShow);
  const isMarkdown = lang === "markdown" || content.path.endsWith(".md");

  return (
    <div className="flex gap-3 px-6 py-3">
      {/* Avatar placeholder */}
      <div className="h-7 w-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center shrink-0 mt-0.5">
        <span className="text-[11px] font-semibold">C</span>
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        {/* Header */}
        <div className="flex items-center gap-1.5 mb-1">
          <span className="text-[13px] font-semibold text-[#111827]">
            Code Generator
          </span>
          <span className="text-[11px] text-[#9CA3AF]">· Generated</span>
          {isPanelForced && (
            <span className="inline-flex items-center gap-1 text-[10px] text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full">
              Workspace 已打开
            </span>
          )}
        </div>

        {/* Code Block directly */}
        {content.content && (
          <div className="rounded-[8px] rounded-bl-[4px] overflow-hidden">
            {/* Simple header */}
            <div className="flex items-center justify-between px-4 py-2 bg-[#F9FAFB] border border-b-0 border-[#E5E7EB] rounded-t-[8px]">
              <span className="text-sm font-medium text-[#111827]">
                {displayTitle}
              </span>
              <div className="flex items-center gap-1">
                {/* ⭐ Markdown 预览按钮 */}
                {isMarkdown && content.content && (
                  <MarkdownPreview
                    content={content.content}
                    title={displayTitle}
                    triggerLabel="Preview"
                    className="inline-flex items-center gap-1 shrink-0 h-7 text-xs rounded px-2 py-0.5 text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
                  />
                )}
                {!isPanelForced && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0 h-7 text-xs"
                    onClick={showPanel}
                  >
                    <ArrowRightCircle className="h-3 w-3 mr-1" />
                    在 Workspace 中查看
                  </Button>
                )}
                <Button variant="ghost" size="sm" className="shrink-0 h-7 text-xs" asChild>
                  <a
                    href={content.download_url}
                    download
                    className="flex items-center gap-1"
                  >
                    <Download className="h-3 w-3" />
                    下载
                  </a>
                </Button>
              </div>
            </div>
            {/* Code with no extra padding */}
            <CodeBlock
              code={content.content}
              lang={lang}
              maxHeight="500px"
            />
          </div>
        )}
      </div>
    </div>
  );
}
