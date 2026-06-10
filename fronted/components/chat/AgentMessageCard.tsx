"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { resolveAgentIdentity, AgentAvatar } from "./AgentAvatar";
import type { ChatMessagePayload } from "@/types";

interface AgentMessageCardProps {
  payload: ChatMessagePayload;
  timestamp: string;
  agentName?: string;
}

export function AgentMessageCard({ payload, agentName, isStreaming }: AgentMessageCardProps & { isStreaming?: boolean }) {
  const rawAgent = agentName || payload.agent || "system";
  const identity = resolveAgentIdentity(rawAgent);
  const displayName = identity.name;
  const displayRole = identity.role;

  return (
    <div className="flex gap-3 px-6 py-3">
      {/* Agent avatar — 用 AgentAvatar 组件（支持 logo 图片） */}
      <AgentAvatar agentId={rawAgent} size="md" className="mt-0.5" />

      {/* Content */}
      <div className="min-w-0 flex-1">
        {/* Agent identity line */}
        <div className="flex items-center gap-1.5 mb-1">
          <span className="text-[13px] font-semibold text-[#111827]">
            {displayName}
          </span>
          <span className="text-[11px] text-[#9CA3AF]">· {isStreaming ? "typing..." : displayRole}</span>
        </div>

        {/* Message bubble */}
        <div className="rounded-[8px] rounded-bl-[4px] border border-[#E5E7EB] bg-white px-4 py-2.5 inline-block max-w-full">
          {payload.format === "markdown" || payload.format === "diff" ? (
            <div className="prose prose-sm max-w-none text-[14px] leading-[1.7] [&_pre]:bg-[#1E293B] [&_pre]:border [&_pre]:border-[#334155] [&_pre]:rounded-lg [&_pre]:my-3 [&_code]:text-[13px] [&_p]:leading-[1.7] [&_li]:leading-[1.7] [&_blockquote]:border-l-2 [&_blockquote]:border-[#E5E7EB] [&_blockquote]:pl-4 [&_blockquote]:text-[#6B7280]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {payload.content}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="whitespace-pre-wrap break-words text-[14px] leading-[1.7] text-[#111827]">
              {payload.content}
              {isStreaming && (
                <span className="inline-block w-2 h-4 bg-[#111827]/60 animate-pulse ml-0.5 align-middle" />
              )}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
