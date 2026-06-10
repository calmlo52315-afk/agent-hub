"use client";

import { useEffect, useRef, useMemo } from "react";
import { useChatStore } from "@/stores/chatStore";
import { useTaskStore } from "@/stores/taskStore";
import { useArtifactStore } from "@/stores/artifactStore";
import { UserMessageCard } from "./UserMessageCard";
import { AgentMessageCard } from "./AgentMessageCard";
import { AgentAvatar } from "./AgentAvatar";
import { MinimalTimeline } from "@/components/task/MinimalTimeline";
import { SimpleCodeCard } from "./SimpleCodeCard";
import { ReviewStatusCard } from "./ReviewStatusCard";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2 } from "lucide-react";
import type { RealtimeMessage, ChatMessagePayload, ArtifactCreatedPayload, FileContent } from "@/types";

/**
 * 判断是否是任务相关消息
 */
const isTaskMessage = (msg: RealtimeMessage) => 
  msg.type === "task.created" || msg.type === "task.updated" || msg.type === "task.completed";

/**
 * 将消息分组 - 把连续的任务消息聚合在一起
 */
type MessageGroup = {
  type: "task" | "other";
  messages: RealtimeMessage[];
};

const groupMessages = (messages: RealtimeMessage[]): MessageGroup[] => {
  const groups: MessageGroup[] = [];
  let currentGroup: MessageGroup | null = null;
  
  for (const msg of messages) {
    const isTask = isTaskMessage(msg);
    const groupType = isTask ? "task" : "other";
    
    if (!currentGroup || currentGroup.type !== groupType) {
      if (currentGroup) {
        groups.push(currentGroup);
      }
      currentGroup = { type: groupType, messages: [msg] };
    } else {
      currentGroup.messages.push(msg);
    }
  }
  
  if (currentGroup) {
    groups.push(currentGroup);
  }
  
  return groups;
};

/**
 * Chat message list — IM-style with minimal timeline
 */
export function ChatMessageList() {
  const messages = useChatStore((s) => s.messages);
  const loadingHistory = useChatStore((s) => s.loadingHistory);
  const viewportRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // 消息分组
  const messageGroups = useMemo(() => groupMessages(messages), [messages]);

  const renderGroup = (group: MessageGroup, groupIndex: number) => {
    if (group.type === "task") {
      // 任务消息组 - 渲染极简时间线
      return (
        <div key={`group-${groupIndex}`}>
          <MinimalTimeline messages={group.messages} />
        </div>
      );
    } else {
      // 其他消息组 - 逐个渲染
      return (
        <div key={`group-${groupIndex}`}>
          {group.messages.map((msg) => renderNonTaskMessage(msg))}
        </div>
      );
    }
  };

  const renderNonTaskMessage = (msg: RealtimeMessage) => {
    // Handle artifact.created messages (for simple task single file display)
    if (msg.type === "artifact.created") {
      const payload = msg.payload as unknown as ArtifactCreatedPayload;
      
      // Check if this is a file artifact and we should display it inline
      if (payload.card?.card_type === "file") {
        const fileContent = payload.card.content as unknown as FileContent;
        
        // Check if this is a simple task or if we only have one file so far
        const isSimpleTask = useTaskStore.getState().tasks.some(t => t.complexity === "simple");
        const totalArtifacts = useArtifactStore.getState().artifacts.length;
        const shouldDisplayInline = isSimpleTask || totalArtifacts === 1;
        
        if (shouldDisplayInline && fileContent) {
          return (
            <SimpleCodeCard
              key={msg.event_id}
              content={fileContent}
              title={payload.card.title}
              summary={payload.card.summary}
            />
          );
        }
      }
      return null;
    }

    const payload = msg.payload as unknown as ChatMessagePayload;
    const role = msg.sender.type;

    // System errors
    if (msg.type === "system.error") {
      return (
        <div key={msg.event_id} className="px-5 py-2">
          <p className="text-xs text-[#9CA3AF] text-center bg-[#FEF2F2] text-[#DC2626] rounded-[8px] px-3 py-1.5 inline-block mx-auto">
            {(msg.payload as Record<string, unknown>)?.message as string ||
              "An error occurred"}
          </p>
        </div>
      );
    }

    // Gateway/frontend system messages
    if (role === "gateway" || role === "frontend") {
      if (!payload.content) return null;
      return (
        <div key={msg.event_id} className="px-5 py-1.5">
          <p className="text-xs text-[#9CA3AF] text-center">
            {payload.content}
          </p>
        </div>
      );
    }

    // User messages
    if (role === "user") {
      return (
        <UserMessageCard
          key={msg.event_id}
          payload={payload}
          timestamp={msg.timestamp}
        />
      );
    }

    // Agent messages
    if (role === "agent" && payload.content) {
      // ⭐ Step 3: 渲染 streaming/running 状态的消息（带闪烁光标）
      if (msg.status === "streaming" || msg.status === "running") {
        const streamContent = useChatStore.getState().streamingMessages.get(
          payload.message_id || msg.event_id
        );
        if (streamContent) {
          return (
            <AgentMessageCard
              key={msg.event_id}
              payload={{ ...payload, content: streamContent }}
              timestamp={msg.timestamp}
              agentName={payload.agent}
              isStreaming={true}
            />
          );
        }
        // 如果没有累积的 streaming 内容，显示加载状态
        return (
          <div key={msg.event_id} className="flex gap-3 px-6 py-3">
            <AgentAvatar agentId={payload.agent} size="md" className="mt-0.5" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[13px] font-semibold text-[#111827]">
                  {payload.agent || "Agent"}
                </span>
                <span className="text-[11px] text-[#9CA3AF]">
                  · processing...
                </span>
              </div>
              <div className="rounded-[8px] rounded-bl-[4px] border border-[#E5E7EB] bg-white px-4 py-2.5 inline-block">
                <span className="text-[14px] text-[#6B7280]">
                  <Loader2 className="h-3 w-3 animate-spin inline mr-1.5" />
                  Generating...
                </span>
              </div>
            </div>
          </div>
        );
      }

      // ⭐ Step 3: review.started / review.completed 状态卡片
      if (msg.type === "review.started") {
        return (
          <ReviewStatusCard
            key={msg.event_id}
            status="reviewing"
            timestamp={msg.timestamp}
          />
        );
      }

      if (msg.type === "review.completed") {
        const reviewPayload = msg.payload as Record<string, unknown>;
        return (
          <ReviewStatusCard
            key={msg.event_id}
            status="completed"
            timestamp={msg.timestamp}
            issueCount={reviewPayload.issue_count as number}
            latencyMs={reviewPayload.latency_ms as number}
          />
        );
      }

      if (msg.type === "review.failed") {
        return (
          <ReviewStatusCard
            key={msg.event_id}
            status="failed"
            timestamp={msg.timestamp}
          />
        );
      }

      // ⭐ Step 3: coding.completed 状态卡片 — 代码已生成，显示摘要
      if (msg.type === "coding.completed") {
        const codingPayload = msg.payload as Record<string, unknown>;
        const changeCount = codingPayload.applied_change_count as number || 0;
        const codingLatencyMs = codingPayload.latency_ms as number || 0;
        const latencySec = codingLatencyMs > 0 ? (codingLatencyMs / 1000).toFixed(1) : null;
        return (
          <div key={msg.event_id} className="px-6 py-2">
            <div className="rounded-[8px] border border-[#10B981]/30 bg-[#ECFDF5] px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-[#065F46]">
                  ✅ Code Generation Complete
                </span>
                <span className="text-[11px] text-[#6B7280]">
                  {changeCount} file{changeCount !== 1 ? "s" : ""} changed
                  {latencySec && ` · ${latencySec}s`}
                </span>
              </div>
            </div>
          </div>
        );
      }

      return (
        <AgentMessageCard
          key={msg.event_id}
          payload={payload}
          timestamp={msg.timestamp}
          agentName={payload.agent}
        />
      );
    }

    return null;
  };

  return (
    <ScrollArea className="flex-1" viewportRef={viewportRef}>
      <div className="py-3">
        {loadingHistory && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-[#9CA3AF]" />
          </div>
        )}

        {!loadingHistory && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
            <p className="text-sm text-[#111827] font-medium mb-1">
              Start the conversation
            </p>
            <p className="text-xs text-[#9CA3AF]">
              Describe your task below to begin collaborating with agents
            </p>
          </div>
        )}

        {/* Message Groups */}
        {messageGroups.map((group, index) => renderGroup(group, index))}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
