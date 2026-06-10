// ============================================================
// Core Domain Types — aligned with Gateway / Runtime specs
// ============================================================

// ---- Session ----
export type SessionMode = "single_agent" | "multi_agent";

// ---- New Domain Model ----
export type InteractionMode = "direct_agent" | "orchestrated";
export type ExecutionMode = "task" | "project";
export type ChatMode = "single" | "group";
export type PackageStrategy = "none" | "zip" | "docker" | "deploy";

// ---- Deprecated (kept for backward compatibility) ----
export type TaskMode = "chat" | "task" | "project";

// ---- Workspace (Session-scoped) ----
export type WorkspaceType = "scratch" | "project" | "imported";

export interface WorkspaceMeta {
  workspace_id: string;        // = session_id (1:1 映射)
  session_id: string;
  root_path: string;           // 工作区根目录路径
  workspace_type: WorkspaceType; // 工作区类型
  source_path?: string;        // IMPORTED 类型的源路径
  source_files_count: number;  // 源文件数量
  total_tasks: number;         // 关联的 task 数量
  created_at: string;
  updated_at: string;
  status: "active" | "archived" | "cleaning";
}

export interface WorkspaceSnapshot {
  snapshot_id: string;
  workspace_id: string;
  task_id: string;            // 触发快照的 task
  file_states: FileState[];   // 快照时的文件状态列表
  created_at: string;
}

export interface FileState {
  path: string;
  hash: string;
  size_bytes: number;
  changed_by_task_id: string;
}

// ---- Workspace Panel Tab Types ----
export interface WorkspaceFileNode {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: WorkspaceFileNode[];
  size_bytes?: number;
  changed_by_task_id?: string;
  content?: string;
}

export interface WorkspaceChangeEntry {
  path: string;
  change_type: "create" | "update" | "delete";
  task_id: string;
  task_title?: string;
  diff_excerpt?: string;
  timestamp: string;
}

export interface WorkspaceHistoryEntry {
  task_id: string;
  title: string;
  status: string;
  agent_flow?: string[];
  summary?: string;
  created_at: string;
  completed_at?: string;
}

// ---- Agent Registry ----
export interface AgentCapability {
  id: string;
  name: string;
  description: string;
}

export interface AgentInfo {
  id: string;
  name: string;
  avatar: string;
  description: string;
  capabilities: AgentCapability[];
  version: string;
  enabled: boolean;
}

// ---- Stage 8: Agent Definition (Persona) ----
export interface AgentDefinition {
  id: string;
  name: string;
  avatar: string;
  description: string;
  system_prompt: string;
  allowed_skills: string[];
  preferred_provider: string;
  visibility: "public" | "private" | "unlisted";
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  mode: SessionMode;
  /** single_agent 模式下的 agent ID（用于侧边栏显示 logo） */
  agent_id?: string;
  updated_at: string;
  last_event_seq: number;
  last_message_preview?: string;
  task_count?: number;
  // Stage 8: Session 级 Workspace
  workspace_id?: string;       // 关联的 workspace（通常等于 session_id）
  workspace_root?: string;     // 工作区根路径
  workspace_type?: WorkspaceType; // 工作区类型
  source_files_count?: number; // 工作区文件数
}

export interface SessionDetail {
  session_id: string;
  title: string;
  mode: SessionMode;
  created_at: string;
  updated_at: string;
  last_event_seq: number;
  // Stage 8: Session 级 Workspace
  workspace_id?: string;       // 关联的 workspace
  workspace_root?: string;     // 工作区根路径
  workspace_type?: WorkspaceType; // 工作区类型
}

// ---- Message ----
export interface SenderInfo {
  type: "user" | "frontend" | "gateway" | "agent";
  id: string;
}

export interface ReceiverInfo {
  type: "gateway" | "frontend" | "session" | "agent";
  id: string;
}

export interface AckInfo {
  mode: "none" | "received" | "processed";
  required: boolean;
}

export type RealtimeMessageType =
  | "connection.ready"
  | "session.snapshot"
  | "session.subscribe"
  | "chat.message"
  | "task.created"
  | "task.updated"
  | "task.completed"
  | "coding.completed"
  | "review.started"
  | "review.completed"
  | "review.failed"
  | "artifact.created"
  | "approval.required"
  | "system.error"
  | "ack"
  | "heartbeat";

export type MessageKind = "command" | "event" | "result" | "error";

export type MessageStatus =
  | "accepted"
  | "running"
  | "streaming"
  | "success"
  | "failed"
  | "replayed";

export type MessageRole = "user" | "agent" | "system";

export interface RealtimeMessage {
  schema_version: string;
  event_id: string;
  session_id: string;
  task_id?: string;
  trace_id?: string;
  type: RealtimeMessageType;
  kind: MessageKind;
  seq: number;
  timestamp: string;
  sender: SenderInfo;
  receiver: ReceiverInfo;
  status?: MessageStatus;
  in_reply_to?: string;
  ack?: AckInfo;
  payload: Record<string, unknown>;
}

export interface ChatMessagePayload {
  message_id?: string;
  role: MessageRole;
  format?: "plain" | "markdown" | "diff";
  content: string;
  stream_chunk?: boolean;
  agent?: string;
}

export interface TaskUpdatedPayload {
  task_id: string;
  status: TaskStatus;
  summary?: string;
  agent?: AgentType;
  progress?: { current: number; total: number };
  complexity?: TaskComplexity;
}

export interface ArtifactCreatedPayload {
  artifact_id: string;
  card: ArtifactCard;
}

export interface ApprovalRequiredPayload {
  approval_id: string;
  reason: "ownership_conflict" | "retry_exceeded" | "review_failed" | "large_change";
  task_id: string;
  options: ["approve", "reject"];
}

// ---- Task ----
export type TaskStatus =
  | "created"
  | "planning"
  | "scheduled"
  | "running"
  | "blocked"
  | "retrying"
  | "completed"
  | "failed"
  | "cancelled";

// RuntimeAgent (系统内置角色)
export type AgentType = "orchestrator" | "coding" | "review" | "artifact" | "testing" | "documentation";
// UserDefinedAgent (Persona)
export type PersonaAgentType = "backend_architect" | "frontend_engineer" | "devops_engineer" | "qa_engineer" | "security_reviewer";
// 向后兼容：mentioned_agent 可以是 AgentType 或 PersonaAgentType
export type MentionedAgent = AgentType | PersonaAgentType | string;

export type TaskComplexity = "simple" | "medium" | "project";

export interface TaskSummary {
  task_id: string;
  session_id: string;
  title: string;
  status: TaskStatus;
  summary?: string;
  current_agent?: AgentType;
  agent_flow?: AgentType[];
  retry_count?: number;
  retry_limit?: number;
  waiting_for_approval?: boolean;
  // New domain model fields
  interaction_mode?: InteractionMode;
  execution_mode?: ExecutionMode;
  chat_mode?: ChatMode;
  review_required?: boolean;
  package_strategy?: PackageStrategy;
  complexity?: TaskComplexity; // 新增：任务复杂度
  // ⭐ Step 4: 编码和审查耗时
  coding_latency_ms?: number;
  review_latency_ms?: number;
  // Stage 8: Task 归属于 Session 的 Workspace
  workspace_id?: string;       // 所属 workspace（指向 session 的 workspace）
  // Deprecated (kept for backward compatibility)
  task_mode?: TaskMode;
  /** @deprecated workspace 现在是 Session 级，不再由 Task 单独声明 */
  workspace_required?: boolean;
  bundle_required?: boolean;
  updated_at: string;
}

export interface TaskDetail extends TaskSummary {
  created_at: string;
}

// ---- Artifact ----
export type CardType = "preview" | "diff" | "file" | "review" | "bundle";

export type CardStatus = "generating" | "ready" | "failed";

export interface ArtifactAction {
  action: string;
  label: string;
  enabled: boolean;
  target?: {
    url?: string;
    path?: string;
    tab?: "preview" | "diff" | "files" | "review";
  };
}

export interface ArtifactProducer {
  type: "gateway" | "artifact-agent" | "review-agent";
  id: string;
}

export interface ArtifactCard {
  card_id: string;
  artifact_id: string;
  session_id: string;
  task_id: string;
  card_type: CardType;
  title: string;
  summary?: string;
  status: CardStatus;
  created_at: string;
  updated_at: string;
  producer: ArtifactProducer;
  badges?: string[];
  actions?: ArtifactAction[];
  content: Record<string, unknown>;
}

// ---- Card Content Types ----
export interface PreviewContent {
  preview_url?: string;
  entry_path?: string;
  viewport?: "desktop" | "mobile";
  framework?: string;
}

export interface DiffFileEntry {
  path: string;
  change_type: "create" | "update" | "delete";
  diff_excerpt?: string;
  content?: string;
  /** ⭐ 新增：修改前文件内容 */
  before_content?: string;
  /** ⭐ 新增：修改后文件内容 */
  after_content?: string;
  /** ⭐ 新增：difflib 生成的 unified diff（用于 DiffViewerCard 渲染绿色/红色行） */
  unified_diff?: string;
}

export interface DiffContent {
  files_changed: number;
  additions: number;
  deletions: number;
  files: DiffFileEntry[];
}

export interface FileContent {
  path: string;
  mime_type: string;
  size_bytes: number;
  download_url: string;
  content?: string;
}

export interface ReviewIssue {
  severity: "high" | "medium" | "low";
  message: string;
  paths?: string[];
  /** ⭐ 问题类型 */
  type?: string;
  /** ⭐ 修复建议 */
  suggestion?: string;
  /** ⭐ 行号 */
  line?: number;
}

export interface ReviewContent {
  decision: "pass" | "fail" | "skipped";
  score: number;
  issues: ReviewIssue[];
  /** ⭐ 审查的文件数 */
  files_reviewed?: number;
}

export interface BundleItem {
  type: "preview" | "diff" | "file" | "review";
  artifact_id: string;
}

export interface BundleContent {
  archive_path: string;
  download_url: string;
  items: BundleItem[];
}

// ---- API Envelope ----
export interface ApiEnvelope<T> {
  request_id: string;
  data: T | null;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  } | null;
}

export interface PaginatedList<T> {
  items: T[];
  next_cursor?: string | null;
}

// ---- WebSocket Ticket ----
export interface WsTicket {
  session_id: string;
  ws_ticket: string;
  expires_at: string;
}

// ---- Connection State ----
export type ConnectionState = "disconnected" | "connecting" | "connected" | "reconnecting";

// ---- Filesystem browsing ----
export interface FsListResponse {
  path: string;
  parent: string;
  directories: string[];
}

// ---- Workspace Sync ----
export type SyncStatus = "idle" | "seeding" | "seeded" | "syncing" | "conflict" | "error";
