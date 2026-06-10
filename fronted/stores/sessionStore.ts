import { create } from "zustand";
import type { SessionSummary, SessionDetail } from "@/types";

export type SessionGroup = "active" | "archived" | "test";

interface SessionStore {
  sessions: SessionSummary[];
  currentSessionId: string | null;
  currentSession: SessionDetail | null;
  /** Stage 10: 单聊模式下当前选中的 Agent ID（如 "codex", "claude-code"） */
  currentAgentId: string | null;
  loading: boolean;
  error: string | null;
  sidebarCollapsed: boolean;

  setSessions: (sessions: SessionSummary[]) => void;
  addSession: (session: SessionSummary) => void;
  setCurrentSessionId: (id: string | null) => void;
  setCurrentSession: (session: SessionDetail | null) => void;
  /** Stage 10: 设置当前单聊 Agent ID */
  setCurrentAgentId: (agentId: string | null) => void;
  updateSession: (sessionId: string, updates: Partial<SessionSummary>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Sidebar UI
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;

  // Session actions
  deleteSession: (id: string) => void;
  archiveSession: (id: string) => void;
  renameSession: (id: string, title: string) => void;

  // Computed getters
  getSessionGroup: (session: SessionSummary) => SessionGroup;
}

// Determine session group
function getSessionGroup(session: SessionSummary): SessionGroup {
  // Test case sessions (Stage6 LLM Test)
  if (
    session.title?.toLowerCase().includes("test") ||
    session.title?.toLowerCase().includes("stage6") ||
    session.title?.includes("测试")
  ) {
    return "test";
  }

  // Archived: older than 30 days
  const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
  if (new Date(session.updated_at).getTime() < thirtyDaysAgo) {
    return "archived";
  }

  return "active";
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  currentSession: null,
  currentAgentId: null,
  loading: false,
  error: null,
  sidebarCollapsed: false,

  setSessions: (sessions) => set({ sessions }),

  addSession: (session) =>
    set((state) => ({
      sessions: [session, ...state.sessions],
    })),

  setCurrentSessionId: (id) => set({ currentSessionId: id }),

  setCurrentSession: (session) => set({ currentSession: session }),

  setCurrentAgentId: (agentId) => set({ currentAgentId: agentId }),

  updateSession: (sessionId, updates) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.session_id === sessionId ? { ...s, ...updates } : s
      ),
    })),

  setLoading: (loading) => set({ loading }),

  setError: (error) => set({ error }),

  // Sidebar UI
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),

  // Session actions
  deleteSession: (id) =>
    set((state) => {
      const filtered = state.sessions.filter((s) => s.session_id !== id);
      const nextId =
        state.currentSessionId === id
          ? filtered[0]?.session_id ?? null
          : state.currentSessionId;
      return { sessions: filtered, currentSessionId: nextId };
    }),

  archiveSession: (id) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.session_id === id
          ? { ...s, updated_at: new Date(0).toISOString() } // Move to 1970 to force archived group
          : s
      ),
    })),

  renameSession: (id, title) =>
    set((state) => ({
      sessions: state.sessions.map((s) =>
        s.session_id === id ? { ...s, title } : s
      ),
    })),

  getSessionGroup,
}));

export { type SessionStore };
