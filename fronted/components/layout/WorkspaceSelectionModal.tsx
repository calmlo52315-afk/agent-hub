"use client";

import { useRef, useState, useEffect } from "react";
import {
  X,
  FileText,
  Box,
  FolderOpen,
  Globe,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { WorkspaceType } from "@/types";
import {
  hasFileSystemAccessSupport,
  requestDirectoryAccess,
  scanDirectory,
  type FsaFile,
} from "@/lib/fileSystemAccess";

interface WorkspaceOption {
  type: WorkspaceType | "git";
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  disabled?: boolean;
  badge?: string;
}

const WORKSPACE_OPTIONS: WorkspaceOption[] = [
  {
    type: "scratch",
    icon: FileText,
    title: "临时工作区",
    description: "用于脚本、Demo、测试任务。生命周期短，自动清理。",
  },
  {
    type: "project",
    icon: Box,
    title: "项目工作区",
    description: "用于长期开发项目。React、FastAPI、Go 服务等。",
  },
  {
    type: "imported",
    icon: FolderOpen,
    title: "导入本地目录",
    description: "修改已有项目，接手老项目。选择本地文件夹。",
  },
  {
    type: "git",
    icon: Globe,
    title: "克隆 Git 仓库",
    description: "从 GitHub / GitLab 仓库创建工作区。",
    disabled: true,
    badge: "Coming Soon",
  },
];

export interface WorkspaceImportPayload {
  workspaceType: WorkspaceType;
  sourcePath?: string;
  files?: FsaFile[];
  directoryHandle?: FileSystemDirectoryHandle;
}

interface WorkspaceSelectionModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (payload: WorkspaceImportPayload) => void;
}

export function WorkspaceSelectionModal({
  open,
  onClose,
  onSelect,
}: WorkspaceSelectionModalProps) {
  const [importing, setImporting] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [selectedDirName, setSelectedDirName] = useState("");
  const [selectedHandle, setSelectedHandle] =
    useState<FileSystemDirectoryHandle | null>(null);
  const [fsaSupported] = useState(hasFileSystemAccessSupport);
  // Legacy fallback refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [legacyFiles, setLegacyFiles] = useState<File[]>([]);

  // 重置内部状态
  useEffect(() => {
    if (!open) {
      setImporting(false);
      setShowConfirmation(false);
      setSelectedDirName("");
      setSelectedHandle(null);
      setLegacyFiles([]);
    }
  }, [open]);

  if (!open) return null;

  const handleSelect = async (option: WorkspaceOption) => {
    if (option.disabled) return;

    if (option.type === "imported") {
      if (fsaSupported) {
        try {
          const handle = await requestDirectoryAccess();
          setSelectedDirName(handle.name);
          setSelectedHandle(handle);
          setShowConfirmation(true);
        } catch (err: any) {
          // User cancelled or permission denied — silently close the picker
          if (err?.name === "AbortError") return;
          console.error("Directory access failed:", err);
        }
      } else {
        // Fallback: use legacy webkitdirectory input
        setSelectedDirName("");
        setLegacyFiles([]);
        fileInputRef.current?.click();
      }
      return;
    }

    onSelect({ workspaceType: option.type as WorkspaceType });
  };

  const handleConfirmImport = async () => {
    if (fsaSupported && selectedHandle) {
      setImporting(true);
      try {
        const files = await scanDirectory(selectedHandle);
        onSelect({
          workspaceType: "imported",
          sourcePath: selectedDirName,
          files,
          directoryHandle: selectedHandle,
        });
      } catch (err) {
        console.error("Failed to scan directory:", err);
        setImporting(false);
      }
      return;
    }

    // Legacy fallback: use webkitdirectory files
    if (legacyFiles.length > 0) {
      setImporting(true);
      try {
        const dirName =
          legacyFiles[0].webkitRelativePath?.split("/")[0] || "imported";
        const files: FsaFile[] = [];
        for (const file of legacyFiles) {
          try {
            const content = await file.text();
            // Skip binary files
            if (content.includes("\x00")) continue;
            files.push({
              path: file.webkitRelativePath || file.name,
              content,
            });
          } catch {
            // skip unreadable files
          }
        }
        onSelect({
          workspaceType: "imported",
          sourcePath: dirName,
          files,
        });
      } catch (err) {
        console.error("Failed to read legacy files:", err);
        setImporting(false);
      }
      return;
    }
  };

  const handleLegacyDirectorySelected = (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const files: File[] = [];
    for (let i = 0; i < fileList.length; i++) {
      files.push(fileList[i]);
    }

    const firstPath = files[0].webkitRelativePath || files[0].name;
    const dirName = firstPath.split("/")[0];

    setSelectedDirName(dirName);
    setLegacyFiles(files);
    setShowConfirmation(true);

    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ---- Import confirmation view ----
  if (showConfirmation || importing) {
    return (
      <>
        <div
          className="fixed inset-0 z-50 bg-black/30 transition-opacity"
          onClick={
            importing ? undefined : () => {
              setShowConfirmation(false);
              onClose();
            }
          }
        />

        {/* Hidden legacy folder picker */}
        {!fsaSupported && (
          <input
            ref={fileInputRef}
            type="file"
            // @ts-expect-error webkitdirectory is non-standard
            webkitdirectory=""
            directory=""
            className="hidden"
            onChange={handleLegacyDirectorySelected}
          />
        )}

        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4">
          <div
            className={cn(
              "pointer-events-auto w-full max-w-md bg-white rounded-2xl border border-[#E5E7EB]",
              "shadow-xl flex flex-col overflow-hidden"
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5E7EB] shrink-0">
              <div>
                <h2 className="text-[15px] font-semibold text-[#111827]">
                  导入本地目录
                </h2>
                <p className="text-[12px] text-[#9CA3AF] mt-0.5">
                  {importing ? "正在扫描文件..." : "确认目录"}
                </p>
              </div>
            </div>

            {/* Body */}
            <div className="p-5 space-y-4">
              {importing ? (
                <div className="flex flex-col items-center py-8 gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-[#111827]" />
                  <p className="text-[13px] text-[#6B7280]">
                    正在读取目录文件...
                  </p>
                  <p className="text-[11px] text-[#9CA3AF]">
                    大目录可能需要几秒钟
                  </p>
                </div>
              ) : (
                <>
                  {/* Selected folder indicator */}
                  <div className="flex items-center gap-2 bg-[#F3F4F6] rounded-xl px-4 py-3">
                    <FolderOpen className="h-4 w-4 text-[#6B7280] shrink-0" />
                    <span className="text-[13px] text-[#374151] font-medium truncate flex-1">
                      {selectedDirName}
                    </span>
                    <button
                      onClick={async () => {
                        if (fsaSupported) {
                          setShowConfirmation(false);
                          setSelectedHandle(null);
                          try {
                            const handle = await requestDirectoryAccess();
                            setSelectedDirName(handle.name);
                            setSelectedHandle(handle);
                            setShowConfirmation(true);
                          } catch {
                            // cancelled
                          }
                        } else {
                          setShowConfirmation(false);
                          setLegacyFiles([]);
                          fileInputRef.current?.click();
                        }
                      }}
                      className="text-[11px] text-[#9CA3AF] hover:text-[#111827] shrink-0"
                    >
                      重新选择
                    </button>
                  </div>

                  {/* File count info */}
                  {legacyFiles.length > 0 && (
                    <p className="text-[12px] text-[#6B7280]">
                      已选择 {legacyFiles.length} 个文件
                    </p>
                  )}

                  {/* No-sync warning for legacy browsers */}
                  {!fsaSupported && (
                    <div className="flex items-start gap-2 bg-[#FEF3C7] rounded-xl px-3 py-2.5">
                      <AlertTriangle className="h-4 w-4 text-[#92400E] shrink-0 mt-0.5" />
                      <p className="text-[11px] text-[#92400E] leading-relaxed">
                        当前浏览器不支持双向同步。文件将上传供 Agent
                        使用，但修改不会写回本地目录。建议使用 Chrome 或 Edge
                        获得完整体验。
                      </p>
                    </div>
                  )}

                  {fsaSupported && (
                    <p className="text-[11px] text-[#9CA3AF] leading-relaxed">
                      Agent 将直接在此目录中修改文件，修改会同步回本地。
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Footer */}
            {!importing && (
              <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[#E5E7EB] bg-[#F9FAFB]">
                <button
                  onClick={() => {
                    setShowConfirmation(false);
                    onClose();
                  }}
                  className="px-4 py-2 text-[13px] font-medium text-[#374151] rounded-xl hover:bg-[#E5E7EB] transition-colors"
                >
                  取消
                </button>
                <button
                  onClick={handleConfirmImport}
                  className={cn(
                    "px-4 py-2 text-[13px] font-semibold rounded-xl transition-colors",
                    "bg-[#111827] text-white hover:bg-[#1F2937]"
                  )}
                >
                  确认导入
                </button>
              </div>
            )}
          </div>
        </div>
      </>
    );
  }

  // ---- Type selection view ----
  return (
    <>
      {/* Hidden legacy folder picker */}
      {!fsaSupported && (
        <input
          ref={fileInputRef}
          type="file"
          // @ts-expect-error webkitdirectory is non-standard
          webkitdirectory=""
          directory=""
          className="hidden"
          onChange={handleLegacyDirectorySelected}
        />
      )}

      <div
        className="fixed inset-0 z-50 bg-black/30 transition-opacity"
        onClick={onClose}
      />

      <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none p-4">
        <div
          className={cn(
            "pointer-events-auto w-full max-w-lg bg-white rounded-2xl border border-[#E5E7EB]",
            "shadow-xl flex flex-col overflow-hidden"
          )}
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-[#E5E7EB] shrink-0">
            <div>
              <h2 className="text-[15px] font-semibold text-[#111827]">
                新建群聊
              </h2>
              <p className="text-[12px] text-[#9CA3AF] mt-0.5">
                请选择工作区类型
              </p>
            </div>
            <button
              onClick={onClose}
              className="flex items-center justify-center h-7 w-7 rounded-lg hover:bg-[#F3F4F6] transition-colors"
            >
              <X className="h-4 w-4 text-[#9CA3AF]" />
            </button>
          </div>

          <div className="p-4 grid grid-cols-2 gap-3">
            {WORKSPACE_OPTIONS.map((option) => {
              const Icon = option.icon;
              const isDisabled = option.disabled;

              return (
                <button
                  key={option.type}
                  onClick={() => handleSelect(option)}
                  disabled={isDisabled}
                  className={cn(
                    "relative flex flex-col items-center text-center p-4 rounded-xl border transition-all",
                    isDisabled
                      ? "border-[#E5E7EB] bg-[#F9FAFB] opacity-50 cursor-not-allowed"
                      : "border-[#E5E7EB] bg-white hover:border-[#111827] hover:shadow-sm cursor-pointer active:scale-[0.98]"
                  )}
                >
                  {option.badge && (
                    <span className="absolute top-2 right-2 text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-[#FEF3C7] text-[#92400E]">
                      {option.badge}
                    </span>
                  )}

                  <div
                    className={cn(
                      "h-10 w-10 rounded-xl flex items-center justify-center mb-2.5",
                      isDisabled
                        ? "bg-[#E5E7EB] text-[#9CA3AF]"
                        : "bg-[#111827] text-white"
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </div>

                  <h3
                    className={cn(
                      "text-[13px] font-semibold mb-1",
                      isDisabled ? "text-[#9CA3AF]" : "text-[#111827]"
                    )}
                  >
                    {option.title}
                  </h3>

                  <p className="text-[11px] text-[#9CA3AF] leading-relaxed">
                    {option.description}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="px-5 py-3 border-t border-[#E5E7EB] bg-[#F9FAFB]">
            <p className="text-[11px] text-[#9CA3AF] text-center">
              选择后系统将自动创建工作区并绑定到新会话
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
