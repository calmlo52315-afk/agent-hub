"use client";

interface EmptyStateGuideProps {
  onRequestNewSession?: (mode: "single_agent" | "multi_agent") => void;
}

export function EmptyStateGuide({ onRequestNewSession }: EmptyStateGuideProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-6 py-12">
      <h1 className="text-2xl font-bold text-[#111827] mb-2 tracking-tight">AgentHub</h1>
      <p className="text-sm text-[#9CA3AF] mb-10 text-center max-w-sm leading-relaxed">
        AI-powered multi-agent coding collaboration platform.
        <br />
        Describe a task, agents plan &rarr; code &rarr; review &rarr; deliver.
      </p>

      <button
        onClick={() => onRequestNewSession?.("multi_agent")}
        className="inline-flex items-center gap-1.5 rounded-[8px] bg-[#111827] px-5 py-2.5 text-sm font-medium text-white hover:bg-[#374151] transition-colors"
      >
        New Session
      </button>
    </div>
  );
}
