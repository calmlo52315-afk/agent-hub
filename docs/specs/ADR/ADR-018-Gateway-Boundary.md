# ADR-018 Gateway Boundary

## Decision

Frontend MUST communicate with Runtime through Gateway.

Runtime MUST NOT be directly exposed to external clients.

Gateway acts as the single entry point of the system.

---

## Background

The system currently uses a Single Runtime architecture.

As frontend capabilities increase (WebSocket, session management, authentication, artifact preview), exposing Runtime directly would couple UI and execution logic.

A dedicated Gateway provides a stable boundary.

---

## Responsibilities

### Gateway

Responsible for:

- REST API
- WebSocket Connection
- Session Management
- Authentication
- Request Validation
- Runtime Invocation
- Response Streaming

Must NOT:

- Execute Agent logic
- Execute Skill logic
- Modify Runtime state directly

---

### Runtime

Responsible for:

- Orchestration
- Agent Execution
- Skill Runtime
- Replay
- Metrics
- State Machine

Must NOT:

- Expose HTTP APIs
- Manage User Sessions
- Handle Authentication

---

## Communication Flow

Frontend

↓

Gateway

↓

Runtime

↓

Gateway

↓

Frontend

Direct Frontend → Runtime communication is forbidden.

---

## Constraints

- Gateway is the only external entrypoint.
- Runtime APIs are internal only.
- Runtime can be replaced without changing frontend contracts.

---

## Future Evolution

Current:

Gateway + Single Runtime

Future:

Gateway + Orchestrator + Worker Pool

Gateway contracts remain unchanged.