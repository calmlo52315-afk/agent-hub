"use client";

import { Play, Clock, List } from "lucide-react";

export default function ReplayPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-center px-6">
      <div className="rounded-full bg-muted p-4 mb-4">
        <Play className="h-8 w-8 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-bold mb-2">任务回放</h2>
      <p className="text-sm text-muted-foreground mb-6 max-w-md">
        全链路时序回放播放器，支持倍速/暂停，分步产物预览。用于故障排查、答辩演示、复现异常。
      </p>
      <div className="flex items-center gap-6 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <List className="h-3.5 w-3.5" /> 任务列表
        </span>
        <span className="flex items-center gap-1.5">
          <Play className="h-3.5 w-3.5" /> 回放播放器
        </span>
        <span className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" /> 倍速控制
        </span>
      </div>
    </div>
  );
}
