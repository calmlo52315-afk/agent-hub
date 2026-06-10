"use client";

import { ChatWorkspace } from "@/components/layout/ChatWorkspace";

interface WorkbenchPageProps {
  onRequestNewSession: () => void;
}

export default function WorkbenchPage({ onRequestNewSession }: WorkbenchPageProps) {
  return <ChatWorkspace onRequestNewSession={onRequestNewSession} />;
}
