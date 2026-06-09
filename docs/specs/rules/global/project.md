# Purpose

Define the executable system-wide rules for AgentHub MVP runtime structure, agent coordination, and operational boundaries.

# Scope

- AgentHub MVP runtime
- Orchestrator
- Coding Agent
- Review Agent
- Artifact Agent
- Global resource management

# Responsibilities

- The runtime MUST execute all agents inside a single runtime and a single process.
- The Orchestrator MUST coordinate task flow, message routing, and cross-agent interaction.
- The system MUST use exactly three core agents in MVP:
  - Coding Agent
  - Review Agent
  - Artifact Agent
- Each core agent MUST operate under a single-responsibility boundary.
- Global resources MUST be maintained as shared singleton state within the runtime.

# Inputs

- `Task`
  - Definition: Work item submitted to the MVP workflow
  - Required fields: Not Defined
- `Message`
  - Definition: Structured communication unit routed through the Orchestrator
  - Required fields: Not Defined
- `GlobalResourceState`
  - Definition: Shared runtime state for file locks, file ownership, and state tables
  - Required fields: Not Defined

# Outputs

- `CodeDiff`
  - Produced by: Coding Agent
- `ReviewReport`
  - Produced by: Review Agent
- `ArtifactBundle`
  - Produced by: Artifact Agent
- `PreviewCard`
  - Produced by: Artifact Agent
- `FinalResult`
  - Definition: Final workflow output after artifact processing
  - Structure: Not Defined

# Workflow

- The MVP workflow MUST follow this sequence:
  - `Task Creation`
  - `Coding Agent`
  - `Review Agent`
  - `Artifact Agent`
  - `Final Result`
- All cross-agent interactions MUST be routed through the Orchestrator.
- Agents MUST NOT directly call or modify each other.

# Rules

- The system MUST run as a single-runtime monolith during MVP.
- The system MUST NOT use microservices, distributed deployment, multi-process agent execution, cross-host execution, message queues, or worker pools.
- All agents MUST be started from one main entry point.
- The runtime MUST keep all agents in the same process.
- The system MUST enforce the fixed MVP agent set of `Coding`, `Review`, and `Artifact`.
- The system MUST preserve strict role boundaries across agents.
- Cross-role operations MUST be routed through the Orchestrator.
- Shared runtime resources MUST be managed as global singletons.
- The system MUST maintain global singleton management for:
  - File locks
  - File ownership
  - State tables
- The Coding Agent MUST perform code generation, task planning, unit test generation, diff generation, and self-check.
- The Review Agent MUST perform code review, issue identification, issue classification, risk assessment, quality scoring, repair suggestion output, and conflict merge handling.
- The Artifact Agent MUST perform artifact collection, integrity validation, file snapshotting, version archiving, metadata generation, preview card generation, and project packaging output.

# Runtime Invariants

- Exactly one runtime process MUST host all MVP agents.
- Exactly one Orchestrator MUST manage agent coordination.
- Exactly three core agents MUST participate in the MVP main workflow.
- All agent-to-agent communication MUST pass through the Orchestrator.
- No agent may own an independent process or port.
- File locks, file ownership, and state tables MUST remain globally shared singleton resources.

# Constraints

- Runtime model: single runtime, single process, single host
- Deployment model: non-distributed only
- Agent topology: fixed to three core agents in MVP
- Communication model: unified message protocol through the Orchestrator only
- Resource model: shared in-memory runtime with singleton global resource control
- Startup model: one main entry point for all agents
- Extension details beyond the fixed MVP model: Not Defined

# Forbidden Actions

- Agents MUST NOT directly invoke another agent.
- Agents MUST NOT directly modify another agent.
- The system MUST NOT introduce additional core agents into the MVP main workflow.
- The system MUST NOT run any core agent as an independent process.
- The system MUST NOT expose a dedicated port for an individual agent.
- The system MUST NOT distribute agent execution across multiple hosts.
- The system MUST NOT replace Orchestrator-routed communication with direct agent communication.
- The Coding Agent MUST NOT perform code review or quality scoring.
- The Coding Agent MUST NOT modify global rules, file standards, or interface contracts.
- The Coding Agent MUST NOT alter original task requirements or specification documents.
- The Review Agent MUST NOT directly add or refactor business code, except for minor formatting correction.
- The Review Agent MUST NOT assign tasks.
- The Review Agent MUST NOT modify file ownership or lock state.
- The Artifact Agent MUST NOT generate or modify business code.
- The Artifact Agent MUST NOT generate or modify unit tests.
- The Artifact Agent MUST NOT perform code review or risk judgment.

# Examples

- Valid:
  - A task is created, routed to the Coding Agent by the Orchestrator, reviewed by the Review Agent, archived by the Artifact Agent, and then returned as the final result.
  - The Review Agent returns a review report with issues and repair suggestions through the Orchestrator.
  - The Artifact Agent generates a preview card and archive package without changing business code.
- Invalid:
  - The Coding Agent sends a direct request to the Artifact Agent.
  - The Review Agent refactors business logic instead of reporting the issue.
  - The Artifact Agent edits a test file.
  - A fourth core agent is added to the MVP main workflow.
  - One agent is started as a separate service on its own port.

# References

- `ADR-001-runtime-architecture`
- `ADR-002-agent-boundary`
