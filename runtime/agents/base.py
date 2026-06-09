from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentContext:
    task_id: str
    trace_id: str
    shared_state: dict[str, Any]


class Agent(Protocol):
    agent_id: str
    role: str

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]: ...
