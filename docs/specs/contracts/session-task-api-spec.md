# Session / Task API Spec

## 1. Goal

Define the minimum HTTP API surface for Stage 5 session management, task inspection, history loading, approval actions, and reconnect preparation.

The API is designed for Gateway only. Runtime remains internal behind Gateway.

## 2. Design Principles

- Gateway is the only external HTTP entrypoint.
- Session and task read APIs SHOULD be simple enough for chat UI initial rendering.
- Mutating task actions MUST be explicit and auditable.
- Storage backend MUST be abstracted behind interfaces so the same API can run on memory, SQLite, Postgres, or Redis.

## 3. Common Conventions

### 3.1 Base Path

`/api/v1`

### 3.2 Authentication

- REST requests MUST carry `Authorization: Bearer <access_token>`.
- WebSocket ticket creation MUST also require a valid `access_token`.

### 3.3 Response Envelope

```json
{
  "request_id": "req_001",
  "data": {},
  "error": null
}
```

Error shape:

```json
{
  "request_id": "req_001",
  "data": null,
  "error": {
    "code": "string",
    "message": "string",
    "details": {}
  }
}
```

## 4. Session APIs

### 4.1 Create Session

`POST /api/v1/sessions`

Request:

```json
{
  "title": "Login page collaboration",
  "mode": "single_agent|multi_agent",
  "initial_message": "生成一个登录页面"
}
```

Response `data`:

```json
{
  "session_id": "sess_001",
  "title": "Login page collaboration",
  "mode": "multi_agent",
  "created_at": "2026-06-05T10:00:00Z",
  "updated_at": "2026-06-05T10:00:00Z",
  "last_event_seq": 0
}
```

### 4.2 List Sessions

`GET /api/v1/sessions?limit=20&cursor=`

Response `data`:

```json
{
  "items": [
    {
      "session_id": "sess_001",
      "title": "Login page collaboration",
      "last_message_preview": "生成一个登录页面",
      "updated_at": "2026-06-05T10:00:00Z",
      "task_count": 1
    }
  ],
  "next_cursor": null
}
```

### 4.3 Get Session Detail

`GET /api/v1/sessions/{session_id}`

Response `data`:

```json
{
  "session_id": "sess_001",
  "title": "Login page collaboration",
  "mode": "multi_agent",
  "created_at": "2026-06-05T10:00:00Z",
  "updated_at": "2026-06-05T10:01:00Z",
  "last_event_seq": 24
}
```

### 4.4 List Session Messages

`GET /api/v1/sessions/{session_id}/messages?before_seq=0&limit=50`

Response `data`:

```json
{
  "items": [],
  "next_before_seq": 0
}
```

Each item SHOULD follow the persisted shape of `websocket-message-spec.md`.

### 4.5 List Session Tasks

`GET /api/v1/sessions/{session_id}/tasks`

Response `data`:

```json
{
  "items": [
    {
      "task_id": "task_001",
      "status": "running",
      "title": "生成登录页面",
      "summary": "Coding Agent 正在输出页面结构",
      "updated_at": "2026-06-05T10:01:00Z"
    }
  ]
}
```

### 4.6 List Session Artifacts

`GET /api/v1/sessions/{session_id}/artifacts`

Response `data`:

```json
{
  "items": [
    {
      "artifact_id": "artifact_001",
      "task_id": "task_001",
      "card_type": "preview",
      "title": "Login Page Preview",
      "status": "ready",
      "updated_at": "2026-06-05T10:02:00Z"
    }
  ]
}
```

## 5. Task APIs

### 5.1 Get Task Detail

`GET /api/v1/tasks/{task_id}`

Response `data`:

```json
{
  "task_id": "task_001",
  "session_id": "sess_001",
  "title": "生成登录页面",
  "status": "running",
  "agent_flow": ["coding", "review", "artifact"],
  "current_agent": "coding",
  "retry_count": 0,
  "retry_limit": 2,
  "waiting_for_approval": false,
  "updated_at": "2026-06-05T10:01:00Z"
}
```

### 5.2 Retry Task

`POST /api/v1/tasks/{task_id}/retry`

Request:

```json
{
  "reason": "manual_retry_after_fix",
  "force": false
}
```

Rules:

- Allowed when task is retryable by policy.
- If retry limit has been exceeded, Gateway MUST require approval context before accepting.

### 5.3 Cancel Task

`POST /api/v1/tasks/{task_id}/cancel`

Request:

```json
{
  "reason": "user_cancelled"
}
```

### 5.4 Submit Approval Decision

`POST /api/v1/tasks/{task_id}/approvals/{approval_id}`

Request:

```json
{
  "decision": "approve|reject",
  "reason": "保留 review 通过版本"
}
```

This endpoint is used for:

- retry exceeded
- ownership conflict
- review failure
- large file modification

### 5.5 Resolve Conflict

`POST /api/v1/tasks/{task_id}/conflicts/{conflict_id}/resolve`

Request:

```json
{
  "resolution": "accept_latest_reviewed|retry_with_context|manual_merge",
  "reason": "保留最新 Review 通过版本"
}
```

### 5.6 Get Artifact Detail

`GET /api/v1/artifacts/{artifact_id}`

Response `data` MUST follow `artifact-card-schema-spec.md`.

## 6. Supporting Realtime API

### 6.1 Issue WebSocket Ticket

`POST /api/v1/ws-tickets`

Request:

```json
{
  "session_id": "sess_001"
}
```

Response `data`:

```json
{
  "session_id": "sess_001",
  "ws_ticket": "ticket_001",
  "expires_at": "2026-06-05T10:05:00Z"
}
```

## 7. Storage Interfaces

The API layer SHOULD depend on replaceable interfaces:

- `SessionRepository`
- `TaskRepository`
- `MessageRepository`
- `ApprovalRepository`
- `AuthRepository`

MVP MAY start with memory implementations.

Later implementations MAY use SQLite, Postgres, or Redis according to operational needs.

## 8. Validation Rules

- `session_id`, `task_id`, `approval_id`, and `conflict_id` MUST be opaque IDs.
- Every mutating endpoint MUST produce an audit record.
- Every mutating endpoint MUST validate session membership before execution.
- Task actions that require human confirmation MUST fail closed when approval context is missing.
- API responses MUST NOT expose internal Runtime-only state structures directly.

## 9. References

- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-019-Session-Model.md`
- `docs/specs/ADR/ADR-022-Gateway-Authentication.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`
- `docs/specs/contracts/websocket-message-spec.md`
