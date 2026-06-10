"use client";

import { useState } from "react";
import type { FileContent } from "@/types";
import { FileText, Download, File, Eye } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CodeBlock } from "./CodeBlock";
import { MarkdownPreview } from "./MarkdownPreview";

interface FileCardProps {
  content: FileContent;
  title: string;
  summary?: string;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

export function FileCard({ content, title, summary }: FileCardProps) {
  const lang = detectLang(content.path);
  const isMarkdown = lang === "markdown" || content.path.endsWith(".md");
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2" style={{ padding: 16 }}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <FileText className="h-4 w-4 text-[#6B7280]" />
            {title}
          </CardTitle>
        </div>
        {summary && (
          <p className="text-xs text-[#9CA3AF] mt-0.5">{summary}</p>
        )}
      </CardHeader>
      <CardContent style={{ padding: "0 16px 16px" }}>
        {/* File Info */}
        <div className="flex items-center justify-between rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] px-3 py-2.5 mb-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#111827]">
              <File className="h-4 w-4 text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-mono truncate text-[#111827]">{content.path}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <Badge variant="secondary" className="text-[10px] px-1.5 h-4">
                  {content.mime_type}
                </Badge>
                <span className="text-[10px] text-[#9CA3AF]">
                  {formatBytes(content.size_bytes)}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {/* ⭐ Markdown 预览按钮 */}
            {isMarkdown && content.content && (
              <MarkdownPreview
                content={content.content}
                title={title}
                triggerLabel="Preview"
                className="inline-flex items-center gap-1 shrink-0 h-8 text-xs rounded px-2 py-0.5 text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
              />
            )}
            <Button variant="ghost" size="sm" className="shrink-0 h-8" asChild>
              <a
                href={content.download_url}
                download
                className="flex items-center gap-1 text-xs"
              >
                <Download className="h-3 w-3" />
                Download
              </a>
            </Button>
          </div>
        </div>

        {/* File Content Preview */}
        {content.content && (
          <CodeBlock
            code={content.content}
            lang={lang}
            maxHeight="300px"
          />
        )}
      </CardContent>
    </Card>
  );
}
