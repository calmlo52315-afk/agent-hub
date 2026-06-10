import { create } from "zustand";

/**
 * Layout Store — 管理 Chat 和 Workspace 面板的宽度。
 *
 * chatWidth: Chat 区域像素宽度，默认 700px，最小 500px，最大由拖拽动态决定。
 * workspace 始终 flex-1 自动填充剩余空间。
 */
interface LayoutStore {
  /** Chat 区域宽度 (px) */
  chatWidth: number;
  /** 拖拽调整 chatWidth */
  setChatWidth: (width: number) => void;
  /** 按 delta 增量调整（供 ResizeHandle 调用） */
  adjustChatWidth: (delta: number) => void;
  /** 重置为默认值 */
  resetChatWidth: () => void;
}

const DEFAULT_CHAT_WIDTH = 700;
const MIN_CHAT_WIDTH = 500;

export const useLayoutStore = create<LayoutStore>((set, get) => ({
  chatWidth: DEFAULT_CHAT_WIDTH,

  setChatWidth: (width) =>
    set({ chatWidth: Math.max(MIN_CHAT_WIDTH, width) }),

  adjustChatWidth: (delta) => {
    const current = get().chatWidth;
    set({ chatWidth: Math.max(MIN_CHAT_WIDTH, current + delta) });
  },

  resetChatWidth: () => set({ chatWidth: DEFAULT_CHAT_WIDTH }),
}));

export type { LayoutStore };
