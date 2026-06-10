"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Trash2,
  Pencil,
  Archive,
  Copy,
  MoreHorizontal,
} from "lucide-react";

interface SessionContextMenuProps {
  sessionId: string;
  sessionTitle: string;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onArchive: (id: string) => void;
  onCopyId: (id: string) => void;
  children?: React.ReactNode;
}

export function SessionContextMenu({
  sessionId,
  sessionTitle,
  onDelete,
  onRename,
  onArchive,
  onCopyId,
  children,
}: SessionContextMenuProps) {
  const handleCopyId = () => {
    navigator.clipboard.writeText(sessionId).catch(console.error);
    onCopyId(sessionId);
  };

  const handleDelete = () => {
    if (window.confirm(`确认删除会话「${sessionTitle}」？\n此操作将同步删除后端工作区目录与回放数据，不可恢复。`)) {
      onDelete(sessionId);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {children || (
          <button className="inline-flex items-center justify-center h-6 w-6 rounded-md opacity-0 group-hover:opacity-100 hover:bg-muted transition-all">
            <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuItem onClick={() => onRename(sessionId, sessionTitle)}>
          <Pencil className="h-3.5 w-3.5" />
          重命名
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => onArchive(sessionId)}>
          <Archive className="h-3.5 w-3.5" />
          归档
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleCopyId}>
          <Copy className="h-3.5 w-3.5" />
          复制会话 ID
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={handleDelete}>
          <Trash2 className="h-3.5 w-3.5" />
          删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
