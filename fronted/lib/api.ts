import type {
  ApiEnvelope,
  SessionSummary,
  SessionDetail,
  PaginatedList,
  RealtimeMessage,
  TaskSummary,
  TaskDetail,
  ArtifactCard,
  WsTicket,
  WorkspaceType,
  WorkspaceFileNode,
  WorkspaceChangeEntry,
  WorkspaceHistoryEntry,
  FsListResponse,
  AgentDefinition,
} from "@/types";

const DIRECT_GATEWAY_BASE_URL = (
  process.env.NEXT_PUBLIC_GATEWAY_BASE_URL || ""
).replace(/\/$/, "");
const USE_DIRECT_GATEWAY =
  process.env.NEXT_PUBLIC_FORCE_DIRECT_GATEWAY === "1";
const TOKEN = process.env.NEXT_PUBLIC_DEMO_ACCESS_TOKEN || "demo-access-token";

// ============================================================
// Base fetch wrapper
// ============================================================
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl =
    typeof window !== "undefined" && !USE_DIRECT_GATEWAY
      ? ""
      : DIRECT_GATEWAY_BASE_URL;
  const url = `${baseUrl}${path}`;
  
  // Build headers - always add Authorization header since Gateway requires it
  const rawHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${TOKEN}`,
  };

  // 合并调用方传入的 headers（只取可枚举自有属性，TypeScript 的 HeadersInit 有多种类型）
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        rawHeaders[key] = value;
      });
    } else if (Array.isArray(options.headers)) {
      for (const [key, value] of options.headers) {
        rawHeaders[key] = value;
      }
    } else {
      Object.assign(rawHeaders, options.headers);
    }
  }

  const res = await fetch(url, {
    ...options,
    headers: rawHeaders,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const envelope = body as ApiEnvelope<never>;
    throw new Error(
      envelope.error?.message || `HTTP ${res.status}: ${res.statusText}`
    );
  }

  const envelope: ApiEnvelope<T> = await res.json();
  if (envelope.error) {
    throw new Error(envelope.error.message);
  }
  // normalize null items → []（Go 的 nil slice JSON 序列化为 null）
  const raw: any = envelope.data;
  if (raw && raw.items === null) {
    raw.items = [];
  }
  return raw as T;
}

// ============================================================
// Session APIs
// ============================================================
export async function createSession(params: {
  title: string;
  mode: "single_agent" | "multi_agent";
  workspace_type?: WorkspaceType;
  source_path?: string;
  initial_message?: string;
}): Promise<SessionDetail> {
  return request<SessionDetail>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function listSessions(
  limit = 20,
  cursor?: string
): Promise<PaginatedList<SessionSummary>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return request<PaginatedList<SessionSummary>>(
    `/api/v1/sessions?${params.toString()}`
  );
}

export async function getSessionDetail(
  sessionId: string
): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/v1/sessions/${sessionId}`);
}

export async function listSessionMessages(
  sessionId: string,
  beforeSeq = 0,
  limit = 50
): Promise<PaginatedList<RealtimeMessage>> {
  const params = new URLSearchParams({
    before_seq: String(beforeSeq),
    limit: String(limit),
  });
  return request<PaginatedList<RealtimeMessage>>(
    `/api/v1/sessions/${sessionId}/messages?${params.toString()}`
  );
}

export async function listSessionTasks(
  sessionId: string
): Promise<PaginatedList<TaskSummary>> {
  return request<PaginatedList<TaskSummary>>(
    `/api/v1/sessions/${sessionId}/tasks`
  );
}

export async function listSessionArtifacts(
  sessionId: string
): Promise<PaginatedList<ArtifactCard>> {
  return request<PaginatedList<ArtifactCard>>(
    `/api/v1/sessions/${sessionId}/artifacts`
  );
}

export async function deleteSession(sessionId: string): Promise<void> {
  return request(`/api/v1/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export async function updateSession(
  sessionId: string,
  params: {
    title?: string;
    mode?: "single_agent" | "multi_agent";
    workspace_root?: string;
    workspace_type?: WorkspaceType;
  }
): Promise<SessionDetail> {
  return request<SessionDetail>(`/api/v1/sessions/${sessionId}`, {
    method: "PUT",
    body: JSON.stringify(params),
  });
}

// ============================================================
// Task APIs
// ============================================================
export async function getTaskDetail(taskId: string): Promise<TaskDetail> {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}`);
}

export async function retryTask(
  taskId: string,
  reason = "manual_retry",
  force = false
): Promise<void> {
  return request(`/api/v1/tasks/${taskId}/retry`, {
    method: "POST",
    body: JSON.stringify({ reason, force }),
  });
}

export async function cancelTask(
  taskId: string,
  reason = "user_cancelled"
): Promise<void> {
  return request(`/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function submitApproval(
  taskId: string,
  approvalId: string,
  decision: "approve" | "reject",
  reason = ""
): Promise<void> {
  return request(`/api/v1/tasks/${taskId}/approvals/${approvalId}`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });
}

export async function resolveConflict(
  taskId: string,
  conflictId: string,
  resolution: "accept_latest_reviewed" | "retry_with_context" | "manual_merge",
  reason = ""
): Promise<void> {
  return request(
    `/api/v1/tasks/${taskId}/conflicts/${conflictId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ resolution, reason }),
    }
  );
}

// ============================================================
// Artifact APIs
// ============================================================
export async function getArtifactDetail(
  artifactId: string
): Promise<ArtifactCard> {
  return request<ArtifactCard>(`/api/v1/artifacts/${artifactId}`);
}

// ============================================================
// Workspace APIs (Stage 8 V2 — VSCode 懒加载模式)
// ============================================================

/** 获取文件树（只含元信息，不含内容） */
export async function getWorkspaceFiles(
  sessionId: string
): Promise<WorkspaceFileNode[]> {
  return request<WorkspaceFileNode[]>(
    `/api/v1/sessions/${sessionId}/workspace/files`
  );
}

/** 按需加载单个文件内容（VSCode 模式：点击 → 请求） */
export async function getWorkspaceFile(
  sessionId: string,
  filePath: string
): Promise<{ path: string; content: string }> {
  const params = new URLSearchParams({ path: filePath });
  return request<{ path: string; content: string }>(
    `/api/v1/sessions/${sessionId}/workspace/file?${params.toString()}`
  );
}

/** 播种 workspace 文件到后端（首次导入） */
export async function seedWorkspace(
  sessionId: string,
  files: Array<{ path: string; content: string }>
): Promise<{ seeded: number; skipped: number; errors: Array<{ path: string; error: string }> }> {
  return request(`/api/v1/sessions/${sessionId}/workspace/seed`, {
    method: "POST",
    body: JSON.stringify({ files }),
  });
}

/** 批量获取文件内容（保留用于同步场景） */
export async function getWorkspaceFilesContent(
  sessionId: string,
  paths: string[]
): Promise<{ contents: Record<string, string | null>; errors: Array<{ path: string; error: string }> }> {
  return request(`/api/v1/sessions/${sessionId}/workspace/files-content`, {
    method: "POST",
    body: JSON.stringify({ paths }),
  });
}

// ============================================================
// Filesystem browsing
// ============================================================
export async function listDirectories(
  path: string = "/"
): Promise<FsListResponse> {
  const params = new URLSearchParams({ path });
  return request<FsListResponse>(`/api/v1/fs/list?${params.toString()}`);
}

// ============================================================
// WebSocket Ticket
// ============================================================
export async function issueWsTicket(
  sessionId: string
): Promise<WsTicket> {
  return request<WsTicket>("/api/v1/ws-tickets", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId }),
  });
}

// ============================================================
// Agent CRUD — 用户自定义 Agent
// ============================================================
export interface AgentCreateRequest {
  id?: string;
  name: string;
  avatar?: string;
  description?: string;
  system_prompt?: string;
  allowed_skills?: string[];
  preferred_provider?: string;
  visibility?: string;
  import_url?: string;
}

export async function listAgents(): Promise<AgentDefinition[]> {
  const res = await request<{ agents?: AgentDefinition[]; items?: AgentDefinition[] }>("/api/v1/agents");
  // Gateway API 返回 { data: { items: [...] } }，兼容两种格式
  const list = res.agents || res.items || [];
  return list;
}

export async function createAgent(
  data: AgentCreateRequest
): Promise<AgentDefinition> {
  return request<AgentDefinition>("/api/v1/agents", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteAgent(
  agentId: string
): Promise<void> {
  return request<void>(`/api/v1/agents/${agentId}`, {
    method: "DELETE",
  });
}
