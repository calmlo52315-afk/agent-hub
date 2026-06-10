import type {
  RealtimeMessage,
  TaskUpdatedPayload,
  ChatMessagePayload,
  ArtifactCreatedPayload,
  ApprovalRequiredPayload,
} from "@/types";
import { useChatStore } from "@/stores/chatStore";
import { useTaskStore } from "@/stores/taskStore";
import { useArtifactStore } from "@/stores/artifactStore";
import { useConnectionStore } from "@/stores/connectionStore";

// ============================================================
// Event handler registry
// ============================================================
type EventHandler = (msg: RealtimeMessage) => void;

// ============================================================
// WebSocket Manager
// ============================================================
export class WebSocketManager {
  private ws: WebSocket | null = null;
  private ticket: string;
  private gatewayUrl: string;
  private sessionId: string;
  private handlers: Map<string, EventHandler[]> = new Map();
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1000;
  private intentionalClose = false;
  private eventIdCounter = 0;

  constructor(sessionId: string, ticket: string, gatewayUrl: string) {
    this.sessionId = sessionId;
    this.ticket = ticket;
    this.gatewayUrl = gatewayUrl;
    this.registerDefaultHandlers();
  }

  // ---- Public API ----

  connect(): void {
    // ⭐ 避免重复连接 — 如果已有活跃连接或重连次数耗尽，不重试
    if (this.ws?.readyState === WebSocket.OPEN) return;
    if (this.reconnectAttempts >= 3 && !this.intentionalClose) {
      console.log("[WebSocket] Skipping connect — reconnect limit reached");
      return;
    }

    const store = useConnectionStore.getState();
    store.setState(
      this.reconnectAttempts > 0 ? "reconnecting" : "connecting"
    );

    // Build WebSocket URL with ticket as query param
    const wsUrl = this.gatewayUrl
      .replace(/^(http|ws)/, (protocol) => protocol.startsWith("http") ? protocol.replace("http", "ws") : protocol)
      .replace(/\/$/, "");
    // Gateway exposes the WebSocket upgrader at `/ws`; Next.js rewrites proxy
    // the same path, so `/api/v1/ws` never reaches the backend.
    const fullUrl = `${wsUrl}/ws?ticket=${encodeURIComponent(this.ticket)}`;
    
    console.log("[WebSocket] Connecting to", fullUrl);
    console.log("[WebSocket] Gateway URL:", this.gatewayUrl);

    try {
      this.ws = new WebSocket(fullUrl);
    } catch (err) {
      console.error("[WebSocket] Failed to create WebSocket connection:", err);
      store.setState("disconnected");
      store.setLastError("Failed to create WebSocket connection");
      return;
    }

    this.ws.onopen = () => {
      console.log("[WebSocket] Connection opened");
      store.setState("connected");
      store.setLastError(null);
      this.reconnectAttempts = 0;

      // Send subscribe
      const resumeSeq = store.lastSeq;
      console.log("[WebSocket] Sending session.subscribe with resume_seq:", resumeSeq);
      this.sendCommand("session.subscribe", {
        resume_from_seq: resumeSeq,
        include_snapshot: true,
      });

      // Start heartbeat
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg: RealtimeMessage = JSON.parse(event.data);
        console.log("[WebSocket] Received message:", msg.type, msg);
        this.dispatch(msg);
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    this.ws.onerror = (event) => {
      console.error("[WebSocket] Connection error:", event);
      // ⭐ 只有 disconnected 时才更新错误，避免反复连接失败时刷屏
      if (store.state !== "disconnected") {
        store.setLastError("WebSocket connection error");
      }
    };

    this.ws.onclose = (event) => {
      console.log("[WebSocket] Connection closed:", event.code, event.reason);
      store.setState("disconnected");
      this.stopHeartbeat();

      if (!this.intentionalClose) {
        // ⭐ 限制重连次数为 3 次，避免无限重连风暴
        if (this.reconnectAttempts < 3) {
          this.scheduleReconnect();
        } else {
          console.log("[WebSocket] Max reconnect (3) reached, stopping");
          store.setLastError("WebSocket disconnected — refresh to reconnect");
        }
      }
    };
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.stopHeartbeat();
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close(1000, "Client disconnect");
      this.ws = null;
    }
    useConnectionStore.getState().setState("disconnected");
  }

  sendCommand(type: string, payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected, cannot send command");
      return;
    }

    const msg: Partial<RealtimeMessage> = {
      schema_version: "1.0",
      event_id: this.nextEventId(),
      session_id: this.sessionId,
      type: type as RealtimeMessage["type"],
      kind: "command",
      timestamp: new Date().toISOString(),
      sender: { type: "frontend", id: "frontend" },
      receiver: { type: "gateway", id: "gateway" },
      payload,
    };

    this.ws.send(JSON.stringify(msg));
  }

  sendChatMessage(
    content: string,
    role: "user" | "system" = "user",
    format: "plain" | "markdown" = "plain",
    mentionedAgent?: string,
  ): void {
    const messageId = `msg_${Date.now()}`;
    const payload: Record<string, unknown> = {
      message_id: messageId,
      role,
      format,
      content,
      stream_chunk: false,
    };
    if (mentionedAgent) {
      payload.mentioned_agent = mentionedAgent;
    }
    this.sendCommand("chat.message", payload);
  }

  on(type: string, handler: EventHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, []);
    }
    this.handlers.get(type)!.push(handler);

    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(type);
      if (handlers) {
        const idx = handlers.indexOf(handler);
        if (idx >= 0) handlers.splice(idx, 1);
      }
    };
  }

  // ---- Internal ----

  private nextEventId(): string {
    this.eventIdCounter++;
    return `evt_frontend_${Date.now()}_${this.eventIdCounter}`;
  }

  private dispatch(msg: RealtimeMessage): void {
    // Update last known seq
    if (msg.seq) {
      useConnectionStore.getState().setLastSeq(msg.seq);
    }

    // Route to registered handlers
    const handlers = this.handlers.get(msg.type) || [];
    handlers.forEach((h) => h(msg));

    // Also route to wildcard handlers
    const wildcardHandlers = this.handlers.get("*") || [];
    wildcardHandlers.forEach((h) => h(msg));
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatInterval = setInterval(() => {
      this.sendCommand("heartbeat", {});
    }, 30_000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      useConnectionStore
        .getState()
        .setLastError("Max reconnect attempts reached");
      return;
    }

    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
      30_000
    );
    this.reconnectAttempts++;

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  // ---- Default Event Handlers ----

  private registerDefaultHandlers(): void {
    // chat.message
    this.on("chat.message", (msg) => {
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);

      // Handle streaming
      const payload = msg.payload as unknown as ChatMessagePayload;
      if (payload.stream_chunk) {
        const messageId = payload.message_id || msg.event_id;
        chatStore.appendStreamChunk(messageId, payload.content);
        if (msg.status === "success" || msg.status === "failed") {
          chatStore.finalizeStream(messageId);
        }
      }
    });

    // task.created
    this.on("task.created", (msg) => {
      const taskStore = useTaskStore.getState();
      const chatStore = useChatStore.getState();
      const payload = msg.payload as unknown as TaskUpdatedPayload;
      taskStore.addTask({
        task_id: payload.task_id || msg.task_id!,
        session_id: msg.session_id,
        title: payload.summary || "New Task",
        status: "created",
        summary: payload.summary,
        current_agent: payload.agent,
        complexity: payload.complexity,
        updated_at: msg.timestamp,
      });
      chatStore.addMessage(msg);
    });

    // task.updated
    this.on("task.updated", (msg) => {
      const taskStore = useTaskStore.getState();
      const chatStore = useChatStore.getState();
      const payload = msg.payload as unknown as TaskUpdatedPayload;
      taskStore.updateTask(payload.task_id || msg.task_id!, {
        status: payload.status,
        summary: payload.summary,
        current_agent: payload.agent,
        complexity: payload.complexity,
        updated_at: msg.timestamp,
      });
      chatStore.addMessage(msg);
    });

    // task.completed
    this.on("task.completed", (msg) => {
      const taskStore = useTaskStore.getState();
      const chatStore = useChatStore.getState();
      const payload = msg.payload as unknown as TaskUpdatedPayload;
      const taskId = payload.task_id || msg.task_id!;
      taskStore.updateTask(taskId, {
        status: payload.status || "completed",
        summary: payload.summary,
        complexity: payload.complexity,
        updated_at: msg.timestamp,
      });
      chatStore.addMessage(msg);
    });

    // coding.completed
    this.on("coding.completed", (msg) => {
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
      // ⭐ Step 4: 更新 task 的编码耗时
      const payload = msg.payload as Record<string, unknown>;
      if (payload.latency_ms && msg.task_id) {
        const taskStore = useTaskStore.getState();
        taskStore.updateTask(msg.task_id, {
          coding_latency_ms: payload.latency_ms as number,
        });
      }
    });

    // review.started
    this.on("review.started", (msg) => {
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
    });

    // review.completed
    this.on("review.completed", (msg) => {
      // Handled as a message in chat flow — also can trigger UI updates
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
      // ⭐ Step 4: 更新 task 的审查耗时
      const payload = msg.payload as Record<string, unknown>;
      if (payload.latency_ms && msg.task_id) {
        const taskStore = useTaskStore.getState();
        taskStore.updateTask(msg.task_id, {
          review_latency_ms: payload.latency_ms as number,
        });
      }
    });

    // review.failed
    this.on("review.failed", (msg) => {
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
    });

    // artifact.created
    this.on("artifact.created", (msg) => {
      const artifactStore = useArtifactStore.getState();
      const chatStore = useChatStore.getState();
      const payload = msg.payload as unknown as ArtifactCreatedPayload;
      if (payload.card) {
        artifactStore.addArtifact(payload.card);
        // 对于简单任务的单个文件，也添加到聊天消息流中
        chatStore.addMessage(msg);
      }
    });

    // system.error
    this.on("system.error", (msg) => {
      const connStore = useConnectionStore.getState();
      const payload = msg.payload as Record<string, unknown>;
      connStore.setLastError(
        (payload.message as string) || "Unknown system error"
      );
      // Also add as chat message for visibility
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
    });

    // approval.required
    this.on("approval.required", (msg) => {
      const chatStore = useChatStore.getState();
      chatStore.addMessage(msg);
      // Update task to show waiting_for_approval
      const payload = msg.payload as unknown as ApprovalRequiredPayload;
      if (payload.task_id) {
        const taskStore = useTaskStore.getState();
        taskStore.updateTask(payload.task_id, {
          waiting_for_approval: true,
          status: "blocked",
        });
      }
    });

    // ack
    this.on("ack", (_msg) => {
      // Ack handling — mostly fire-and-forget for the UI
    });

    // heartbeat
    this.on("heartbeat", (_msg) => {
      // No UI action needed for heartbeat replies
    });

    // connection.ready
    this.on("connection.ready", (_msg) => {
      useConnectionStore.getState().setState("connected");
    });

    // session.snapshot
    this.on("session.snapshot", (msg) => {
      // ⭐ Stage 9: 不覆盖 HTTP 加载的消息。只在消息列表为空时才接受 snapshot。
      const chatStore = useChatStore.getState();
      if (chatStore.messages.length === 0) {
        chatStore.addMessage(msg);
      }
      // 如果已有消息（HTTP API 加载的），跳过 snapshot 以避免清除已有消息
    });
  }
}

// ============================================================
// Singleton manager instance (per active session)
// ============================================================
let activeManager: WebSocketManager | null = null;

export function getActiveManager(): WebSocketManager | null {
  return activeManager;
}

export function createManager(
  sessionId: string,
  ticket: string,
  gatewayUrl?: string
): WebSocketManager {
  // Disconnect existing
  if (activeManager) {
    activeManager.disconnect();
  }

  const useDirectGateway =
    process.env.NEXT_PUBLIC_FORCE_DIRECT_GATEWAY === "1";
  const url =
    gatewayUrl ||
    process.env.NEXT_PUBLIC_GATEWAY_WS_URL ||
    (useDirectGateway ? process.env.NEXT_PUBLIC_GATEWAY_BASE_URL : "") ||
    (typeof window !== "undefined"
      ? window.location.origin
      : "http://localhost:3000");
  
  console.log("[WebSocket] Creating manager:");
  console.log("  - sessionId:", sessionId);
  console.log("  - useDirectGateway:", useDirectGateway);
  console.log("  - NEXT_PUBLIC_GATEWAY_BASE_URL:", process.env.NEXT_PUBLIC_GATEWAY_BASE_URL);
  console.log("  - Using URL:", url);

  activeManager = new WebSocketManager(sessionId, ticket, url);
  return activeManager;
}

export function disconnectManager(): void {
  if (activeManager) {
    activeManager.disconnect();
    activeManager = null;
  }
}
