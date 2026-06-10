/**
 * File System Access API helpers for workspace import/sync.
 *
 * Uses the browser's File System Access API (Chrome/Edge) to get read/write
 * access to a user-selected local directory. Directory handles are persisted
 * in IndexedDB so access survives page reloads.
 */

// Type declarations provided by @types/wicg-file-system-access
// via tsconfig.json types. showDirectoryPicker is on window, entries()
// is on FileSystemDirectoryHandle, etc.

export interface FsaFile {
  path: string; // relative path from directory root, e.g. "src/main.ts"
  content: string;
}

export type FsaProgressCallback = (done: number, total: number) => void;

// ---- Feature detection ----

export function hasFileSystemAccessSupport(): boolean {
  return (
    typeof window !== "undefined" &&
    "showDirectoryPicker" in window &&
    typeof (window as any).showDirectoryPicker === "function"
  );
}

// ---- IndexedDB persistence for directory handles ----

const DB_NAME = "fsa-handles";
const DB_VERSION = 1;
const STORE_NAME = "handles";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE_NAME)) {
        req.result.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbGet(key: string): Promise<FileSystemDirectoryHandle | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function dbSet(key: string, handle: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(handle, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function dbDelete(key: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).delete(key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function savePersistedHandle(
  sessionId: string,
  handle: FileSystemDirectoryHandle
): Promise<void> {
  await dbSet(`dir-${sessionId}`, handle);
}

export async function getPersistedHandle(
  sessionId: string
): Promise<FileSystemDirectoryHandle | undefined> {
  return dbGet(`dir-${sessionId}`);
}

export async function removePersistedHandle(sessionId: string): Promise<void> {
  await dbDelete(`dir-${sessionId}`);
}

// ---- Directory picker ----

export async function requestDirectoryAccess(): Promise<FileSystemDirectoryHandle> {
  if (!hasFileSystemAccessSupport()) {
    throw new Error("File System Access API is not supported in this browser");
  }
  const handle = await (window as any).showDirectoryPicker({
    mode: "readwrite",
  });
  return handle as FileSystemDirectoryHandle;
}

// ---- Directory reading ----

const SKIP_PATTERNS = [
  "node_modules",
  ".git",
  ".next",
  "__pycache__",
  ".venv",
  "venv",
  ".DS_Store",
  "dist",
  "build",
  ".cache",
  "coverage",
];

function shouldSkip(name: string): boolean {
  if (name.startsWith(".")) return true;
  if (SKIP_PATTERNS.includes(name)) return true;
  return false;
}

function isBinaryContent(content: string): boolean {
  // Check first 4KB for null bytes or high ratio of non-printable chars
  const sample = content.slice(0, 4096);
  if (sample.includes("\x00")) return true;
  const nonPrintable = sample.match(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g);
  if (nonPrintable && nonPrintable.length > sample.length * 0.1) return true;
  return false;
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5MB per file

async function readDirectoryRecursive(
  handle: FileSystemDirectoryHandle,
  basePath: string,
  onProgress?: FsaProgressCallback,
  _estimated?: number
): Promise<FsaFile[]> {
  const files: FsaFile[] = [];
  let scanned = 0;
  const paths: string[] = [];

  // First pass: collect all entries
  const collect = async (
    dirHandle: FileSystemDirectoryHandle,
    relPath: string
  ) => {
    for await (const [name, entry] of dirHandle.entries()) {
      if (shouldSkip(name)) continue;
      const entryPath = relPath ? `${relPath}/${name}` : name;
      if (entry.kind === "file") {
        paths.push(entryPath);
      } else if (entry.kind === "directory") {
        await collect(entry as FileSystemDirectoryHandle, entryPath);
      }
    }
  };

  await collect(handle, basePath);

  const total = paths.length;
  if (total > 5000) {
    throw new Error(
      `Directory contains ${total} files (max 5000). Please select a smaller directory.`
    );
  }

  // Second pass: read files incrementally
  for (const relPath of paths) {
    try {
      const fileContent = await readFileByPath(handle, relPath);
      if (fileContent.length > MAX_FILE_SIZE_BYTES) continue;
      if (isBinaryContent(fileContent)) continue;
      files.push({ path: relPath, content: fileContent });
    } catch {
      // Skip files that can't be read
    }
    scanned++;
    onProgress?.(scanned, total);
  }

  return files;
}

export async function readFileByPath(
  dirHandle: FileSystemDirectoryHandle,
  relPath: string
): Promise<string> {
  const parts = relPath.split("/");
  let currentHandle: FileSystemDirectoryHandle = dirHandle;

  // Navigate into subdirectories
  for (let i = 0; i < parts.length - 1; i++) {
    currentHandle = await currentHandle.getDirectoryHandle(parts[i]);
  }

  const fileHandle = await currentHandle.getFileHandle(
    parts[parts.length - 1]
  );
  const file = await fileHandle.getFile();
  return file.text();
}

export async function scanDirectory(
  handle: FileSystemDirectoryHandle,
  onProgress?: FsaProgressCallback
): Promise<FsaFile[]> {
  return readDirectoryRecursive(handle, "", onProgress);
}

// ---- File writing (sync-back) ----

export async function writeFileToDirectory(
  dirHandle: FileSystemDirectoryHandle,
  relPath: string,
  content: string
): Promise<void> {
  const parts = relPath.split("/");
  let currentHandle = dirHandle;

  // Navigate into / create subdirectories
  for (let i = 0; i < parts.length - 1; i++) {
    currentHandle = await currentHandle.getDirectoryHandle(parts[i], {
      create: true,
    });
  }

  const fileName = parts[parts.length - 1];
  const fileHandle = await currentHandle.getFileHandle(fileName, {
    create: true,
  });
  const writable = await fileHandle.createWritable();
  await writable.write(content);
  await writable.close();
}

export async function deleteFileFromDirectory(
  dirHandle: FileSystemDirectoryHandle,
  relPath: string
): Promise<void> {
  const parts = relPath.split("/");
  let currentHandle = dirHandle;

  for (let i = 0; i < parts.length - 1; i++) {
    try {
      currentHandle = await currentHandle.getDirectoryHandle(parts[i]);
    } catch {
      return; // parent dir doesn't exist, nothing to delete
    }
  }

  try {
    await currentHandle.removeEntry(parts[parts.length - 1]);
  } catch {
    // File may not exist
  }
}
