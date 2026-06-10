"use client";

import { FolderTree, FileText, FolderOpen } from "lucide-react";

export default function FilesPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center px-6">
      <div className="rounded-full bg-muted p-4 mb-4">
        <FolderTree className="h-8 w-8 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-bold mb-2">项目文件浏览</h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        树形目录浏览全项目文件，支持 Shiki 在线源码预览。从产物 Bundle 跳转打开。
      </p>
      <div className="flex items-center gap-6 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <FolderOpen className="h-3.5 w-3.5" /> 目录树
        </span>
        <span className="flex items-center gap-1.5">
          <FileText className="h-3.5 w-3.5" /> 源码预览
        </span>
      </div>
    </div>
  );
}
