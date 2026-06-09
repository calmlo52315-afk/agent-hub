# WebSocket Message Spec

## 1. Goal

Define the Stage 5 frontend <-> Gateway WebSocket envelope for chat streaming, task progress, approval prompts, artifact cards, and reconnect replay.

This spec reuses the core ideas from `message-spec.md` and aligns with ADR-020, while adding session-aware realtime fields needed by the frontend.

## 2. Design Principles

- All realtime traffic MUST use one JSON envelope.
- Raw strings are forbidden.
- The envelope MUST carry `session_id` so the Gateway can bind messages to one conversation.
- The envelope SHOULD preserve `task_id`, `trace_id`, `sender`, `receiver`, and `payload` semantics from `message-spec.md`.
- The protocol MUST support streaming order, ack, and reconnect replay.

## 3. Envelope Schema

```json
{
  "schema_version": "1.0",
  "event_id": "evt_001",
  "session_id": "sess_001",
  "task_id": "task_001",
  "trace_id": "trace_001",
  "type": "chat.message",
  "kind": "command|event|result|error",
  "seq": 12,
  "timestamp": "2026-06-05T10:00:00Z",
  "sender": {
    "type": "user|frontend|gateway|agent",
    "id": "user_001"
  },
  "receiver": {
    "type": "gateway|frontend|session|agent",
    "id": "sess_001"
  },
  "status": "accepted|running|streaming|success|failed|replayed",
  "in_reply_to": "evt_000",
  "ack": {
    "mode": "none|received|processed",
    "required": true
  },
  "payload": {}
}
```

## 4. Field Definitions

- `schema_version`: protocol version for Gateway/frontend compatibility checks.
- `event_id`: unique realtime event identifier on the WebSocket edge.
- `session_id`: required conversation/session identifier.
- `task_id`: optional for pure session events; required for task-scoped events.
- `trace_id`: correlates one request across Gateway, Runtime, and UI rendering.
- `type`: business event type consumed by the frontend.
- `kind`: high-level envelope purpose, compatible with internal message routing concepts.
- `seq`: monotonically increasing per-session event sequence assigned by Gateway; required for Gateway -> Frontend events and optional for client -> Gateway commands.
- `timestamp`: ISO-8601 UTC timestamp.
- `sender` / `receiver`: sender and receiver identity.
- `status`: delivery or execution state visible to the frontend.
- `in_reply_to`: correlates request/response or ack relationships.
- `ack`: indicates whether the sender expects acknowledgment and at which level.
- `payload`: typed business payload.

## 5. Event Types

### 5.1 Client -> Gateway Commands

- `session.subscribe`
- `chat.message`
- `task.retry.request`
- `task.cancel.request`
- `task.approval.submit`
- `conflict.resolution.submit`
- `heartbeat`

### 5.2 Gateway -> Frontend Events

- `connection.ready`
- `session.snapshot`
- `chat.message`
- `task.created`
- `task.updated`
- `task.completed`
- `review.completed`
- `artifact.created`
- `approval.required`
- `system.error`
- `ack`
- `heartbeat`

## 6. Payload Shapes

### 6.1 `session.subscribe`

```json
{
  "resume_from_seq": 0,
  "include_snapshot": true
}
```

### 6.2 `chat.message`

```json
{
  "message_id": "msg_001",
  "role": "user|agent|system",
  "format": "plain|markdown|diff",
  "content": "string",
  "stream_chunk": false
}
```

### 6.3 `task.updated`

```json
{
  "task_id": "task_001",
  "status": "created|planning|scheduled|running|blocked|retrying|completed|failed|cancelled",
  "summary": "string",
  "agent": "coding|review|artifact",
  "progress": {
    "current": 1,
    "total": 3
  }
}
```

### 6.4 `artifact.created`

```json
{
  "artifact_id": "artifact_001",
  "card": {}
}
```

`card` MUST follow `artifact-card-schema-spec.md`.

### 6.5 `approval.required`

```json
{
  "approval_id": "approval_001",
  "reason": "ownership_conflict|retry_exceeded|review_failed|large_change",
  "task_id": "task_001",
  "options": ["approve", "reject"]
}
```

### 6.6 `ack`

```json
{
  "ack_event_id": "evt_001",
  "ack_mode": "received|processed",
  "accepted": true,
  "reason": "string"
}
```

## 7. Sequencing

- Gateway MUST assign a strictly increasing `seq` for each session stream.
- Frontend MUST treat `seq` as the source of truth for render ordering during one session.
- When two events refer to the same `task_id`, frontend SHOULD additionally group them by `task_id` for timeline display.
- `timestamp` is used for audit and cross-system ordering, but replay resume MUST use `seq`.

## 8. Ack and Replay

- Commands that mutate state SHOULD set `ack.required=true`.
- Gateway MUST emit `ack` with `ack_mode=received` after validating envelope shape and session binding.
- Gateway MUST emit `ack` with `ack_mode=processed` after the command is accepted or rejected by business logic.
- On reconnect, frontend sends `session.subscribe` with `resume_from_seq`.
- If replay is available, Gateway MUST replay all missing events with `status=replayed`.
- If replay gap is too large or the cursor is expired, Gateway MUST send `session.snapshot` and continue from the latest `seq`.

## 9. Mapping to Internal Message Spec

- `event_id` maps to the edge-level message identifier.
- `task_id`, `trace_id`, `sender`, `receiver`, `kind`, `status`, `in_reply_to`, and `payload` reuse the same semantics as `message-spec.md`.
- Gateway MAY transform one external WebSocket event into one or more internal runtime messages.
- Runtime internal message details MUST NOT leak directly to the frontend without Gateway normalization.

## 10. Validation Rules

- Every WebSocket frame MUST be valid JSON.
- Every Gateway -> Frontend frame MUST contain `event_id`, `session_id`, `type`, `seq`, `timestamp`, and `payload`.
- Client -> Gateway commands MUST contain `event_id`, `session_id`, `type`, `timestamp`, and `payload`; `seq` MAY be omitted.
- Task-scoped events MUST carry `task_id`.
- Unknown `type` values MUST be rejected with `system.error`.
- Unknown fields SHOULD be ignored for forward compatibility.

## 11. References

- `docs/specs/ADR/ADR-018-Gateway-Boundary.md`
- `docs/specs/ADR/ADR-020-WebSocket Protocol`
- `docs/specs/contracts/message-spec.md`
- `docs/specs/contracts/artifact-card-schema-spec.md`
