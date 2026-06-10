"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, formatTime } from "@/lib/utils";
import { AgentTag } from "./AgentTag";
import type { RealtimeMessage, ChatMessagePayload } from "@/types";
import { User, Bot, AlertCircle } from "lucide-react";

interface MessageBubbleProps {
  message: RealtimeMessage;
  isStreaming?: boolean;
}

export function MessageBubble({
  message,
  isStreaming,
}: MessageBubbleProps) {
  const role = message.sender.type;
  const payload = message.payload as unknown as ChatMessagePayload;
  const isUser = role === "user";
  const isAgent = role === "agent";
  const isSystem = role === "gateway";
  const isError = message.type === "system.error";

  const avatarContent = useMemo(() => {
    if (isUser) return <User className="h-4 w-4" />;
    if (isAgent) return <Bot className="h-4 w-4" />;
    return <AlertCircle className="h-4 w-4" />;
  }, [isUser, isAgent]);

  const bubbleStyle = cn(
    "flex gap-3 px-4 py-3 group",
    isUser && "justify-end",
    isError && "bg-red-500/5 border-y border-red-500/10"
  );

  const contentStyle = cn(
    "max-w-[85%] min-w-0",
    isUser && "items-end"
  );

  const cardStyle = cn(
    "rounded-xl px-4 py-3.5 text-sm",
    isUser &&
      "bg-primary text-primary-foreground rounded-br-md leading-relaxed",
    isAgent &&
      "bg-card border border-border/60 shadow-sm rounded-bl-md leading-relaxed",
    isSystem && "bg-muted/30 border border-border/30 rounded-lg text-muted-foreground leading-relaxed",
    isError && "bg-red-500/10 border border-red-500/20 text-red-700 dark:text-red-400 leading-relaxed"
  );

  // If the payload has no content (e.g., pure event), show compact event line
  if (!payload.content && !isError) {
    return null;
  }

  return (
    <div className={bubbleStyle}>
      {/* Avatar (non-user) */}
      {!isUser && (
        <div
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full mt-0.5",
            isAgent
              ? "bg-[#F3F4F6] text-[#111827]"
              : isError
                ? "bg-red-500/10 text-red-600"
                : "bg-muted text-muted-foreground"
          )}
        >
          {avatarContent}
        </div>
      )}

      <div className={contentStyle}>
        {/* Agent Tag */}
        {isAgent && payload.agent && (
          <div className="mb-1.5">
            <AgentTag agent={payload.agent} />
          </div>
        )}

        {/* Message Card */}
        <div className={cardStyle}>
          {isStreaming && !payload.content ? (
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <span className="animate-pulse">●</span> 思考中...
            </span>
          ) : payload.format === "markdown" || payload.format === "diff" ? (
            <div className="prose prose-sm dark:prose-invert max-w-none [&_pre]:rounded-lg [&_pre]:bg-muted/50 [&_code]:text-xs [&_pre_code]:bg-transparent [&_p]:leading-[1.6] [&_li]:leading-[1.6] [&_ul]:list-disc [&_ol]:list-decimal [&_blockquote]:border-l-2 [&_blockquote]:border-muted-foreground/30 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_table]:w-full [&_th]:border [&_td]:border [&_th]:px-2 [&_td]:px-2 [&_th]:py-1 [&_td]:py-1">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {payload.content}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="whitespace-pre-wrap break-words">
              {payload.content}
            </p>
          )}

          {/* Streaming indicator */}
          {isStreaming && (
            <span className="inline-block w-2 h-4 bg-foreground/60 animate-pulse rounded-sm ml-0.5 align-middle" />
          )}
        </div>

        {/* Timestamp */}
        <p
          className={cn(
            "text-[10px] text-muted-foreground mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity",
            isUser && "text-right"
          )}
        >
          {formatTime(message.timestamp)}
          {message.status === "replayed" && (
            <span className="ml-1 text-[10px] italic">(已回放)</span>
          )}
        </p>
      </div>

      {/* Avatar (user) */}
      {isUser && (
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary mt-0.5">
          {avatarContent}
        </div>
      )}
    </div>
  );
}
