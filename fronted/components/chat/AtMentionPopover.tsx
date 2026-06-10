"use client";

import { AGENT_REGISTRY } from "./AgentAvatar";

export interface AgentOption {
  id: string;
  name: string;
  role: string;
  icon: React.ComponentType<{ className?: string }>;
  group: "system" | "persona";
}

const SYSTEM_AGENTS: AgentOption[] = [
  {
    id: "claude-code",
    name: "Claude Code",
    role: "复杂项目",
    icon: AGENT_REGISTRY["claude-code"].icon,
    group: "system",
  },
  {
    id: "testing",
    name: "Test Agent",
    role: "测试生成",
    icon: AGENT_REGISTRY.testing.icon,
    group: "system",
  },
  {
    id: "documentation",
    name: "Doc Agent",
    role: "文档生成",
    icon: AGENT_REGISTRY.documentation.icon,
    group: "system",
  },
  {
    id: "codex",
    name: "Codex",
    role: "项目快速开发",
    icon: AGENT_REGISTRY.codex.icon,
    group: "system",
  },
];

const PERSONA_AGENTS: AgentOption[] = [
  {
    id: "backend_architect",
    name: "Backend Architect",
    role: "后端架构 — Go/Gin/GORM",
    icon: AGENT_REGISTRY.backend_architect.icon,
    group: "persona",
  },
  {
    id: "frontend_engineer",
    name: "Frontend Engineer",
    role: "前端开发 — React/Next.js",
    icon: AGENT_REGISTRY.frontend_engineer.icon,
    group: "persona",
  },
  {
    id: "devops_engineer",
    name: "DevOps Engineer",
    role: "部署运维 — Docker/K8s",
    icon: AGENT_REGISTRY.devops_engineer.icon,
    group: "persona",
  },
  {
    id: "qa_engineer",
    name: "QA Engineer",
    role: "质量保证 — 测试与审查",
    icon: AGENT_REGISTRY.qa_engineer.icon,
    group: "persona",
  },
  {
    id: "security_reviewer",
    name: "Security Reviewer",
    role: "安全审查 — OWASP",
    icon: AGENT_REGISTRY.security_reviewer.icon,
    group: "persona",
  },
];

const OFFICIAL_AGENTS: AgentOption[] = [...SYSTEM_AGENTS, ...PERSONA_AGENTS];

interface AtMentionPopoverProps {
  open: boolean;
  onClose: () => void;
  onSelect: (agent: AgentOption) => void;
}

export function AtMentionPopover({
  open,
  onClose,
  onSelect,
}: AtMentionPopoverProps) {
  if (!open) return null;

  const handleSelect = (agent: AgentOption) => {
    onSelect(agent);
    onClose();
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40" onClick={onClose} />

      {/* Popover */}
      <div className="absolute bottom-full left-0 mb-2 z-50 w-56 rounded-[8px] border border-[#E5E7EB] bg-white animate-fade-in-up overflow-hidden">
        {/* Header */}
        <div className="px-3 py-2 border-b border-[#E5E7EB]">
          <p className="text-[11px] text-[#9CA3AF] font-medium">Mention Agent</p>
        </div>

        {/* System Agents */}
        <div className="py-1">
          <div className="px-3 py-1">
            <p className="text-[10px] text-[#9CA3AF] font-medium uppercase tracking-wide">Runtime Agent</p>
          </div>
          {SYSTEM_AGENTS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => handleSelect(agent)}
              className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[#F3F4F6] transition-colors"
            >
              <div className="h-6 w-6 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                <span className="text-[10px] font-semibold">{agent.name.charAt(0)}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-[#111827] leading-tight">@{agent.name}</p>
                <p className="text-[11px] text-[#9CA3AF] leading-tight">{agent.role}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="mx-3 border-t border-[#E5E7EB]" />

        {/* Persona Agents */}
        <div className="py-1">
          <div className="px-3 py-1">
            <p className="text-[10px] text-[#9CA3AF] font-medium uppercase tracking-wide">Persona Agent</p>
          </div>
          {PERSONA_AGENTS.map((agent) => (
            <button
              key={agent.id}
              onClick={() => handleSelect(agent)}
              className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-[#F3F4F6] transition-colors"
            >
              <div className="h-6 w-6 rounded-full bg-[#111827] text-white flex items-center justify-center shrink-0">
                <span className="text-[10px] font-semibold">{agent.name.charAt(0)}</span>
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-[#111827] leading-tight">@{agent.name}</p>
                <p className="text-[11px] text-[#9CA3AF] leading-tight">{agent.role}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export { OFFICIAL_AGENTS };
