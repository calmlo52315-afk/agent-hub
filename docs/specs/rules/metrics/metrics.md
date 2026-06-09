# Purpose

Define the executable metrics collection rules for AgentHub runtime, including required metric items, tagging dimensions, and a JSON event format for export.

# Scope

- AgentHub runtime metrics collection in MVP and Stage 2 hardening
- Orchestrator lifecycle and per-agent execution boundaries
- Harness metrics module

# Responsibilities

- The runtime MUST collect metrics as structured events, tagged by `task_id` and `agent`.
- The Orchestrator MUST emit lifecycle metrics at task state transitions.
- The Harness MUST expose a single metrics sink interface for emitting and exporting metrics events.
- Metrics MUST be derived from runtime execution events and MUST NOT require changes to agent business logic.

# Inputs

- `Task`
  - Definition: A unit of work managed by the Orchestrator
  - Required fields: `task_id`
- `Message`
  - Definition: Unified structured message routed through the Orchestrator
  - Required fields: `task_id`, `type`, `agent`, `timestamp`
- `ExecutionEvent`
  - Definition: Internal runtime event captured at boundaries (agent start/end, validation pass/fail, retry, artifact persisted)
  - Required fields: `task_id`, `agent`, `event_type`, `timestamp`

# Outputs

- `MetricEvent` (JSON)
  - Definition: Single metric measurement or counter increment emitted by runtime
  - Format:
    ```json
    {
      "task_id": "task_001",
      "agent": "coding|review|artifact|orchestrator|harness",
      "metric": "task_success_rate|retry_count|review_pass_rate|token_usage|avg_response_time",
      "value": 1,
      "unit": "count|ms|token|ratio",
      "timestamp": "2026-05-30T12:00:00Z",
      "tags": {
        "stage": "stage-2-harness-stability",
        "schema_version": "v1"
      }
    }
    ```
- `MetricSnapshot`
  - Definition: Aggregated view computed from MetricEvent streams
  - Structure: Not Defined

# Workflow

- On task start:
  - Emit `avg_response_time` baseline start timestamp (internal) and task lifecycle event.
- On each agent execution boundary:
  - Emit latency and success/failure counters.
- On each validation outcome:
  - Emit validation pass/fail counters and tags for failure classification.
- On retry/fallback:
  - Emit `retry_count` increments and tags for retry reason.
- On task completion:
  - Emit success/failure and compute task-level aggregates.

# Rules

- The system MUST collect the following metrics (forced collection):
  - `task_success_rate`
  - `retry_count`
  - `review_pass_rate`
  - `token_usage`
  - `avg_response_time`
- All metrics MUST be dimensioned by:
  - `task_id`
  - `agent`
- Metrics events MUST be emitted as JSON objects (one event per line) to enable replay and offline analysis.
- Metrics collection MUST NOT block the main workflow. On sink failure, metrics emission MUST degrade to best-effort.
- Metrics collection MUST NOT log secrets, API keys, tokens, or raw repository file contents.

# Runtime Invariants

- Metric events MUST be attributable to exactly one `task_id`.
- Each MetricEvent MUST include `metric`, `value`, and `timestamp`.
- Metrics MUST be emitted from Orchestrator/Harness boundaries, not from ad-hoc agent internals.

# Constraints

- Aggregation and dashboards are out of scope for Stage 2. Only event emission and basic counters are required.
- Storage backend is Not Defined. Export mechanism may be file-based or in-memory for MVP.

# Forbidden Actions

- The runtime MUST NOT emit metric events containing secrets or sensitive content.
- The runtime MUST NOT require external services (Prometheus/OTel collector) as a hard dependency in MVP.
- Agents MUST NOT directly write metrics to storage. All metrics MUST flow through Harness.

# Examples

- Valid:
  - Emit `retry_count` when schema validation fails and retry is triggered.
  - Emit `avg_response_time` measured at agent boundary completion.
- Invalid:
  - Logging full code diffs or repository files as metric tags.
  - Emitting metrics without `task_id`.

# References

- `ADR-009-metrics`

