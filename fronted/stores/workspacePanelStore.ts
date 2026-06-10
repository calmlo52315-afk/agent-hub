import { create } from "zustand";

interface WorkspacePanelStore {
  /** 是否强制显示 Workspace 面板 */
  forceShow: boolean;
  /** 强制显示 Workspace 面板 */
  showPanel: () => void;
  /** 隐藏 Workspace 面板 */
  hidePanel: () => void;
  /** 切换显示状态 */
  toggle: () => void;
  /** 重置显示状态 */
  reset: () => void;
}

export const useWorkspacePanelStore = create<WorkspacePanelStore>((set) => ({
  forceShow: false,

  showPanel: () => set({ forceShow: true }),

  hidePanel: () => set({ forceShow: false }),

  toggle: () => set((s) => ({ forceShow: !s.forceShow })),

  reset: () => set({ forceShow: false }),
}));
