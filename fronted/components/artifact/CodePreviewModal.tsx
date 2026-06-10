"use client";

import { useState, useEffect } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { CodeBlock } from "./CodeBlock";
import { X, Copy, Download } from "lucide-react";
import { cn } from "@/lib/utils";

interface CodePreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  code: string;
  lang?: string;
  title?: string;
}

export function CodePreviewModal({
  open,
  onOpenChange,
  code,
  lang = "text",
  title = "代码预览",
}: CodePreviewModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const ta = document.createElement("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    const blob = new Blob([code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = title.replace(/[^a-zA-Z0-9]/g, "_") + `.${lang}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        {/* Overlay */}
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />

        {/* Content */}
        <Dialog.Content
          className={cn(
            "fixed inset-4 z-50 bg-[#0d1117] rounded-xl border border-border/40 shadow-2xl",
            "flex flex-col",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border/20 shrink-0">
            <div className="min-w-0 flex-1">
              <Dialog.Title className="text-sm font-medium text-foreground truncate">
                {title}
              </Dialog.Title>
              <p className="text-[10px] text-muted-foreground font-mono uppercase">
                {lang}
              </p>
            </div>
            <div className="flex items-center gap-1 ml-4">
              <button
                onClick={handleCopy}
                className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors"
              >
                <Copy className="h-3.5 w-3.5" />
                {copied ? "已复制" : "复制"}
              </button>
              <button
                onClick={handleDownload}
                className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors"
              >
                <Download className="h-3.5 w-3.5" />
                下载
              </button>
              <Dialog.Close asChild>
                <button
                  className="inline-flex items-center justify-center h-8 w-8 rounded-md hover:bg-white/10 transition-colors"
                  aria-label="关闭"
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              </Dialog.Close>
            </div>
          </div>

          {/* Body */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <CodeBlock
              code={code}
              lang={lang}
              showLineNumbers
              maxHeight="100%"
              className="h-full border-0 rounded-none"
            />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
