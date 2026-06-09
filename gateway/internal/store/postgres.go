package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"time"

	"agenthub/gateway/internal/protocol"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PostgresStore 实现 store.Backend，将 Gateway 会话、事件、任务等持久化到 PostgreSQL。
// 表结构对应 db/migrations/001_initial_schema.up.sql。
type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(ctx context.Context, dsn string) (*PostgresStore, error) {
	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("postgres parse dsn: %w", err)
	}
	cfg.MaxConns = 20

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("postgres connect: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("postgres ping: %w", err)
	}
	// 确保 workspace_files 表存在（兼容未执行迁移的环境）
	if _, err := pool.Exec(ctx, `CREATE TABLE IF NOT EXISTS workspace_files (
		session_id TEXT NOT NULL,
		file_path TEXT NOT NULL,
		size_bytes BIGINT NOT NULL DEFAULT 0,
		sha256_hash TEXT NOT NULL DEFAULT '',
		updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
		PRIMARY KEY (session_id, file_path)
	)`); err != nil {
		pool.Close()
		return nil, fmt.Errorf("postgres workspace_files migration: %w", err)
	}
	return &PostgresStore{pool: pool}, nil
}

func (s *PostgresStore) Close() error {
	if s == nil || s.pool == nil {
		return nil
	}
	s.pool.Close()
	return nil
}

// ── helpers ──────────────────────────────────────────────────────────

func pgBool(b bool) bool { return b }

func scanErrNoRows(err error) bool {
	return errors.Is(err, pgx.ErrNoRows)
}

// ── AuthStore ────────────────────────────────────────────────────────

func (s *PostgresStore) SaveAccessToken(record AccessTokenRecord) error {
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO access_tokens (token, principal_id, role, expires_at)
		 VALUES ($1, $2, $3, $4)
		 ON CONFLICT (token) DO UPDATE SET principal_id=$2, role=$3, expires_at=$4`,
		record.Token, record.PrincipalID, record.Role, record.ExpiresAt.UTC(),
	)
	return err
}

func (s *PostgresStore) GetAccessToken(token string) (AccessTokenRecord, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT token, principal_id, role, expires_at FROM access_tokens WHERE token = $1`, token,
	)
	var rec AccessTokenRecord
	if err := row.Scan(&rec.Token, &rec.PrincipalID, &rec.Role, &rec.ExpiresAt); err != nil {
		if scanErrNoRows(err) {
			return AccessTokenRecord{}, ErrNotFound
		}
		return AccessTokenRecord{}, err
	}
	if !rec.ExpiresAt.IsZero() && time.Now().After(rec.ExpiresAt) {
		return AccessTokenRecord{}, ErrNotFound
	}
	return rec, nil
}

// ── WS Tickets ───────────────────────────────────────────────────────

func (s *PostgresStore) SaveWSTicket(record WSTicketRecord) error {
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO ws_tickets (ticket, session_id, principal_id, expires_at, used)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (ticket) DO UPDATE SET session_id=$2, principal_id=$3, expires_at=$4, used=$5`,
		record.Ticket, record.SessionID, record.PrincipalID,
		record.ExpiresAt.UTC(), record.Used,
	)
	return err
}

func (s *PostgresStore) ConsumeWSTicket(ticket string) (WSTicketRecord, error) {
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return WSTicketRecord{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// 原子操作：将未使用的 ticket 标记为 used，返回更新后的行
	row := tx.QueryRow(ctx,
		`UPDATE ws_tickets SET used = TRUE
		 WHERE ticket = $1 AND used = FALSE AND expires_at > NOW()
		 RETURNING ticket, session_id, principal_id, expires_at, used`,
		ticket,
	)
	var rec WSTicketRecord
	if err := row.Scan(&rec.Ticket, &rec.SessionID, &rec.PrincipalID, &rec.ExpiresAt, &rec.Used); err != nil {
		if scanErrNoRows(err) {
			return WSTicketRecord{}, ErrTicketExpired
		}
		return WSTicketRecord{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return WSTicketRecord{}, err
	}
	return rec, nil
}

// ── SessionStore ─────────────────────────────────────────────────────

func (s *PostgresStore) CreateSession(session Session) error {
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	_, err = tx.Exec(ctx,
		`INSERT INTO sessions (id, title, mode, owner_id, created_at, updated_at, last_event_seq, workspace_root, workspace_type)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
		session.SessionID, session.Title, session.Mode, session.OwnerID,
		session.CreatedAt.UTC(), session.UpdatedAt.UTC(), session.LastEventSeq,
		session.WorkspaceRoot, session.WorkspaceType,
	)
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx,
		`INSERT INTO session_members (session_id, principal_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
		session.SessionID, session.OwnerID,
	)
	if err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *PostgresStore) GetSession(sessionID string) (Session, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT id, title, mode, owner_id, created_at, updated_at, last_event_seq, workspace_root, workspace_type
		 FROM sessions WHERE id = $1`, sessionID,
	)
	return scanSession(row)
}

func (s *PostgresStore) ListSessions(ownerID string) []Session {
	rows, err := s.pool.Query(context.Background(),
		`SELECT s.id, s.title, s.mode, s.owner_id, s.created_at, s.updated_at, s.last_event_seq, s.workspace_root, s.workspace_type
		 FROM sessions s
		 JOIN session_members sm ON sm.session_id = s.id
		 WHERE sm.principal_id = $1
		 ORDER BY s.updated_at DESC`,
		ownerID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var items []Session
	for rows.Next() {
		sess, err := scanSession(rows)
		if err != nil {
			continue
		}
		items = append(items, sess)
	}
	return items
}

func (s *PostgresStore) AddSessionMember(sessionID, principalID string) error {
	if _, err := s.GetSession(sessionID); err != nil {
		return err
	}
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO session_members (session_id, principal_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`,
		sessionID, principalID,
	)
	return err
}

func (s *PostgresStore) IsSessionMember(sessionID, principalID string) bool {
	var exists int
	err := s.pool.QueryRow(context.Background(),
		`SELECT 1 FROM session_members WHERE session_id = $1 AND principal_id = $2 LIMIT 1`,
		sessionID, principalID,
	).Scan(&exists)
	return err == nil
}

func (s *PostgresStore) UpdateSessionTimestamp(sessionID string, updatedAt time.Time) error {
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE sessions SET updated_at = $1 WHERE id = $2`,
		updatedAt.UTC(), sessionID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) UpdateSessionSeq(sessionID string, seq int64) error {
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE sessions SET last_event_seq = $1, updated_at = NOW() WHERE id = $2`,
		seq, sessionID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) UpdateSession(session Session) error {
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE sessions 
		 SET title = $1, mode = $2, updated_at = NOW(), 
		     workspace_root = $3, workspace_type = $4
		 WHERE id = $5`,
		session.Title, session.Mode,
		session.WorkspaceRoot, session.WorkspaceType,
		session.SessionID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) DeleteSession(sessionID string) error {
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	_, _ = tx.Exec(ctx, `DELETE FROM events WHERE session_id = $1`, sessionID)
	_, _ = tx.Exec(ctx, `DELETE FROM tasks WHERE session_id = $1`, sessionID)
	_, _ = tx.Exec(ctx, `DELETE FROM artifacts WHERE session_id = $1`, sessionID)
	_, _ = tx.Exec(ctx, `DELETE FROM session_members WHERE session_id = $1`, sessionID)
	_, _ = tx.Exec(ctx, `DELETE FROM sessions WHERE id = $1`, sessionID)

	return tx.Commit(ctx)
}

func scanSession(row pgx.Row) (Session, error) {
	var sess Session
	if err := row.Scan(&sess.SessionID, &sess.Title, &sess.Mode, &sess.OwnerID,
		&sess.CreatedAt, &sess.UpdatedAt, &sess.LastEventSeq, &sess.WorkspaceRoot, &sess.WorkspaceType); err != nil {
		if scanErrNoRows(err) {
			return Session{}, ErrNotFound
		}
		return Session{}, err
	}
	return sess, nil
}

// ── EventStore ───────────────────────────────────────────────────────

func (s *PostgresStore) AppendEvent(sessionID string, event protocol.WSEvent) (protocol.WSEvent, error) {
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return protocol.WSEvent{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	// 原子获取下一个 seq
	var nextSeq int64
	if err := tx.QueryRow(ctx,
		`SELECT COALESCE(last_event_seq, 0) + 1 FROM sessions WHERE id = $1 FOR UPDATE`,
		sessionID,
	).Scan(&nextSeq); err != nil {
		if scanErrNoRows(err) {
			return protocol.WSEvent{}, ErrNotFound
		}
		return protocol.WSEvent{}, err
	}
	event.Seq = nextSeq

	// 提取结构化列
	role := extractRole(event.Sender)
	agentName := extractAgentName(event.Sender)
	payloadBytes, _ := json.Marshal(event)
	metadataBytes, _ := json.Marshal(map[string]any{
		"sender":   event.Sender,
		"receiver": event.Receiver,
	})

	_, err = tx.Exec(ctx,
		`INSERT INTO events (session_id, task_id, trace_id, seq, event_type, role, agent_name, payload, metadata)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
		sessionID,
		nullStr(event.TaskID),
		event.TraceID,
		event.Seq,
		event.Type,
		role,
		agentName,
		payloadBytes,
		metadataBytes,
	)
	if err != nil {
		return protocol.WSEvent{}, err
	}

	// 更新会话的 last_event_seq
	_, err = tx.Exec(ctx,
		`UPDATE sessions SET last_event_seq = $1, updated_at = NOW() WHERE id = $2`,
		event.Seq, sessionID,
	)
	if err != nil {
		return protocol.WSEvent{}, err
	}

	if err := tx.Commit(ctx); err != nil {
		return protocol.WSEvent{}, err
	}
	return event, nil
}

func (s *PostgresStore) ListEvents(sessionID string, afterSeq int64, limit int) []protocol.WSEvent {
	query := `SELECT payload FROM events WHERE session_id = $1 AND seq > $2 ORDER BY seq ASC`
	args := []any{sessionID, afterSeq}
	if limit > 0 {
		query += fmt.Sprintf(` LIMIT %d`, limit)
	}
	rows, err := s.pool.Query(context.Background(), query, args...)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var items []protocol.WSEvent
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err != nil {
			continue
		}
		var event protocol.WSEvent
		if err := json.Unmarshal(raw, &event); err != nil {
			continue
		}
		items = append(items, event)
	}
	return items
}

func extractRole(sender protocol.Party) string {
	switch sender.Type {
	case "user":
		return "user"
	case "agent":
		return "agent"
	case "gateway":
		return "system"
	default:
		return sender.Type
	}
}

func extractAgentName(sender protocol.Party) string {
	if sender.Type == "agent" {
		return sender.ID
	}
	return ""
}

// ── TaskStore ────────────────────────────────────────────────────────

func (s *PostgresStore) CreateTask(task Task) error {
	agentFlowJSON, _ := json.Marshal(task.AgentFlow)
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO tasks (id, session_id, title, instruction, status, summary,
		 agent_flow, current_agent, retry_count, retry_limit, waiting_for_approval,
		 approval_id, runtime_job_id, runtime_task_id, runtime_trace_id,
		 mentioned_agent, updated_at)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)`,
		task.TaskID, task.SessionID, task.Title, task.Instruction, task.Status,
		task.Summary, agentFlowJSON, task.CurrentAgent, task.RetryCount, task.RetryLimit,
		task.WaitingForApproval, nullStr(task.ApprovalID),
		task.RuntimeJobID, task.RuntimeTaskID, task.RuntimeTraceID,
		task.MentionedAgent, task.UpdatedAt.UTC(),
	)
	return err
}

func (s *PostgresStore) GetTask(taskID string) (Task, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT id, session_id, title, instruction, status, summary,
		 agent_flow, current_agent, retry_count, retry_limit, waiting_for_approval,
		 COALESCE(approval_id::text, ''), runtime_job_id, runtime_task_id, runtime_trace_id,
		 mentioned_agent, updated_at
		 FROM tasks WHERE id = $1`, taskID,
	)
	return pgScanTask(row)
}

func (s *PostgresStore) UpdateTask(task Task) error {
	agentFlowJSON, _ := json.Marshal(task.AgentFlow)
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE tasks SET session_id=$1, title=$2, instruction=$3, status=$4, summary=$5,
		 agent_flow=$6, current_agent=$7, retry_count=$8, retry_limit=$9,
		 waiting_for_approval=$10, approval_id=$11::uuid, runtime_job_id=$12,
		 runtime_task_id=$13, runtime_trace_id=$14, mentioned_agent=$15, updated_at=$16
		 WHERE id=$17`,
		task.SessionID, task.Title, task.Instruction, task.Status, task.Summary,
		agentFlowJSON, task.CurrentAgent, task.RetryCount, task.RetryLimit,
		task.WaitingForApproval, nullStr(task.ApprovalID),
		task.RuntimeJobID, task.RuntimeTaskID, task.RuntimeTraceID,
		task.MentionedAgent, task.UpdatedAt.UTC(), task.TaskID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) ListSessionTasks(sessionID string) []Task {
	rows, err := s.pool.Query(context.Background(),
		`SELECT id, session_id, title, instruction, status, summary,
		 agent_flow, current_agent, retry_count, retry_limit, waiting_for_approval,
		 COALESCE(approval_id::text, ''), runtime_job_id, runtime_task_id, runtime_trace_id,
		 mentioned_agent, updated_at
		 FROM tasks WHERE session_id = $1 ORDER BY updated_at DESC`,
		sessionID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var items []Task
	for rows.Next() {
		task, err := pgScanTask(rows)
		if err != nil {
			continue
		}
		items = append(items, task)
	}
	return items
}

func pgScanTask(row pgx.Row) (Task, error) {
	var task Task
	var agentFlowJSON []byte
	if err := row.Scan(
		&task.TaskID, &task.SessionID, &task.Title, &task.Instruction,
		&task.Status, &task.Summary, &agentFlowJSON, &task.CurrentAgent,
		&task.RetryCount, &task.RetryLimit, &task.WaitingForApproval,
		&task.ApprovalID, &task.RuntimeJobID, &task.RuntimeTaskID,
		&task.RuntimeTraceID, &task.MentionedAgent, &task.UpdatedAt,
	); err != nil {
		if scanErrNoRows(err) {
			return Task{}, ErrNotFound
		}
		return Task{}, err
	}
	_ = json.Unmarshal(agentFlowJSON, &task.AgentFlow)
	return task, nil
}

// ── ArtifactStore ────────────────────────────────────────────────────

func (s *PostgresStore) SaveArtifact(card protocol.ArtifactCard) error {
	cardJSON, _ := json.Marshal(card)
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO artifacts (id, session_id, task_id, artifact_type, name, updated_at, card_json)
		 VALUES ($1, $2, $3, $4, $5, $6, $7)
		 ON CONFLICT (id) DO UPDATE SET session_id=$2, task_id=$3, artifact_type=$4,
		 name=$5, updated_at=$6, card_json=$7`,
		card.ArtifactID, card.SessionID, card.TaskID, card.CardType,
		card.Title, card.UpdatedAt, cardJSON,
	)
	return err
}

func (s *PostgresStore) GetArtifact(artifactID string) (protocol.ArtifactCard, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT card_json FROM artifacts WHERE id = $1`, artifactID,
	)
	var raw []byte
	if err := row.Scan(&raw); err != nil {
		if scanErrNoRows(err) {
			return protocol.ArtifactCard{}, ErrNotFound
		}
		return protocol.ArtifactCard{}, err
	}
	var card protocol.ArtifactCard
	if err := json.Unmarshal(raw, &card); err != nil {
		return protocol.ArtifactCard{}, err
	}
	return card, nil
}

func (s *PostgresStore) ListSessionArtifacts(sessionID string) []protocol.ArtifactCard {
	rows, err := s.pool.Query(context.Background(),
		`SELECT card_json FROM artifacts WHERE session_id = $1`, sessionID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()

	var items []protocol.ArtifactCard
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err != nil {
			continue
		}
		var card protocol.ArtifactCard
		if err := json.Unmarshal(raw, &card); err != nil {
			continue
		}
		items = append(items, card)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].UpdatedAt > items[j].UpdatedAt })
	return items
}

// ── ApprovalStore ────────────────────────────────────────────────────

func (s *PostgresStore) SaveApproval(record ApprovalRecord) error {
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO approvals (id, session_id, task_id, approver, decision, reason, status, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
		 ON CONFLICT (id) DO UPDATE SET session_id=$2, task_id=$3, approver=$4,
		 decision=$5, reason=$6, status=$7, updated_at=NOW()`,
		record.ApprovalID, record.SessionID, record.TaskID, record.Approver,
		record.Decision, record.Reason, record.Status, record.Timestamp.UTC(),
	)
	return err
}

func (s *PostgresStore) GetApproval(approvalID string) (ApprovalRecord, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT id, session_id, task_id, approver, decision, reason, status, created_at
		 FROM approvals WHERE id = $1`, approvalID,
	)
	var rec ApprovalRecord
	if err := row.Scan(&rec.ApprovalID, &rec.SessionID, &rec.TaskID,
		&rec.Approver, &rec.Decision, &rec.Reason, &rec.Status, &rec.Timestamp); err != nil {
		if scanErrNoRows(err) {
			return ApprovalRecord{}, ErrNotFound
		}
		return ApprovalRecord{}, err
	}
	return rec, nil
}

func (s *PostgresStore) UpdateApproval(record ApprovalRecord) error {
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE approvals SET session_id=$1, task_id=$2, approver=$3, decision=$4,
		 reason=$5, status=$6, updated_at=NOW() WHERE id=$7`,
		record.SessionID, record.TaskID, record.Approver,
		record.Decision, record.Reason, record.Status, record.ApprovalID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

// ── AgentDefinitionStore ─────────────────────────────────────────────

func (s *PostgresStore) CreateAgentDefinition(record AgentDefinitionRecord) error {
	skillsJSON, _ := json.Marshal(record.AllowedSkills)
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO agent_definitions (id, name, avatar, description, system_prompt,
		 allowed_skills, preferred_provider, visibility, created_by, created_at, updated_at)
		 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
		record.ID, record.Name, record.Avatar, record.Description, record.SystemPrompt,
		skillsJSON, record.PreferredProvider, record.Visibility,
		record.CreatedBy, record.CreatedAt, record.UpdatedAt,
	)
	return err
}

func (s *PostgresStore) GetAgentDefinition(id string) (AgentDefinitionRecord, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT id, name, avatar, description, system_prompt, allowed_skills,
		 preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE id = $1`, id,
	)
	var rec AgentDefinitionRecord
	var skillsJSON []byte
	err := row.Scan(&rec.ID, &rec.Name, &rec.Avatar, &rec.Description, &rec.SystemPrompt,
		&skillsJSON, &rec.PreferredProvider, &rec.Visibility,
		&rec.CreatedBy, &rec.CreatedAt, &rec.UpdatedAt,
	)
	if err != nil {
		if scanErrNoRows(err) {
			return AgentDefinitionRecord{}, ErrNotFound
		}
		return AgentDefinitionRecord{}, err
	}
	_ = json.Unmarshal(skillsJSON, &rec.AllowedSkills)
	if rec.AllowedSkills == nil {
		rec.AllowedSkills = []string{}
	}
	return rec, nil
}

func (s *PostgresStore) ListAgentDefinitions(ownerID string) []AgentDefinitionRecord {
	rows, err := s.pool.Query(context.Background(),
		`SELECT id, name, avatar, description, system_prompt, allowed_skills,
		 preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE created_by = $1 ORDER BY updated_at DESC`, ownerID,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()
	return scanAgentDefRows(rows)
}

func (s *PostgresStore) ListPublicAgentDefinitions() []AgentDefinitionRecord {
	rows, err := s.pool.Query(context.Background(),
		`SELECT id, name, avatar, description, system_prompt, allowed_skills,
		 preferred_provider, visibility, created_by, created_at, updated_at
		 FROM agent_definitions WHERE visibility = 'public' ORDER BY updated_at DESC`,
	)
	if err != nil {
		return nil
	}
	defer rows.Close()
	return scanAgentDefRows(rows)
}

func (s *PostgresStore) UpdateAgentDefinition(record AgentDefinitionRecord) error {
	skillsJSON, _ := json.Marshal(record.AllowedSkills)
	tag, err := s.pool.Exec(context.Background(),
		`UPDATE agent_definitions SET name=$1, avatar=$2, description=$3,
		 system_prompt=$4, allowed_skills=$5, preferred_provider=$6,
		 visibility=$7, updated_at=$8 WHERE id=$9`,
		record.Name, record.Avatar, record.Description, record.SystemPrompt,
		skillsJSON, record.PreferredProvider, record.Visibility,
		record.UpdatedAt, record.ID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *PostgresStore) DeleteAgentDefinition(id string) error {
	tag, err := s.pool.Exec(context.Background(),
		`DELETE FROM agent_definitions WHERE id = $1`, id,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func scanAgentDefRows(rows pgx.Rows) []AgentDefinitionRecord {
	var result []AgentDefinitionRecord
	for rows.Next() {
		var rec AgentDefinitionRecord
		var skillsJSON []byte
		if err := rows.Scan(&rec.ID, &rec.Name, &rec.Avatar, &rec.Description,
			&rec.SystemPrompt, &skillsJSON, &rec.PreferredProvider, &rec.Visibility,
			&rec.CreatedBy, &rec.CreatedAt, &rec.UpdatedAt,
		); err != nil {
			continue
		}
		_ = json.Unmarshal(skillsJSON, &rec.AllowedSkills)
		if rec.AllowedSkills == nil {
			rec.AllowedSkills = []string{}
		}
		result = append(result, rec)
	}
	return result
}

// ── Session File Store (PostgresStore) ─────────────────────────────

var _ SessionFileStore = (*PostgresStore)(nil)

func (s *PostgresStore) SaveSessionFile(sessionID, filePath, content string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO session_file_contents (session_id, file_path, file_content, created_at, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (session_id, file_path) DO UPDATE SET
		 file_content = excluded.file_content,
		 updated_at = excluded.updated_at`,
		sessionID, filePath, content, now, now,
	)
	return err
}

func (s *PostgresStore) GetSessionFile(sessionID, filePath string) (string, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT file_content FROM session_file_contents WHERE session_id = $1 AND file_path = $2`,
		sessionID, filePath,
	)
	var content string
	err := row.Scan(&content)
	if err != nil {
		if scanErrNoRows(err) {
			return "", ErrNotFound
		}
		return "", err
	}
	return content, nil
}

func (s *PostgresStore) ListSessionFiles(sessionID string) (map[string]string, error) {
	rows, err := s.pool.Query(context.Background(),
		`SELECT file_path, file_content FROM session_file_contents WHERE session_id = $1`,
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

func (s *PostgresStore) DeleteSessionFile(sessionID, filePath string) error {
	_, err := s.pool.Exec(context.Background(),
		`DELETE FROM session_file_contents WHERE session_id = $1 AND file_path = $2`,
		sessionID, filePath,
	)
	return err
}

// ── helpers ──────────────────────────────────────────────────────────

func nullStr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// ── Workspace File Index Store (PostgresStore) ───────────────────────

var _ WorkspaceFileIndexStore = (*PostgresStore)(nil)

func (s *PostgresStore) UpsertWorkspaceFileIndex(sessionID, filePath string, sizeBytes int64, sha256Hash string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(context.Background(),
		`INSERT INTO workspace_files (session_id, file_path, size_bytes, sha256_hash, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (session_id, file_path) DO UPDATE SET
		 size_bytes = excluded.size_bytes,
		 sha256_hash = excluded.sha256_hash,
		 updated_at = excluded.updated_at`,
		sessionID, filePath, sizeBytes, sha256Hash, now,
	)
	return err
}

func (s *PostgresStore) GetWorkspaceFileIndex(sessionID, filePath string) (WorkspaceFileIndex, error) {
	row := s.pool.QueryRow(context.Background(),
		`SELECT session_id, file_path, size_bytes, sha256_hash, updated_at
		 FROM workspace_files WHERE session_id = $1 AND file_path = $2`,
		sessionID, filePath,
	)
	var idx WorkspaceFileIndex
	err := row.Scan(&idx.SessionID, &idx.FilePath, &idx.SizeBytes, &idx.Sha256Hash, &idx.UpdatedAt)
	if err != nil {
		if scanErrNoRows(err) {
			return WorkspaceFileIndex{}, ErrNotFound
		}
		return WorkspaceFileIndex{}, err
	}
	return idx, nil
}

func (s *PostgresStore) ListWorkspaceFileIndexes(sessionID string) ([]WorkspaceFileIndex, error) {
	rows, err := s.pool.Query(context.Background(),
		`SELECT session_id, file_path, size_bytes, sha256_hash, updated_at
		 FROM workspace_files WHERE session_id = $1 ORDER BY file_path ASC`,
		sessionID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []WorkspaceFileIndex
	for rows.Next() {
		var idx WorkspaceFileIndex
		if err := rows.Scan(&idx.SessionID, &idx.FilePath, &idx.SizeBytes, &idx.Sha256Hash, &idx.UpdatedAt); err != nil {
			continue
		}
		result = append(result, idx)
	}
	if result == nil {
		result = []WorkspaceFileIndex{}
	}
	return result, nil
}

func (s *PostgresStore) DeleteWorkspaceFileIndex(sessionID, filePath string) error {
	_, err := s.pool.Exec(context.Background(),
		`DELETE FROM workspace_files WHERE session_id = $1 AND file_path = $2`,
		sessionID, filePath,
	)
	return err
}

func (s *PostgresStore) DeleteWorkspaceFileIndexes(sessionID string) error {
	_, err := s.pool.Exec(context.Background(),
		`DELETE FROM workspace_files WHERE session_id = $1`,
		sessionID,
	)
	return err
}

// 确保编译时检查接口实现
var _ Backend = (*PostgresStore)(nil)
var _ AgentDefinitionStore = (*PostgresStore)(nil)
var _ SessionFileStore = (*PostgresStore)(nil)
var _ WorkspaceFileIndexStore = (*PostgresStore)(nil)
var _ Closer = (*PostgresStore)(nil)
