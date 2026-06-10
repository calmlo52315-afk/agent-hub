import { create } from "zustand";
import type {
  WorkspaceMeta,
  WorkspaceSnapshot,
  WorkspaceFileNode,
  SyncStatus,
} from "@/types";
import { getWorkspaceFile } from "@/lib/api";

/*
 * VSCode 模式的 Workspace Store
 *
 * 设计意图：
 *   - 进入会话 → 获取文件树（只含元信息，不含内容）
 *   - 用户点击文件 → 懒加载单个文件内容
 *   - 数据库只存索引，不存内容
 *
 * 废弃的模式：
 *   - ❌ 进入会话 → 全部文件内容 → SQLite → 前端 ← 500+ 文件直接爆炸
 *   - ❌ localStorage 缓存文件内容 ← 大项目直接撑满存储
 */

interface WorkspaceStore {
  /** 当前 workspace 元信息 */
  meta: WorkspaceMeta | null;
  /** 文件树（只含结构元信息，不含内容） */
  fileTree: WorkspaceFileNode[];
  /** 当前已加载的文件内容缓存（内存缓存，不持久化） */
  fileContentCache: Record<string, string>;
  /** Snapshots */
  snapshots: WorkspaceSnapshot[];
  /** loading */
  loading: boolean;
  error: string | null;

  // File System Access API sync state
  directoryHandle: FileSystemDirectoryHandle | null;
  directoryName: string;
  syncStatus: SyncStatus;

  // Actions
  setMeta: (meta: WorkspaceMeta | null) => void;
  updateMeta: (updates: Partial<WorkspaceMeta>) => void;
  setFileTree: (fileTree: WorkspaceFileNode[]) => void;
  setLoading: (v: boolean) => void;
  setError: (e: string | null) => void;
  setDirectoryHandle: (
    handle: FileSystemDirectoryHandle | null,
    name: string
  ) => void;
  setSyncStatus: (status: SyncStatus) => void;
  clear: () => void;

  // 懒加载：按需获取单个文件内容
  loadFileContent: (sessionId: string, filePath: string) => Promise<string | null>;
  getCachedContent: (filePath: string) => string | null;
  clearContentCache: () => void;

  // Computed
  hasWorkspace: () => boolean;
  fileCount: () => number;
  hasDirectoryHandle: () => boolean;
}

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => ({
  meta: null,
  fileTree: [],
  fileContentCache: {},
  snapshots: [],
  loading: false,
  error: null,
  directoryHandle: null,
  directoryName: "",
  syncStatus: "idle",

  setMeta: (meta) => set({ meta }),

  updateMeta: (updates) =>
    set((state) => ({
      meta: state.meta ? { ...state.meta, ...updates } : null,
    })),

  setFileTree: (fileTree) => set({ fileTree }),

  setLoading: (v) => set({ loading: v }),
  setError: (e) => set({ error: e }),
  setDirectoryHandle: (handle, name) =>
    set({ directoryHandle: handle, directoryName: name }),
  setSyncStatus: (syncStatus) => set({ syncStatus }),
  clear: () =>
    set({
      meta: null,
      fileTree: [],
      fileContentCache: {},
      snapshots: [],
      error: null,
      directoryHandle: null,
      directoryName: "",
      syncStatus: "idle",
    }),

  // 懒加载：按需获取单个文件内容
  loadFileContent: async (sessionId: string, filePath: string) => {
    // 先检查内存缓存
    const cached = get().fileContentCache[filePath];
    if (cached !== undefined) return cached;

    try {
      const result = await getWorkspaceFile(sessionId, filePath);
      if (result.content !== undefined && result.content !== null) {
        // 写入内存缓存
        set((state) => ({
          fileContentCache: {
            ...state.fileContentCache,
            [filePath]: result.content,
          },
        }));
        return result.content;
      }
      return null;
    } catch (err) {
      console.error(`[WorkspaceStore] Failed to load file ${filePath}:`, err);
      return null;
    }
  },

  getCachedContent: (filePath: string) => {
    return get().fileContentCache[filePath] || null;
  },

  clearContentCache: () => set({ fileContentCache: {} }),

  hasWorkspace: () => get().meta !== null,
  fileCount: () => get().meta?.source_files_count ?? 0,
  hasDirectoryHandle: () => get().directoryHandle !== null,
}));

export type { WorkspaceStore };
