"use client";

import type { DiffContent, DiffFileEntry } from "@/types";
import {
  FileCode,
  Plus,
  Minus,
  ChevronDown,
  FilePlus,
  FileEdit,
  FileMinus,
  Maximize2,
  Copy,
  Check,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CodePreviewModal } from "./CodePreviewModal";
import { useState, useCallback } from "react";

interface DiffViewerCardProps {
  content: DiffContent;
  title: string;
  summary?: string;
}

const changeIcon: Record<string, React.ComponentType<{ className?: string }>> = {
  create: FilePlus,
  update: FileEdit,
  delete: FileMinus,
};

const changeColor: Record<string, string> = {
  create: "text-[#10B981]",
  update: "text-[#3B82F6]",
  delete: "text-[#DC2626]",
};

const changeBgColor: Record<string, string> = {
  create: "bg-[#ECFDF5] border-[#10B981]/30",
  update: "bg-[#EFF6FF] border-[#3B82F6]/30",
  delete: "bg-[#FEF2F2] border-[#DC2626]/30",
};

/**
 * ⭐ Parse unified diff output into structured lines with add/remove/context markers.
 * Returns an array of {type, content, oldLine, newLine} for rendering.
 */
interface DiffLine {
  type: "add" | "remove" | "context" | "header" | "hunk";
  content: string;
  oldLine?: number;
  newLine?: number;
}

function parseUnifiedDiff(diffText: string): DiffLine[] {
  if (!diffText) return [];

  const lines: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const raw of diffText.split("\n")) {
    if (raw.startsWith("--- ") || raw.startsWith("+++ ")) {
      lines.push({ type: "header", content: raw });
    } else if (raw.startsWith("@@")) {
      // Parse @@ -old,count +new,count @@
      const match = raw.match(/@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        newLine = parseInt(match[3], 10);
      }
      lines.push({ type: "hunk", content: raw });
    } else if (raw.startsWith("+")) {
      lines.push({ type: "add", content: raw.substring(1), oldLine: undefined, newLine: newLine++ });
    } else if (raw.startsWith("-")) {
      lines.push({ type: "remove", content: raw.substring(1), oldLine: oldLine++, newLine: undefined });
    } else {
      // context line (starts with space or is empty)
      const text = raw.startsWith(" ") ? raw.substring(1) : raw;
      lines.push({ type: "context", content: text, oldLine: oldLine++, newLine: newLine++ });
    }
  }

  return lines;
}

export function DiffViewerCard({ content, title, summary }: DiffViewerCardProps) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [fullscreenFile, setFullscreenFile] = useState<{
    content: string;
    lang: string;
    path: string;
  } | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const toggleFile = (path: string) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleCopy = useCallback(async (text: string, path: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedPath(path);
      setTimeout(() => setCopiedPath(null), 2000);
    } catch {
      // fallback
    }
  }, []);

  return (
    <>
      <Card className="overflow-hidden">
        <CardHeader className="pb-2" style={{ padding: 16 }}>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FileCode className="h-4 w-4 text-[#6B7280]" />
              {title}
            </CardTitle>
          </div>
          {summary && (
            <p className="text-xs text-[#9CA3AF] mt-0.5">{summary}</p>
          )}
          <div className="flex items-center gap-3 mt-1.5">
            <div className="flex items-center gap-1 text-xs">
              <span className="text-[#9CA3AF]">
                {content.files_changed} files
              </span>
            </div>
            <div className="flex items-center gap-1 text-xs text-[#10B981]">
              <Plus className="h-3 w-3" />
              {content.additions}
            </div>
            <div className="flex items-center gap-1 text-xs text-[#DC2626]">
              <Minus className="h-3 w-3" />
              {content.deletions}
            </div>
          </div>
        </CardHeader>
        <CardContent style={{ padding: "0 16px 16px" }}>
          <div className="space-y-1.5">
            {content.files.map((file) => (
              <FileDiffItem
                key={file.path}
                file={file}
                expanded={expandedFiles.has(file.path)}
                onToggle={() => toggleFile(file.path)}
                onFullscreen={(content, lang, path) =>
                  setFullscreenFile({ content, lang, path })
                }
                copied={copiedPath === file.path}
                onCopy={(text) => handleCopy(text, file.path)}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {fullscreenFile && (
        <CodePreviewModal
          open={!!fullscreenFile}
          onOpenChange={(open) => {
            if (!open) setFullscreenFile(null);
          }}
          code={fullscreenFile.content}
          lang={fullscreenFile.lang}
          title={fullscreenFile.path}
        />
      )}
    </>
  );
}

function FileDiffItem({
  file,
  expanded,
  onToggle,
  onFullscreen,
  copied,
  onCopy,
}: {
  file: DiffFileEntry & {
    content?: string;
    before_content?: string;
    after_content?: string;
    unified_diff?: string;
  };
  expanded: boolean;
  onToggle: () => void;
  onFullscreen: (content: string, lang: string, path: string) => void;
  copied: boolean;
  onCopy: (text: string) => void;
}) {
  const Icon = changeIcon[file.change_type] || FileEdit;
  const color = changeColor[file.change_type] || "text-[#3B82F6]";
  const bg = changeBgColor[file.change_type] || "bg-[#EFF6FF] border-[#BFDBFE]";

  // ⭐ Get the diff content to display
  const diffText = file.unified_diff || file.diff_excerpt || "";
  const hasDiff = diffText.length > 0;
  const hasContent = !!(file.content || file.after_content);

  return (
    <div className={`rounded-[6px] border overflow-hidden transition-colors ${
      expanded ? bg : "border-[#E5E7EB]"
    }`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-black/5 transition-colors text-left"
      >
        <ChevronDown
          className={`h-3 w-3 shrink-0 text-[#9CA3AF] transition-transform ${
            expanded ? "rotate-0" : "-rotate-90"
          }`}
        />
        <Icon className={`h-3 w-3 shrink-0 ${color}`} />
        <span className="font-mono text-xs truncate flex-1">
          {file.path}
        </span>
        <Badge
          variant="outline"
          className={`text-[10px] px-1.5 h-4 ${color}`}
        >
          {file.change_type}
        </Badge>
      </button>

      {expanded && (
        <div className="border-t border-[#E5E7EB]/50">
          {/* ⭐ Render unified diff with green/red highlighting */}
          {hasDiff ? (
            <DiffRenderer
              diffText={diffText}
              path={file.path}
              onFullscreen={() => onFullscreen(diffText, "diff", file.path)}
              onCopy={() => onCopy(diffText)}
              copied={copied}
            />
          ) : hasContent ? (
            /* Fallback: plain content if no diff available */
            <PlainContentRenderer
              content={file.after_content || file.content || ""}
              path={file.path}
              onFullscreen={() =>
                onFullscreen(file.after_content || file.content || "", "text", file.path)
              }
              onCopy={() => onCopy(file.after_content || file.content || "")}
              copied={copied}
            />
          ) : (
            <div className="p-4 text-xs text-[#9CA3AF] text-center">
              No content preview
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * ⭐ Diff Renderer — parses unified diff and renders green/red/context lines.
 */
function DiffRenderer({
  diffText,
  path,
  onFullscreen,
  onCopy,
  copied,
}: {
  diffText: string;
  path: string;
  onFullscreen: () => void;
  onCopy: () => void;
  copied: boolean;
}) {
  const diffLines = parseUnifiedDiff(diffText);
  const MAX_PREVIEW = 80; // max lines to preview before truncating
  const truncated = diffLines.length > MAX_PREVIEW;
  const visibleLines = truncated ? diffLines.slice(0, MAX_PREVIEW) : diffLines;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#F9FAFB] border-b border-[#E5E7EB]/50">
        <span className="text-[10px] font-mono text-[#6B7280] uppercase">diff</span>
        <div className="flex items-center gap-1">
          <button
            onClick={onCopy}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-[#10B981]" />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                Copy
              </>
            )}
          </button>
          <button
            onClick={onFullscreen}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
          >
            <Maximize2 className="h-3 w-3" />
            Full
          </button>
        </div>
      </div>

      {/* Diff Lines */}
      <div className="overflow-x-auto" style={{ maxHeight: "300px", overflowY: "auto" }}>
        <table className="w-full text-xs font-mono leading-relaxed border-collapse">
          <tbody>
            {visibleLines.map((line, i) => {
              const isAdd = line.type === "add";
              const isRemove = line.type === "remove";
              const isHeader = line.type === "header";
              const isHunk = line.type === "hunk";

              return (
                <tr
                  key={i}
                  className={
                    isAdd
                      ? "bg-[#ECFDF5]"
                      : isRemove
                      ? "bg-[#FEF2F2]"
                      : isHeader
                      ? "bg-[#F0F9FF]"
                      : isHunk
                      ? "bg-[#F3F4F6]"
                      : ""
                  }
                >
                  {/* Line numbers */}
                  <td
                    className={`select-none text-right px-2 py-0 border-r w-12 ${
                      isRemove
                        ? "text-[#DC2626]/50 bg-[#FEF2F2] border-[#FECACA]"
                        : isAdd
                        ? "text-[#10B981]/50 bg-[#ECFDF5] border-[#A7F3D0]"
                        : "text-[#9CA3AF] border-[#E5E7EB] bg-[#F9FAFB]"
                    }`}
                  >
                    {line.oldLine ?? ""}
                  </td>
                  <td
                    className={`select-none text-right px-2 py-0 border-r w-12 ${
                      isRemove
                        ? "text-[#DC2626]/50 bg-[#FEF2F2] border-[#FECACA]"
                        : isAdd
                        ? "text-[#10B981]/50 bg-[#ECFDF5] border-[#A7F3D0]"
                        : "text-[#9CA3AF] border-[#E5E7EB] bg-[#F9FAFB]"
                    }`}
                  >
                    {line.newLine ?? ""}
                  </td>
                  {/* Sign column: + / - */}
                  <td
                    className={`select-none text-center px-1 py-0 w-5 font-bold ${
                      isAdd
                        ? "text-[#10B981]"
                        : isRemove
                        ? "text-[#DC2626]"
                        : "text-[#9CA3AF]"
                    }`}
                  >
                    {isAdd ? "+" : isRemove ? "-" : ""}
                  </td>
                  {/* Content */}
                  <td
                    className={`px-2 py-0 whitespace-pre-wrap break-all ${
                      isAdd
                        ? "text-[#065F46]"
                        : isRemove
                        ? "text-[#991B1B]"
                        : isHeader
                        ? "text-[#0369A1] font-semibold"
                        : isHunk
                        ? "text-[#6B7280]"
                        : "text-[#374151]"
                    }`}
                  >
                    {line.content}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {truncated && (
        <div className="px-3 py-2 text-[10px] text-[#9CA3AF] text-center border-t border-[#E5E7EB]/50 bg-[#F9FAFB]">
          Showing {MAX_PREVIEW} of {diffLines.length} lines.
          <button
            onClick={onFullscreen}
            className="ml-1 text-[#3B82F6] hover:underline"
          >
            View all
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Fallback plain content renderer (when no diff is available).
 */
function PlainContentRenderer({
  content,
  path,
  onFullscreen,
  onCopy,
  copied,
}: {
  content: string;
  path: string;
  onFullscreen: () => void;
  onCopy: () => void;
  copied: boolean;
}) {
  const lines = content.split("\n");
  const MAX_PREVIEW = 60;
  const truncated = lines.length > MAX_PREVIEW;
  const visibleLines = truncated ? lines.slice(0, MAX_PREVIEW) : lines;

  return (
    <div>
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#F9FAFB] border-b border-[#E5E7EB]/50">
        <span className="text-[10px] font-mono text-[#6B7280] uppercase">
          {path.split(".").pop() || "text"}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={onCopy}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
          >
            {copied ? (
              <>
                <Check className="h-3 w-3 text-[#10B981]" />
                Copied
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" />
                Copy
              </>
            )}
          </button>
          <button
            onClick={onFullscreen}
            className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] text-[#6B7280] hover:text-[#111827] hover:bg-[#E5E7EB] transition-colors"
          >
            <Maximize2 className="h-3 w-3" />
            Full
          </button>
        </div>
      </div>
      <div className="overflow-x-auto" style={{ maxHeight: "300px", overflowY: "auto" }}>
        <table className="w-full text-xs font-mono leading-relaxed border-collapse">
          <tbody>
            {visibleLines.map((line, i) => (
              <tr key={i}>
                <td className="select-none text-right px-2 py-0 border-r border-[#E5E7EB] w-12 text-[#9CA3AF] bg-[#F9FAFB]">
                  {i + 1}
                </td>
                <td className="px-2 py-0 whitespace-pre-wrap break-all text-[#374151]">
                  {line}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <div className="px-3 py-2 text-[10px] text-[#9CA3AF] text-center border-t border-[#E5E7EB]/50 bg-[#F9FAFB]">
          {lines.length - MAX_PREVIEW} more lines.
          <button
            onClick={onFullscreen}
            className="ml-1 text-[#3B82F6] hover:underline"
          >
            View all
          </button>
        </div>
      )}
    </div>
  );
}
