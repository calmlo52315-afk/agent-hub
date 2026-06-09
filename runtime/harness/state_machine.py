from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class IllegalStateTransitionError(RuntimeError):
    """Raised when the workflow receives an event without a legal transition."""


@dataclass
class WorkflowStateMachine:
    """Track workflow progress using an explicit transition table.

    The state machine is owned by the Orchestrator and acts as the single source
    of truth for legal stage progression during one task run.
    """

    state: str
    transitions: dict[tuple[str, str], str]
    terminal_states: set[str]

    @classmethod
    def from_execution_policy(cls, execution_policy: dict[str, Any], *, initial_state: str) -> "WorkflowStateMachine":
        """Build a state machine from execution rules loaded at runtime."""

        rules = (execution_policy.get("rules") or {}).get("workflow") or {}
        transitions_obj = rules.get("transitions") or []
        terminal_states_obj = rules.get("terminal_states") or []

        transitions: dict[tuple[str, str], str] = {}
        if isinstance(transitions_obj, list):
            for t in transitions_obj:
                if not isinstance(t, dict):
                    continue
                from_state = t.get("from")
                event = t.get("on")
                to_state = t.get("to")
                if isinstance(from_state, str) and isinstance(event, str) and isinstance(to_state, str):
                    transitions[(from_state, event)] = to_state

        terminal_states = {s for s in terminal_states_obj if isinstance(s, str)}

        return cls(state=initial_state, transitions=transitions, terminal_states=terminal_states)

    def transition(self, *, event: str, diagnostics: list[dict[str, Any]] | None = None) -> str:
        """Apply one event and record diagnostics for both legal and illegal moves."""

        diagnostics = diagnostics if diagnostics is not None else []

        if self.state in self.terminal_states:
            diagnostics.append(
                {
                    "kind": "illegal_transition",
                    "reason": "terminal_state",
                    "from": self.state,
                    "event": event,
                }
            )
            raise IllegalStateTransitionError(f"cannot transition from terminal state: {self.state}")

        key = (self.state, event)
        if key not in self.transitions:
            allowed = sorted([e for (s, e), _ in self.transitions.items() if s == self.state])
            diagnostics.append(
                {
                    "kind": "illegal_transition",
                    "reason": "no_rule",
                    "from": self.state,
                    "event": event,
                    "allowed_events": allowed,
                }
            )
            raise IllegalStateTransitionError(f"illegal transition: {self.state} --{event}--> ?")

        from_state = self.state
        to_state = self.transitions[key]
        self.state = to_state
        diagnostics.append({"kind": "transition", "from": from_state, "to": to_state, "event": event})
        return to_state
