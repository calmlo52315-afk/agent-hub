"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ScrollArea } from "@/components/ui/scroll-area";
import { X } from "lucide-react";

interface MarkdownPreviewProps {
  content: string;
  title?: string;
  triggerLabel?: string;
  className?: string;
}

/**
 * ⭐ Markdown 预览组件 — 点击按钮弹出 dialog，用 react-markdown 渲染 .md 内容。
 * 用于 SimpleCodeCard / FileCard 中 .md 文件的预览。
 */
export function MarkdownPreview({
  content,
  title = "Preview",
  triggerLabel = "Preview",
  className,
}: MarkdownPreviewProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(true)}
        className={className}
      >
        {triggerLabel}
      </button>

      {/* Dialog overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
          />
          {/* Panel */}
          <div className="relative z-10 w-full max-w-3xl max-h-[85vh] bg-white rounded-xl shadow-2xl border border-[#E5E7EB] flex flex-col mx-4">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E7EB] shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[13px] font-semibold text-[#111827] truncate">
                  {title}
                </span>
                <span className="text-[10px] text-[#9CA3AF] bg-[#F3F4F6] px-1.5 py-0.5 rounded">
                  Markdown
                </span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="flex items-center justify-center h-7 w-7 rounded-lg hover:bg-[#F3F4F6] transition-colors shrink-0"
              >
                <X className="h-4 w-4 text-[#6B7280]" />
              </button>
            </div>
            {/* Content */}
            <ScrollArea className="flex-1">
              <div className="px-6 py-4 prose prose-sm max-w-none text-[14px] leading-[1.7] [&_pre]:bg-[#1E293B] [&_pre]:border [&_pre]:border-[#334155] [&_pre]:rounded-lg [&_pre]:my-3 [&_code]:text-[13px] [&_p]:leading-[1.7] [&_li]:leading-[1.7] [&_blockquote]:border-l-2 [&_blockquote]:border-[#E5E7EB] [&_blockquote]:pl-4 [&_blockquote]:text-[#6B7280] [&_h1]:text-[20px] [&_h2]:text-[17px] [&_h3]:text-[15px] [&_table]:text-[13px] [&_th]:text-[13px] [&_td]:text-[13px]">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {content}
                </ReactMarkdown>
              </div>
            </ScrollArea>
          </div>
        </div>
      )}
    </>
  );
}
