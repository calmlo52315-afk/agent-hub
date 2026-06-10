package store

import (
	"errors"
	"sort"
	"sync"
	"time"

	"agenthub/gateway/internal/protocol"
)

var (
	ErrNotFound         = errors.New("record not found")
	ErrSessionForbidden = errors.New("principal is not a member of this session")
	ErrTicketExpired    = errors.New("ws ticket expired or invalid")
)

// ── Agent Definition ──────────────────────────────────────────

type AgentDefinitionRecord struct {
	ID                string   `json:"id"`
	Name              string   `json:"name"`
	Avatar            string   `json:"avatar"`
	Description       string   `json:"description"`
	SystemPrompt      string   `json:"system_prompt"`
	AllowedSkills     []string `json:"allowed_skills"`
	PreferredProvider string   `json:"preferred_provider"`
	Visibility        string   `json:"visibility"`
	CreatedBy         string   `json:"created_by"`
	CreatedAt         string   `json:"created_at"`
	UpdatedAt         string   `json:"updated_at"`
}

type AgentDefinitionStore interface {
	CreateAgentDefinition(record AgentDefinitionRecord) error
	GetAgentDefinition(id string) (AgentDefinitionRecord, error)
	ListAgentDefinitions(ownerID string) []AgentDefinitionRecord
	ListPublicAgentDefinitions() []AgentDefinitionRecord
	UpdateAgentDefinition(record AgentDefinitionRecord) error
	DeleteAgentDefinition(id string) error
}

// 这些接口定义了 Gateway 依赖的数据边界，后续可以替换为 SQLite / Postgres / Redis。
type AuthStore interface {
	SaveAccessToken(record AccessTokenRecord) error
	GetAccessToken(token string) (AccessTokenRecord, error)
	SaveWSTicket(record WSTicketRecord) error
	ConsumeWSTicket(ticket string) (WSTicketRecord, error)
}

type SessionStore interface {
	CreateSession(session Session) error
	GetSession(sessionID string) (Session, error)
	ListSessions(ownerID string) []Session
	AddSessionMember(sessionID, principalID string) error
	IsSessionMember(sessionID, principalID string) bool
	UpdateSessionTimestamp(sessionID string, updatedAt time.Time) error
	UpdateSessionSeq(sessionID string, seq int64) error
	UpdateSession(session Session) error
	DeleteSession(sessionID string) error
}

type EventStore interface {
	AppendEvent(sessionID string, event protocol.WSEvent) (protocol.WSEvent, error)
	ListEvents(sessionID string, afterSeq int64, limit int) []protocol.WSEvent
}

type TaskStore interface {
	CreateTask(task Task) error
	GetTask(taskID string) (Task, error)
	UpdateTask(task Task) error
	ListSessionTasks(sessionID string) []Task
}

type ArtifactStore interface {
	SaveArtifact(card protocol.ArtifactCard) error
	GetArtifact(artifactID string) (protocol.ArtifactCard, error)
	ListSessionArtifacts(sessionID string) []protocol.ArtifactCard
}

type ApprovalStore interface {
	SaveApproval(record ApprovalRecord) error
	GetApproval(approvalID string) (ApprovalRecord, error)
	UpdateApproval(record ApprovalRecord) error
}

// WorkspaceFileIndex 是文件元信息的索引记录，不存储文件内容。
// 内容始终从磁盘（Runtime workspace）按需读取。
type WorkspaceFileIndex struct {
	SessionID  string    `json:"session_id"`
	FilePath   string    `json:"file_path"`
	SizeBytes  int64     `json:"size_bytes"`
	Sha256Hash string    `json:"sha256_hash"`
	UpdatedAt  time.Time `json:"updated_at"`
}

// WorkspaceFileIndexStore 管理 workspace 文件索引（元信息），不存内容。
// 设计意图：避免将整个 workspace 加载到数据库；只存索引用于搜索/对比/最近修改。
type WorkspaceFileIndexStore interface {
	UpsertWorkspaceFileIndex(sessionID, filePath string, sizeBytes int64, sha256Hash string) error
	GetWorkspaceFileIndex(sessionID, filePath string) (WorkspaceFileIndex, error)
	ListWorkspaceFileIndexes(sessionID string) ([]WorkspaceFileIndex, error)
	DeleteWorkspaceFileIndex(sessionID, filePath string) error
	DeleteWorkspaceFileIndexes(sessionID string) error
}

// Deprecated: SessionFileStore — 向后兼容。新代码使用 WorkspaceFileIndexStore。
type SessionFileStore interface {
	SaveSessionFile(sessionID, filePath, content string) error
	GetSessionFile(sessionID, filePath string) (string, error)
	ListSessionFiles(sessionID string) (map[string]string, error)
	DeleteSessionFile(sessionID, filePath string) error
}

type AccessTokenRecord struct {
	Token       string
	PrincipalID string
	Role        string
	ExpiresAt   time.Time
}

type WSTicketRecord struct {
	Ticket      string
	SessionID   string
	PrincipalID string
	ExpiresAt   time.Time
	Used        bool
}

type Session struct {
	SessionID     string    `json:"session_id"`
	Title         string    `json:"title"`
	Mode          string    `json:"mode"`
	OwnerID       string    `json:"owner_id"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
	LastEventSeq  int64     `json:"last_event_seq"`
	WorkspaceRoot string    `json:"workspace_root,omitempty"`
	WorkspaceType string    `json:"workspace_type,omitempty"`
}

type Task struct {
	TaskID             string    `json:"task_id"`
	SessionID          string    `json:"session_id"`
	Title              string    `json:"title"`
	Instruction        string    `json:"instruction"`
	Status             string    `json:"status"`
	Summary            string    `json:"summary"`
	AgentFlow          []string  `json:"agent_flow"`
	CurrentAgent       string    `json:"current_agent"`
	RetryCount         int       `json:"retry_count"`
	RetryLimit         int       `json:"retry_limit"`
	WaitingForApproval bool      `json:"waiting_for_approval"`
	ApprovalID         string    `json:"approval_id,omitempty"`
	RuntimeJobID       string    `json:"runtime_job_id,omitempty"`
	RuntimeTaskID      string    `json:"runtime_task_id,omitempty"`
	RuntimeTraceID     string    `json:"runtime_trace_id,omitempty"`
	MentionedAgent     string    `json:"mentioned_agent,omitempty"`
	ReviewAgent        string    `json:"review_agent,omitempty"`
	UpdatedAt          time.Time `json:"updated_at"`
}

type ApprovalRecord struct {
	ApprovalID string    `json:"approval_id"`
	SessionID  string    `json:"session_id"`
	TaskID     string    `json:"task_id"`
	Approver   string    `json:"approver"`
	Decision   string    `json:"decision"`
	Reason     string    `json:"reason"`
	Status     string    `json:"status"`
	Timestamp  time.Time `json:"timestamp"`
}

// MemoryStore 是当前 MVP 的默认实现，尽量保持简单并可被后端持久化替换。
type MemoryStore struct {
	mu sync.RWMutex

	accessTokens     map[string]AccessTokenRecord
	wsTickets        map[string]WSTicketRecord
	sessions         map[string]Session
	sessionUsers     map[string]map[string]struct{}
	sessionEvents    map[string][]protocol.WSEvent
	tasks            map[string]Task
	sessionTasks     map[string][]string
	artifacts        map[string]protocol.ArtifactCard
	sessionArtifacts map[string][]string
	approvals        map[string]ApprovalRecord
	agentDefs        map[string]AgentDefinitionRecord
	sessionFiles     map[string]map[string]string
	workspaceFileIndexes map[string]map[string]WorkspaceFileIndex
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		accessTokens:          make(map[string]AccessTokenRecord),
		wsTickets:             make(map[string]WSTicketRecord),
		sessions:              make(map[string]Session),
		sessionUsers:          make(map[string]map[string]struct{}),
		sessionEvents:         make(map[string][]protocol.WSEvent),
		tasks:                 make(map[string]Task),
		sessionTasks:          make(map[string][]string),
		artifacts:             make(map[string]protocol.ArtifactCard),
		sessionArtifacts:      make(map[string][]string),
		approvals:             make(map[string]ApprovalRecord),
		sessionFiles:          make(map[string]map[string]string),
		workspaceFileIndexes:  make(map[string]map[string]WorkspaceFileIndex),
	}
}

func (s *MemoryStore) SaveAccessToken(record AccessTokenRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.accessTokens[record.Token] = record
	return nil
}

func (s *MemoryStore) GetAccessToken(token string) (AccessTokenRecord, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	record, ok := s.accessTokens[token]
	if !ok || (!record.ExpiresAt.IsZero() && time.Now().After(record.ExpiresAt)) {
		return AccessTokenRecord{}, ErrNotFound
	}
	return record, nil
}

func (s *MemoryStore) SaveWSTicket(record WSTicketRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.wsTickets[record.Ticket] = record
	return nil
}

func (s *MemoryStore) ConsumeWSTicket(ticket string) (WSTicketRecord, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.wsTickets[ticket]
	if !ok || record.Used || time.Now().After(record.ExpiresAt) {
		return WSTicketRecord{}, ErrTicketExpired
	}
	record.Used = true
	s.wsTickets[ticket] = record
	return record, nil
}

func (s *MemoryStore) CreateSession(session Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.sessions[session.SessionID] = session
	if _, ok := s.sessionUsers[session.SessionID]; !ok {
		s.sessionUsers[session.SessionID] = make(map[string]struct{})
	}
	s.sessionUsers[session.SessionID][session.OwnerID] = struct{}{}
	return nil
}

func (s *MemoryStore) GetSession(sessionID string) (Session, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return Session{}, ErrNotFound
	}
	return session, nil
}

func (s *MemoryStore) ListSessions(ownerID string) []Session {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]Session, 0)
	for _, session := range s.sessions {
		if _, ok := s.sessionUsers[session.SessionID][ownerID]; ok {
			items = append(items, session)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	return items
}

func (s *MemoryStore) AddSessionMember(sessionID, principalID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.sessions[sessionID]; !ok {
		return ErrNotFound
	}
	if _, ok := s.sessionUsers[sessionID]; !ok {
		s.sessionUsers[sessionID] = make(map[string]struct{})
	}
	s.sessionUsers[sessionID][principalID] = struct{}{}
	return nil
}

func (s *MemoryStore) IsSessionMember(sessionID, principalID string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	_, ok := s.sessionUsers[sessionID][principalID]
	return ok
}

func (s *MemoryStore) UpdateSessionTimestamp(sessionID string, updatedAt time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return ErrNotFound
	}
	session.UpdatedAt = updatedAt
	s.sessions[sessionID] = session
	return nil
}

func (s *MemoryStore) UpdateSessionSeq(sessionID string, seq int64) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return ErrNotFound
	}
	session.LastEventSeq = seq
	session.UpdatedAt = time.Now().UTC()
	s.sessions[sessionID] = session
	return nil
}

func (s *MemoryStore) UpdateSession(session Session) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.sessions[session.SessionID]; !ok {
		return ErrNotFound
	}
	s.sessions[session.SessionID] = session
	return nil
}

func (s *MemoryStore) AppendEvent(sessionID string, event protocol.WSEvent) (protocol.WSEvent, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return protocol.WSEvent{}, ErrNotFound
	}
	event.Seq = session.LastEventSeq + 1
	session.LastEventSeq = event.Seq
	session.UpdatedAt = time.Now().UTC()
	s.sessions[sessionID] = session
	s.sessionEvents[sessionID] = append(s.sessionEvents[sessionID], event)
	return event, nil
}

func (s *MemoryStore) ListEvents(sessionID string, afterSeq int64, limit int) []protocol.WSEvent {
	s.mu.RLock()
	defer s.mu.RUnlock()
	events := s.sessionEvents[sessionID]
	items := make([]protocol.WSEvent, 0)
	for _, event := range events {
		if event.Seq > afterSeq {
			items = append(items, event)
			if limit > 0 && len(items) >= limit {
				break
			}
		}
	}
	return items
}

func (s *MemoryStore) CreateTask(task Task) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.tasks[task.TaskID] = task
	s.sessionTasks[task.SessionID] = append(s.sessionTasks[task.SessionID], task.TaskID)
	return nil
}

func (s *MemoryStore) GetTask(taskID string) (Task, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	task, ok := s.tasks[taskID]
	if !ok {
		return Task{}, ErrNotFound
	}
	return task, nil
}

func (s *MemoryStore) UpdateTask(task Task) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.tasks[task.TaskID]; !ok {
		return ErrNotFound
	}
	s.tasks[task.TaskID] = task
	return nil
}

func (s *MemoryStore) ListSessionTasks(sessionID string) []Task {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]Task, 0, len(s.sessionTasks[sessionID]))
	for _, taskID := range s.sessionTasks[sessionID] {
		items = append(items, s.tasks[taskID])
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt.After(items[j].UpdatedAt)
	})
	return items
}

func (s *MemoryStore) SaveArtifact(card protocol.ArtifactCard) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.artifacts[card.ArtifactID] = card
	s.sessionArtifacts[card.SessionID] = appendIfMissing(s.sessionArtifacts[card.SessionID], card.ArtifactID)
	return nil
}

func (s *MemoryStore) GetArtifact(artifactID string) (protocol.ArtifactCard, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	card, ok := s.artifacts[artifactID]
	if !ok {
		return protocol.ArtifactCard{}, ErrNotFound
	}
	return card, nil
}

func (s *MemoryStore) ListSessionArtifacts(sessionID string) []protocol.ArtifactCard {
	s.mu.RLock()
	defer s.mu.RUnlock()
	ids := s.sessionArtifacts[sessionID]
	items := make([]protocol.ArtifactCard, 0, len(ids))
	for _, artifactID := range ids {
		items = append(items, s.artifacts[artifactID])
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt > items[j].UpdatedAt
	})
	return items
}

func (s *MemoryStore) SaveApproval(record ApprovalRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.approvals[record.ApprovalID] = record
	return nil
}

func (s *MemoryStore) GetApproval(approvalID string) (ApprovalRecord, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	record, ok := s.approvals[approvalID]
	if !ok {
		return ApprovalRecord{}, ErrNotFound
	}
	return record, nil
}

func (s *MemoryStore) UpdateApproval(record ApprovalRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.approvals[record.ApprovalID]; !ok {
		return ErrNotFound
	}
	s.approvals[record.ApprovalID] = record
	return nil
}

func (s *MemoryStore) DeleteSession(sessionID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	delete(s.sessions, sessionID)
	delete(s.sessionUsers, sessionID)
	delete(s.sessionEvents, sessionID)

	if taskIDs, ok := s.sessionTasks[sessionID]; ok {
		for _, taskID := range taskIDs {
			delete(s.tasks, taskID)
		}
	}
	delete(s.sessionTasks, sessionID)

	if artifactIDs, ok := s.sessionArtifacts[sessionID]; ok {
		for _, artifactID := range artifactIDs {
			delete(s.artifacts, artifactID)
		}
	}
	delete(s.sessionArtifacts, sessionID)

	return nil
}

// ── Workspace File Index Store (MemoryStore) ────────────────────────

var _ WorkspaceFileIndexStore = (*MemoryStore)(nil)

func (s *MemoryStore) UpsertWorkspaceFileIndex(sessionID, filePath string, sizeBytes int64, sha256Hash string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.workspaceFileIndexes == nil {
		s.workspaceFileIndexes = make(map[string]map[string]WorkspaceFileIndex)
	}
	if s.workspaceFileIndexes[sessionID] == nil {
		s.workspaceFileIndexes[sessionID] = make(map[string]WorkspaceFileIndex)
	}
	s.workspaceFileIndexes[sessionID][filePath] = WorkspaceFileIndex{
		SessionID:  sessionID,
		FilePath:   filePath,
		SizeBytes:  sizeBytes,
		Sha256Hash: sha256Hash,
		UpdatedAt:  time.Now().UTC(),
	}
	return nil
}

func (s *MemoryStore) GetWorkspaceFileIndex(sessionID, filePath string) (WorkspaceFileIndex, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.workspaceFileIndexes == nil || s.workspaceFileIndexes[sessionID] == nil {
		return WorkspaceFileIndex{}, ErrNotFound
	}
	idx, ok := s.workspaceFileIndexes[sessionID][filePath]
	if !ok {
		return WorkspaceFileIndex{}, ErrNotFound
	}
	return idx, nil
}

func (s *MemoryStore) ListWorkspaceFileIndexes(sessionID string) ([]WorkspaceFileIndex, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.workspaceFileIndexes == nil || s.workspaceFileIndexes[sessionID] == nil {
		return nil, nil
	}
	result := make([]WorkspaceFileIndex, 0, len(s.workspaceFileIndexes[sessionID]))
	for _, idx := range s.workspaceFileIndexes[sessionID] {
		result = append(result, idx)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].FilePath < result[j].FilePath })
	return result, nil
}

func (s *MemoryStore) DeleteWorkspaceFileIndex(sessionID, filePath string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.workspaceFileIndexes == nil || s.workspaceFileIndexes[sessionID] == nil {
		return nil
	}
	delete(s.workspaceFileIndexes[sessionID], filePath)
	return nil
}

func (s *MemoryStore) DeleteWorkspaceFileIndexes(sessionID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.workspaceFileIndexes, sessionID)
	return nil
}

func appendIfMissing(items []string, value string) []string {
	for _, item := range items {
		if item == value {
			return items
		}
	}
	return append(items, value)
}

// ── Agent Definition (MemoryStore) ─────────────────────────────

var _ AgentDefinitionStore = (*MemoryStore)(nil)

func (s *MemoryStore) CreateAgentDefinition(record AgentDefinitionRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.agentDefs == nil {
		s.agentDefs = make(map[string]AgentDefinitionRecord)
	}
	if _, exists := s.agentDefs[record.ID]; exists {
		return errors.New("agent definition already exists")
	}
	s.agentDefs[record.ID] = record
	return nil
}

func (s *MemoryStore) GetAgentDefinition(id string) (AgentDefinitionRecord, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	rec, ok := s.agentDefs[id]
	if !ok {
		return AgentDefinitionRecord{}, ErrNotFound
	}
	return rec, nil
}

func (s *MemoryStore) ListAgentDefinitions(ownerID string) []AgentDefinitionRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []AgentDefinitionRecord
	for _, rec := range s.agentDefs {
		if rec.CreatedBy == ownerID {
			result = append(result, rec)
		}
	}
	return result
}

func (s *MemoryStore) ListPublicAgentDefinitions() []AgentDefinitionRecord {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var result []AgentDefinitionRecord
	for _, rec := range s.agentDefs {
		if rec.Visibility == "public" {
			result = append(result, rec)
		}
	}
	return result
}

func (s *MemoryStore) UpdateAgentDefinition(record AgentDefinitionRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.agentDefs == nil {
		s.agentDefs = make(map[string]AgentDefinitionRecord)
	}
	if _, exists := s.agentDefs[record.ID]; !exists {
		return ErrNotFound
	}
	s.agentDefs[record.ID] = record
	return nil
}

func (s *MemoryStore) DeleteAgentDefinition(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.agentDefs[id]; !exists {
		return ErrNotFound
	}
	delete(s.agentDefs, id)
	return nil
}

// ── Session File Store (MemoryStore) ─────────────────────────────

var _ SessionFileStore = (*MemoryStore)(nil)

func (s *MemoryStore) SaveSessionFile(sessionID, filePath, content string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.sessionFiles == nil {
		s.sessionFiles = make(map[string]map[string]string)
	}
	if s.sessionFiles[sessionID] == nil {
		s.sessionFiles[sessionID] = make(map[string]string)
	}
	s.sessionFiles[sessionID][filePath] = content
	return nil
}

func (s *MemoryStore) GetSessionFile(sessionID, filePath string) (string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.sessionFiles == nil || s.sessionFiles[sessionID] == nil {
		return "", ErrNotFound
	}
	content, ok := s.sessionFiles[sessionID][filePath]
	if !ok {
		return "", ErrNotFound
	}
	return content, nil
}

func (s *MemoryStore) ListSessionFiles(sessionID string) (map[string]string, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if s.sessionFiles == nil || s.sessionFiles[sessionID] == nil {
		return make(map[string]string), nil
	}
	// Return a copy to avoid external modification
	result := make(map[string]string)
	for k, v := range s.sessionFiles[sessionID] {
		result[k] = v
	}
	return result, nil
}

func (s *MemoryStore) DeleteSessionFile(sessionID, filePath string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.sessionFiles == nil || s.sessionFiles[sessionID] == nil {
		return nil
	}
	delete(s.sessionFiles[sessionID], filePath)
	return nil
}
