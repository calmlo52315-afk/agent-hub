"use client";

import { useState, useEffect, useMemo } from "react";
import { useArtifactStore } from "@/stores/artifactStore";
import { useTaskStore } from "@/stores/taskStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import MonacoEditor from "@monaco-editor/react";
import { CodePreviewModal } from "@/components/artifact/CodePreviewModal";
import { DiffViewerCard } from "@/components/artifact/DiffViewerCard";
import { BundleCard } from "@/components/artifact/BundleCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { getWorkspaceFile } from "@/lib/api";
import {
  FileCode,
  ChevronDown,
  ChevronRight,
  Package,
  FileDiff,
  FolderOpen,
  Clock,
  Search,
  Folder,
} from "lucide-react";
import type {
  ArtifactCard,
  DiffContent,
  BundleContent,
  WorkspaceFileNode,
} from "@/types";

type TabKey = "files" | "changes" | "bundles" | "history";

interface TabDef {
  key: TabKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: TabDef[] = [
  { key: "files", label: "文件", icon: FolderOpen },
  { key: "changes", label: "代码变更", icon: FileDiff },
  { key: "bundles", label: "打包产物", icon: Package },
  { key: "history", label: "历史记录", icon: Clock },
];

// ---- Helpers ----

function detectLang(path: string) {
  const ext = path.split(".").pop()?.toLowerCase() || "text";
  const map: Record<string, string> = {
    ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
    py: "python", go: "go", rs: "rust", json: "json", css: "css",
    html: "html", md: "markdown", sql: "sql", yaml: "yaml", yml: "yaml",
    sh: "bash", xml: "xml", java: "java", c: "c", cpp: "cpp",
    h: "c", hpp: "cpp", toml: "toml", env: "text",
  };
  return map[ext] || ext;
}

/** Build a file tree from artifact diff data */
function buildFileTree(artifacts: ArtifactCard[]): WorkspaceFileNode[] {
  const fileMap = new Map<string, { content: string; changeType: string; taskId: string }>();

  for (const a of artifacts) {
    if (a.card_type === "diff") {
      const c = a.content as unknown as DiffContent;
      c.files?.forEach((f) => {
        // Use the latest version of each file (by artifact timestamp)
        const existing = fileMap.get(f.path);
        if (!existing || new Date(a.updated_at) > new Date(a.created_at)) {
          fileMap.set(f.path, {
            content: f.content || f.diff_excerpt || "",
            changeType: f.change_type,
            taskId: a.task_id,
          });
        }
      });
    }
  }

  // Build tree
  const root: Record<string, any> = {};
  for (const [path, info] of fileMap) {
    const parts = path.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      if (!current[part]) {
        current[part] = isLast
          ? { __file: true, __path: path, __content: info.content, __changeType: info.changeType, __taskId: info.taskId }
          : { __dir: true, __children: {} };
      }
      if (!isLast) {
        current = current[part].__children;
      }
    }
  }

  function toNodes(obj: Record<string, any>, parentPath: string): WorkspaceFileNode[] {
    const entries = Object.entries(obj);
    // Sort: directories first, then files; alphabetically within each
    entries.sort((a, b) => {
      const aIsDir = a[1].__dir;
      const bIsDir = b[1].__dir;
      if (aIsDir && !bIsDir) return -1;
      if (!aIsDir && bIsDir) return 1;
      return a[0].localeCompare(b[0]);
    });

    return entries.map(([name, node]) => {
      const fullPath = parentPath ? `${parentPath}/${name}` : name;
      if (node.__dir) {
        return {
          name,
          path: fullPath,
          type: "directory" as const,
          children: toNodes(node.__children, fullPath),
        };
      }
      return {
        name,
        path: node.__path,
        type: "file" as const,
        changed_by_task_id: node.__taskId,
      };
    });
  }

  return toNodes(root, "");
}

/** Recursively count files in tree */
function countFiles(nodes: WorkspaceFileNode[]): number {
  let count = 0;
  for (const n of nodes) {
    if (n.type === "file") count++;
    if (n.children) count += countFiles(n.children);
  }
  return count;
}

// ---- File Tree Node Component ----

function FileTreeNode({
  node,
  depth,
  expandedPaths,
  onToggle,
  selectedPath,
  onSelectFile,
}: {
  node: WorkspaceFileNode;
  depth: number;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
  selectedPath: string | null;
  onSelectFile: (node: WorkspaceFileNode) => void;
}) {
  const isDir = node.type === "directory";
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;

  return (
    <div>
      <button
        onClick={() => isDir ? onToggle(node.path) : onSelectFile(node)}
        className={cn(
          "w-full flex items-center gap-1 py-1 px-2 text-[12px] rounded-[4px] text-left transition-colors",
          isSelected
            ? "bg-[#F3F4F6] text-[#111827] font-medium"
            : "text-[#374151] hover:bg-[#F3F4F6]"
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {isDir ? (
          <>
            {isExpanded ? (
              <ChevronDown className="h-3 w-3 shrink-0 text-[#9CA3AF]" />
            ) : (
              <ChevronRight className="h-3 w-3 shrink-0 text-[#9CA3AF]" />
            )}
            <Folder className="h-3.5 w-3.5 shrink-0 text-[#6B7280]" />
          </>
        ) : (
          <>
            <span className="w-3 shrink-0" />
            <FileCode className="h-3.5 w-3.5 shrink-0 text-[#9CA3AF]" />
          </>
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {isDir && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expandedPaths={expandedPaths}
              onToggle={onToggle}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Main Component ----

export function ArtifactPanel() {
  const artifacts = useArtifactStore((s) => s.artifacts);
  const tasks = useTaskStore((s) => s.tasks);
  const wsMeta = useWorkspaceStore((s) => s.meta);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);

  // ⭐ 按当前 session 过滤 artifacts，防止跨会话数据泄漏
  const sessionArtifacts = useMemo(
    () => artifacts.filter(a => a.session_id === currentSessionId),
    [artifacts, currentSessionId]
  );

  const [activeTab, setActiveTab] = useState<TabKey>("files");
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [selectedFile, setSelectedFile] = useState<{
    path: string;
    content: string;
  } | null>(null);
  const [loadingFilePath, setLoadingFilePath] = useState<string | null>(null);
  const [fullscreenFile, setFullscreenFile] = useState<{
    path: string;
    content: string;
  } | null>(null);
  const [fileSearch, setFileSearch] = useState("");
  const [codePanelHeight, setCodePanelHeight] = useState(350); // 代码区默认高度 px

  // Build file tree from workspace files (API) or fall back to diff artifacts
  // ⭐ 使用 session-filtered artifacts 构建文件树
  const wsFileTree = useWorkspaceStore((s) => s.fileTree);
  const artifactFileTree = useMemo(() => buildFileTree(sessionArtifacts), [sessionArtifacts]);
  const fileTree = wsFileTree.length > 0 ? wsFileTree : artifactFileTree;
  const totalFileCount = useMemo(() => countFiles(fileTree), [fileTree]);

  // Filtered files by search
  const filteredTree = useMemo(() => {
    if (!fileSearch.trim()) return fileTree;
    const q = fileSearch.toLowerCase();
    // Return only nodes whose name or path matches
    function filterNodes(nodes: WorkspaceFileNode[]): WorkspaceFileNode[] {
      const result: WorkspaceFileNode[] = [];
      for (const n of nodes) {
        const nameMatch = n.name.toLowerCase().includes(q);
        const pathMatch = n.path.toLowerCase().includes(q);
        if (n.type === "file") {
          if (nameMatch || pathMatch) result.push(n);
        } else {
          const filteredChildren = n.children ? filterNodes(n.children) : [];
          if (nameMatch || pathMatch || filteredChildren.length > 0) {
            result.push({ ...n, children: filteredChildren });
          }
        }
      }
      return result;
    }
    return filterNodes(fileTree);
  }, [fileTree, fileSearch]);

  // Expand first level by default
  useEffect(() => {
    if (fileTree.length > 0 && expandedPaths.size === 0) {
      const firstLevel = new Set(fileTree.filter(n => n.type === "directory").map(n => n.path));
      if (firstLevel.size > 0) setExpandedPaths(firstLevel);
    }
  }, [fileTree]);

  // ⭐ session 切换时重置选中文件和展开状态
  useEffect(() => {
    setSelectedFile(null);
    setExpandedPaths(new Set());
    setFileSearch("");
  }, [currentSessionId]);


  const togglePath = (path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleSelectFile = async (node: WorkspaceFileNode) => {
    // 1. 先检查内存缓存 (workspaceStore)
    const cachedContent = useWorkspaceStore.getState().getCachedContent(node.path);
    if (cachedContent) {
      setSelectedFile({ path: node.path, content: cachedContent });
      return;
    }

    // ⭐ 1.5: 检查 FSA directory handle — 直接从用户本地文件系统读取
    const dirHandle = useWorkspaceStore.getState().directoryHandle;
    if (dirHandle) {
      setLoadingFilePath(node.path);
      setSelectedFile(null);
      try {
        const { readFileByPath } = await import("@/lib/fileSystemAccess");
        const content = await readFileByPath(dirHandle, node.path);
        setSelectedFile({ path: node.path, content });
        setLoadingFilePath(null);
        return;
      } catch (err) {
        console.warn("[ArtifactPanel] FSA read failed for", node.path, ", falling back to API:", err);
        // 继续走 API 路径
      }
    }

    // 2. 然后检查 diff artifacts（当前 session 的）
    for (const a of sessionArtifacts) {
      if (a.card_type === "diff") {
        const c = a.content as unknown as DiffContent;
        const found = c.files?.find((f) => f.path === node.path);
        if (found?.content || found?.diff_excerpt) {
          const content = found.content || found.diff_excerpt || "";
          setSelectedFile({ path: node.path, content });
          return;
        }
      }
    }

    // 3. 懒加载：按需从后端获取单个文件内容
    const sessionId = wsMeta?.session_id;
    if (!sessionId || sessionId === "pending") {
      console.error("[ArtifactPanel] Invalid sessionId for file content fetch:", sessionId);
      setSelectedFile({ path: node.path, content: "// Session not ready — please wait" });
      return;
    }

    setLoadingFilePath(node.path);
    setSelectedFile(null); // 清除之前的选中状态，展示 loading

    try {
      const content = await useWorkspaceStore.getState().loadFileContent(sessionId, node.path);
      if (content !== null) {
        setSelectedFile({ path: node.path, content });
      } else {
        setSelectedFile({ path: node.path, content: "// File content not available" });
      }
    } catch (err) {
      console.error("[ArtifactPanel] Failed to fetch file content:", err);
      setSelectedFile({ path: node.path, content: "// Failed to load file content" });
    } finally {
      setLoadingFilePath(null);
    }
  };
  // ---- Tab: Changes ----
  const diffArtifacts = useMemo(
    () => sessionArtifacts.filter((a) => a.card_type === "diff"),
    [sessionArtifacts]
  );

  // ---- Tab: Bundles ----
  const bundleArtifacts = useMemo(
    () => sessionArtifacts.filter((a) => a.card_type === "bundle"),
    [sessionArtifacts]
  );

  // ---- Empty state ----
  // For imported workspaces with a file tree from browser selection, show files immediately
  const hasImportedFiles = wsMeta?.workspace_type === "imported" && wsFileTree.length > 0;

  if (sessionArtifacts.length === 0 && tasks.length === 0 && !hasImportedFiles) {
    return (
      <div className="flex h-full flex-col bg-white">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB]">
          <span className="text-[13px] font-semibold text-[#111827]">
            Workspace
          </span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center px-6">
            <Package className="h-8 w-8 text-[#D1D5DB] mx-auto mb-3" />
            <p className="text-[13px] text-[#9CA3AF] mb-1">
              暂无工作区内容
            </p>
            <p className="text-xs text-[#9CA3AF]">
              {wsMeta?.workspace_type === "project"
                ? "开始任务来构建您的项目"
                : "输出文件、差异和预览将显示在这里"}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB] shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-[#111827]">
            Workspace
          </span>
          {totalFileCount > 0 && (
            <span className="text-[10px] text-[#9CA3AF] bg-[#F3F4F6] px-1.5 py-0.5 rounded-full font-medium">
              {totalFileCount}
            </span>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#E5E7EB] shrink-0">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "flex items-center gap-1.5 px-4 py-2.5 text-[13px] font-medium transition-colors relative",
                isActive
                  ? "text-[#111827]"
                  : "text-[#9CA3AF] hover:text-[#374151]"
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
              {isActive && (
                <div className="absolute bottom-0 left-3 right-3 h-[2px] bg-[#111827] rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* ---- Files Tab ---- */}
        {activeTab === "files" && (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Search */}
            <div className="px-3 py-2 border-b border-[#E5E7EB] shrink-0">
              <div className="flex items-center gap-2 bg-[#F3F4F6] rounded-lg px-3 py-1.5">
                <Search className="h-3.5 w-3.5 text-[#9CA3AF] shrink-0" />
                <input
                  type="text"
                  placeholder="搜索文件..."
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="flex-1 bg-transparent text-[12px] text-[#111827] placeholder-[#9CA3AF] outline-none border-none"
                />
                {fileSearch && (
                  <button
                    onClick={() => setFileSearch("")}
                    className="text-[10px] text-[#9CA3AF] hover:text-[#111827]"
                  >
                    清除
                  </button>
                )}
              </div>
            </div>

            {/* File Tree */}
            <ScrollArea className="flex-1">
              <div className="py-1">
                {filteredTree.length === 0 ? (
                  <p className="text-[12px] text-[#9CA3AF] text-center py-8">
                    {fileSearch ? "无匹配文件" : "工作区中没有文件"}
                  </p>
                ) : (
                  filteredTree.map((node) => (
                    <FileTreeNode
                      key={node.path}
                      node={node}
                      depth={0}
                      expandedPaths={expandedPaths}
                      onToggle={togglePath}
                      selectedPath={selectedFile?.path ?? null}
                      onSelectFile={handleSelectFile}
                    />
                  ))
                )}
              </div>
            </ScrollArea>

            {/* Resize Handle + Code Preview Pane */}
            <div
              onMouseDown={(e) => {
                e.preventDefault();
                const startY = e.clientY;
                const startH = codePanelHeight;
                const onMove = (ev: MouseEvent) => {
                  setCodePanelHeight(Math.max(100, startH - (ev.clientY - startY)));
                };
                const onUp = () => {
                  document.removeEventListener("mousemove", onMove);
                  document.removeEventListener("mouseup", onUp);
                  document.body.style.cursor = "";
                  document.body.style.userSelect = "";
                };
                document.body.style.cursor = "row-resize";
                document.body.style.userSelect = "none";
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
              }}
              className="shrink-0 h-2 cursor-row-resize flex items-center justify-center group hover:bg-[#F3F4F6] transition-colors border-t border-[#E5E7EB]"
            >
              <div className="w-8 h-1 rounded-full bg-[#E5E7EB] group-hover:bg-[#9CA3AF] transition-colors" />
            </div>
            <div
              className="shrink-0 w-full overflow-hidden flex flex-col"
              style={{ height: codePanelHeight, minHeight: 100 }}
            >
              {selectedFile ? (
                loadingFilePath === selectedFile.path ? (
                  <div className="flex items-center justify-center h-full">
                    <p className="text-xs text-[#9CA3AF]">加载文件内容...</p>
                  </div>
                ) : (
                <div className="w-full h-full flex flex-col rounded-lg overflow-hidden border border-[#E5E7EB] m-2">
                  <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#E5E7EB] bg-[#F9FAFB] shrink-0 rounded-t-lg">
                    <span className="text-[11px] font-mono text-[#6B7280] truncate max-w-[45%]">
                      {selectedFile.path.split('/').pop()}
                    </span>
                    <span className="text-[10px] text-[#9CA3AF] truncate max-w-[40%]" title={selectedFile.path}>
                      {selectedFile.path.split('/').slice(0, -1).join('/')}
                    </span>
                    <button
                      onClick={() => setFullscreenFile(selectedFile)}
                      className="text-[10px] text-[#9CA3AF] hover:text-[#111827] shrink-0 ml-1"
                    >
                      全屏
                    </button>
                  </div>
                  <div className="flex-1 min-h-0 rounded-b-lg overflow-hidden">
                    <MonacoEditor
                      language={detectLang(selectedFile.path)}
                      value={selectedFile.content}
                      theme="vs-light"
                      options={{
                        readOnly: true,
                        minimap: { enabled: false },
                        fontSize: 12,
                        lineNumbers: "on",
                        scrollBeyondLastLine: false,
                        wordWrap: "on",
                        padding: { top: 8 },
                        automaticLayout: true,
                      }}
                    />
                  </div>
                </div>
                )
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-xs text-[#9CA3AF]">
                    选择文件进行预览
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ---- Changes Tab ---- */}
        {activeTab === "changes" && (
          <ScrollArea className="flex-1">
            <div className="p-3 space-y-3">
              {diffArtifacts.length > 0 ? (
                diffArtifacts.map((a) => (
                  <DiffViewerCard
                    key={a.artifact_id}
                    content={a.content as unknown as DiffContent}
                    title={a.title}
                    summary={a.summary}
                  />
                ))
              ) : (
                <div className="flex items-center justify-center py-16">
                  <p className="text-xs text-[#9CA3AF]">
                    暂无代码变更
                  </p>
                </div>
              )}
            </div>
          </ScrollArea>
        )}

        {/* ---- Bundles Tab ---- */}
        {activeTab === "bundles" && (
          <ScrollArea className="flex-1">
            <div className="p-3 space-y-3">
              {bundleArtifacts.length > 0 ? (
                bundleArtifacts.map((a) => (
                  <BundleCard
                    key={a.artifact_id}
                    content={a.content as unknown as BundleContent}
                    title={a.title}
                    summary={a.summary}
                    taskId={a.task_id}
                  />
                ))
              ) : (
                <div className="flex items-center justify-center py-16">
                  <p className="text-xs text-[#9CA3AF]">
                    暂无打包产物。项目任务完成后，打包产物将显示在这里。
                  </p>
                </div>
              )}
            </div>
          </ScrollArea>
        )}

        {/* ---- History Tab ---- */}
        {activeTab === "history" && (
          <ScrollArea className="flex-1">
            <div className="p-3">
              {tasks.length > 0 ? (
                <div className="space-y-1">
                  {[...tasks]
                    .sort(
                      (a, b) =>
                        new Date(b.updated_at).getTime() -
                        new Date(a.updated_at).getTime()
                    )
                    .map((task, idx) => (
                      <div
                        key={task.task_id}
                        className="flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-[#F3F4F6] transition-colors"
                      >
                        {/* Timeline dot */}
                        <div className="relative flex flex-col items-center shrink-0 pt-1">
                          <div
                            className={cn(
                              "h-2.5 w-2.5 rounded-full border-2",
                              task.status === "completed"
                                ? "bg-[#10B981] border-[#10B981]"
                                : task.status === "failed"
                                ? "bg-[#EF4444] border-[#EF4444]"
                                : task.status === "running" || task.status === "planning"
                                ? "bg-[#3B82F6] border-[#3B82F6] animate-pulse"
                                : "bg-[#D1D5DB] border-[#D1D5DB]"
                            )}
                          />
                          {idx < tasks.length - 1 && (
                            <div className="w-px flex-1 bg-[#E5E7EB] mt-0.5" />
                          )}
                        </div>

                        {/* Content */}
                        <div className="min-w-0 flex-1 pb-3">
                          <div className="flex items-center gap-2 mb-0.5">
                            <p className="text-[13px] font-medium text-[#111827] truncate">
                              {task.title}
                            </p>
                            <span
                              className={cn(
                                "text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0",
                                task.status === "completed"
                                  ? "bg-[#D1FAE5] text-[#065F46]"
                                  : task.status === "failed"
                                  ? "bg-[#FEE2E2] text-[#991B1B]"
                                  : task.status === "running"
                                  ? "bg-[#DBEAFE] text-[#1E40AF]"
                                  : "bg-[#F3F4F6] text-[#6B7280]"
                              )}
                            >
                              {task.status}
                            </span>
                          </div>
                          {task.summary && (
                            <p className="text-[11px] text-[#9CA3AF] line-clamp-2">
                              {task.summary}
                            </p>
                          )}
                          <p className="text-[10px] text-[#9CA3AF] mt-1">
                            {new Date(task.updated_at).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div className="flex items-center justify-center py-16">
                  <div className="text-center">
                    <Clock className="h-8 w-8 text-[#D1D5DB] mx-auto mb-3" />
                    <p className="text-xs text-[#9CA3AF]">
                      暂无任务历史
                    </p>
                    <p className="text-[11px] text-[#9CA3AF] mt-1">
                      任务执行时间线将显示在这里
                    </p>
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        )}
      </div>

      {/* Fullscreen Monaco Modal */}
      {fullscreenFile && (
        <CodePreviewModal
          open={!!fullscreenFile}
          onOpenChange={(o) => {
            if (!o) setFullscreenFile(null);
          }}
          code={fullscreenFile.content}
          lang={detectLang(fullscreenFile.path)}
          title={fullscreenFile.path}
        />
      )}
    </div>
  );
}
