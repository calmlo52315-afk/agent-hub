"use client";

import { useMemo } from "react";
import type { ChatMessagePayload } from "@/types";

interface UserMessageCardProps {
  payload: ChatMessagePayload;
  timestamp: string;
  senderName?: string;
}

const MENTION_RE = /@(Claude Code|Codex|Orchestrator|Review Agent|Artifact Agent)\b/g;

export function UserMessageCard({ payload }: UserMessageCardProps) {
  const parts = useMemo(() => {
    const text = payload.content;
    const result: Array<{ type: "text" | "mention"; value: string }> = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = MENTION_RE.exec(text)) !== null) {
      if (match.index > lastIndex) {
        result.push({ type: "text", value: text.slice(lastIndex, match.index) });
      }
      result.push({ type: "mention", value: `@${match[1]}` });
      lastIndex = MENTION_RE.lastIndex;
    }
    if (lastIndex < text.length) {
      result.push({ type: "text", value: text.slice(lastIndex) });
    }
    return result;
  }, [payload.content]);

  const hasMentions = parts.some((p) => p.type === "mention");

  return (
    <div className="flex justify-end px-6 py-2">
      <div className="max-w-[75%] rounded-[8px] rounded-br-[4px] px-4 py-2.5 text-[14px] leading-[1.65] bg-[#F3F4F6] text-[#111827]">
        {hasMentions ? (
          <p className="whitespace-pre-wrap break-words">
            {parts.map((part, i) =>
              part.type === "mention" ? (
                <span
                  key={i}
                  className="inline font-medium bg-[#E5E7EB] text-[#111827] rounded-[4px] px-1 py-0.5"
                >
                  {part.value}
                </span>
              ) : (
                <span key={i}>{part.value}</span>
              )
            )}
          </p>
        ) : (
          <p className="whitespace-pre-wrap break-words">{payload.content}</p>
        )}
      </div>
    </div>
  );
}
