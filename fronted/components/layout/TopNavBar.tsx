"use client";

import { useRouter } from "next/navigation";

/**
 * Minimal header with brand only
 */
export function TopNavBar() {
  const router = useRouter();

  return (
    <nav className="shrink-0 h-8 flex items-center justify-center select-none">
      {/* Center: Brand */}
      <span
        className="text-[13px] font-semibold text-[#111827] cursor-pointer tracking-tight"
        onClick={() => router.push("/")}
      >
        AgentHub
      </span>
    </nav>
  );
}
