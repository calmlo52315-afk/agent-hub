"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import Image from "next/image";
import { useSessionStore } from "@/stores/sessionStore";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { SessionSummary, AgentDefinition } from "@/types";
import * as api from "@/lib/api";
import { Trash2, UserPlus, Trash2Icon } from "lucide-react";
import { CreateAgentModal } from "./CreateAgentModal";

// ---- Agent Contact Definitions ----
interface AgentContact {
  id: string;
  name: string;
  tag: string;
  mentionPrefix: string;
  /** Logo 路径；有则用图片，无则用首字母 */
  logoPath?: string;
  /** 首字母覆盖 */
  initial?: string;
  /** 是否为用户创建的 agent */
  isUserAgent?: boolean;
}

const SYSTEM_AGENT_CONTACTS: AgentContact[] = [
  { id: "claude-code", name: "Claude Code", tag: "复杂项目开发", mentionPrefix: "@claude-code", logoPath: "/logo/claude-icon.svg" },
  { id: "codex", name: "Codex", tag: "项目快速开发", mentionPrefix: "@codex", logoPath: "/logo/codex-color.svg" },
  { id: "testing", name: "Test Agent", tag: "测试生成", mentionPrefix: "@testing", initial: "T" },
  { id: "documentation", name: "Doc Agent", tag: "文档生成", mentionPrefix: "@documentation", initial: "D" },
];

function userAgentToContact(a: AgentDefinition): AgentContact {
  return {
    id: a.id,
    name: a.name,
    tag: a.description || "用户 Agent",
    mentionPrefix: `@${a.name}`,
    initial: a.name.charAt(0),
    isUserAgent: true,
  };
}

interface SessionSidebarProps {
  /** agentId 仅在 single_agent 模式下有意义，表示用户选择了哪个 Agent 单聊 */
  onRequestNewSession: (mode: "single_agent" | "multi_agent", agentId?: string) => void;
}

/** Group sessions by date: Today / Yesterday / Older */
function groupSessionsByDate(sessions: SessionSummary[]) {
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);

  const groups: { label: string; items: SessionSummary[] }[] = [];
  const today: SessionSummary[] = [];
  const yesterday: SessionSummary[] = [];
  const older: SessionSummary[] = [];

  for (const s of sessions) {
    const d = new Date(s.updated_at);
    if (d >= todayStart) {
      today.push(s);
    } else if (d >= yesterdayStart) {
      yesterday.push(s);
    } else {
      older.push(s);
    }
  }

  if (today.length) groups.push({ label: "今天", items: today });
  if (yesterday.length) groups.push({ label: "昨天", items: yesterday });
  if (older.length) groups.push({ label: "更早", items: older });

  return groups;
}

export function SessionSidebar({ onRequestNewSession }: SessionSidebarProps) {
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const setCurrentSessionId = useSessionStore((s) => s.setCurrentSessionId);
  const loading = useSessionStore((s) => s.loading);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [userAgents, setUserAgents] = useState<AgentDefinition[]>([]);

  const grouped = useMemo(() => groupSessionsByDate(sessions), [sessions]);

  // ⭐ 加载用户自定义 agent
  const loadUserAgents = useCallback(async () => {
    try {
      const agents = await api.listAgents();
      // 过滤掉内置 agent（它们的 visibility 为 "public" 但 id 在 SYSTEM_AGENT_CONTACTS 中）
      const systemIds = new Set(SYSTEM_AGENT_CONTACTS.map((a) => a.id));
      setUserAgents(agents.filter((a) => !systemIds.has(a.id)));
    } catch {
      // 静默失败 — 用户 agent 不可用时不影响基础功能
    }
  }, []);

  useEffect(() => {
    loadUserAgents();
  }, [loadUserAgents]);

  // ⭐ 合并 agent 列表：系统 + 用户
  const allContacts = useMemo<AgentContact[]>(() => {
    const userContacts = userAgents.map(userAgentToContact);
    return [...SYSTEM_AGENT_CONTACTS, ...userContacts];
  }, [userAgents]);

  const handleAgentCreated = useCallback(
    (agent: AgentDefinition) => {
      setUserAgents((prev) => [...prev, agent]);
    },
    []
  );

  const handleDeleteUserAgent = useCallback(
    async (e: React.MouseEvent, agentId: string) => {
      e.stopPropagation();
      try {
        await api.deleteAgent(agentId);
        setUserAgents((prev) => prev.filter((a) => a.id !== agentId));
      } catch (err) {
        console.error("Failed to delete agent:", err);
      }
    },
    []
  );

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await api.deleteSession(sessionId);
      deleteSession(sessionId);
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between shrink-0">
        <span className="text-[13px] font-semibold text-[#111827] tracking-tight">
          对话
        </span>
      </div>

      <div className="flex-1 flex flex-col min-h-0">
        {/* Agent Contacts — fixed at top */}
        <div className="px-3 pb-1 shrink-0">
          <p className="text-[11px] font-medium text-[#9CA3AF] uppercase tracking-wide px-1 mb-1">
            Agents
          </p>
          {/* Create Group Chat Button */}
          <button
            onClick={() => onRequestNewSession("multi_agent")}
            className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left hover:bg-[#F3F4F6] transition-colors mb-1"
          >
            <div className="h-7 w-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center shrink-0">
              <span className="text-[11px] font-semibold">+</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium text-[#111827] truncate">新建群聊</p>
              <p className="text-[11px] text-[#9CA3AF] truncate">选择工作区类型</p>
            </div>
          </button>

          {allContacts.map((agent) => (
            <div key={agent.id} className="group relative">
              <button
                onClick={() => onRequestNewSession("single_agent", agent.id)}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left hover:bg-[#F3F4F6] transition-colors"
              >
                {agent.logoPath ? (
                  <div className="h-7 w-7 rounded-full bg-white border border-[#E5E7EB] flex items-center justify-center shrink-0 overflow-hidden">
                    <Image
                      src={agent.logoPath}
                      alt={agent.name}
                      width={20}
                      height={20}
                      className="object-contain"
                    />
                  </div>
                ) : (
                  <div className="h-7 w-7 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                    <span className="text-[11px] font-semibold">
                      {agent.initial || agent.name.charAt(0)}
                    </span>
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-[#111827] truncate">
                    {agent.name}
                  </p>
                  <p className="text-[11px] text-[#9CA3AF] truncate">
                    {agent.tag}
                  </p>
                </div>
              </button>
              {/* 用户 agent 可删除 */}
              {agent.isUserAgent && (
                <button
                  onClick={(e) => handleDeleteUserAgent(e, agent.id)}
                  className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-50 hover:text-red-500 rounded"
                  title="删除 Agent"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}

          {/* ⭐ 创建 Agent 按钮 */}
          <button
            onClick={() => setShowCreateAgent(true)}
            className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left hover:bg-[#F3F4F6] transition-colors mt-0.5"
          >
            <div className="h-7 w-7 rounded-full border border-dashed border-[#D1D5DB] text-[#9CA3AF] flex items-center justify-center shrink-0">
              <UserPlus className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] text-[#9CA3AF]">创建 Agent</p>
            </div>
          </button>
        </div>

        {/* Divider */}
        <div className="mx-3 border-t border-[#E5E7EB] shrink-0" />

        {/* History Sessions — scrollable */}
        <ScrollArea className="flex-1">
          <div className="px-3 py-2">
            {loading ? (
              <div className="space-y-1">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-9 rounded-lg bg-[#F3F4F6] animate-pulse" />
                ))}
              </div>
            ) : grouped.length === 0 ? (
              <div className="py-8 text-center">
                <p className="text-xs text-[#9CA3AF]">暂无对话</p>
              </div>
            ) : (
              <div className="space-y-3">
                {grouped.map((group) => (
                  <div key={group.label}>
                    <p className="text-[11px] font-medium text-[#9CA3AF] px-2 mb-1">
                      {group.label}
                    </p>
                    <div className="space-y-0.5">
                      {group.items.map((session) => {
                        // ⭐ 聊天历史显示对应的单聊/群聊 logo
                        const isMulti = session.mode === "multi_agent";
                        const singleAgentId = !isMulti ? session.agent_id : null;
                        const singleContact = singleAgentId
                          ? allContacts.find((c) => c.id === singleAgentId)
                          : null;

                        return (
                        <div
                          key={session.session_id}
                          className={cn(
                            "w-full text-left rounded-lg px-2 py-1.5 transition-colors group flex items-center gap-2",
                            session.session_id === currentSessionId
                              ? "bg-[#E5E7EB]"
                              : "hover:bg-[#F3F4F6]"
                          )}
                        >
                          {/* 会话模式 logo */}
                          {isMulti ? (
                            <div className="h-5 w-5 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center shrink-0">
                              <span className="text-[8px] font-semibold">群</span>
                            </div>
                          ) : singleContact?.logoPath ? (
                            <div className="h-5 w-5 rounded-full bg-white border border-[#E5E7EB] flex items-center justify-center shrink-0 overflow-hidden">
                              <Image
                                src={singleContact.logoPath}
                                alt={singleContact.name}
                                width={14}
                                height={14}
                                className="object-contain"
                              />
                            </div>
                          ) : (
                            <div className="h-5 w-5 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                              <span className="text-[8px] font-semibold">
                                {singleContact?.initial || "单"}
                              </span>
                            </div>
                          )}
                          <button
                            onClick={() => setCurrentSessionId(session.session_id)}
                            className="flex-1 text-left min-w-0"
                          >
                            <p className="text-[13px] font-medium text-[#111827] truncate">
                              {session.title}
                            </p>
                          </button>
                          <button
                            onClick={(e) => handleDeleteSession(e, session.session_id)}
                            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-red-50 hover:text-red-500 rounded shrink-0"
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* ⭐ 创建 Agent 弹窗 */}
      <CreateAgentModal
        open={showCreateAgent}
        onClose={() => setShowCreateAgent(false)}
        onCreated={handleAgentCreated}
      />

      {/* Bottom — user area */}
      <div className="border-t border-[#E5E7EB] px-4 py-2.5 flex items-center gap-2 shrink-0">
        <div className="h-6 w-6 rounded-full bg-[#111827] text-white text-[10px] flex items-center justify-center font-semibold shrink-0">
          AH
        </div>
        <span className="text-xs text-[#9CA3AF] truncate">AgentHub User</span>
      </div>
    </div>
  );
}
