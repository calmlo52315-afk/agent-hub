# ADR-022 Gateway Authentication

## Decision

Gateway authenticates all external clients.

Runtime MUST NOT authenticate frontend users directly.

Gateway issues session-bound credentials for REST and short-lived tickets for WebSocket upgrade.

Authentication and session persistence MUST be accessed through replaceable storage interfaces so that MVP can start with memory and later switch to SQLite, Postgres, or Redis without changing Gateway contracts.

---

## Background

Stage 5 introduces:

- IM-style frontend chat
- WebSocket streaming
- session management
- artifact and diff display
- human approval actions

According to ADR-018, Gateway is the only external entrypoint.

Therefore frontend authentication, session membership validation, and permission checks must stop at Gateway instead of leaking into Runtime.

Browser WebSocket clients also cannot rely on custom authorization headers in a portable way, so the system needs a dedicated WebSocket authentication path.

---

## Authentication Model

### Principal

MVP supports a lightweight principal model:

- `guest`
- `user`

Current MVP MAY start with anonymous `guest` sessions for demo purposes.

Future versions MAY map the same contract to Feishu, OAuth, or enterprise SSO identities.

---

### Credentials

Gateway manages two credential types:

1. `access_token`
   - Used for REST API calls
   - Bound to one principal
   - Carries expiry and session membership scope
2. `ws_ticket`
   - Used only for WebSocket upgrade
   - Short-lived
   - Bound to one `session_id`
   - Single-use or near single-use by policy

Runtime only receives trusted identity context forwarded by Gateway, never raw external credentials.

---

## Communication Flow

Frontend

↓

Gateway REST authentication / session bootstrap

↓

`access_token`

↓

Frontend requests `ws_ticket`

↓

Gateway validates token and issues ticket

↓

Frontend opens WebSocket with `ws_ticket`

↓

Gateway validates ticket and binds connection to session

↓

Gateway forwards trusted session context to Runtime

Direct Frontend → Runtime authentication is forbidden.

---

## Responsibilities

### Gateway

Responsible for:

- principal authentication
- token issuing and validation
- WebSocket ticket issuing and validation
- session membership validation
- permission gate for frontend-triggered actions
- approval audit logging

Must NOT:

- delegate external authentication to Runtime
- accept unauthenticated WebSocket upgrade
- expose internal Runtime credentials to frontend

---

### Runtime

Responsible for:

- orchestrating tasks after Gateway admission
- consuming trusted identity context
- respecting approval decisions already validated by Gateway

Must NOT:

- parse or validate user tokens
- manage browser login state
- expose direct login or WebSocket endpoints to frontend

---

## Storage Abstraction

Gateway MUST depend on interfaces instead of hard-coding one storage backend.

Minimum interfaces:

- `AuthStore`
  - stores `access_token` metadata
  - stores `ws_ticket` metadata
  - validates expiry and revocation
- `SessionStore`
  - stores session metadata
  - stores session membership
  - stores last acknowledged event cursor for replay/resume
- `ApprovalStore`
  - stores human approval records
  - stores decision reason and timestamp

MVP default implementation MAY use in-memory storage.

The same interfaces SHOULD allow SQLite, Postgres, or Redis implementations later.

---

## Security Constraints

- Gateway is the only component allowed to issue frontend-facing credentials.
- `ws_ticket` MUST expire quickly and MUST be scoped to one `session_id`.
- WebSocket authentication MUST complete before any chat or task command is accepted.
- Permission checks for retry, conflict resolution, and approval actions MUST happen at Gateway.
- Approval decisions MUST record `approver`, `session_id`, `task_id`, `decision`, `reason`, and `timestamp`.
- Runtime internal calls MUST trust Gateway identity context and MUST NOT reopen authentication logic.

---

## Future Evolution

Future versions may add:

- Feishu or OAuth login
- refresh tokens
- RBAC / workspace roles
- signed cookies
- shared-session membership policies

Gateway contracts remain stable if the credential backend changes.
