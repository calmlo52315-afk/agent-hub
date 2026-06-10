"use client";

import { useConnectionStore } from "@/stores/connectionStore";
import { cn } from "@/lib/utils";

export function ConnectionStatus() {
  const state = useConnectionStore((s) => s.state);

  const config = {
    disconnected: { label: "Disconnected", color: "bg-[#D1D5DB]" },
    connecting: { label: "Connecting...", color: "bg-[#9CA3AF] animate-pulse" },
    connected: { label: "Connected", color: "bg-[#6B7280]" },
    reconnecting: { label: "Reconnecting...", color: "bg-[#9CA3AF] animate-pulse" },
  };

  const { label, color } = config[state];

  return (
    <div className="flex items-center gap-1.5 text-[11px] text-[#9CA3AF]">
      <span className={cn("relative flex h-1.5 w-1.5")}>
        <span className={cn("relative inline-flex rounded-full h-1.5 w-1.5", color)} />
      </span>
      <span>{label}</span>
    </div>
  );
}
