import { create } from "zustand";
import type { RealtimeMessage, ChatMessagePayload } from "@/types";

interface ChatStore {
  messages: RealtimeMessage[];
  streamingMessages: Map<string, string>; // message_id -> accumulated stream content
  loadingHistory: boolean;

  setMessages: (messages: RealtimeMessage[]) => void;
  addMessage: (message: RealtimeMessage) => void;
  addMessages: (messages: RealtimeMessage[]) => void;
  appendStreamChunk: (messageId: string, chunk: string) => void;
  finalizeStream: (messageId: string) => void;
  clearMessages: () => void;
  setLoadingHistory: (v: boolean) => void;
  maxSeq: () => number;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  streamingMessages: new Map(),
  loadingHistory: false,

  setMessages: (messages) =>
    set({
      messages: messages.sort((a, b) => a.seq - b.seq),
    }),

  addMessage: (message) =>
    set((state) => {
      // Deduplicate by event_id
      if (state.messages.some((m) => m.event_id === message.event_id)) {
        return state;
      }
      const newMessages = [...state.messages, message].sort(
        (a, b) => a.seq - b.seq
      );
      return { messages: newMessages };
    }),

  addMessages: (messages) =>
    set((state) => {
      const existingIds = new Set(state.messages.map((m) => m.event_id));
      const newOnes = messages.filter((m) => !existingIds.has(m.event_id));
      if (newOnes.length === 0) return state;
      const all = [...state.messages, ...newOnes].sort(
        (a, b) => a.seq - b.seq
      );
      return { messages: all };
    }),

  appendStreamChunk: (messageId, chunk) =>
    set((state) => {
      const current = state.streamingMessages.get(messageId) || "";
      const next = new Map(state.streamingMessages);
      next.set(messageId, current + chunk);
      return { streamingMessages: next };
    }),

  finalizeStream: (messageId) =>
    set((state) => {
      const next = new Map(state.streamingMessages);
      next.delete(messageId);
      return { streamingMessages: next };
    }),

  clearMessages: () => set({ messages: [], streamingMessages: new Map() }),

  setLoadingHistory: (v) => set({ loadingHistory: v }),

  maxSeq: () => {
    const msgs = get().messages;
    if (msgs.length === 0) return 0;
    return msgs.reduce((max, m) => Math.max(max, m.seq), 0);
  },
}));

export { type ChatStore };
