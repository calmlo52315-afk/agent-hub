-- ============================================================================
-- AgentHub 数据库初始化 Schema V2.0
-- PostgreSQL 统一存储 — 替代 Gateway SQLite + Replay SQLite + Metrics JSONL
-- ============================================================================

-- 阶段 A：核心业务表（迁移 Gateway + Replay）

-- A1. sessions -----------------------------------------------------------------
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL DEFAULT '',
    mode            TEXT NOT NULL DEFAULT 'multi_agent',
    owner_id        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    last_event_seq  BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_owner_updated ON sessions (owner_id, updated_at DESC);

-- A2. session_members ----------------------------------------------------------
CREATE TABLE session_members (
    session_id   UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL,
    joined_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, principal_id)
);

-- A3. access_tokens ------------------------------------------------------------
CREATE TABLE access_tokens (
    token        TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'user',
    expires_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_access_tokens_expires ON access_tokens (expires_at)
    WHERE expires_at IS NOT NULL;

-- A4. ws_tickets ---------------------------------------------------------------
CREATE TABLE ws_tickets (
    ticket       TEXT PRIMARY KEY,
    session_id   UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    principal_id TEXT NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    used         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX idx_ws_tickets_expires ON ws_tickets (expires_at)
    WHERE used = FALSE;

-- A5. agent_definitions --------------------------------------------------------
CREATE TABLE agent_definitions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    avatar              TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    system_prompt       TEXT NOT NULL DEFAULT '',
    allowed_skills      JSONB NOT NULL DEFAULT '[]',
    preferred_provider  TEXT NOT NULL DEFAULT 'claude_code',
    visibility          TEXT NOT NULL DEFAULT 'private',
    created_by          TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_defs_owner ON agent_definitions (created_by, updated_at DESC);
CREATE INDEX idx_agent_defs_public ON agent_definitions (visibility, updated_at DESC)
    WHERE visibility = 'public';

-- A6. tasks --------------------------------------------------------------------
CREATE TABLE tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id           UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    parent_task_id       UUID,
    title                TEXT NOT NULL DEFAULT '',
    instruction          TEXT NOT NULL DEFAULT '',
    goal                 TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'created',
    priority             TEXT NOT NULL DEFAULT 'medium',
    assigned_agent       TEXT NOT NULL DEFAULT '',
    agent_flow           JSONB NOT NULL DEFAULT '[]',
    current_agent        TEXT NOT NULL DEFAULT '',
    retry_count          INTEGER NOT NULL DEFAULT 0,
    retry_limit          INTEGER NOT NULL DEFAULT 2,
    waiting_for_approval BOOLEAN NOT NULL DEFAULT FALSE,
    approval_id          UUID,
    runtime_job_id       TEXT NOT NULL DEFAULT '',
    runtime_task_id      TEXT NOT NULL DEFAULT '',
    runtime_trace_id     TEXT NOT NULL DEFAULT '',
    mentioned_agent      TEXT NOT NULL DEFAULT '',
    input_summary        TEXT NOT NULL DEFAULT '',
    output_summary       TEXT NOT NULL DEFAULT '',
    error_code           TEXT NOT NULL DEFAULT '',
    error_message        TEXT NOT NULL DEFAULT '',
    timeout_seconds      INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_parent_task FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
CREATE INDEX idx_tasks_session_status ON tasks (session_id, status, updated_at DESC);
CREATE INDEX idx_tasks_status ON tasks (status, updated_at DESC);
CREATE INDEX idx_tasks_runtime_trace ON tasks (runtime_trace_id)
    WHERE runtime_trace_id != '';

-- A7. approvals ----------------------------------------------------------------
CREATE TABLE approvals (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    task_id     UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    approver    TEXT NOT NULL DEFAULT '',
    decision    TEXT NOT NULL DEFAULT '',
    reason      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_approvals_task ON approvals (task_id, created_at DESC);

-- A8. artifacts ----------------------------------------------------------------
CREATE TABLE artifacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    task_id        UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    artifact_type  TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL DEFAULT '',
    path           TEXT NOT NULL DEFAULT '',
    version        INTEGER NOT NULL DEFAULT 1,
    summary        TEXT NOT NULL DEFAULT '',
    card_json      JSONB NOT NULL DEFAULT '{}',
    metadata_json  JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_artifacts_session ON artifacts (session_id, updated_at DESC);
CREATE INDEX idx_artifacts_task ON artifacts (task_id, updated_at DESC);
CREATE INDEX idx_artifacts_type ON artifacts (session_id, artifact_type, updated_at DESC);

-- A9. events（统一 Gateway session_events + Replay replay_records）--------------
CREATE TABLE events (
    id           BIGSERIAL PRIMARY KEY,
    session_id   UUID NOT NULL,
    task_id      UUID,
    trace_id     TEXT NOT NULL DEFAULT '',
    seq          BIGINT NOT NULL,
    event_type   TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT '',
    agent_name   TEXT NOT NULL DEFAULT '',
    payload      JSONB NOT NULL DEFAULT '{}',
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_events_session_seq ON events (session_id, seq);
CREATE INDEX idx_events_task_time ON events (task_id, created_at, id)
    WHERE task_id IS NOT NULL;
CREATE INDEX idx_events_type_time ON events (event_type, created_at, id);
CREATE INDEX idx_events_trace ON events (trace_id, created_at)
    WHERE trace_id != '';

-- ============================================================================
-- 阶段 B：执行与追踪表（幂等、DAG、预算的存储基座）
-- ============================================================================

-- B1. task_dependencies --------------------------------------------------------
CREATE TABLE task_dependencies (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id           UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    depends_on_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    dependency_type   TEXT NOT NULL DEFAULT 'hard',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (task_id, depends_on_task_id),
    CONSTRAINT chk_no_self_dep CHECK (task_id != depends_on_task_id)
);
CREATE INDEX idx_task_deps_depends ON task_dependencies (depends_on_task_id);

-- B2. agent_runs ---------------------------------------------------------------
CREATE TABLE agent_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_name          TEXT NOT NULL,
    run_index           INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'pending',
    input_payload       JSONB NOT NULL DEFAULT '{}',
    output_payload      JSONB NOT NULL DEFAULT '{}',
    validation_passed   BOOLEAN,
    failure_type        TEXT NOT NULL DEFAULT '',
    failure_category    TEXT NOT NULL DEFAULT '',
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    latency_ms          INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_runs_task ON agent_runs (task_id, run_index);
CREATE INDEX idx_agent_runs_failed ON agent_runs (status, finished_at DESC)
    WHERE status IN ('failed', 'retrying');

-- B3. reviews ------------------------------------------------------------------
CREATE TABLE reviews (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_run_id  UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
    passed        BOOLEAN NOT NULL DEFAULT FALSE,
    score         INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
    issues_json   JSONB NOT NULL DEFAULT '[]',
    suggestions_json JSONB NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reviews_task ON reviews (task_id, created_at DESC);

-- B4. idempotency_keys ---------------------------------------------------------
CREATE TABLE idempotency_keys (
    key             TEXT PRIMARY KEY,
    invocation_id   TEXT UNIQUE NOT NULL,
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    skill_name      TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    result_json     JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_idempotency_expires ON idempotency_keys (expires_at)
    WHERE status IN ('completed', 'failed');

-- B5. skill_invocations --------------------------------------------------------
CREATE TABLE skill_invocations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invocation_id    TEXT UNIQUE NOT NULL,
    idempotency_key  TEXT,
    task_id          UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    skill_name       TEXT NOT NULL,
    skill_version    TEXT NOT NULL DEFAULT '',
    workflow_stage   TEXT NOT NULL DEFAULT '',
    agent_binding    TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending',
    input_summary    TEXT NOT NULL DEFAULT '',
    output_summary   TEXT NOT NULL DEFAULT '',
    error_category   TEXT NOT NULL DEFAULT '',
    error_code       TEXT NOT NULL DEFAULT '',
    retry_count      INTEGER NOT NULL DEFAULT 0,
    duration_ms      INTEGER NOT NULL DEFAULT 0,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_skill_invoc_task ON skill_invocations (task_id, created_at);
CREATE INDEX idx_skill_invoc_idem ON skill_invocations (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX idx_skill_invoc_status ON skill_invocations (status, created_at)
    WHERE status = 'failed';

-- B6. metric_events ------------------------------------------------------------
CREATE TABLE metric_events (
    id         BIGSERIAL PRIMARY KEY,
    task_id    UUID NOT NULL,
    agent      TEXT NOT NULL DEFAULT '',
    metric     TEXT NOT NULL,
    value      DOUBLE PRECISION NOT NULL,
    unit       TEXT NOT NULL DEFAULT 'count',
    tags       JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_metric_events_task ON metric_events (task_id, metric, created_at);
CREATE INDEX idx_metric_events_agent ON metric_events (agent, metric, created_at);
CREATE INDEX idx_metric_events_time ON metric_events (created_at);

-- ============================================================================
-- 阶段 C：扩展预留表
-- ============================================================================

-- C1. rule_versions ------------------------------------------------------------
CREATE TABLE rule_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name   TEXT NOT NULL,
    version     TEXT NOT NULL,
    path        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_name, version)
);

-- C2. spec_versions ------------------------------------------------------------
CREATE TABLE spec_versions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spec_name   TEXT NOT NULL,
    version     TEXT NOT NULL,
    path        TEXT NOT NULL,
    checksum    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (spec_name, version)
);

-- C3. workspace_files (文件索引——不存內容，內容從磁盤按需讀取) ---------------
CREATE TABLE workspace_files (
    session_id  TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    size_bytes  BIGINT NOT NULL DEFAULT 0,
    sha256_hash TEXT NOT NULL DEFAULT '',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, file_path)
);
CREATE INDEX idx_workspace_files_session ON workspace_files (session_id);
CREATE INDEX idx_workspace_files_path ON workspace_files (session_id, file_path);
