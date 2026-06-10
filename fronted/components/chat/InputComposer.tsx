"use client";

import { useState, useRef, useCallback, KeyboardEvent, useEffect } from "react";
import { AtSign, ArrowUp, Square } from "lucide-react";
import { cn } from "@/lib/utils";
import { AtMentionPopover } from "./AtMentionPopover";
import type { AgentOption } from "./AtMentionPopover";

interface InputComposerProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isTaskRunning?: boolean;
  placeholder?: string;
  showAtButton?: boolean;
}

export function InputComposer({
  onSend,
  onStop,
  disabled = false,
  isTaskRunning = false,
  placeholder = "Describe your task...",
  showAtButton = true,
}: InputComposerProps) {
  const [value, setValue] = useState("");
  const [sending, setSending] = useState(false);
  const [atPopoverOpen, setAtPopoverOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendingTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Reset sending state if it gets stuck when user switches back
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && sending) {
        // If page becomes visible and we're still sending after a delay, reset it
        sendingTimeoutRef.current = setTimeout(() => {
          setSending(false);
        }, 500);
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (sendingTimeoutRef.current) {
        clearTimeout(sendingTimeoutRef.current);
      }
    };
  }, [sending]);

  // Reset sending state when isTaskRunning changes from true to false
  useEffect(() => {
    if (!isTaskRunning && sending) {
      setSending(false);
    }
  }, [isTaskRunning, sending]);

  const handleSend = useCallback(async () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || isTaskRunning || sending) return;
    
    // Clear any existing timeout
    if (sendingTimeoutRef.current) {
      clearTimeout(sendingTimeoutRef.current);
    }
    
    setSending(true);
    try {
      onSend(trimmed);
      setValue("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "48px";
      }
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }, [value, disabled, onSend, isTaskRunning, sending]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isTaskRunning) {
        handleSend();
      }
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "48px";
    el.style.height = Math.min(el.scrollHeight, 128) + "px";
  };

  const handleAtSelect = (agent: AgentOption) => {
    setValue((prev) => prev + `@${agent.name} `);
    textareaRef.current?.focus();
  };

  const hasContent = value.trim().length > 0;

  return (
    <div className="border-t border-[#E5E7EB] bg-white px-6 py-4">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2">
          {/* @ Button - only show in multi-agent mode */}
          {showAtButton && (
            <button
              onClick={() => setAtPopoverOpen(!atPopoverOpen)}
              disabled={isTaskRunning}
              className={cn(
                "flex items-center justify-center h-[48px] w-[48px] rounded-[12px] shrink-0 transition-colors",
                isTaskRunning
                  ? "bg-[#F3F4F6] text-[#D1D5DB] cursor-not-allowed"
                  : atPopoverOpen
                  ? "bg-[#E5E7EB] text-[#111827]"
                  : "bg-[#F3F4F6] text-[#9CA3AF] hover:bg-[#E5E7EB] hover:text-[#374151]"
              )}
              title="@ Mention Agent"
            >
              <AtSign className="h-5 w-5" />
            </button>
          )}

          {/* Text Input */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onInput={handleInput}
              placeholder={placeholder}
              disabled={disabled || isTaskRunning}
              rows={1}
              style={{ height: 48 }}
              className={cn(
                "w-full resize-none rounded-[16px] border px-4 py-3.5 text-[15px] leading-relaxed",
                "bg-[#F9FAFB] border-[#E5E7EB]",
                "placeholder:text-[#9CA3AF]",
                "focus-visible:outline-none focus-visible:border-[#374151] focus-visible:bg-white",
                "disabled:cursor-not-allowed disabled:opacity-50",
                "max-h-[128px]"
              )}
            />

            {showAtButton && (
              <AtMentionPopover
                open={atPopoverOpen}
                onClose={() => setAtPopoverOpen(false)}
                onSelect={handleAtSelect}
              />
            )}
          </div>

          {/* Send/Stop Button */}
          {isTaskRunning ? (
            <button
              onClick={onStop}
              className={cn(
                "flex items-center justify-center h-[48px] w-[48px] rounded-[12px] shrink-0 transition-all bg-[#DC2626] text-white hover:bg-[#B91C1C]"
              )}
              title="Stop Task"
            >
              <Square className="h-5 w-5" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={disabled || !hasContent}
              className={cn(
                "flex items-center justify-center h-[48px] w-[48px] rounded-[12px] shrink-0 transition-all",
                hasContent
                  ? "bg-[#111827] text-white hover:bg-[#374151]"
                  : "bg-[#F3F4F6] text-[#D1D5DB] cursor-not-allowed"
              )}
              title="Send Message"
            >
              <ArrowUp className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
