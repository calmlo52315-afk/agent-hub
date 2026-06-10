"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";
import {
  Code2,
  SearchCheck,
  Sparkles,
  ShieldCheck,
  Package,
  User,
  Bot,
  FlaskConical,
  FileText,
  Server,
  Wrench,
  Bug,
  Lock,
  Monitor,
} from "lucide-react";

// ---- Agent Logo Map —— 用 public/logo/ 下的 SVG 图片替代黑色圆圈 ----
const AGENT_LOGOS: Record<string, string> = {
  "claude-code": "/logo/claude-icon.svg",
  codex: "/logo/codex-color.svg",
};

// ---- Agent Identity Config ----
// Pure black/white avatars — no colors

// ── RuntimeAgent (系统内置) ──────────────────────────
export type RuntimeAgentId =
  | "claude-code"
  | "codex"
  | "orchestrator"
  | "review-agent"
  | "artifact-agent"
  | "testing"
  | "documentation"
  | "user"
  | "system";

// ── UserDefinedAgent (Persona) ────────────────────────
export type PersonaAgentId =
  | "backend_architect"
  | "frontend_engineer"
  | "devops_engineer"
  | "qa_engineer"
  | "security_reviewer";

export type AgentId = RuntimeAgentId | PersonaAgentId;

export interface AgentIdentity {
  id: string;
  name: string;
  role: string;
  avatar?: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const AGENT_REGISTRY: Record<string, AgentIdentity> = {
  // ── RuntimeAgent (系统内置) ──────────────────────────
  "claude-code": {
    id: "claude-code",
    name: "Claude Code",
    role: "代码生成",
    icon: Code2,
  },
  codex: {
    id: "codex",
    name: "Codex",
    role: "代码评审",
    icon: SearchCheck,
  },
  orchestrator: {
    id: "orchestrator",
    name: "Orchestrator",
    role: "编排调度",
    icon: Sparkles,
  },
  "review-agent": {
    id: "review-agent",
    name: "Review Agent",
    role: "代码审查",
    icon: ShieldCheck,
  },
  "artifact-agent": {
    id: "artifact-agent",
    name: "Artifact Agent",
    role: "产物归档",
    icon: Package,
  },
  testing: {
    id: "testing",
    name: "Test Agent",
    role: "测试生成",
    icon: FlaskConical,
  },
  documentation: {
    id: "documentation",
    name: "Doc Agent",
    role: "文档生成",
    icon: FileText,
  },
  user: {
    id: "user",
    name: "You",
    role: "用户",
    icon: User,
  },
  system: {
    id: "system",
    name: "System",
    role: "系统",
    icon: Bot,
  },
  // ── UserDefinedAgent (Persona) ───────────────────────
  backend_architect: {
    id: "backend_architect",
    name: "Backend Architect",
    role: "后端架构",
    icon: Server,
  },
  frontend_engineer: {
    id: "frontend_engineer",
    name: "Frontend Engineer",
    role: "前端开发",
    icon: Monitor,
  },
  devops_engineer: {
    id: "devops_engineer",
    name: "DevOps Engineer",
    role: "部署运维",
    icon: Wrench,
  },
  qa_engineer: {
    id: "qa_engineer",
    name: "QA Engineer",
    role: "质量保证",
    icon: Bug,
  },
  security_reviewer: {
    id: "security_reviewer",
    name: "Security Reviewer",
    role: "安全审查",
    icon: Lock,
  },
};

/**
 * Resolve agent identity from a raw agent string/type.
 */
export function resolveAgentIdentity(raw?: string): AgentIdentity {
  if (!raw) return AGENT_REGISTRY.system;
  if (AGENT_REGISTRY[raw]) return AGENT_REGISTRY[raw];

  const mapping: Record<string, string> = {
    coding: "claude-code",
    review: "codex",
    artifact: "artifact-agent",
    orchestrator: "orchestrator",
    testing: "testing",
    documentation: "documentation",
    backend_architect: "backend_architect",
    frontend_engineer: "frontend_engineer",
    devops_engineer: "devops_engineer",
    qa_engineer: "qa_engineer",
    security_reviewer: "security_reviewer",
  };
  const mapped = mapping[raw];
  if (mapped && AGENT_REGISTRY[mapped]) return AGENT_REGISTRY[mapped];

  const lower = raw.toLowerCase();
  if (lower.includes("claude") || lower.includes("coding"))
    return AGENT_REGISTRY["claude-code"];
  if (lower.includes("codex") || lower.includes("review"))
    return AGENT_REGISTRY.codex;
  if (lower.includes("orchestrat") || lower.includes("plan"))
    return AGENT_REGISTRY.orchestrator;
  if (lower.includes("artifact") || lower.includes("bundle") || lower.includes("package"))
    return AGENT_REGISTRY["artifact-agent"];
  if (lower.includes("test"))
    return AGENT_REGISTRY.testing;
  if (lower.includes("doc") || lower.includes("documentation"))
    return AGENT_REGISTRY.documentation;
  if (lower.includes("backend") || lower.includes("architect"))
    return AGENT_REGISTRY.backend_architect;
  if (lower.includes("frontend"))
    return AGENT_REGISTRY.frontend_engineer;
  if (lower.includes("devops") || lower.includes("deploy"))
    return AGENT_REGISTRY.devops_engineer;
  if (lower.includes("qa") || lower.includes("quality"))
    return AGENT_REGISTRY.qa_engineer;
  if (lower.includes("security") || lower.includes("安全"))
    return AGENT_REGISTRY.security_reviewer;

  return AGENT_REGISTRY.system;
}

// ---- AgentAvatar Component ----

export interface AgentAvatarProps {
  agentId?: string;
  name?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const sizeConfig = {
  sm: { container: "h-5 w-5", icon: "h-2.5 w-2.5", text: "text-[9px]", img: "h-3.5 w-3.5" },
  md: { container: "h-7 w-7", icon: "h-3 w-3", text: "text-[11px]", img: "h-5 w-5" },
  lg: { container: "h-8 w-8", icon: "h-4 w-4", text: "text-[13px]", img: "h-6 w-6" },
};

export function AgentAvatar({
  agentId,
  name,
  size = "md",
  className,
}: AgentAvatarProps) {
  const identity = agentId
    ? resolveAgentIdentity(agentId)
    : AGENT_REGISTRY.system;

  const displayName = name || identity.name;
  const sizes = sizeConfig[size];

  // ⭐ 如果该 agent 有对应的 logo SVG，用图片渲染
  const logoPath = AGENT_LOGOS[identity.id];
  if (logoPath) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-full bg-white border border-[#E5E7EB] shrink-0 overflow-hidden",
          sizes.container,
          className
        )}
      >
        <Image
          src={logoPath}
          alt={displayName}
          width={28}
          height={28}
          className={cn("object-contain", sizes.img)}
        />
      </div>
    );
  }

  // 无 logo 的 agent 用 lucide icon
  const IconComponent = identity.icon;
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full bg-[#111827] text-white shrink-0",
        sizes.container,
        className
      )}
    >
      <IconComponent className={sizes.icon} />
    </div>
  );
}
