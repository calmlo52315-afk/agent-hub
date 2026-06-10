import { create } from "zustand";
import type { ConnectionState, WsTicket } from "@/types";

interface ConnectionStore {
  state: ConnectionState;
  wsTicket: WsTicket | null;
  lastSeq: number;
  lastError: string | null;

  setState: (state: ConnectionState) => void;
  setWsTicket: (ticket: WsTicket | null) => void;
  setLastSeq: (seq: number) => void;
  setLastError: (error: string | null) => void;
  reset: () => void;
}

export const useConnectionStore = create<ConnectionStore>((set) => ({
  state: "disconnected",
  wsTicket: null,
  lastSeq: 0,
  lastError: null,

  setState: (state) => set({ state }),
  setWsTicket: (ticket) => set({ wsTicket: ticket }),
  setLastSeq: (seq) => set({ lastSeq: seq }),
  setLastError: (error) => set({ lastError: error }),

  reset: () =>
    set({
      state: "disconnected",
      wsTicket: null,
      lastSeq: 0,
      lastError: null,
    }),
}));

export { type ConnectionStore };
