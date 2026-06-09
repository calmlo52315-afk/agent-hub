# ADR-019 Session Model

## Decision

A Session contains multiple Tasks.

Task and Session are different concepts.

---

## Background

Users interact through conversations.

A single conversation may create multiple development tasks.

Therefore Session becomes the top-level container.

---

## Model

Session

├── Task-001

├── Task-002

└── Task-003

---

## Definitions

### Session

Represents:

- Conversation context
- User interaction history
- Task collection

Fields:

- session_id
- title
- created_at
- updated_at

---

### Task

Represents:

- One executable unit of work

Fields:

- task_id
- session_id
- status
- description

---

## Constraints

- Every Task MUST belong to one Session.
- A Session MAY contain multiple Tasks.
- Tasks MUST NOT exist without Session ownership.

---

## Future Evolution

Future versions may support:

- Shared Sessions
- Team Sessions
- Workspace-level Sessions

Current MVP only supports personal Sessions.