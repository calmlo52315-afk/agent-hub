# Purpose

Define the executable schema validation rules for AgentHub runtime using Pydantic, enforcing structured inputs/outputs across Orchestrator and all core agents.

# Scope

- Runtime schema validation for:
  - Orchestrator message envelope
  - Agent input/output payloads
  - Artifact metadata payloads
- Harness validator module

# Responsibilities

- The runtime MUST validate all agent outputs against Pydantic schemas before the outputs are accepted by downstream steps.
- The Orchestrator MUST reject messages that do not conform to the unified message envelope schema.
- The Harness MUST provide a single validation entrypoint and return a structured validation result.

# Inputs

- `MessageEnvelope`
  - Definition: Unified message protocol wrapper
  - Required fields: `task_id`, `type`, `agent`, `timestamp`, `payload`
- `AgentOutputPayload`
  - Definition: The `payload` field within MessageEnvelope when `type=agent_output`
  - Required fields: Not Defined (per-agent schema)

# Outputs

- `ValidationResult`
  - Structure (minimum):
    ```json
    {
      "passed": true,
      "errors": [],
      "schema": "AgentOutputSchemaV1"
    }
    ```

# Workflow

- On each message routed by Orchestrator:
  - Validate `MessageEnvelope`.
- On each agent output:
  - Validate against the agent-specific Pydantic model.
  - If failed:
    - Emit a structured validation error event.
    - Trigger retry/fallback per execution rules (Stage 2).

# Rules

- All agent outputs MUST be parseable JSON objects.
- All required fields for the corresponding schema MUST be present.
- Extra fields MUST be either rejected or explicitly allowed by schema configuration (implementation-defined), but behavior MUST be consistent across agents.
- The system MUST NOT accept:
  - Pure natural language output without JSON
  - JSON embedded inside Markdown fences as the only content
  - Unversioned or ambiguous payload structures
- Validation failures MUST be classified and propagated as structured errors for retry/fallback decisions.

# Runtime Invariants

- No downstream step (review/artifact) may consume an upstream output that failed schema validation.
- Validation must be deterministic given the same input payload and schema version.

# Constraints

- Stage 2 uses Pydantic as the validation engine.
- Cross-language schema sharing is out of scope for Stage 2.

# Forbidden Actions

- Agents MUST NOT bypass schema validation by directly mutating runtime state or files.
- The runtime MUST NOT silently coerce invalid payloads into valid ones without recording a validation error.

# Examples

- Valid:
  - Agent returns `{ "summary": "...", "files": [...], "diff": "..." }` matching the configured schema.
- Invalid:
  - Agent returns Markdown with a code fence around JSON but additional prose that breaks parsing expectations.
  - Agent returns missing required fields and proceeds to the next step without retry.

# References

- `ADR-011-message-protocol`
- Stage 2 decision: Pydantic validation engine

