"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { SessionSidebar } from "@/components/layout/SessionSidebar";
import { ArtifactPanel } from "@/components/layout/ArtifactPanel";
import { WorkspaceSelectionModal, type WorkspaceImportPayload } from "@/components/layout/WorkspaceSelectionModal";
import { ChatWorkspace } from "@/components/layout/ChatWorkspace";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";
import { useTaskStore } from "@/stores/taskStore";
import { useArtifactStore } from "@/stores/artifactStore";
import { useChatStore } from "@/stores/chatStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { useWorkspacePanelStore } from "@/stores/workspacePanelStore";
import { createSession, listSessions, getSessionDetail, listSessionMessages, listSessionTasks, listSessionArtifacts, getWorkspaceFiles, issueWsTicket, seedWorkspace } from "@/lib/api";
import { getActiveManager, createManager, disconnectManager } from "@/lib/websocket";
import { useConnectionStore } from "@/stores/connectionStore";
import { syncAgentChangesToUserDirectory } from "@/lib/workspaceSync";
import { savePersistedHandle } from "@/lib/fileSystemAccess";
import { useLayoutStore } from "@/stores/layoutStore";
import { ResizeHandle } from "@/components/layout/ResizeHandle";
import type { WorkspaceType, WorkspaceFileNode } from "@/types";

/**
 * Build file tree from FSA files array.
 */
function buildFileTreeFromFiles(files: Array<{ path: string; content: string }>): WorkspaceFileNode[] {
  const root: Record<string, any> = {};

  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      if (!current[part]) {
        if (isLast) {
          current[part] = { __file: true, __path: file.path };
        } else {
          current[part] = { __dir: true, __children: {} };
        }
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
      };
    });
  }

  return toNodes(root, "");
}

export default function MainLayout() {
  const [initialized, setInitialized] = useState(false);
  const [showWorkspaceSelection, setShowWorkspaceSelection] = useState(false);
  const [pendingSessionMode, setPendingSessionMode] = useState<"single_agent" | "multi_agent">("multi_agent");
  const sessionStore = useSessionStore();
  const taskStore = useTaskStore();
  const artifactStore = useArtifactStore();
  const chatStore = useChatStore();
  const workspaceStore = useWorkspaceStore();
  const workspacePanelStore = useWorkspacePanelStore();
  const layoutStore = useLayoutStore();

  // ---- Unified session creation (after workspace type selected) ----
  const createSessionWithWorkspace = async (
    workspaceType: WorkspaceType,
    sourcePath?: string,
    files?: Array<{ path: string; content: string }>,
    directoryHandle?: FileSystemDirectoryHandle,
    mode: "single_agent" | "multi_agent" = "multi_agent",
    agentId?: string,
  ) => {
    try {
      // ⭐ imported 工作区：source_path 是 FSA handle 的完整路径或者用户选中的目录名
      // 对非 FSA 模式，这里只是一个目录名，实际文件路径由 Runtime 端管理
      const effectiveSourcePath = workspaceType === "imported"
        ? (sourcePath || (directoryHandle?.name ?? ""))
        : (sourcePath || "");

      const title = `${
        workspaceType === "scratch" ? "Chat" : "Project"
      } ${new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}`;
      const newSession = await createSession({
        title,
        mode,
        workspace_type: workspaceType,
        source_path: effectiveSourcePath,
      });
      if (!newSession?.session_id) throw new Error("Failed to create session");

      // Update workspace store session_id from "pending" to real one
      const existingMeta = useWorkspaceStore.getState().meta;
      if (existingMeta?.session_id === "pending") {
        useWorkspaceStore.getState().updateMeta({
          session_id: newSession.session_id,
          workspace_id: newSession.workspace_id || newSession.session_id,
        });
      } else {
        // Initialize workspace store if not already set
        useWorkspaceStore.getState().setMeta({
          workspace_id: newSession.workspace_id || newSession.session_id,
          session_id: newSession.session_id,
          root_path: newSession.workspace_root || effectiveSourcePath,
          workspace_type: workspaceType,
          source_path: effectiveSourcePath || newSession.workspace_root,
          source_files_count: files?.length ?? 0,
          total_tasks: 0,
          created_at: newSession.created_at,
          updated_at: newSession.updated_at,
          status: "active",
        });
      }

      // ---- Seed workspace with user's actual files ----
      if (workspaceType === "imported" && files && files.length > 0 && directoryHandle) {
        useWorkspaceStore.getState().setSyncStatus("seeding");
        try {
          // ⭐ imported 工作区：不复制文件内容，只 write workspace_meta
          // Agent 直接在用户的原始目录（通过 FSA handle）读写代码
          // FSA write-back 在 task 完成后通过 workspaceSync 同步
          const result = await seedWorkspace(newSession.session_id, []);
          useWorkspaceStore.getState().updateMeta({
            source_files_count: files.length,
          });
          useWorkspaceStore.getState().setSyncStatus("seeded");
        } catch (e) {
          console.error("Failed to seed workspace", e);
          useWorkspaceStore.getState().setSyncStatus("error");
        }
      }

      // ---- Persist directory handle for sync-back ----
      if (directoryHandle) {
        useWorkspaceStore.getState().setDirectoryHandle(
          directoryHandle,
          effectiveSourcePath || directoryHandle.name
        );
        try {
          await savePersistedHandle(newSession.session_id, directoryHandle);
        } catch {
          // IndexedDB may be unavailable; sync-back will still work for this session
        }
      }

      useSessionStore.getState().addSession({
        session_id: newSession.session_id,
        title: newSession.title,
        mode: newSession.mode,
        agent_id: agentId || undefined,
        updated_at: newSession.updated_at,
        last_event_seq: 0,
        task_count: 0,
        workspace_id: newSession.workspace_id || newSession.session_id,
        workspace_root: effectiveSourcePath || newSession.workspace_root,
        workspace_type: workspaceType,
        source_files_count: files?.length ?? 0,
      });
      useSessionStore.getState().setCurrentSessionId(newSession.session_id);
      // ⭐ Stage 10: 单聊模式下保存 agentId，发消息时自动带上 mentionedAgent
      if (agentId) {
        useSessionStore.getState().setCurrentAgentId(agentId);
      }
    } catch (e) {
      console.error("Failed to create session", e);
      alert("Failed to create session. Please try again.");
    }
  };

  const [pendingSessionAgentId, setPendingSessionAgentId] = useState<string | undefined>(undefined);

  // ⭐ 竞态保护：每次 loadSessionDetail 调用递增，回调中检查是否仍为最新
  const loadSeqRef = useRef(0);
  // ⭐ 文件树轮询 interval ref
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ---- Open workspace selection modal ----
  const handleRequestNewSession = (mode: "single_agent" | "multi_agent" = "multi_agent", agentId?: string) => {
    setPendingSessionMode(mode);
    setPendingSessionAgentId(agentId);
    setShowWorkspaceSelection(true);
  };

  // ---- Workspace type selected ----
  const handleWorkspaceSelected = (payload: WorkspaceImportPayload) => {
    setShowWorkspaceSelection(false);

    // Optimistically set workspace meta for imported workspaces,
    // so the workspace panel stays visible immediately
    if (payload.workspaceType === "imported" && payload.files) {
      // Build file tree
      const fileTree = buildFileTreeFromFiles(payload.files);

      useWorkspaceStore.getState().setMeta({
        workspace_id: "pending",
        session_id: "pending",
        root_path: payload.sourcePath || "",
        workspace_type: "imported",
        source_path: payload.sourcePath,
        source_files_count: payload.files.length,
        total_tasks: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        status: "active",
      });

      useWorkspaceStore.getState().setFileTree(fileTree);
      // VSCode 模式：不预加载全部文件内容，只存文件树
      // 内容在用户点击文件时按需加载
    }

    createSessionWithWorkspace(
      payload.workspaceType,
      payload.sourcePath,
      payload.files,
      payload.directoryHandle,
      pendingSessionMode,
      pendingSessionAgentId
    );
  };

  const loadSessionDetail = async (sessionId: string) => {
    // ⭐ 竞态保护：递增序列号，只有最新请求的结果才写入 store
    loadSeqRef.current += 1;
    const mySeq = loadSeqRef.current;

    try {
      // Try to get session detail (graceful failure)
      let sessionDetail = null;
      try {
        sessionDetail = await getSessionDetail(sessionId);
        useSessionStore.getState().setCurrentSession(sessionDetail);

        // ⭐ Stage 9: 始终从 Gateway 返回的 session 重建 workspace meta
        // 刷新页面后 meta 是 null，需要重新初始化
        const existingMeta = useWorkspaceStore.getState().meta;
        const needsMetaInit = !existingMeta || existingMeta.session_id !== sessionId;

        if (needsMetaInit || (sessionDetail?.workspace_type && existingMeta?.workspace_type !== sessionDetail.workspace_type)) {
          // 清理旧 workspace 状态（如果切换到不同的 session）
          if (existingMeta?.session_id && existingMeta.session_id !== sessionId && existingMeta.session_id !== "pending") {
            useWorkspaceStore.getState().clear();
          }

          // ⭐ 从 session detail 重建 workspace meta
          useWorkspaceStore.getState().setMeta({
            workspace_id: sessionDetail.workspace_id || sessionId,
            session_id: sessionId,
            workspace_type: sessionDetail.workspace_type || "scratch",
            root_path: sessionDetail.workspace_root || "",
            source_path: sessionDetail.workspace_root || "",
            source_files_count: 0, // 从文件树获取准确数量
            total_tasks: 0,
            created_at: sessionDetail.created_at,
            updated_at: sessionDetail.updated_at,
            status: "active",
          });
        }
      } catch (e) {
        console.log("Could not load session detail, continuing with basic functionality", e);
      }

      // 只在切换到不同 session 时才清空状态
      const currentMeta = useWorkspaceStore.getState().meta;
      const isSameSession = currentMeta?.session_id === sessionId;

      if (!isSameSession) {
        useTaskStore.getState().setTasks([]);
        useArtifactStore.getState().setArtifacts([]);
        useChatStore.getState().clearMessages();
        useWorkspaceStore.getState().clear();
        useSessionStore.getState().setCurrentAgentId(null);
      }

      // Try to load messages
      try {
        const { items: messages } = await listSessionMessages(sessionId);
        useChatStore.getState().clearMessages(); // Only clear if we have new messages
        messages.forEach((m: any) => {
          useChatStore.getState().addMessage(m);
        });
      } catch (e) {
        console.log("Could not load messages", e);
      }

      // Try to load tasks
      try {
        const { items: tasks } = await listSessionTasks(sessionId);
        useTaskStore.getState().setTasks(tasks);
      } catch (e) {
        console.log("Could not load tasks", e);
      }

      // Try to load artifacts
      try {
        const { items: artifacts } = await listSessionArtifacts(sessionId);
        useArtifactStore.getState().setArtifacts(artifacts);
      } catch (e) {
        console.log("Could not load artifacts", e);
      }

      // Try to load workspace file tree
      const meta = useWorkspaceStore.getState().meta;
      const isImported = meta?.workspace_type === "imported";
      const hasPersistedTree = useWorkspaceStore.getState().fileTree.length > 0;
      
      if (!isImported || !hasPersistedTree) {
        try {
          const files = await getWorkspaceFiles(sessionId);
          useWorkspaceStore.getState().setFileTree(files);
        } catch (e) {
          console.log("Could not load workspace files", e);
        }
      }

    } catch (e) {
      console.error("Failed in loadSessionDetail", e);
    }
    // ⭐ 竞态保护：回调结束时检查，如果不是最新请求则丢弃结果
    if (mySeq !== loadSeqRef.current) {
      console.log(`[loadSessionDetail] Dropping stale result for session ${sessionId} (seq=${mySeq}, current=${loadSeqRef.current})`);
      return;
    }
  };

  useEffect(() => {
    if (!initialized) {
      setInitialized(true);
      listSessions().then(({ items: sessions }) => {
        useSessionStore.getState().setSessions(sessions);
        if (sessions.length > 0) {
          useSessionStore.getState().setCurrentSessionId(sessions[0].session_id);
        }
      }).catch((e) => {
        console.log("Could not list sessions, continuing without session history", e);
      });
    }
    return () => {
      disconnectManager();
    };
  }, [initialized]);

  // React to session changes
  useEffect(() => {
    const sessionId = sessionStore.currentSessionId;
    if (sessionId) {
      // Disconnect previous session first
      disconnectManager();
      loadSessionDetail(sessionId);

      // Connect to new session (graceful failure)
      issueWsTicket(sessionId)
        .then((ticket) => {
          createManager(sessionId, ticket.ws_ticket);
          const manager = getActiveManager();
          if (manager) {
            // ---- Register sync-back handler for task completion ----
            manager.on("task.completed", async () => {
              const wsStore = useWorkspaceStore.getState();
              const handle = wsStore.directoryHandle;

              // ⭐ Stage 9: 任务完成后自动刷新 workspace 文件树
              try {
                const files = await getWorkspaceFiles(sessionId);
                useWorkspaceStore.getState().setFileTree(files);
              } catch (e) {
                console.log("[workspace] Failed to refresh file tree after task:", e);
              }

              if (!handle || wsStore.syncStatus === "syncing") return;

              // Kick off sync in background
              syncAgentChangesToUserDirectory(sessionId, handle).then(
                (result) => {
                  if (result.synced > 0) {
                    console.log(
                      `[sync] Wrote ${result.synced} files back to local directory`
                    );
                  }
                }
              );
            });

            manager.connect();
          }
        })
        .catch((e) => {
          console.log("Could not get WebSocket ticket, offline mode only", e);
        });
    }
  }, [sessionStore.currentSessionId]);

  // ⭐ 文件树轮询：每 5 秒刷新一次（任务运行中每 3 秒）
  const isTaskRunning = useMemo(() => {
    return taskStore.tasks.some(
      (t) => t.status === "running" || t.status === "planning" || t.status === "retrying"
    );
  }, [taskStore.tasks]);
  useEffect(() => {
    const sessionId = sessionStore.currentSessionId;
    if (!sessionId) return;

    const pollMs = isTaskRunning ? 3000 : 5000;

    // 清理旧 interval
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }

    pollIntervalRef.current = setInterval(async () => {
      try {
        // ⭐ 只在当前 session 仍活跃时刷新
        if (useSessionStore.getState().currentSessionId !== sessionId) return;
        const files = await getWorkspaceFiles(sessionId);
        if (useSessionStore.getState().currentSessionId !== sessionId) return;
        useWorkspaceStore.getState().setFileTree(files);
      } catch {
        // 静默忽略轮询错误
      }
    }, pollMs);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [sessionStore.currentSessionId, isTaskRunning]);

  // Check if there are any artifacts
  const hasArtifacts = artifactStore.artifacts.length > 0;

  // Get the latest task to check its interaction mode and package strategy
  const latestTask = useMemo(() => {
    if (taskStore.tasks.length === 0) return null;
    return [...taskStore.tasks].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    )[0];
  }, [taskStore.tasks]);

  // Stage 8 V2: Chat Mode vs Project Mode
  const shouldShowWorkspacePanel = useMemo(() => {
    // 如果用户强制显示，直接返回 true
    if (workspacePanelStore.forceShow) return true;

    // 主动检查 workspace meta —— 可能在 currentSession 加载前就已设置
    const wsType = workspaceStore.meta?.workspace_type ||
      (sessionStore.currentSession as any)?.workspace_type;

    // IMPORTED → always show workspace panel (even without currentSession)
    if (wsType === "imported") return true;

    // 没有 currentSession 且不是 IMPORTED 类型，隐藏面板
    if (!sessionStore.currentSession) return false;

    // SCRATCH = Chat Mode → hide panel (unless it has artifacts from a task)
    if (wsType === "scratch") {
      return hasArtifacts;
    }

    // PROJECT = Project Mode → always show workspace panel
    if (wsType === "project") return true;

    // Backward compat: no type declared
    if (hasArtifacts) return true;
    if (sessionStore.currentSession.workspace_id) return true;

    return false;
  }, [sessionStore.currentSession, workspaceStore.meta, hasArtifacts, workspacePanelStore.forceShow]);

  return (
    <div className="flex h-full w-full overflow-hidden bg-[#F5F3EF]">
      {/* Left — Session Sidebar */}
      <div className="w-[240px] shrink-0 h-full bg-white rounded-2xl border border-[#E5E7EB] overflow-hidden mr-3">
        <SessionSidebar
          onRequestNewSession={handleRequestNewSession}
        />
      </div>

      {/* Center — Chat Area (dynamic width) */}
      <div
        className="h-full flex flex-col bg-white rounded-2xl border border-[#E5E7EB] overflow-hidden shrink-0"
        style={{ width: shouldShowWorkspacePanel ? layoutStore.chatWidth : layoutStore.chatWidth }}
      >
        <ChatWorkspace onRequestNewSession={handleRequestNewSession} />
      </div>

      {/* Resize Handle + Workspace Panel */}
      {shouldShowWorkspacePanel && (
        <>
          <ResizeHandle
            direction="horizontal"
            onResize={(delta) => layoutStore.adjustChatWidth(delta)}
          />
          <div className="flex-1 min-w-[400px] h-full bg-white rounded-2xl border border-[#E5E7EB] overflow-hidden ml-3">
            <ArtifactPanel />
          </div>
        </>
      )}

      {/* Right Spacer — when workspace is hidden */}
      {!shouldShowWorkspacePanel && (
        <div className="flex-1 bg-[#F5F3EF] ml-3" />
      )}

      {/* Workspace Selection Modal */}
      <WorkspaceSelectionModal
        open={showWorkspaceSelection}
        onClose={() => setShowWorkspaceSelection(false)}
        onSelect={handleWorkspaceSelected}
      />
    </div>
  );
}
