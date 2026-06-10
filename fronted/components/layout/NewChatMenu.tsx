"use client";

import { useState, useRef, useEffect } from "react";
import { Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";

// ---- Agent Contact Definitions ----
interface AgentContact {
  id: string;
  name: string;
  tag: string;
  mentionPrefix: string;
  group: "system" | "persona";
}

const SYSTEM_AGENTS: AgentContact[] = [
  { id: "claude-code", name: "Claude Code", tag: "复杂项目审查", mentionPrefix: "@Claude Code", group: "system" },
  { id: "testing", name: "Test Agent", tag: "测试生成", mentionPrefix: "@Test Agent", group: "system" },
  { id: "documentation", name: "Doc Agent", tag: "文档生成", mentionPrefix: "@Doc Agent", group: "system" },
  { id: "codex", name: "Codex", tag: "项目快速开发", mentionPrefix: "@Codex", group: "system" },
];

const PERSONA_AGENTS: AgentContact[] = [
  { id: "backend_architect", name: "Backend Architect", tag: "后端架构 — Go/Gin", mentionPrefix: "@Backend Architect", group: "persona" },
  { id: "frontend_engineer", name: "Frontend Engineer", tag: "前端开发 — React/Next.js", mentionPrefix: "@Frontend Engineer", group: "persona" },
  { id: "devops_engineer", name: "DevOps Engineer", tag: "部署运维 — Docker/K8s", mentionPrefix: "@DevOps Engineer", group: "persona" },
  { id: "qa_engineer", name: "QA Engineer", tag: "质量保证 — 测试审查", mentionPrefix: "@QA Engineer", group: "persona" },
  { id: "security_reviewer", name: "Security Reviewer", tag: "安全审查 — OWASP", mentionPrefix: "@Security Reviewer", group: "persona" },
];

interface NewChatMenuProps {
  onCreateMultiAgentSession: () => void;
  onCreateSingleAgentSession: (agent: AgentContact) => void;
}

export function NewChatMenu({ onCreateMultiAgentSession, onCreateSingleAgentSession }: NewChatMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        open &&
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  return (
    <div className="relative">
      {/* Trigger Button */}
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        className="flex items-center justify-center h-7 w-7 rounded-lg hover:bg-[#F3F4F6] transition-colors"
      >
        {open ? <X className="h-4 w-4 text-[#9CA3AF]" /> : <Plus className="h-4 w-4 text-[#9CA3AF]" />}
      </button>

      {/* Popup Menu */}
      {open && (
        <div
          ref={menuRef}
          className="absolute right-0 bottom-full mb-2 z-50 w-64 rounded-xl border border-[#E5E7EB] bg-white shadow-lg overflow-hidden animate-fade-in-up"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-[#E5E7EB]">
            <p className="text-[13px] font-semibold text-[#111827]">新建群聊</p>
            <p className="text-[11px] text-[#9CA3AF] mt-0.5">选择对话类型</p>
          </div>

          {/* Group Chat Option */}
          <button
            onClick={() => {
              onCreateMultiAgentSession();
              setOpen(false);
            }}
            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#F3F4F6] transition-colors"
          >
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center shrink-0">
              <span className="text-[13px] font-semibold">群</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-medium text-[#111827] truncate">新建群聊</p>
              <p className="text-[11px] text-[#9CA3AF] truncate">使用 @ 提到多个 agent 协作</p>
            </div>
          </button>

          {/* Divider */}
          <div className="mx-4 border-t border-[#E5E7EB]" />

          {/* System Agents */}
          <div className="px-4 py-3">
            <p className="text-[11px] font-medium text-[#9CA3AF] uppercase tracking-wide mb-2">Runtime Agent</p>
            {SYSTEM_AGENTS.map((agent) => (
              <button
                key={agent.id}
                onClick={() => {
                  onCreateSingleAgentSession(agent);
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left hover:bg-[#F3F4F6] transition-colors mb-1"
              >
                <div className="h-7 w-7 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                  <span className="text-[11px] font-semibold">{agent.name.charAt(0)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-[#111827] truncate">{agent.name}</p>
                  <p className="text-[11px] text-[#9CA3AF] truncate">{agent.tag}</p>
                </div>
              </button>
            ))}
          </div>

          {/* Divider */}
          <div className="mx-4 border-t border-[#E5E7EB]" />

          {/* Persona Agents */}
          <div className="px-4 py-3">
            <p className="text-[11px] font-medium text-[#9CA3AF] uppercase tracking-wide mb-2">Persona Agent</p>
            {PERSONA_AGENTS.map((agent) => (
              <button
                key={agent.id}
                onClick={() => {
                  onCreateSingleAgentSession(agent);
                  setOpen(false);
                }}
                className="w-full flex items-center gap-2.5 px-2 py-1.5 rounded-lg text-left hover:bg-[#F3F4F6] transition-colors mb-1"
              >
                <div className="h-7 w-7 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                  <span className="text-[11px] font-semibold">{agent.name.charAt(0)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-[#111827] truncate">{agent.name}</p>
                  <p className="text-[11px] text-[#9CA3AF] truncate">{agent.tag}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
