package store

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"

	"agenthub/gateway/internal/protocol"

	_ "modernc.org/sqlite"
)

// SQLiteStore 用于把 Gateway 会话、事件与任务状态持久化到本地 SQLite。
type SQLiteStore struct {
	db *sql.DB
}

func NewSQLiteStore(dbPath string) (*SQLiteStore, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return nil, fmt.Errorf("create sqlite directory: %w", err)
	}
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	store := &SQLiteStore{db: db}
	if err := store.initSchema(); err != nil {
		_ = db.Close()
		return nil, err
	}
	return store, nil
}

func (s *SQLiteStore) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *SQLiteStore) initSchema() error {
	statements := []string{
		`CREATE TABLE IF NOT EXISTS access_tokens (
			token TEXT PRIMARY KEY,
			principal_id TEXT NOT NULL,
			role TEXT NOT NULL,
			expires_at TEXT NOT NULL
		);`,
		`CREATE TABLE IF NOT EXISTS ws_tickets (
			ticket TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			principal_id TEXT NOT NULL,
			expires_at TEXT NOT NULL,
			used INTEGER NOT NULL DEFAULT 0
		);`,
		`CREATE TABLE IF NOT EXISTS sessions (
			session_id TEXT PRIMARY KEY,
			title TEXT NOT NULL,
			mode TEXT NOT NULL,
			owner_id TEXT NOT NULL,
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL,
			last_event_seq INTEGER NOT NULL DEFAULT 0,
			workspace_root TEXT NOT NULL DEFAULT '',
			workspace_type TEXT NOT NULL DEFAULT ''
		);`,
		`CREATE TABLE IF NOT EXISTS session_file_contents (
			session_id TEXT NOT NULL,
			file_path TEXT NOT NULL,
			file_content TEXT NOT NULL,
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL,
			PRIMARY KEY (session_id, file_path)
		);`,
		`CREATE TABLE IF NOT EXISTS session_members (
			session_id TEXT NOT NULL,
			principal_id TEXT NOT NULL,
			PRIMARY KEY (session_id, principal_id)
		);`,
		`CREATE TABLE IF NOT EXISTS session_events (
			session_id TEXT NOT NULL,
			seq INTEGER NOT NULL,
			event_json TEXT NOT NULL,
			created_at TEXT NOT NULL,
			PRIMARY KEY (session_id, seq)
		);`,
		`CREATE TABLE IF NOT EXISTS tasks (
			task_id TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			title TEXT NOT NULL,
			instruction TEXT NOT NULL,
			status TEXT NOT NULL,
			summary TEXT NOT NULL,
			agent_flow_json TEXT NOT NULL,
			current_agent TEXT NOT NULL,
			retry_count INTEGER NOT NULL,
			retry_limit INTEGER NOT NULL,
			waiting_for_approval INTEGER NOT NULL,
			approval_id TEXT NOT NULL,
			runtime_job_id TEXT NOT NULL,
			runtime_task_id TEXT NOT NULL,
			runtime_trace_id TEXT NOT NULL,
			updated_at TEXT NOT NULL
		);`,
		`CREATE TABLE IF NOT EXISTS artifacts (
			artifact_id TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			updated_at TEXT NOT NULL,
			card_json TEXT NOT NULL
		);`,
		`CREATE TABLE IF NOT EXISTS approvals (
			approval_id TEXT PRIMARY KEY,
			session_id TEXT NOT NULL,
			task_id TEXT NOT NULL,
			approver TEXT NOT NULL,
			decision TEXT NOT NULL,
			reason TEXT NOT NULL,
			status TEXT NOT NULL,
			timestamp TEXT NOT NULL
		);`,
		`CREATE TABLE IF NOT EXISTS agent_definitions (
			id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			avatar TEXT NOT NULL DEFAULT '',
			description TEXT NOT NULL DEFAULT '',
			system_prompt TEXT NOT NULL,
			allowed_skills_json TEXT NOT NULL DEFAULT '[]',
			preferred_provider TEXT NOT NULL DEFAULT 'claude_code',
			visibility TEXT NOT NULL DEFAULT 'private',
			created_by TEXT NOT NULL,
			created_at TEXT NOT NULL,
			updated_at TEXT NOT NULL
		);`,
	}

	for _, statement := range statements {
		if _, err := s.db.Exec(statement); err != nil {
			return fmt.Errorf("init sqlite schema: %w", err)
		}
	}
	if err := s.migrateSchema(); err != nil {
		return fmt.Errorf("migrate sqlite schema: %w", err)
	}
	return nil
}

func (s *SQLiteStore) migrateSchema() error {
	taskColumns, err := s.tableColumns("tasks")
	if err != nil {
		return err
	}
	requiredTaskColumns := map[string]string{
		"runtime_job_id":   "ALTER TABLE tasks ADD COLUMN runtime_job_id TEXT NOT NULL DEFAULT ''",
		"runtime_task_id":  "ALTER TABLE tasks ADD COLUMN runtime_task_id TEXT NOT NULL DEFAULT ''",
		"runtime_trace_id": "ALTER TABLE tasks ADD COLUMN runtime_trace_id TEXT NOT NULL DEFAULT ''",
	}
	for columnName, statement := range requiredTaskColumns {
		if taskColumns[columnName] {
			continue
		}
		if _, err := s.db.Exec(statement); err != nil {
			return fmt.Errorf("add tasks.%s: %w", columnName, err)
		}
	}

	sessionColumns, err := s.tableColumns("sessions")
	if err != nil {
		return err
	}
	requiredSessionColumns := map[string]string{
		"workspace_root": "ALTER TABLE sessions ADD COLUMN workspace_root TEXT NOT NULL DEFAULT ''",
		"workspace_type": "ALTER TABLE sessions ADD COLUMN workspace_type TEXT NOT NULL DEFAULT ''",
	}
	for columnName, statement := range requiredSessionColumns {
		if sessionColumns[columnName] {
			continue
		}
		if _, err := s.db.Exec(statement); err != nil {
			return fmt.Errorf("add sessions.%s: %w", columnName, err)
		}
	}

	// workspace_files 表（如果不存在则创建）
	if _, err := s.db.Exec(`CREATE TABLE IF NOT EXISTS workspace_files (
		session_id TEXT NOT NULL,
		file_path TEXT NOT NULL,
		size_bytes INTEGER NOT NULL DEFAULT 0,
		sha256_hash TEXT NOT NULL DEFAULT '',
		updated_at TEXT NOT NULL,
		PRIMARY KEY (session_id, file_path)
	)`); err != nil {
		return fmt.Errorf("migrate workspace_files: %w", err)
	}

	return nil
}

func (s *SQLiteStore) tableColumns(tableName string) (map[string]bool, error) {
	rows, err := s.db.Query(fmt.Sprintf("PRAGMA table_info(%s)", tableName))
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns := make(map[string]bool)
	for rows.Next() {
		var (
			cid        int
			name       string
			columnType string
			notNull    int
			defaultVal sql.NullString
			pk         int
		)
		if err := rows.Scan(&cid, &name, &columnType, &notNull, &defaultVal, &pk); err != nil {
			return nil, err
		}
		columns[name] = true
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return columns, nil
}

func (s *SQLiteStore) SaveAccessToken(record AccessTokenRecord) error {
	_, err := s.db.Exec(
		`INSERT OR REPLACE INTO access_tokens (token, principal_id, role, expires_at) VALUES (?, ?, ?, ?)`,
		record.Token,
		record.PrincipalID,
		record.Role,
		record.ExpiresAt.UTC().Format(time.RFC3339Nano),
	)
	return err
}

func (s *SQLiteStore) GetAccessToken(token string) (AccessTokenRecord, error) {
	row := s.db.QueryRow(`SELECT token, principal_id, role, expires_at FROM access_tokens WHERE token = ?`, token)
	var record AccessTokenRecord
	var expiresAt string
	if err := row.Scan(&record.Token, &record.PrincipalID, &record.Role, &expiresAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return AccessTokenRecord{}, ErrNotFound
		}
		return AccessTokenRecord{}, err
	}
	record.ExpiresAt = mustParseTime(expiresAt)
	if !record.ExpiresAt.IsZero() && time.Now().After(record.ExpiresAt) {
		return AccessTokenRecord{}, ErrNotFound
	}
	return record, nil
}

func (s *SQLiteStore) SaveWSTicket(record WSTicketRecord) error {
	_, err := s.db.Exec(
		`INSERT OR REPLACE INTO ws_tickets (ticket, session_id, principal_id, expires_at, used) VALUES (?, ?, ?, ?, ?)`,
		record.Ticket,
		record.SessionID,
		record.PrincipalID,
		record.ExpiresAt.UTC().Format(time.RFC3339Nano),
		boolToInt(record.Used),
	)
	return err
}

func (s *SQLiteStore) ConsumeWSTicket(ticket string) (WSTicketRecord, error) {
	tx, err := s.db.Begin()
	if err != nil {
		return WSTicketRecord{}, err
	}
	defer func() { _ = tx.Rollback() }()

	row := tx.QueryRow(`SELECT ticket, session_id, principal_id, expires_at, used FROM ws_tickets WHERE ticket = ?`, ticket)
	var record WSTicketRecord
	var expiresAt string
	var used int
	if err := row.Scan(&record.Ticket, &record.SessionID, &record.PrincipalID, &expiresAt, &used); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return WSTicketRecord{}, ErrTicketExpired
		}
		return WSTicketRecord{}, err
	}
	record.ExpiresAt = mustParseTime(expiresAt)
	record.Used = used == 1
	if record.Used || time.Now().After(record.ExpiresAt) {
		return WSTicketRecord{}, ErrTicketExpired
	}
	if _, err := tx.Exec(`UPDATE ws_tickets SET used = 1 WHERE ticket = ?`, ticket); err != nil {
		return WSTicketRecord{}, err
	}
	if err := tx.Commit(); err != nil {
		return WSTicketRecord{}, err
	}
	record.Used = true
	return record, nil
}

func (s *SQLiteStore) CreateSession(session Session) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.Exec(
		`INSERT INTO sessions (session_id, title, mode, owner_id, created_at, updated_at, last_event_seq, workspace_root, workspace_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		session.SessionID,
		session.Title,
		session.Mode,
		session.OwnerID,
		session.CreatedAt.UTC().Format(time.RFC3339Nano),
		session.UpdatedAt.UTC().Format(time.RFC3339Nano),
		session.LastEventSeq,
		session.WorkspaceRoot,
		session.WorkspaceType,
	); err != nil {
		return err
	}
	if _, err := tx.Exec(`INSERT OR IGNORE INTO session_members (session_id, principal_id) VALUES (?, ?)`, session.SessionID, session.OwnerID); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *SQLiteStore) GetSession(sessionID string) (Session, error) {
	row := s.db.QueryRow(`SELECT session_id, title, mode, owner_id, created_at, updated_at, last_event_seq, workspace_root, workspace_type FROM sessions WHERE session_id = ?`, sessionID)
	var session Session
	var createdAt, updatedAt string
	if err := row.Scan(&session.SessionID, &session.Title, &session.Mode, &session.OwnerID, &createdAt, &updatedAt, &session.LastEventSeq, &session.WorkspaceRoot, &session.WorkspaceType); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Session{}, ErrNotFound
		}
		return Session{}, err
	}
	session.CreatedAt = mustParseTime(createdAt)
	session.UpdatedAt = mustParseTime(updatedAt)
	return session, nil
}

func (s *SQLiteStore) ListSessions(ownerID string) []Session {
	rows, err := s.db.Query(
		`SELECT s.session_id, s.title, s.mode, s.owner_id, s.created_at, s.updated_at, s.last_event_seq, s.workspace_root, s.workspace_type
		 FROM sessions s
		 JOIN session_members sm ON sm.session_id = s.session_id
		 WHERE sm.principal_id = ?
		 ORDER BY s.updated_at DESC`,
		ownerID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()

	items := make([]Session, 0)
	for rows.Next() {
		var session Session
		var createdAt, updatedAt string
		if err := rows.Scan(&session.SessionID, &session.Title, &session.Mode, &session.OwnerID, &createdAt, &updatedAt, &session.LastEventSeq, &session.WorkspaceRoot, &session.WorkspaceType); err != nil {
			continue
		}
		session.CreatedAt = mustParseTime(createdAt)
		session.UpdatedAt = mustParseTime(updatedAt)
		items = append(items, session)
	}
	return items
}

func (s *SQLiteStore) AddSessionMember(sessionID, principalID string) error {
	if _, err := s.GetSession(sessionID); err != nil {
		return err
	}
	_, err := s.db.Exec(`INSERT OR IGNORE INTO session_members (session_id, principal_id) VALUES (?, ?)`, sessionID, principalID)
	return err
}

func (s *SQLiteStore) IsSessionMember(sessionID, principalID string) bool {
	row := s.db.QueryRow(`SELECT 1 FROM session_members WHERE session_id = ? AND principal_id = ? LIMIT 1`, sessionID, principalID)
	var exists int
	return row.Scan(&exists) == nil
}

func (s *SQLiteStore) UpdateSessionTimestamp(sessionID string, updatedAt time.Time) error {
	result, err := s.db.Exec(`UPDATE sessions SET updated_at = ? WHERE session_id = ?`, updatedAt.UTC().Format(time.RFC3339Nano), sessionID)
	if err != nil {
		return err
	}
	if affected, _ := result.RowsAffected(); affected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SQLiteStore) UpdateSessionSeq(sessionID string, seq int64) error {
	result, err := s.db.Exec(`UPDATE sessions SET last_event_seq = ?, updated_at = ? WHERE session_id = ?`, seq, time.Now().UTC().Format(time.RFC3339Nano), sessionID)
	if err != nil {
		return err
	}
	if affected, _ := result.RowsAffected(); affected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SQLiteStore) UpdateSession(session Session) error {
	result, err := s.db.Exec(
		`UPDATE sessions 
		 SET title = ?, mode = ?, updated_at = ?, workspace_root = ?, workspace_type = ?
		 WHERE session_id = ?`,
		session.Title,
		session.Mode,
		time.Now().UTC().Format(time.RFC3339Nano),
		session.WorkspaceRoot,
		session.WorkspaceType,
		session.SessionID,
	)
	if err != nil {
		return err
	}
	if affected, _ := result.RowsAffected(); affected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SQLiteStore) DeleteSession(sessionID string) error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback() }()

	// 删除相关数据
	if _, err := tx.Exec(`DELETE FROM session_events WHERE session_id = ?`, sessionID); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM tasks WHERE session_id = ?`, sessionID); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM artifacts WHERE session_id = ?`, sessionID); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM session_members WHERE session_id = ?`, sessionID); err != nil {
		return err
	}
	if _, err := tx.Exec(`DELETE FROM sessions WHERE session_id = ?`, sessionID); err != nil {
		return err
	}

	return tx.Commit()
}

func (s *SQLiteStore) AppendEvent(sessionID string, event protocol.WSEvent) (protocol.WSEvent, error) {
	tx, err := s.db.Begin()
	if err != nil {
		return protocol.WSEvent{}, err
	}
	defer func() { _ = tx.Rollback() }()

	var currentSeq int64
	if scanErr := tx.QueryRow(`SELECT last_event_seq FROM sessions WHERE session_id = ?`, sessionID).Scan(&currentSeq); scanErr != nil {
		if errors.Is(scanErr, sql.ErrNoRows) {
			return protocol.WSEvent{}, ErrNotFound
		}
		return protocol.WSEvent{}, scanErr
	}
	event.Seq = currentSeq + 1
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return protocol.WSEvent{}, err
	}
	if _, err := tx.Exec(
		`INSERT INTO session_events (session_id, seq, event_json, created_at) VALUES (?, ?, ?, ?)`,
		sessionID,
		event.Seq,
		string(eventJSON),
		time.Now().UTC().Format(time.RFC3339Nano),
	); err != nil {
		return protocol.WSEvent{}, err
	}
	if _, err := tx.Exec(
		`UPDATE sessions SET last_event_seq = ?, updated_at = ? WHERE session_id = ?`,
		event.Seq,
		time.Now().UTC().Format(time.RFC3339Nano),
		sessionID,
	); err != nil {
		return protocol.WSEvent{}, err
	}
	if err := tx.Commit(); err != nil {
		return protocol.WSEvent{}, err
	}
	return event, nil
}

func (s *SQLiteStore) ListEvents(sessionID string, afterSeq int64, limit int) []protocol.WSEvent {
	query := `SELECT event_json FROM session_events WHERE session_id = ? AND seq > ? ORDER BY seq ASC`
	args := []any{sessionID, afterSeq}
	if limit > 0 {
		query += ` LIMIT ?`
		args = append(args, limit)
	}
	rows, err := s.db.Query(query, args...)
	if err != nil {
		return nil
	}
	defer rows.Close()
	items := make([]protocol.WSEvent, 0)
	for rows.Next() {
		var raw string
		if err := rows.Scan(&raw); err != nil {
			continue
		}
		var event protocol.WSEvent
		if err := json.Unmarshal([]byte(raw), &event); err != nil {
			continue
		}
		items = append(items, event)
	}
	return items
}

func (s *SQLiteStore) CreateTask(task Task) error {
	agentFlowJSON, err := json.Marshal(task.AgentFlow)
	if err != nil {
		return err
	}
	_, err = s.db.Exec(
		`INSERT INTO tasks (task_id, session_id, title, instruction, status, summary, agent_flow_json, current_agent, retry_count, retry_limit, waiting_for_approval, approval_id, runtime_job_id, runtime_task_id, runtime_trace_id, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		task.TaskID,
		task.SessionID,
		task.Title,
		task.Instruction,
		task.Status,
		task.Summary,
		string(agentFlowJSON),
		task.CurrentAgent,
		task.RetryCount,
		task.RetryLimit,
		boolToInt(task.WaitingForApproval),
		task.ApprovalID,
		task.RuntimeJobID,
		task.RuntimeTaskID,
		task.RuntimeTraceID,
		task.UpdatedAt.UTC().Format(time.RFC3339Nano),
	)
	return err
}

func (s *SQLiteStore) GetTask(taskID string) (Task, error) {
	row := s.db.QueryRow(
		`SELECT task_id, session_id, title, instruction, status, summary, agent_flow_json, current_agent, retry_count, retry_limit, waiting_for_approval, approval_id, runtime_job_id, runtime_task_id, runtime_trace_id, updated_at
		 FROM tasks WHERE task_id = ?`,
		taskID,
	)
	return scanTask(row)
}

func (s *SQLiteStore) UpdateTask(task Task) error {
	agentFlowJSON, err := json.Marshal(task.AgentFlow)
	if err != nil {
		return err
	}
	result, err := s.db.Exec(
		`UPDATE tasks
		 SET session_id = ?, title = ?, instruction = ?, status = ?, summary = ?, agent_flow_json = ?, current_agent = ?, retry_count = ?, retry_limit = ?, waiting_for_approval = ?, approval_id = ?, runtime_job_id = ?, runtime_task_id = ?, runtime_trace_id = ?, updated_at = ?
		 WHERE task_id = ?`,
		task.SessionID,
		task.Title,
		task.Instruction,
		task.Status,
		task.Summary,
		string(agentFlowJSON),
		task.CurrentAgent,
		task.RetryCount,
		task.RetryLimit,
		boolToInt(task.WaitingForApproval),
		task.ApprovalID,
		task.RuntimeJobID,
		task.RuntimeTaskID,
		task.RuntimeTraceID,
		task.UpdatedAt.UTC().Format(time.RFC3339Nano),
		task.TaskID,
	)
	if err != nil {
		return err
	}
	if affected, _ := result.RowsAffected(); affected == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SQLiteStore) ListSessionTasks(sessionID string) []Task {
	rows, err := s.db.Query(
		`SELECT task_id, session_id, title, instruction, status, summary, agent_flow_json, current_agent, retry_count, retry_limit, waiting_for_approval, approval_id, runtime_job_id, runtime_task_id, runtime_trace_id, updated_at
		 FROM tasks WHERE session_id = ? ORDER BY updated_at DESC`,
		sessionID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()

	items := make([]Task, 0)
	for rows.Next() {
		task, err := scanTask(rows)
		if err != nil {
			continue
		}
		items = append(items, task)
	}
	return items
}

func (s *SQLiteStore) SaveArtifact(card protocol.ArtifactCard) error {
	cardJSON, err := json.Marshal(card)
	if err != nil {
		return err
	}
	_, err = s.db.Exec(
		`INSERT OR REPLACE INTO artifacts (artifact_id, session_id, updated_at, card_json) VALUES (?, ?, ?, ?)`,
		card.ArtifactID,
		card.SessionID,
		card.UpdatedAt,
		string(cardJSON),
	)
	return err
}

func (s *SQLiteStore) GetArtifact(artifactID string) (protocol.ArtifactCard, error) {
	row := s.db.QueryRow(`SELECT card_json FROM artifacts WHERE artifact_id = ?`, artifactID)
	var raw string
	if err := row.Scan(&raw); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return protocol.ArtifactCard{}, ErrNotFound
		}
		return protocol.ArtifactCard{}, err
	}
	var card protocol.ArtifactCard
	if err := json.Unmarshal([]byte(raw), &card); err != nil {
		return protocol.ArtifactCard{}, err
	}
	return card, nil
}

func (s *SQLiteStore) ListSessionArtifacts(sessionID string) []protocol.ArtifactCard {
	rows, err := s.db.Query(`SELECT card_json FROM artifacts WHERE session_id = ?`, sessionID)
	if err != nil {
		return nil
	}
	defer rows.Close()
	items := make([]protocol.ArtifactCard, 0)
	for rows.Next() {
		var raw string
		if err := rows.Scan(&raw); err != nil {
			continue
		}
		var card protocol.ArtifactCard
		if err := json.Unmarshal([]byte(raw), &card); err != nil {
			continue
		}
		items = append(items, card)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].UpdatedAt > items[j].UpdatedAt })
	return items
}

func (s *SQLiteStore) SaveApproval(record ApprovalRecord) error {
	_, err := s.db.Exec(
		`INSERT OR REPLACE INTO approvals (approval_id, session_id, task_id, approver, decision, reason, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		record.ApprovalID,
		record.SessionID,
		record.TaskID,
		record.Approver,
		record.Decision,
		record.Reason,
		record.Status,
		record.Timestamp.UTC().Format(time.RFC3339Nano),
	)
	return err
}

func (s *SQLiteStore) GetApproval(approvalID string) (ApprovalRecord, error) {
	row := s.db.QueryRow(`SELECT approval_id, session_id, task_id, approver, decision, reason, status, timestamp FROM approvals WHERE approval_id = ?`, approvalID)
	var record ApprovalRecord
	var timestamp string
	if err := row.Scan(&record.ApprovalID, &record.SessionID, &record.TaskID, &record.Approver, &record.Decision, &record.Reason, &record.Status, &timestamp); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return ApprovalRecord{}, ErrNotFound
		}
		return ApprovalRecord{}, err
	}
	record.Timestamp = mustParseTime(timestamp)
	return record, nil
}

func (s *SQLiteStore) UpdateApproval(record ApprovalRecord) error {
	result, err := s.db.Exec(
		`UPDATE approvals SET session_id = ?, task_id = ?, approver = ?, decision = ?, reason = ?, status = ?, timestamp = ? WHERE approval_id = ?`,
		record.SessionID,
		record.TaskID,
		record.Approver,
		record.Decision,
		record.Reason,
		record.Status,
		record.Timestamp.UTC().Format(time.RFC3339Nano),
		record.ApprovalID,
	)
	if err != nil {
		return err
	}
	if affected, _ := result.RowsAffected(); affected == 0 {
		return ErrNotFound
	}
	return nil
}

func scanTask(scanner interface{ Scan(dest ...any) error }) (Task, error) {
	var task Task
	var updatedAt string
	var agentFlowJSON string
	var waitingForApproval int
	if err := scanner.Scan(
		&task.TaskID,
		&task.SessionID,
		&task.Title,
		&task.Instruction,
		&task.Status,
		&task.Summary,
		&agentFlowJSON,
		&task.CurrentAgent,
		&task.RetryCount,
		&task.RetryLimit,
		&waitingForApproval,
		&task.ApprovalID,
		&task.RuntimeJobID,
		&task.RuntimeTaskID,
		&task.RuntimeTraceID,
		&updatedAt,
	); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return Task{}, ErrNotFound
		}
		return Task{}, err
	}
	_ = json.Unmarshal([]byte(agentFlowJSON), &task.AgentFlow)
	task.WaitingForApproval = waitingForApproval == 1
	task.UpdatedAt = mustParseTime(updatedAt)
	return task, nil
}

func mustParseTime(value string) time.Time {
	if value == "" {
		return time.Time{}
	}
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return time.Time{}
	}
	return parsed
}

func boolToInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

// ── Agent Definition (SQLiteStore) ──────────────────────────────

var _ AgentDefinitionStore = (*SQLiteStore)(nil)

func (s *SQLiteStore) CreateAgentDefinition(record AgentDefinitionRecord) error {
	skillsJSON, _ := json.Marshal(record.AllowedSkills)
	_, err := s.db.Exec(
		`INSERT INTO agent_definitions (id, name, avatar, description, system_prompt, allowed_skills_json, preferred_provider, visibility, created_by, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		record.ID, record.Name, record.Avatar, record.Description, record.SystemPrompt,
		string(skillsJSON), record.PreferredProvider, record.Visibility,
		record.CreatedBy, record.CreatedAt, record.UpdatedAt,
	)
	return err
}

func (s *SQLiteStore) GetAgentDefinition(id string) (AgentDefinitionRecord, error) {
	row := s.db.QueryRow(
		`SELECT id, name, avatar, description, system_prompt, allowed_skills_json, preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE id = ?`, id,
	)
	var rec AgentDefinitionRecord
	var skillsJSON string
	err := row.Scan(&rec.ID, &rec.Name, &rec.Avatar, &rec.Description, &rec.SystemPrompt,
		&skillsJSON, &rec.PreferredProvider, &rec.Visibility,
		&rec.CreatedBy, &rec.CreatedAt, &rec.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return AgentDefinitionRecord{}, ErrNotFound
		}
		return AgentDefinitionRecord{}, err
	}
	_ = json.Unmarshal([]byte(skillsJSON), &rec.AllowedSkills)
	if rec.AllowedSkills == nil {
		rec.AllowedSkills = []string{}
	}
	return rec, nil
}

func (s *SQLiteStore) ListAgentDefinitions(ownerID string) []AgentDefinitionRecord {
	rows, err := s.db.Query(
		`SELECT id, name, avatar, description, system_prompt, allowed_skills_json, preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE created_by = ? ORDER BY updated_at DESC`, ownerID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()
	return scanAgentDefinitionRows(rows)
}

func (s *SQLiteStore) ListPublicAgentDefinitions() []AgentDefinitionRecord {
	rows, err := s.db.Query(
		`SELECT id, name, avatar, description, system_prompt, allowed_skills_json, preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE visibility = 'public' ORDER BY updated_at DESC`,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()
	return scanAgentDefinitionRows(rows)
}

func (s *SQLiteStore) UpdateAgentDefinition(record AgentDefinitionRecord) error {
	skillsJSON, _ := json.Marshal(record.AllowedSkills)
	result, err := s.db.Exec(
		`UPDATE agent_definitions SET name=?, avatar=?, description=?, system_prompt=?, allowed_skills_json=?, preferred_provider=?, visibility=?, updated_at=?
		 WHERE id=?`,
		record.Name, record.Avatar, record.Description, record.SystemPrompt,
		string(skillsJSON), record.PreferredProvider, record.Visibility,
		record.UpdatedAt, record.ID,
	)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SQLiteStore) DeleteAgentDefinition(id string) error {
	result, err := s.db.Exec(`DELETE FROM agent_definitions WHERE id=?`, id)
	if err != nil {
		return err
	}
	n, _ := result.RowsAffected()
	if n == 0 {
		return ErrNotFound
	}
	return nil
}

func scanAgentDefinitionRows(rows *sql.Rows) []AgentDefinitionRecord {
	var result []AgentDefinitionRecord
	for rows.Next() {
		var rec AgentDefinitionRecord
		var skillsJSON string
		if err := rows.Scan(&rec.ID, &rec.Name, &rec.Avatar, &rec.Description, &rec.SystemPrompt,
			&skillsJSON, &rec.PreferredProvider, &rec.Visibility,
			&rec.CreatedBy, &rec.CreatedAt, &rec.UpdatedAt,
		); err != nil {
			continue
		}
		_ = json.Unmarshal([]byte(skillsJSON), &rec.AllowedSkills)
		if rec.AllowedSkills == nil {
			rec.AllowedSkills = []string{}
		}
		result = append(result, rec)
	}
	return result
}

// ── Session File Store (SQLiteStore) ─────────────────────────────

var _ SessionFileStore = (*SQLiteStore)(nil)

func (s *SQLiteStore) SaveSessionFile(sessionID, filePath, content string) error {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	_, err := s.db.Exec(
		`INSERT INTO session_file_contents (session_id, file_path, file_content, created_at, updated_at)
		 VALUES (?, ?, ?, ?, ?)
		 ON CONFLICT(session_id, file_path) DO UPDATE SET
		 file_content = excluded.file_content,
		 updated_at = excluded.updated_at`,
		sessionID, filePath, content, now, now,
	)
	return err
}

func (s *SQLiteStore) GetSessionFile(sessionID, filePath string) (string, error) {
	row := s.db.QueryRow(
		`SELECT file_content FROM session_file_contents WHERE session_id = ? AND file_path = ?`,
		sessionID, filePath,
	)
	var content string
	err := row.Scan(&content)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return "", ErrNotFound
		}
		return "", err
	}
	return content, nil
}

func (s *SQLiteStore) ListSessionFiles(sessionID string) (map[string]string, error) {
	rows, err := s.db.Query(
		`SELECT file_path, file_content FROM session_file_contents WHERE session_id = ?`,
		sessionID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	result := make(map[string]string)
	for rows.Next() {
		var path, content string
		if err := rows.Scan(&path, &content); err != nil {
			continue
		}
		result[path] = content
	}
	return result, nil
}

func (s *SQLiteStore) DeleteSessionFile(sessionID, filePath string) error {
	_, err := s.db.Exec(
		`DELETE FROM session_file_contents WHERE session_id = ? AND file_path = ?`,
		sessionID, filePath,
	)
	return err
}

// ── Workspace File Index Store (SQLiteStore) ───────────────────────────

var _ WorkspaceFileIndexStore = (*SQLiteStore)(nil)

func (s *SQLiteStore) UpsertWorkspaceFileIndex(sessionID, filePath string, sizeBytes int64, sha256Hash string) error {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	_, err := s.db.Exec(
		`INSERT INTO workspace_files (session_id, file_path, size_bytes, sha256_hash, updated_at)
		 VALUES (?, ?, ?, ?, ?)
		 ON CONFLICT(session_id, file_path) DO UPDATE SET
		 size_bytes = excluded.size_bytes,
		 sha256_hash = excluded.sha256_hash,
		 updated_at = excluded.updated_at`,
		sessionID, filePath, sizeBytes, sha256Hash, now,
	)
	return err
}

func (s *SQLiteStore) GetWorkspaceFileIndex(sessionID, filePath string) (WorkspaceFileIndex, error) {
	row := s.db.QueryRow(
		`SELECT session_id, file_path, size_bytes, sha256_hash, updated_at
		 FROM workspace_files WHERE session_id = ? AND file_path = ?`,
		sessionID, filePath,
	)
	var idx WorkspaceFileIndex
	var updatedAt string
	err := row.Scan(&idx.SessionID, &idx.FilePath, &idx.SizeBytes, &idx.Sha256Hash, &updatedAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return WorkspaceFileIndex{}, ErrNotFound
		}
		return WorkspaceFileIndex{}, err
	}
	idx.UpdatedAt = mustParseTime(updatedAt)
	return idx, nil
}

func (s *SQLiteStore) ListWorkspaceFileIndexes(sessionID string) ([]WorkspaceFileIndex, error) {
	rows, err := s.db.Query(
		`SELECT session_id, file_path, size_bytes, sha256_hash, updated_at
		 FROM workspace_files WHERE session_id = ? ORDER BY file_path ASC`,
		sessionID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []WorkspaceFileIndex
	for rows.Next() {
		var idx WorkspaceFileIndex
		var updatedAt string
		if err := rows.Scan(&idx.SessionID, &idx.FilePath, &idx.SizeBytes, &idx.Sha256Hash, &updatedAt); err != nil {
			continue
		}
		idx.UpdatedAt = mustParseTime(updatedAt)
		result = append(result, idx)
	}
	if result == nil {
		result = []WorkspaceFileIndex{}
	}
	return result, nil
}

func (s *SQLiteStore) DeleteWorkspaceFileIndex(sessionID, filePath string) error {
	_, err := s.db.Exec(
		`DELETE FROM workspace_files WHERE session_id = ? AND file_path = ?`,
		sessionID, filePath,
	)
	return err
}

func (s *SQLiteStore) DeleteWorkspaceFileIndexes(sessionID string) error {
	_, err := s.db.Exec(`DELETE FROM workspace_files WHERE session_id = ?`, sessionID)
	return err
}
