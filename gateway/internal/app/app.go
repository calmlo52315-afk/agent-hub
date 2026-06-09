package app

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"os"
	"strings"
	"sync"
	"time"

	"agenthub/gateway/internal/auth"
	"agenthub/gateway/internal/protocol"
	"agenthub/gateway/internal/runtimeclient"
	"agenthub/gateway/internal/store"
	"agenthub/gateway/internal/ws"

	"github.com/google/uuid"
)

var ErrApprovalRequired = errors.New("approval required before retry")

type taskExecution struct {
	cancel       context.CancelFunc
	runtimeJobID string
}

// GatewayApp 统一管理 Gateway 的业务状态与 Runtime 调用。
type GatewayApp struct {
	Store   store.Backend
	Auth    *auth.Service
	Runtime runtimeclient.Client
	Hub     *ws.Hub

	closeStore  func() error
	taskTimeout time.Duration
	mu          sync.Mutex
	running     map[string]*taskExecution
}

func New(repoRoot string) (*GatewayApp, string, error) {
	_ = repoRoot
	backend, closeStore, err := store.NewDefaultStore()
	if err != nil {
		return nil, "", err
	}
	authService := auth.NewService(backend)
	demoToken, err := authService.BootstrapDemoPrincipal(auth.Principal{
		ID:   "demo-user",
		Role: "session_approver",
	})
	if err != nil {
		return nil, "", err
	}

	httpClient := runtimeclient.NewHTTPClient(
		getenvDefault("RUNTIME_BASE_URL", "http://127.0.0.1:8001"),
		getenvDefault("RUNTIME_INTERNAL_TOKEN", "runtime-internal-token"),
		3*time.Minute,
	)
	httpClient.PollTimeout = getenvDurationDefault("GATEWAY_POLL_TIMEOUT", 600*time.Second)

	return &GatewayApp{
		Store:       backend,
		Auth:        authService,
		Runtime:     httpClient,
		Hub:         ws.NewHub(),
		closeStore:  closeStore,
		taskTimeout: getenvDurationDefault("GATEWAY_TASK_TIMEOUT", 10*time.Minute),
		running:     make(map[string]*taskExecution),
	}, demoToken, nil
}

func (a *GatewayApp) Close() error {
	if a == nil || a.closeStore == nil {
		return nil
	}
	return a.closeStore()
}

func (a *GatewayApp) CreateSession(principal auth.Principal, title, mode, initialMessage, workspaceType, sourcePath string) (store.Session, error) {
	if strings.TrimSpace(title) == "" {
		title = "New Session"
	}
	if strings.TrimSpace(mode) == "" {
		mode = "multi_agent"
	}
	now := time.Now().UTC()
	session := store.Session{
		SessionID:     newID("sess"),
		Title:         title,
		Mode:          mode,
		OwnerID:       principal.ID,
		CreatedAt:     now,
		UpdatedAt:     now,
		LastEventSeq:  0,
		WorkspaceRoot: sourcePath,
		WorkspaceType: workspaceType,
	}
	if err := a.Store.CreateSession(session); err != nil {
		return store.Session{}, err
	}

	if strings.TrimSpace(initialMessage) != "" {
		event := a.newEvent(
			session.SessionID,
			"",
			"",
			"chat.message",
			"event",
			"success",
			protocol.Party{Type: "user", ID: principal.ID},
			protocol.Party{Type: "session", ID: session.SessionID},
			map[string]any{
				"message_id":   newID("msg"),
				"role":         "user",
				"format":       "plain",
				"content":      initialMessage,
				"stream_chunk": false,
			},
		)
		_, _ = a.Store.AppendEvent(session.SessionID, event)
	}

	return a.Store.GetSession(session.SessionID)
}

func (a *GatewayApp) ListSessions(principal auth.Principal) []store.Session {
	return a.Store.ListSessions(principal.ID)
}

func (a *GatewayApp) GetSession(principal auth.Principal, sessionID string) (store.Session, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return store.Session{}, store.ErrSessionForbidden
	}
	return a.Store.GetSession(sessionID)
}

func (a *GatewayApp) UpdateSession(principal auth.Principal, session store.Session) (store.Session, error) {
	if !a.Store.IsSessionMember(session.SessionID, principal.ID) {
		return store.Session{}, store.ErrSessionForbidden
	}
	if err := a.Store.UpdateSession(session); err != nil {
		return store.Session{}, err
	}
	return a.Store.GetSession(session.SessionID)
}

func (a *GatewayApp) DeleteSession(principal auth.Principal, sessionID string) error {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return store.ErrSessionForbidden
	}

	// 获取该会话下的所有任务
	tasks := a.Store.ListSessionTasks(sessionID)

	// 对每个任务，删除对应的 artifact 目录
	for _, task := range tasks {
		// 构造 artifact 目录路径
		artifactDir := "artifacts/" + task.TaskID
		// 删除该目录
		if err := os.RemoveAll(artifactDir); err != nil {
			log.Printf("Warning: failed to delete artifact directory %s: %v", artifactDir, err)
		}
	}

	// 删除会话相关的数据
	return a.Store.DeleteSession(sessionID)
}

func (a *GatewayApp) SeedWorkspace(principal auth.Principal, sessionID string, files []runtimeclient.WorkspaceSeedFile) (runtimeclient.WorkspaceSeedResult, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return runtimeclient.WorkspaceSeedResult{}, store.ErrSessionForbidden
	}
	result, err := a.Runtime.SeedWorkspace(context.Background(), sessionID, files)
	if err != nil {
		return result, err
	}

	// 更新会话表，记录工作区信息
	session, err := a.Store.GetSession(sessionID)
	if err == nil {
		session.WorkspaceType = "imported"
		if err := a.Store.UpdateSession(session); err != nil {
			fmt.Printf("Failed to update session workspace info: %v\n", err)
		}
	}

	// 写入文件索引（只存元信息，不存内容）
	for _, file := range files {
		// 计算内容的简单 hash（SHA-256）
		hash := sha256Hex([]byte(file.Content))
		if err := a.Store.UpsertWorkspaceFileIndex(sessionID, file.Path, int64(len(file.Content)), hash); err != nil {
			fmt.Printf("Failed to save workspace file index for %s: %v\n", file.Path, err)
		}
	}

	return result, nil
}

func (a *GatewayApp) ReadWorkspaceFilesContent(principal auth.Principal, sessionID string, paths []string) (runtimeclient.WorkspaceFilesContentResult, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return runtimeclient.WorkspaceFilesContentResult{}, store.ErrSessionForbidden
	}

	// 总是从 Runtime 磁盘读取文件内容（懒加载模式）。
	// 数据库只存索引，不存内容。这避免了"一次加载整个 workspace 到数据库"的坑。
	return a.Runtime.ReadWorkspaceFilesContent(context.Background(), sessionID, paths)
}

// ReadWorkspaceFile 按需读取单个文件内容（VSCode 懒加载模式）。
// 使用 Runtime 的 GET /workspace/file 端点。
func (a *GatewayApp) ReadWorkspaceFile(principal auth.Principal, sessionID, filePath string) (map[string]any, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return nil, store.ErrSessionForbidden
	}
	return a.Runtime.ReadWorkspaceFile(context.Background(), sessionID, filePath)
}

func (a *GatewayApp) GetWorkspaceFiles(principal auth.Principal, sessionID string) ([]map[string]any, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return nil, store.ErrSessionForbidden
	}
	return a.Runtime.GetWorkspaceFiles(context.Background(), sessionID)
}

func (a *GatewayApp) ListSessionMessages(principal auth.Principal, sessionID string, beforeSeq int64, limit int) ([]protocol.WSEvent, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return nil, store.ErrSessionForbidden
	}
	events := a.Store.ListEvents(sessionID, 0, 0)
	if beforeSeq <= 0 {
		beforeSeq = 1<<62 - 1
	}
	items := make([]protocol.WSEvent, 0)
	for i := len(events) - 1; i >= 0; i-- {
		if events[i].Seq < beforeSeq {
			items = append(items, events[i])
			if limit > 0 && len(items) >= limit {
				break
			}
		}
	}
	return items, nil
}

func (a *GatewayApp) ListSessionTasks(principal auth.Principal, sessionID string) ([]store.Task, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return nil, store.ErrSessionForbidden
	}
	return a.Store.ListSessionTasks(sessionID), nil
}

func (a *GatewayApp) ListSessionArtifacts(principal auth.Principal, sessionID string) ([]protocol.ArtifactCard, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return nil, store.ErrSessionForbidden
	}
	return a.Store.ListSessionArtifacts(sessionID), nil
}

func (a *GatewayApp) GetTask(principal auth.Principal, taskID string) (store.Task, error) {
	task, err := a.Store.GetTask(taskID)
	if err != nil {
		return store.Task{}, err
	}
	if !a.Store.IsSessionMember(task.SessionID, principal.ID) {
		return store.Task{}, store.ErrSessionForbidden
	}
	return task, nil
}

func (a *GatewayApp) GetArtifact(principal auth.Principal, artifactID string) (protocol.ArtifactCard, error) {
	card, err := a.Store.GetArtifact(artifactID)
	if err != nil {
		return protocol.ArtifactCard{}, err
	}
	if !a.Store.IsSessionMember(card.SessionID, principal.ID) {
		return protocol.ArtifactCard{}, store.ErrSessionForbidden
	}
	return card, nil
}

func (a *GatewayApp) IssueWSTicket(principal auth.Principal, sessionID string) (string, time.Time, error) {
	if !a.Store.IsSessionMember(sessionID, principal.ID) {
		return "", time.Time{}, store.ErrSessionForbidden
	}
	return a.Auth.IssueWSTicket(principal, sessionID, 5*time.Minute)
}

// HandleWSCommand 负责把 WebSocket 命令转成会话内业务动作。
func (a *GatewayApp) HandleWSCommand(client *ws.Client, event protocol.WSEvent) {
	switch event.Type {
	case "session.subscribe":
		a.handleSessionSubscribe(client, event)
	case "chat.message":
		a.handleChatMessage(client, event)
	case "task.retry.request":
		a.handleRetryRequest(client, event)
	case "task.cancel.request":
		a.handleCancelRequest(client, event)
	case "task.approval.submit":
		a.handleApprovalSubmit(client, event)
	case "conflict.resolution.submit":
		a.handleConflictResolution(client, event)
	case "heartbeat":
		a.Hub.Send(client, a.newEvent(client.SessionID, "", "", "heartbeat", "event", "success", protocol.Party{Type: "gateway", ID: "gateway"}, protocol.Party{Type: "frontend", ID: client.PrincipalID}, map[string]any{"alive": true}))
	default:
		a.sendSystemError(client, event, "unsupported_event_type", "unsupported websocket event type")
	}
}

func (a *GatewayApp) RequestTaskRetry(principal auth.Principal, taskID, reason string, force bool) (map[string]any, error) {
	task, err := a.GetTask(principal, taskID)
	if err != nil {
		return nil, err
	}
	if task.Status == "running" {
		return nil, fmt.Errorf("task is still running")
	}
	if task.RetryCount >= task.RetryLimit && !force {
		approval := store.ApprovalRecord{
			ApprovalID: newID("approval"),
			SessionID:  task.SessionID,
			TaskID:     task.TaskID,
			Status:     "pending",
			Reason:     reason,
			Timestamp:  time.Now().UTC(),
		}
		if err := a.Store.SaveApproval(approval); err != nil {
			return nil, err
		}
		task.WaitingForApproval = true
		task.ApprovalID = approval.ApprovalID
		task.UpdatedAt = time.Now().UTC()
		if err := a.Store.UpdateTask(task); err != nil {
			return nil, err
		}
		approvalEvent := a.newEvent(
			task.SessionID,
			task.TaskID,
			task.RuntimeTraceID,
			"approval.required",
			"event",
			"success",
			protocol.Party{Type: "gateway", ID: "gateway"},
			protocol.Party{Type: "session", ID: task.SessionID},
			map[string]any{
				"approval_id": approval.ApprovalID,
				"reason":      "retry_exceeded",
				"task_id":     task.TaskID,
				"options":     []string{"approve", "reject"},
			},
		)
		a.persistAndBroadcast(task.SessionID, approvalEvent)
		return map[string]any{"approval_id": approval.ApprovalID, "status": "pending_approval"}, ErrApprovalRequired
	}

	task.RetryCount++
	task.Status = "retrying"
	task.Summary = reason
	task.WaitingForApproval = false
	task.ApprovalID = ""
	task.UpdatedAt = time.Now().UTC()
	if err := a.Store.UpdateTask(task); err != nil {
		return nil, err
	}
	go a.executeTask(task, task.MentionedAgent)
	return map[string]any{"task_id": task.TaskID, "status": "retrying"}, nil
}

func (a *GatewayApp) CancelTask(principal auth.Principal, taskID, reason string) error {
	task, err := a.GetTask(principal, taskID)
	if err != nil {
		return err
	}
	if task.Status == "cancelled" || task.Status == "completed" || task.Status == "failed" || task.Status == "timed_out" {
		return fmt.Errorf("task is already in terminal state")
	}
	a.mu.Lock()
	handle, ok := a.running[taskID]
	a.mu.Unlock()
	if ok && handle.runtimeJobID != "" {
		_ = a.Runtime.CancelTask(context.Background(), handle.runtimeJobID)
	}
	if ok && handle.cancel != nil {
		handle.cancel()
	} else if task.RuntimeJobID != "" {
		_ = a.Runtime.CancelTask(context.Background(), task.RuntimeJobID)
	}
	task.Status = "cancelled"
	task.Summary = reason
	task.CurrentAgent = ""
	task.UpdatedAt = time.Now().UTC()
	if err := a.Store.UpdateTask(task); err != nil {
		return err
	}
	cancelEvent := a.newEvent(
		task.SessionID,
		task.TaskID,
		task.RuntimeTraceID,
		"task.updated",
		"event",
		"cancelled",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"task_id":        task.TaskID,
			"status":         "cancelled",
			"summary":        reason,
			"agent":          task.CurrentAgent,
			"runtime_job_id": task.RuntimeJobID,
		},
	)
	a.persistAndBroadcast(task.SessionID, cancelEvent)
	return nil
}

func (a *GatewayApp) SubmitApproval(principal auth.Principal, taskID, approvalID, decision, reason string) (map[string]any, error) {
	task, err := a.GetTask(principal, taskID)
	if err != nil {
		return nil, err
	}
	if principal.Role != "session_approver" {
		return nil, auth.ErrUnauthorized
	}
	record, err := a.Store.GetApproval(approvalID)
	if err != nil {
		return nil, err
	}
	record.Decision = decision
	record.Reason = reason
	record.Approver = principal.ID
	record.Status = "completed"
	record.Timestamp = time.Now().UTC()
	if err := a.Store.UpdateApproval(record); err != nil {
		return nil, err
	}
	task.WaitingForApproval = false
	task.ApprovalID = ""
	task.UpdatedAt = time.Now().UTC()
	if err := a.Store.UpdateTask(task); err != nil {
		return nil, err
	}
	if decision == "approve" {
		return a.RequestTaskRetry(principal, taskID, "approved retry", true)
	}
	return map[string]any{"task_id": taskID, "status": "rejected"}, nil
}

func (a *GatewayApp) ResolveConflict(principal auth.Principal, taskID, conflictID, resolution, reason string) (map[string]any, error) {
	if principal.Role != "session_approver" {
		return nil, auth.ErrUnauthorized
	}
	task, err := a.GetTask(principal, taskID)
	if err != nil {
		return nil, err
	}
	event := a.newEvent(
		task.SessionID,
		task.TaskID,
		task.RuntimeTraceID,
		"task.updated",
		"event",
		"success",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"task_id":     task.TaskID,
			"status":      task.Status,
			"summary":     "conflict resolved",
			"resolution":  resolution,
			"reason":      reason,
			"conflict_id": conflictID,
		},
	)
	a.persistAndBroadcast(task.SessionID, event)
	return map[string]any{"task_id": taskID, "resolution": resolution}, nil
}

func (a *GatewayApp) handleSessionSubscribe(client *ws.Client, event protocol.WSEvent) {
	payload := event.Payload
	resumeFrom, _ := payload["resume_from_seq"].(float64)
	includeSnapshot, _ := payload["include_snapshot"].(bool)
	a.Hub.MarkSubscribed(client)
	a.sendAck(client, event, "received", true, "")
	a.sendAck(client, event, "processed", true, "")

	ready := a.newEvent(
		client.SessionID,
		"",
		"",
		"connection.ready",
		"event",
		"success",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "frontend", ID: client.PrincipalID},
		map[string]any{"session_id": client.SessionID},
	)
	a.Hub.Send(client, ready)

	if resumeFrom > 0 {
		a.Hub.Replay(client, a.Store.ListEvents(client.SessionID, int64(resumeFrom), 200))
		return
	}
	if includeSnapshot {
		session, _ := a.Store.GetSession(client.SessionID)
		snapshot := a.newEvent(
			client.SessionID,
			"",
			"",
			"session.snapshot",
			"event",
			"success",
			protocol.Party{Type: "gateway", ID: "gateway"},
			protocol.Party{Type: "frontend", ID: client.PrincipalID},
			map[string]any{
				"session":   session,
				"tasks":     a.Store.ListSessionTasks(client.SessionID),
				"artifacts": a.Store.ListSessionArtifacts(client.SessionID),
			},
		)
		a.Hub.Send(client, snapshot)
	}
}

func (a *GatewayApp) handleChatMessage(client *ws.Client, event protocol.WSEvent) {
	content, _ := event.Payload["content"].(string)
	content = strings.TrimSpace(content)
	if content == "" {
		a.sendSystemError(client, event, "invalid_chat_message", "message content is required")
		return
	}
	fmt.Printf("[DEBUG] Received chat message: %s\n", content)
	a.sendAck(client, event, "received", true, "")
	a.sendAck(client, event, "processed", true, "")

	userChat := a.newEvent(
		client.SessionID,
		"",
		"",
		"chat.message",
		"event",
		"success",
		protocol.Party{Type: "user", ID: client.PrincipalID},
		protocol.Party{Type: "session", ID: client.SessionID},
		map[string]any{
			"message_id":   newID("msg"),
			"role":         "user",
			"format":       defaultString(event.Payload["format"], "plain"),
			"content":      content,
			"stream_chunk": false,
		},
	)
	a.persistAndBroadcast(client.SessionID, userChat)

	// ⭐ Stage 10: 优先从 WebSocket payload 中获取 mentioned_agent, 兜底从文本解析
	mentionedAgent, _ := event.Payload["mentioned_agent"].(string)
	if mentionedAgent == "" {
		mentionedAgent = extractMentionedAgent(content)
	}
	fmt.Printf("[DEBUG] Extracted mentionedAgent: '%s' (from payload: %v)\n", mentionedAgent, event.Payload["mentioned_agent"])

	task := store.Task{
		TaskID:             newID("task"),
		SessionID:          client.SessionID,
		Title:              truncate(content, 32),
		Instruction:        content,
		Status:             "created",
		Summary:            "Gateway accepted user instruction",
		AgentFlow:          []string{"coding", "review", "artifact"},
		CurrentAgent:       "coding",
		RetryLimit:         2,
		WaitingForApproval: false,
		MentionedAgent:     mentionedAgent,
		UpdatedAt:          time.Now().UTC(),
	}
	if err := a.Store.CreateTask(task); err != nil {
		a.sendSystemError(client, event, "task_create_failed", err.Error())
		return
	}

	createdEvent := a.newEvent(
		client.SessionID,
		task.TaskID,
		"",
		"task.created",
		"event",
		"accepted",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: client.SessionID},
		map[string]any{
			"task_id": task.TaskID,
			"status":  "created",
			"summary": task.Summary,
			"agent":   "coding",
			"progress": map[string]any{
				"current": 0,
				"total":   3,
			},
		},
	)
	a.persistAndBroadcast(client.SessionID, createdEvent)

	task.Status = "running"
	task.Summary = "Coding Agent is running"
	task.UpdatedAt = time.Now().UTC()
	_ = a.Store.UpdateTask(task)
	runningEvent := a.newEvent(
		client.SessionID,
		task.TaskID,
		"",
		"task.updated",
		"event",
		"running",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: client.SessionID},
		map[string]any{
			"task_id": task.TaskID,
			"status":  "running",
			"summary": task.Summary,
			"agent":   "coding",
			"progress": map[string]any{
				"current": 1,
				"total":   3,
			},
		},
	)
	a.persistAndBroadcast(client.SessionID, runningEvent)
	go a.executeTask(task, task.MentionedAgent)
}

func extractMentionedAgent(content string) string {
	lowerContent := strings.ToLower(content)
	switch {
	case strings.Contains(lowerContent, "@claude-code") || strings.Contains(lowerContent, "@claude code"):
		return "claude_code"
	case strings.Contains(lowerContent, "@codex"):
		return "codex"
	default:
		return ""
	}
}

func (a *GatewayApp) handleRetryRequest(client *ws.Client, event protocol.WSEvent) {
	taskID := firstString(event.TaskID, anyToString(event.Payload["task_id"]))
	_, err := a.RequestTaskRetry(auth.Principal{ID: client.PrincipalID, Role: "session_approver"}, taskID, "retry from websocket", false)
	if err != nil && !errors.Is(err, ErrApprovalRequired) {
		a.sendSystemError(client, event, "retry_failed", err.Error())
		return
	}
	a.sendAck(client, event, "processed", true, "")
}

func (a *GatewayApp) handleCancelRequest(client *ws.Client, event protocol.WSEvent) {
	taskID := firstString(event.TaskID, anyToString(event.Payload["task_id"]))
	if err := a.CancelTask(auth.Principal{ID: client.PrincipalID, Role: "session_approver"}, taskID, "cancelled from websocket"); err != nil {
		a.sendSystemError(client, event, "cancel_failed", err.Error())
		return
	}
	a.sendAck(client, event, "processed", true, "")
}

func (a *GatewayApp) handleApprovalSubmit(client *ws.Client, event protocol.WSEvent) {
	taskID := firstString(event.TaskID, anyToString(event.Payload["task_id"]))
	approvalID := anyToString(event.Payload["approval_id"])
	decision := anyToString(event.Payload["decision"])
	reason := anyToString(event.Payload["reason"])
	if _, err := a.SubmitApproval(auth.Principal{ID: client.PrincipalID, Role: "session_approver"}, taskID, approvalID, decision, reason); err != nil {
		a.sendSystemError(client, event, "approval_submit_failed", err.Error())
		return
	}
	a.sendAck(client, event, "processed", true, "")
}

func (a *GatewayApp) handleConflictResolution(client *ws.Client, event protocol.WSEvent) {
	taskID := firstString(event.TaskID, anyToString(event.Payload["task_id"]))
	conflictID := anyToString(event.Payload["conflict_id"])
	resolution := anyToString(event.Payload["resolution"])
	reason := anyToString(event.Payload["reason"])
	if _, err := a.ResolveConflict(auth.Principal{ID: client.PrincipalID, Role: "session_approver"}, taskID, conflictID, resolution, reason); err != nil {
		a.sendSystemError(client, event, "conflict_resolution_failed", err.Error())
		return
	}
	a.sendAck(client, event, "processed", true, "")
}

// executeTask 把 Runtime 结果映射成 Stage 5 的 task / review / artifact 事件。
func (a *GatewayApp) executeTask(task store.Task, mentionedAgent string) {
	log.Printf("[Gateway] ========== Starting task execution ==========")
	log.Printf("[Gateway] Task ID: %s", task.TaskID)
	log.Printf("[Gateway] Session ID: %s", task.SessionID)
	log.Printf("[Gateway] Instruction: %s", task.Instruction)
	if mentionedAgent != "" {
		log.Printf("[Gateway] Mentioned Agent: %s", mentionedAgent)
	}

	ctx, cancel := context.WithTimeout(context.Background(), a.taskTimeout)
	handle := &taskExecution{cancel: cancel}
	a.mu.Lock()
	a.running[task.TaskID] = handle
	a.mu.Unlock()
	defer func() {
		a.mu.Lock()
		delete(a.running, task.TaskID)
		a.mu.Unlock()
		cancel()
		log.Printf("[Gateway] ========== Task execution complete ==========")
	}()

	log.Printf("[Gateway] Submitting instruction to Runtime (session=%s)...", task.SessionID)
	submitted, err := a.Runtime.SubmitInstruction(ctx, task.Instruction, mentionedAgent, task.SessionID)
	if err != nil {
		if errors.Is(err, context.Canceled) {
			latest, getErr := a.Store.GetTask(task.TaskID)
			if getErr == nil && latest.Status == "cancelled" {
				return
			}
			a.handleTaskFailure(task, "cancelled", "task_cancelled", "task was cancelled")
			return
		}
		if errors.Is(err, context.DeadlineExceeded) {
			a.handleTaskFailure(task, "timed_out", "task_timeout", "gateway task execution timeout")
			return
		}
		a.handleTaskFailure(task, "failed", "runtime_submit_failed", err.Error())
		return
	}
	task.RuntimeJobID = submitted.RuntimeJobID
	task.UpdatedAt = time.Now().UTC()
	_ = a.Store.UpdateTask(task)
	a.mu.Lock()
	if current, ok := a.running[task.TaskID]; ok {
		current.runtimeJobID = submitted.RuntimeJobID
	}
	a.mu.Unlock()
	log.Printf("[Gateway] Instruction submitted, Runtime Job ID: %s", submitted.RuntimeJobID)
	log.Printf("[Gateway] Waiting for results from Runtime...")

	// 使用 progress-aware 轮询，将中间事件实时转发给前端
	result, err := a.Runtime.WaitForResultWithProgress(ctx, submitted, func(evt runtimeclient.ProgressEvent) {
		agent, progress := mapEventToProgress(evt.Kind)
		task.CurrentAgent = agent
		task.Summary = evt.Kind
		task.UpdatedAt = time.Now().UTC()
		_ = a.Store.UpdateTask(task)


			log.Printf("[Gateway] Progress: %s (agent: %s)", evt.Kind, agent)

			a.persistAndBroadcast(task.SessionID, a.newEvent(
				task.SessionID,
				task.TaskID,
				"",
				"task.updated",
				"event",
				"running",
				protocol.Party{Type: "agent", ID: agent},
				protocol.Party{Type: "session", ID: task.SessionID},
				map[string]any{
					"task_id":  task.TaskID,
					"status":   "running",
					"summary":  evt.Kind,
					"agent":    agent,
					"progress": progress,
				},
			))
		})
	if err != nil {
		if errors.Is(err, runtimeclient.ErrRuntimeCancelled) {
			latest, getErr := a.Store.GetTask(task.TaskID)
			if getErr == nil && latest.Status == "cancelled" {
				return
			}
			a.handleTaskFailure(task, "cancelled", "runtime_task_cancelled", "runtime task was cancelled")
			return
		}
		if errors.Is(err, runtimeclient.ErrPollTimeout) {
			_ = a.Runtime.CancelTask(context.Background(), submitted.RuntimeJobID)
			a.handleTaskFailure(task, "timed_out", "poll_timeout", "gateway poll timeout while waiting for runtime result")
			return
		}
		if errors.Is(err, context.DeadlineExceeded) {
			_ = a.Runtime.CancelTask(context.Background(), submitted.RuntimeJobID)
			a.handleTaskFailure(task, "timed_out", "task_timeout", "gateway task execution timeout")
			return
		}
		if errors.Is(err, context.Canceled) {
			latest, getErr := a.Store.GetTask(task.TaskID)
			if getErr == nil && latest.Status == "cancelled" {
				return
			}
			a.handleTaskFailure(task, "cancelled", "task_cancelled", "task was cancelled")
			return
		}
		a.handleTaskFailure(task, "failed", "runtime_execution_failed", err.Error())
		return
	}

	log.Printf("[Gateway] Received result from Runtime!")
	log.Printf("[Gateway] Runtime Task ID: %s", result.TaskID)
	log.Printf("[Gateway] Review pass: %v, issues count: %d", result.Result.Review.Pass, len(result.Result.Review.Issues))

	task.RuntimeTaskID = result.TaskID
	task.RuntimeTraceID = result.TraceID
	task.CurrentAgent = "review"
	task.Summary = "Review Agent completed"
	task.UpdatedAt = time.Now().UTC()
	_ = a.Store.UpdateTask(task)

	reviewEvent := a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"review.completed",
		"result",
		"success",
		protocol.Party{Type: "agent", ID: "review"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"task_id": task.TaskID,
			"review":  result.Result.Review,
		},
	)
	a.persistAndBroadcast(task.SessionID, reviewEvent)

	diffCard := buildDiffCard(task, result)
	bundleCard := buildBundleCard(task, result)
	reviewCard := buildReviewCard(task, result)

	_ = a.Store.SaveArtifact(diffCard)
	_ = a.Store.SaveArtifact(bundleCard)
	_ = a.Store.SaveArtifact(reviewCard)

	log.Printf("[Gateway] Saving artifacts for task %s", task.TaskID)
	log.Printf("  - Diff card: %s", diffCard.ArtifactID)
	log.Printf("  - Bundle card: %s", bundleCard.ArtifactID)
	log.Printf("  - Review card: %s (decision: %s, score: %d)", reviewCard.ArtifactID, reviewCard.Content["decision"], reviewCard.Content["score"])

	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"artifact.created",
		"result",
		"success",
		protocol.Party{Type: "agent", ID: "artifact"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"artifact_id": diffCard.ArtifactID,
			"card":        diffCard,
		},
	))
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"artifact.created",
		"result",
		"success",
		protocol.Party{Type: "agent", ID: "artifact"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"artifact_id": bundleCard.ArtifactID,
			"card":        bundleCard,
		},
	))
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"artifact.created",
		"result",
		"success",
		protocol.Party{Type: "agent", ID: "review"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"artifact_id": reviewCard.ArtifactID,
			"card":        reviewCard,
		},
	))

	var content string
	if len(result.Result.UsedSkills) > 0 {
		content = fmt.Sprintf("任务已完成。使用技能: %v。Review 结果: `pass=%v`，已生成 diff 与 artifact 卡片。", result.Result.UsedSkills, result.Result.Review.Pass)
	} else {
		content = fmt.Sprintf("任务已完成。Review 结果: `pass=%v`，已生成 diff 与 artifact 卡片。", result.Result.Review.Pass)
	}
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"chat.message",
		"result",
		"success",
		protocol.Party{Type: "agent", ID: "artifact"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"message_id":   newID("msg"),
			"role":         "agent",
			"format":       "markdown",
			"content":      content,
			"stream_chunk": false,
		},
	))

	task.Status = "completed"
	task.CurrentAgent = ""
	task.Summary = "Gateway completed runtime orchestration"
	task.UpdatedAt = time.Now().UTC()
	_ = a.Store.UpdateTask(task)
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		result.TraceID,
		"task.completed",
		"result",
		"success",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"task_id": task.TaskID,
			"status":  "completed",
			"summary": task.Summary,
			"agent":   "artifact",
			"progress": map[string]any{
				"current": 3,
				"total":   3,
			},
			"runtime_task_id": result.TaskID,
			"trace_id":        result.TraceID,
		},
	))
}

func (a *GatewayApp) handleTaskFailure(task store.Task, status string, errorCode string, message string) {
	task.Status = status
	task.Summary = message
	task.CurrentAgent = ""
	task.UpdatedAt = time.Now().UTC()
	_ = a.Store.UpdateTask(task)
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		task.RuntimeTraceID,
		"task.updated",
		"event",
		status,
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"task_id":        task.TaskID,
			"status":         status,
			"summary":        message,
			"runtime_job_id": task.RuntimeJobID,
		},
	))
	a.persistAndBroadcast(task.SessionID, a.newEvent(
		task.SessionID,
		task.TaskID,
		task.RuntimeTraceID,
		"system.error",
		"error",
		"failed",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "session", ID: task.SessionID},
		map[string]any{
			"code":           errorCode,
			"message":        message,
			"runtime_job_id": task.RuntimeJobID,
		},
	))
}

func buildDiffCard(task store.Task, result runtimeclient.RunResult) protocol.ArtifactCard {
	now := protocol.NowISO()
	files := make([]map[string]any, 0)
	coding := result.Result.Coding

	// 现在 coding 已经是 agent_output 本身了
	changes, _ := coding["changes"].([]any)
	exampleDiffs, _ := coding["example_diff"].([]any)

	log.Printf("[Gateway] Building diff card with %d changes", len(changes))

	for idx, item := range changes {
		change, _ := item.(map[string]any)
		diffExcerpt := ""
		var beforeContent, afterContent, unifiedDiff *string
		if idx < len(exampleDiffs) {
			if diffMap, ok := exampleDiffs[idx].(map[string]any); ok {
				diffExcerpt = anyToString(diffMap["diff"])
				// ⭐ 提取新的 diff 字段
				if bc, ok := diffMap["before_content"].(string); ok && bc != "" {
					v := bc
					beforeContent = &v
				}
				if ac, ok := diffMap["after_content"].(string); ok && ac != "" {
					v := ac
					afterContent = &v
				}
				if ud, ok := diffMap["diff"].(string); ok && ud != "" {
					v := ud
					unifiedDiff = &v
				}
			}
		}

		path := anyToString(change["path"])
		fullContent := anyToString(change["content"])

		log.Printf("  - File: %s, action: %s, content size: %d bytes", path, change["action"], len(fullContent))

		fileEntry := map[string]any{
			"path":         path,
			"change_type":  anyToString(change["action"]),
			"diff_excerpt": diffExcerpt,
			"content":      fullContent,
		}
		// ⭐ 添加新的 diff 字段（仅在不为空时）
		if beforeContent != nil {
			fileEntry["before_content"] = *beforeContent
		}
		if afterContent != nil {
			fileEntry["after_content"] = *afterContent
		}
		if unifiedDiff != nil {
			fileEntry["unified_diff"] = *unifiedDiff
		}
		files = append(files, fileEntry)
	}

	return protocol.ArtifactCard{
		SchemaVersion: "1.0",
		CardID:        newID("card"),
		ArtifactID:    newID("artifact"),
		SessionID:     task.SessionID,
		TaskID:        task.TaskID,
		CardType:      "diff",
		Title:         "Runtime Diff",
		Summary:       "Coding Agent 变更摘要",
		Status:        "ready",
		CreatedAt:     now,
		UpdatedAt:     now,
		Producer:      protocol.CardProducer{Type: "gateway", ID: "gateway"},
		Badges:        []string{"diff-ready"},
		Actions: []protocol.ArtifactAction{
			{Action: "open_diff", Label: "Open Diff", Enabled: true, Target: &protocol.ArtifactActionRef{Tab: "diff"}},
		},
		Content: map[string]any{
			"files_changed": len(files),
			"additions":     len(files),
			"deletions":     0,
			"files":         files,
		},
	}
}

func buildBundleCard(task store.Task, result runtimeclient.RunResult) protocol.ArtifactCard {
	now := protocol.NowISO()
	return protocol.ArtifactCard{
		SchemaVersion: "1.0",
		CardID:        newID("card"),
		ArtifactID:    newID("artifact"),
		SessionID:     task.SessionID,
		TaskID:        task.TaskID,
		CardType:      "bundle",
		Title:         "Artifact Bundle",
		Summary:       "Artifact Agent 归档结果",
		Status:        "ready",
		CreatedAt:     now,
		UpdatedAt:     now,
		Producer:      protocol.CardProducer{Type: "artifact-agent", ID: "artifact"},
		Badges:        []string{"artifact-ready"},
		Actions: []protocol.ArtifactAction{
			{
				Action:  "open_file",
				Label:   "Open Artifact",
				Enabled: true,
				Target:  &protocol.ArtifactActionRef{Path: result.Result.Artifact.ArtifactDir, Tab: "files"},
			},
		},
		Content: map[string]any{
			"archive_path": result.Result.Artifact.ArtifactDir,
			"items": []map[string]any{
				{"type": "bundle", "artifact_id": result.TaskID},
			},
		},
	}
}

func buildFileCards(task store.Task, result runtimeclient.RunResult) []protocol.ArtifactCard {
	var cards []protocol.ArtifactCard
	now := protocol.NowISO()
	coding := result.Result.Coding

	// 现在 coding 已经是 agent_output 本身了
	changes, _ := coding["changes"].([]any)

	for _, item := range changes {
		change, _ := item.(map[string]any)
		path := anyToString(change["path"])
		content := anyToString(change["content"])
		mimeType := guessMimeType(path)
		size := len(content)

		fileCard := protocol.ArtifactCard{
			SchemaVersion: "1.0",
			CardID:        newID("card"),
			ArtifactID:    newID("artifact"),
			SessionID:     task.SessionID,
			TaskID:        task.TaskID,
			CardType:      "file",
			Title:         path,
			Summary:       "生成的代码文件",
			Status:        "ready",
			CreatedAt:     now,
			UpdatedAt:     now,
			Producer:      protocol.CardProducer{Type: "gateway", ID: "gateway"},
			Badges:        []string{"file-ready"},
			Actions: []protocol.ArtifactAction{
				{
					Action:  "download",
					Label:   "Download",
					Enabled: true,
					Target:  &protocol.ArtifactActionRef{Path: path},
				},
			},
			Content: map[string]any{
				"path":         path,
				"mime_type":    mimeType,
				"size_bytes":   size,
				"download_url": path,
				"content":      content,
			},
		}
		cards = append(cards, fileCard)
	}

	return cards
}

func buildReviewCard(task store.Task, result runtimeclient.RunResult) protocol.ArtifactCard {
	now := protocol.NowISO()
	review := result.Result.Review

	// ⭐ Stage 9: review skipped → don't create misleading card
	if review.Skipped {
		return protocol.ArtifactCard{
			SchemaVersion: "1.0",
			CardID:        newID("card"),
			ArtifactID:    newID("artifact"),
			SessionID:     task.SessionID,
			TaskID:        task.TaskID,
			CardType:      "review",
			Title:         "代码审查",
			Summary:       "简单任务，已跳过审查",
			Status:        "ready",
			CreatedAt:     now,
			UpdatedAt:     now,
			Producer:      protocol.CardProducer{Type: "review-agent", ID: "review"},
			Badges:        []string{"review-skipped"},
			Content: map[string]any{
				"decision": "skipped",
				"score":    100,
				"issues":   []map[string]any{},
			},
		}
	}

	passed := review.Pass
	issues := review.Issues
	score := review.Score
	if score == 0 {
		score = 100 - len(issues)*20
		if score < 0 {
			score = 0
		}
	}

	reviewIssues := make([]map[string]any, 0)
	for _, issue := range issues {
		issueMap := map[string]any{
			"severity":   "medium",
			"message":    "",
			"paths":      []string{},
		}
		if sev, ok := issue["severity"].(string); ok && sev != "" {
			issueMap["severity"] = sev
		}
		if msg, ok := issue["message"].(string); ok {
			issueMap["message"] = msg
		}
		if path, ok := issue["path"].(string); ok && path != "" {
			issueMap["paths"] = []string{path}
		}
		if typ, ok := issue["type"].(string); ok {
			issueMap["type"] = typ
		}
		if sug, ok := issue["suggestion"].(string); ok {
			issueMap["suggestion"] = sug
		}
		if line, ok := issue["line"].(float64); ok {
			issueMap["line"] = int(line)
		}
		reviewIssues = append(reviewIssues, issueMap)
	}

	decision := map[bool]string{true: "pass", false: "fail"}[passed]

	return protocol.ArtifactCard{
		SchemaVersion: "1.0",
		CardID:        newID("card"),
		ArtifactID:    newID("artifact"),
		SessionID:     task.SessionID,
		TaskID:        task.TaskID,
		CardType:      "review",
		Title:         "代码审查",
		Summary:       fmt.Sprintf("Review: %s (%d issues, score=%d)", decision, len(reviewIssues), score),
		Status:        "ready",
		CreatedAt:     now,
		UpdatedAt:     now,
		Producer:      protocol.CardProducer{Type: "review-agent", ID: "review"},
		Badges:        []string{"review-ready"},
		Actions: []protocol.ArtifactAction{
			{
				Action:  "view_review",
				Label:   "查看审查结果",
				Enabled: true,
				Target:  &protocol.ArtifactActionRef{Tab: "review"},
			},
		},
		Content: map[string]any{
			"decision":   decision,
			"score":      score,
			"issues":     reviewIssues,
			"files_reviewed": review.FilesReviewed,
		},
	}
}

func guessMimeType(path string) string {
	lowerPath := strings.ToLower(path)
	switch {
	case strings.HasSuffix(lowerPath, ".go"):
		return "text/x-go"
	case strings.HasSuffix(lowerPath, ".tsx"), strings.HasSuffix(lowerPath, ".ts"):
		return "text/typescript"
	case strings.HasSuffix(lowerPath, ".jsx"), strings.HasSuffix(lowerPath, ".js"):
		return "application/javascript"
	case strings.HasSuffix(lowerPath, ".py"):
		return "text/x-python"
	case strings.HasSuffix(lowerPath, ".css"):
		return "text/css"
	case strings.HasSuffix(lowerPath, ".html"):
		return "text/html"
	case strings.HasSuffix(lowerPath, ".json"):
		return "application/json"
	case strings.HasSuffix(lowerPath, ".md"):
		return "text/markdown"
	case strings.HasSuffix(lowerPath, ".txt"):
		return "text/plain"
	default:
		return "application/octet-stream"
	}
}

func (a *GatewayApp) persistAndBroadcast(sessionID string, event protocol.WSEvent) {
	persisted, err := a.Store.AppendEvent(sessionID, event)
	if err != nil {
		return
	}
	a.Hub.Broadcast(sessionID, persisted)
}

func (a *GatewayApp) sendAck(client *ws.Client, inReplyTo protocol.WSEvent, mode string, accepted bool, reason string) {
	ack := a.newEvent(
		client.SessionID,
		inReplyTo.TaskID,
		inReplyTo.TraceID,
		"ack",
		"event",
		"success",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "frontend", ID: client.PrincipalID},
		map[string]any{
			"ack_event_id": inReplyTo.EventID,
			"ack_mode":     mode,
			"accepted":     accepted,
			"reason":       reason,
		},
	)
	ack.InReplyTo = inReplyTo.EventID
	a.Hub.Send(client, ack)
}

func (a *GatewayApp) sendSystemError(client *ws.Client, inReplyTo protocol.WSEvent, code, message string) {
	event := a.newEvent(
		client.SessionID,
		inReplyTo.TaskID,
		inReplyTo.TraceID,
		"system.error",
		"error",
		"failed",
		protocol.Party{Type: "gateway", ID: "gateway"},
		protocol.Party{Type: "frontend", ID: client.PrincipalID},
		map[string]any{
			"code":    code,
			"message": message,
		},
	)
	event.InReplyTo = inReplyTo.EventID
	a.Hub.Send(client, event)
}

func (a *GatewayApp) newEvent(sessionID, taskID, traceID, eventType, kind, status string, sender, receiver protocol.Party, payload map[string]any) protocol.WSEvent {
	return protocol.WSEvent{
		SchemaVersion: "1.0",
		EventID:       newID("evt"),
		SessionID:     sessionID,
		TaskID:        taskID,
		TraceID:       traceID,
		Type:          eventType,
		Kind:          kind,
		Timestamp:     protocol.NowISO(),
		Sender:        sender,
		Receiver:      receiver,
		Status:        status,
		Payload:       payload,
	}
}

func newID(prefix string) string {
	return uuid.NewString()
}

func truncate(text string, limit int) string {
	runes := []rune(text)
	if len(runes) <= limit {
		return text
	}
	return string(runes[:limit])
}

func defaultString(value any, fallback string) string {
	if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
		return text
	}
	return fallback
}

func anyToString(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return ""
}

func firstString(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

// mapEventToProgress 把 Stage 6 事件 kind 映射为前端 agent 名称和进度值。
func mapEventToProgress(kind string) (agent string, progress map[string]any) {
	switch kind {
	case "planning.started":
		return "planner", map[string]any{"current": 0, "total": 4}
	case "planning.completed":
		return "planner", map[string]any{"current": 1, "total": 4}
	case "coding.started":
		return "coding", map[string]any{"current": 1, "total": 4}
	case "coding.completed":
		return "coding", map[string]any{"current": 2, "total": 4}
	case "cli.started":
		return "coding", map[string]any{"current": 1, "total": 4, "using": "claude_code"}
	case "builtin.started":
		return "coding", map[string]any{"current": 1, "total": 4, "using": "builtin_llm"}
	case "review.started":
		return "review", map[string]any{"current": 2, "total": 4}
	case "review.completed":
		return "review", map[string]any{"current": 3, "total": 4}
	case "artifact.started":
		return "artifact", map[string]any{"current": 3, "total": 4}
	case "artifact.completed":
		return "artifact", map[string]any{"current": 4, "total": 4}
	case "approval.required":
		return "approval", map[string]any{"current": 3, "total": 4}
	case "task.paused":
		return "approval", map[string]any{"current": 3, "total": 4, "paused": true}
	default:
		return "orchestrator", map[string]any{"current": 0, "total": 4}
	}
}

func getenvDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func getenvDurationDefault(key string, fallback time.Duration) time.Duration {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}
	return parsed
}

func sha256Hex(data []byte) string {
	h := sha256.Sum256(data)
	return hex.EncodeToString(h[:])
}

// ── Agent Definitions ───────────────────────────────────────────

func (a *GatewayApp) CreateAgentDefinition(principal auth.Principal, record store.AgentDefinitionRecord) (store.AgentDefinitionRecord, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	record.ID = "agent_" + uuid.NewString()
	if record.CreatedBy == "" {
		record.CreatedBy = principal.ID
	}
	if record.Visibility == "" {
		record.Visibility = "private"
	}
	if record.PreferredProvider == "" {
		record.PreferredProvider = "claude_code"
	}
	record.CreatedAt = now
	record.UpdatedAt = now
	if err := a.Store.CreateAgentDefinition(record); err != nil {
		return store.AgentDefinitionRecord{}, err
	}
	return record, nil
}

func (a *GatewayApp) GetAgentDefinition(id string) (store.AgentDefinitionRecord, error) {
	return a.Store.GetAgentDefinition(id)
}

func (a *GatewayApp) ListAgentDefinitions(principal auth.Principal) []store.AgentDefinitionRecord {
	return a.Store.ListAgentDefinitions(principal.ID)
}

func (a *GatewayApp) ListPublicAgentDefinitions() []store.AgentDefinitionRecord {
	return a.Store.ListPublicAgentDefinitions()
}

func (a *GatewayApp) UpdateAgentDefinition(principal auth.Principal, record store.AgentDefinitionRecord) (store.AgentDefinitionRecord, error) {
	existing, err := a.Store.GetAgentDefinition(record.ID)
	if err != nil {
		return store.AgentDefinitionRecord{}, err
	}
	if existing.CreatedBy != principal.ID {
		return store.AgentDefinitionRecord{}, errors.New("not allowed to modify this agent definition")
	}
	record.CreatedBy = existing.CreatedBy
	record.CreatedAt = existing.CreatedAt
	record.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	if err := a.Store.UpdateAgentDefinition(record); err != nil {
		return store.AgentDefinitionRecord{}, err
	}
	return record, nil
}

func (a *GatewayApp) DeleteAgentDefinition(principal auth.Principal, id string) error {
	existing, err := a.Store.GetAgentDefinition(id)
	if err != nil {
		return err
	}
	if existing.CreatedBy != principal.ID && existing.CreatedBy != "system" {
		return errors.New("not allowed to delete this agent definition")
	}
	return a.Store.DeleteAgentDefinition(id)
}
