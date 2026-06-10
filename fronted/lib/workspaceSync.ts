import {
  getWorkspaceFiles,
  getWorkspaceFile,
} from "@/lib/api";
import { writeFileToDirectory } from "@/lib/fileSystemAccess";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import type { WorkspaceFileNode } from "@/types";

export interface SyncResult {
  synced: number;
  failed: number;
  skipped: number;
}

/**
 * Collect all file paths from a workspace file tree (flattened).
 */
function collectFilePaths(nodes: WorkspaceFileNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (node.type === "file") {
      paths.push(node.path);
    }
    if (node.children) {
      paths.push(...collectFilePaths(node.children));
    }
  }
  return paths;
}

/**
 * Sync agent changes from the Runtime workspace back to the user's local
 * directory via the File System Access API handle.
 *
 * VSCode 懒加载模式：
 *   1. 获取文件树（元信息）
 *   2. 对每个文件：先查内存缓存 → 再按需从后端加载单个文件
 *   3. 写回本地目录
 */
export async function syncAgentChangesToUserDirectory(
  sessionId: string,
  handle: FileSystemDirectoryHandle
): Promise<SyncResult> {
  const store = useWorkspaceStore.getState();
  store.setSyncStatus("syncing");

  let synced = 0;
  let failed = 0;
  let skipped = 0;

  try {
    // 1. 获取文件树
    const fileTree = await getWorkspaceFiles(sessionId);
    const paths = collectFilePaths(fileTree);

    if (paths.length === 0) {
      store.setSyncStatus("idle");
      return { synced: 0, failed: 0, skipped: 0 };
    }

    // 2. 对每个文件按需加载内容
    for (const filePath of paths) {
      // 先查内存缓存
      let content = store.getCachedContent(filePath);

      // 如果没缓存，从后端懒加载
      if (content === null) {
        try {
          content = await store.loadFileContent(sessionId, filePath);
        } catch (err) {
          console.warn(`Failed to fetch content for ${filePath}:`, err);
        }
      }

      if (content === null) {
        skipped++;
        continue;
      }

      try {
        await writeFileToDirectory(handle, filePath, content);
        synced++;
      } catch {
        failed++;
      }
    }
  } catch (err) {
    console.error("Sync failed:", err);
    store.setSyncStatus("error");
    return { synced, failed, skipped };
  }

  store.setSyncStatus(synced > 0 ? "seeded" : "idle");
  return { synced, failed, skipped };
}
