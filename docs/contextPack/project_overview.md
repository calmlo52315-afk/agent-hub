# Project Overview

## Project Name

AgentHub

## Project Goal

AgentHub is a multi-agent collaborative coding platform.

The system coordinates multiple specialized AI agents to complete software development tasks through structured workflows, task routing, code review, and artifact management.

Current focus is MVP delivery and stable agent collaboration.

---

## Runtime Architecture

Current architecture uses a Single Runtime model.

All agents run inside the same process and communicate through structured messages managed by a central Orchestrator.

No microservices, distributed deployment, message queue, or worker pool are used in MVP.

---

## Core Agents

### Coding Agent

Responsible for:

* Task planning
* Code generation
* Unit test generation
* Diff generation

### Review Agent

Responsible for:

* Code review
* Risk assessment
* Quality scoring
* Improvement suggestions

### Artifact Agent

Responsible for:

* Artifact collection
* Metadata generation
* Version archiving
* Preview generation

---

## Communication

All communication between agents must use the unified Message Protocol.

Agents must not directly call or modify each other.

All interactions are routed through the Orchestrator.

---

## Development Principles

* Single responsibility for each agent
* Structured inputs and outputs
* Deterministic workflow execution
* Rule-driven behavior
* File ownership enforcement
* Task-oriented execution

---

## MVP Scope

The MVP workflow is:

Task Creation
→ Coding Agent
→ Review Agent
→ Artifact Agent
→ Final Result

Advanced features such as distributed execution, model routing, vector memory, and Kubernetes deployment are out of scope for MVP.
