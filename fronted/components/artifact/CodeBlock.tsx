"use client";

import { useState, useEffect, useCallback } from "react";
import { Copy, Check, Maximize2, Loader2, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/utils";

interface DiffLineMarker {
  line: number;
  type: "add" | "remove";
}

interface CodeBlockProps {
  code: string;
  lang?: string;
  showLineNumbers?: boolean;
  diffMarkers?: DiffLineMarker[];
  maxHeight?: string;
  className?: string;
  onFullscreen?: () => void;
}

export function CodeBlock({
  code,
  lang = "text",
  showLineNumbers = true,
  diffMarkers = [],
  maxHeight = "400px",
  className,
  onFullscreen,
}: CodeBlockProps) {
  const [html, setHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [isDark, setIsDark] = useState(false); // Default to light

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const highlight = async () => {
      try {
        const { codeToHtml } = await import("shiki");
        const result = await codeToHtml(code, {
          lang,
          theme: isDark ? "github-dark" : "github-light",
        });
        if (!cancelled) {
          setHtml(result);
          setLoading(false);
        }
      } catch {
        if (!cancelled) {
          setHtml(
            `<pre class="shiki ${isDark ? 'github-dark' : 'github-light'}"><code>${escapeHtml(code)}</code></pre>`
          );
          setLoading(false);
        }
      }
    };

    highlight();
    return () => {
      cancelled = true;
    };
  }, [code, lang, isDark]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [code]);

  const toggleTheme = () => {
    setIsDark(!isDark);
  };

  return (
    <div className={cn(
      "relative group rounded-2xl overflow-hidden border",
      isDark 
        ? "border-[#334155] bg-[#1E293B]" 
        : "border-[#E5E7EB] bg-[#FFFFFF]",
      "[box-shadow:none]",
      className
    )}>
      {/* Action Bar */}
      <div className={cn(
        "flex items-center justify-between px-4 py-2 border-b",
        isDark 
          ? "bg-[#1E293B] border-[#334155]" 
          : "bg-[#F9FAFB] border-[#E5E7EB]"
      )}>
        <span className={cn(
          "text-[10px] font-mono uppercase",
          isDark ? "text-[#94A3B8]" : "text-[#6B7280]"
        )}>
          {lang}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={toggleTheme}
            className={cn(
              "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] transition-colors",
              isDark 
                ? "text-[#94A3B8] hover:text-white hover:bg-white/10" 
                : "text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB]"
            )}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {isDark ? <Sun className="h-3 w-3" /> : <Moon className="h-3 w-3" />}
          </button>
          
          <button
            onClick={handleCopy}
            className={cn(
              "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] transition-colors",
              isDark 
                ? "text-[#94A3B8] hover:text-white hover:bg-white/10" 
                : "text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB]"
            )}
            title="Copy code"
          >
            {copied ? (
              <>
                <Check className={cn("h-3 w-3", isDark ? "text-[#86EFAC]" : "text-[#10B981]")} />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                Copy
              </>
            )}
          </button>

          {onFullscreen && (
            <button
              onClick={onFullscreen}
              className={cn(
                "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] transition-colors",
                isDark 
                  ? "text-[#94A3B8] hover:text-white hover:bg-white/10" 
                  : "text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB]"
              )}
              title="Fullscreen"
            >
              <Maximize2 className="h-3 w-3" />
              Full
            </button>
          )}
        </div>
      </div>

      {/* Code Content */}
      <div
        className={cn("overflow-x-auto overflow-y-auto", isDark && "code-dark")}
        style={{ maxHeight }}
      >
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className={cn("h-5 w-5 animate-spin", isDark ? "text-[#94A3B8]" : "text-[#9CA3AF]")} />
          </div>
        ) : html ? (
          <div
            dangerouslySetInnerHTML={{ __html: html }}
            className={cn(
              "[&_pre]:!bg-transparent [&_pre]:!p-4 [&_pre]:!m-0",
              "[&_pre]:!shadow-none [&_pre]:!border-0",
              "[&_code]:!font-mono [&_code]:!text-xs [&_code]:!leading-relaxed",
              "[&_code]:!bg-transparent",
              "[&_*]:!shadow-none",
              isDark 
                ? "[&::-webkit-scrollbar]:h-[6px] [&::-webkit-scrollbar]:w-[6px] [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-[#475569] [&::-webkit-scrollbar-thumb]:rounded-[3px] [&::-webkit-scrollbar-thumb]:hover:bg-[#64748B] [&::-webkit-scrollbar-corner]:bg-transparent"
                : "[&::-webkit-scrollbar]:h-[6px] [&::-webkit-scrollbar]:w-[6px] [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-[#D1D5DB] [&::-webkit-scrollbar-thumb]:rounded-[3px] [&::-webkit-scrollbar-thumb]:hover:bg-[#9CA3AF] [&::-webkit-scrollbar-corner]:bg-transparent"
            )}
          />
        ) : (
          <pre className={cn(
            "p-4 m-0 text-xs font-mono bg-transparent shadow-none border-0",
            isDark ? "text-[#94A3B8]" : "text-[#374151]"
          )}>
            <code>{code}</code>
          </pre>
        )}
      </div>
    </div>
  );
}

function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (ch) => map[ch] || ch);
}
