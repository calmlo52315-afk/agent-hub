# Purpose

Define the executable replay storage rules for AgentHub runtime, including storage engine choice, retention policy, and the scope/boundaries of replay data.

# Scope

- Task execution replay for debugging, demonstration, and post-mortem analysis
- Orchestrator and Harness event logging required for deterministic replay
- Artifact and message tracing needed for “可复现”

# Responsibilities

- The runtime MUST persist replay logs for each task.
- The runtime MUST enforce retention constraints to prevent unbounded growth.
- Replay data MUST be sufficient to reconstruct the task execution timeline at the message/event level.
- Replay MUST NOT be required for the main workflow correctness; it is an auxiliary capability.

# Inputs

- `Task`
  - Required fields: `task_id`
- `Message`
  - Required fields: `task_id`, `type`, `agent`, `timestamp`, `payload`
- `ExecutionEvent`
  - Required fields: `task_id`, `event_type`, `timestamp`
- `ArtifactMetadata`
  - Required fields: `task_id`, `artifact_id`, `timestamp`

# Outputs

- `ReplayRecord`
  - Definition: Stored record for timeline reconstruction
  - Structure: Not Defined (implementation-defined), but MUST include:
    - `task_id`
    - `timestamp`
    - `record_type` (message|event|artifact)
    - `payload` (structured JSON)
- `ReplaySession`
  - Definition: Queryable collection of ReplayRecord for a task
  - Structure: Not Defined

# Workflow

- On every Orchestrator-routed message:
  - Persist a ReplayRecord with `record_type=message`.
- On key workflow transitions (state changes, validation results, retries):
  - Persist a ReplayRecord with `record_type=event`.
- On artifact persistence:
  - Persist a ReplayRecord with `record_type=artifact`, referencing artifact metadata (not full contents).

# Rules

- Storage engine MUST be SQLite.
- Retention MUST be enforced:
  - `retain_days`: 30
  - `max_records`: 5000
- When retention limits are reached, the runtime MUST evict old records by time (oldest first).
- Replay data MUST be stored only for debugging/复盘/演示 and MUST NOT participate in the main business workflow.
- Replay logs MUST NOT contain secrets, API keys, or sensitive raw content beyond what is required to replay the timeline.

# Runtime Invariants

- For each `task_id`, records MUST be time-ordered by `timestamp` for replay consumption.
- Replay persistence failures MUST NOT crash the runtime; they MUST degrade to best-effort with an error event.

# Constraints

- High-concurrency scaling and time-series storage are out of scope for MVP.
- Advanced features (search/filter/rerun) are out of scope for Stage 2 unless explicitly required.

# Forbidden Actions

- The runtime MUST NOT store replay data indefinitely.
- Replay storage MUST NOT write outside the configured replay storage location.
- Replay logs MUST NOT include credentials or environment secrets.

# Examples

- Valid:
  - Persist a message record for each agent output routed by Orchestrator.
  - Persist an event record for each retry attempt with reason classification.
- Invalid:
  - Using Redis as the sole replay storage engine in MVP.
  - Storing unlimited replay records without eviction.

# References

- `ADR-008-replay-storage`

