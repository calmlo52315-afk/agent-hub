"use client";

import { useMemo } from "react";
import Image from "next/image";
import { useSessionStore } from "@/stores/sessionStore";
import { useConnectionStore } from "@/stores/connectionStore";
import { useTaskStore } from "@/stores/taskStore";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { useWorkspacePanelStore } from "@/stores/workspacePanelStore";
import { ChatMessageList } from "@/components/chat/ChatMessageList";
import { InputComposer } from "@/components/chat/InputComposer";
import { EmptyStateGuide } from "@/components/chat/EmptyStateGuide";
import { ThinkBar } from "@/components/chat/ThinkBar";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { resolveAgentIdentity } from "@/components/chat/AgentAvatar";
import { getActiveManager } from "@/lib/websocket";
import { cn } from "@/lib/utils";
import { PanelRightOpen, PanelRightClose, X } from "lucide-react";

// ---- Agent Logo Map (与 AgentAvatar.tsx 保持一致) ----
const AGENT_LOGOS: Record<string, string> = {
  "claude-code": "/logo/claude-icon.svg",
  codex: "/logo/codex-color.svg",
};

interface ChatWorkspaceProps {
  onRequestNewSession: (mode: "single_agent" | "multi_agent", agentId?: string) => void;
}

export function ChatWorkspace({ onRequestNewSession }: ChatWorkspaceProps) {
  const currentSession = useSessionStore((s) => s.currentSession);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const connected = useConnectionStore((s) => s.state === "connected");
  const tasks = useTaskStore((s) => s.tasks);

  const wsMeta = useWorkspaceStore((s) => s.meta);
  const workspacePanel = useWorkspacePanelStore();
  // ⭐ 所有 hooks 必须在 early return 之前调用
  const currentAgentId = useSessionStore((s) => s.currentAgentId);

  const thinkStatus = useMemo(() => {
    if (tasks.length === 0) return { status: "", visible: false };
    const runningTask = tasks.find(
      (t) => t.status === "running" || t.status === "planning" || t.status === "retrying"
    );
    if (runningTask) {
      if (runningTask.current_agent === "coding") return { status: "coding", visible: true };
      if (runningTask.current_agent === "review") return { status: "review", visible: true };
      if (runningTask.current_agent === "artifact") return { status: "bundle", visible: true };
      if (runningTask.status === "planning") return { status: "planning", visible: true };
      return { status: "running", visible: true };
    }
    const allDone = tasks.every((t) => t.status === "completed" || t.status === "failed");
    if (allDone && tasks.length > 0) return { status: "completed", visible: true };
    return { status: "", visible: false };
  }, [tasks]);

  const isTaskRunning = useMemo(() => {
    return tasks.some(
      (t) => t.status === "running" || t.status === "planning" || t.status === "retrying"
    );
  }, [tasks]);

  const handleSendMessage = (content: string) => {
    if (!currentSessionId) return;
    const manager = getActiveManager();
    if (manager) {
      // ⭐ Stage 10: 单聊模式下自动传递 mentionedAgent
      const agentId = useSessionStore.getState().currentAgentId;
      manager.sendChatMessage(content, "user", "plain", agentId || undefined);
    }
  };

  const handleStopTask = () => {
    const manager = getActiveManager();
    if (manager) {
      console.log("Stopping task...");
    }
  };

  // No session — show empty state
  if (!currentSession) {
    return (
      <div className="flex h-full flex-col bg-white">
        <div className="flex-1 flex items-center justify-center">
          <EmptyStateGuide
            onRequestNewSession={onRequestNewSession}
          />
        </div>
      </div>
    );
  }

  // 检测会话模式
  const isSingleAgent = currentSession?.mode === "single_agent";

  // 工作区类型指示器
  const wsType = wsMeta?.workspace_type;
  const wsTypeLabel =
    wsType === "scratch" ? "临时" :
    wsType === "project" ? "项目" :
    wsType === "imported" ? "导入" : "";

  const getPlaceholder = () => {
    if (!connected) return "Connecting...";
    if (isSingleAgent) {
      return "描述你的任务...";
    }
    return "描述你的任务... @Agent to mention";
  };

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Top Bar */}
      <div className="flex items-center justify-between px-6 py-3 shrink-0">
        <div className="min-w-0 flex-1 flex items-center gap-3">
          <div className="flex items-center gap-2">
            {/* ⭐ 对话类型指示器 — 群聊 / Claude Code / Codex */}
            {isSingleAgent && currentAgentId ? (
              (() => {
                const agentIdentity = resolveAgentIdentity(currentAgentId);
                const logoPath = AGENT_LOGOS[agentIdentity.id];
                return (
                  <>
                    {logoPath ? (
                      <div className="h-6 w-6 rounded-full bg-white border border-[#E5E7EB] flex items-center justify-center shrink-0 overflow-hidden">
                        <Image
                          src={logoPath}
                          alt={agentIdentity.name}
                          width={16}
                          height={16}
                          className="object-contain"
                        />
                      </div>
                    ) : (
                      <div className="h-6 w-6 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-white flex items-center justify-center shrink-0">
                        <span className="text-[10px] font-semibold">单</span>
                      </div>
                    )}
                    <h2 className="text-[15px] font-semibold text-[#111827] truncate max-w-[400px]">
                      {currentSession.title}
                    </h2>
                  </>
                );
              })()
            ) : (
              <>
                <div className="h-6 w-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center shrink-0">
                  <span className="text-[10px] font-semibold">群</span>
                </div>
                <h2 className="text-[15px] font-semibold text-[#111827] truncate max-w-[400px]">
                  {currentSession.title}
                </h2>
              </>
            )}
            {/* Workspace type badge */}
            {wsType && (
              <span className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0",
                wsType === "scratch"
                  ? "bg-[#F3F4F6] text-[#6B7280]"
                  : wsType === "project"
                  ? "bg-[#DBEAFE] text-[#1E40AF]"
                  : "bg-[#FEF3C7] text-[#92400E]"
              )}>
                {wsTypeLabel}
              </span>
            )}
          </div>
          <ConnectionStatus />
        </div>

        {/* ⭐ Workspace panel toggle — moved to top-right */}
        <button
          onClick={() => useWorkspacePanelStore.getState().toggle()}
          className="flex items-center justify-center h-7 w-7 rounded-lg hover:bg-[#F3F4F6] transition-colors shrink-0"
          title={workspacePanel.forceShow ? "隐藏工作区" : "显示工作区"}
        >
          {workspacePanel.forceShow ? (
            <PanelRightClose className="h-4 w-4 text-[#6B7280]" />
          ) : (
            <PanelRightOpen className="h-4 w-4 text-[#9CA3AF]" />
          )}
        </button>
      </div>

      {/* Divider */}
      <div className="mx-6 border-t border-[#E5E7EB]" />

      {/* Messages */}
      <ChatMessageList />

      {/* Think Bar */}


      {/* Input */}
      <InputComposer
        onSend={handleSendMessage}
        onStop={handleStopTask}
        isTaskRunning={isTaskRunning}
        disabled={!connected}
        placeholder={getPlaceholder()}
        showAtButton={!isSingleAgent}
      />
    </div>
  );
}
