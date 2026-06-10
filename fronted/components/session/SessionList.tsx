"use client";

import { useSessionStore } from "@/stores/sessionStore";
import { SessionContextMenu } from "./SessionContextMenu";
import { cn, formatRelativeTime } from "@/lib/utils";
import { MessageSquare, Plus } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import type { SessionSummary } from "@/types";

interface SessionListProps {
  onNewSession: () => void;
  searchQuery?: string;
}

export function SessionList({ onNewSession, searchQuery = "" }: SessionListProps) {
  const sessions = useSessionStore((s) => s.sessions);
  const currentSessionId = useSessionStore((s) => s.currentSessionId);
  const setCurrentSessionId = useSessionStore((s) => s.setCurrentSessionId);
  const loading = useSessionStore((s) => s.loading);
  const deleteSession = useSessionStore((s) => s.deleteSession);
  const archiveSession = useSessionStore((s) => s.archiveSession);
  const renameSession = useSessionStore((s) => s.renameSession);

  const filtered = sessions.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.title.toLowerCase().includes(q) ||
      s.session_id.toLowerCase().includes(q)
    );
  });

  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id).catch(console.error);
  };

  if (loading) {
    return (
      <div className="space-y-0.5 p-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="px-3 py-2.5 space-y-1.5">
            <Skeleton className="h-4 w-3/4 rounded bg-[#2a2b30]" />
            <Skeleton className="h-3 w-full rounded bg-[#2a2b30]" />
          </div>
        ))}
      </div>
    );
  }

  if (filtered.length === 0 && sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
        <div className="rounded-full bg-[#2a2b30] p-3 mb-3">
          <MessageSquare className="h-5 w-5 text-[#6b6b6b]" />
        </div>
        <p className="text-sm text-[#9b9b9b] mb-1">No conversations yet</p>
        <p className="text-xs text-[#6b6b6b] mb-4">Start a new chat</p>
        <button
          onClick={onNewSession}
          className="inline-flex items-center gap-1.5 rounded-[8px] bg-[#111827] px-3.5 py-2 text-xs font-medium text-white hover:bg-[#374151] transition-colors"
        >
          <Plus className="h-3.5 w-3.5" />
          New Chat
        </button>
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="px-4 py-6 text-center">
        <p className="text-xs text-[#6b6b6b]">No matching chats</p>
      </div>
    );
  }

  return (
    <div className="space-y-0.5 px-2 py-1">
      {filtered.map((session) => (
        <SessionItem
          key={session.session_id}
          session={session}
          isActive={session.session_id === currentSessionId}
          onClick={() => setCurrentSessionId(session.session_id)}
          onDelete={(id) => deleteSession(id)}
          onRename={(id, title) => {
            const t = window.prompt("Rename:", title);
            if (t?.trim() && t.trim() !== title) renameSession(id, t.trim());
          }}
          onArchive={(id) => archiveSession(id)}
          onCopyId={handleCopyId}
        />
      ))}
    </div>
  );
}

function SessionItem({
  session,
  isActive,
  onClick,
  onDelete,
  onRename,
  onArchive,
  onCopyId,
}: {
  session: SessionSummary;
  isActive: boolean;
  onClick: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onArchive: (id: string) => void;
  onCopyId: (id: string) => void;
}) {
  return (
    <SessionContextMenu
      sessionId={session.session_id}
      sessionTitle={session.title}
      onDelete={onDelete}
      onRename={onRename}
      onArchive={onArchive}
      onCopyId={onCopyId}
    >
      <div
        onClick={onClick}
        className={cn(
          "group relative w-full text-left rounded-lg py-2.5 px-3 transition-colors cursor-pointer",
          isActive
            ? "bg-[#E5E7EB] text-[#111827]"
            : "text-[#111827] hover:bg-[#F3F4F6]"
        )}
      >
        <div className="min-w-0">
          <p className="text-[13px] font-medium truncate">
            {session.title}
          </p>
          <p className="text-[11px] text-[#6b6b6b] mt-0.5">
            {formatRelativeTime(session.updated_at)}
          </p>
        </div>
      </div>
    </SessionContextMenu>
  );
}
