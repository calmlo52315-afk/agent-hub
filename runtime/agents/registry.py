from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any


@dataclass
class AgentCapability:
    """Agent capability definition"""
    id: str
    name: str
    description: str


@dataclass
class AgentInfo:
    """Agent information for registry"""
    id: str
    name: str
    avatar: str
    description: str
    capabilities: List[AgentCapability] = field(default_factory=list)
    version: str = "1.0.0"
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "description": self.description,
            "capabilities": [cap.__dict__ for cap in self.capabilities],
            "version": self.version,
            "enabled": self.enabled
        }


class AgentRegistry:
    """Central registry for all available agents"""

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    def register(self, agent_info: AgentInfo) -> None:
        """Register an agent with the registry"""
        self._agents[agent_info.id] = agent_info

    def get(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info by ID"""
        return self._agents.get(agent_id)

    def list_all(self) -> List[AgentInfo]:
        """List all registered agents"""
        return list(self._agents.values())

    def list_enabled(self) -> List[AgentInfo]:
        """List all enabled agents"""
        return [agent for agent in self._agents.values() if agent.enabled]

    def unregister(self, agent_id: str) -> None:
        """Unregister an agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]

    def exists(self, agent_id: str) -> bool:
        """Check if an agent exists"""
        return agent_id in self._agents


# Global registry instance
_registry: Optional[AgentRegistry] = None


def get_registry() -> AgentRegistry:
    """Get the global agent registry instance"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        _initialize_default_agents(_registry)
    return _registry


def _initialize_default_agents(registry: AgentRegistry) -> None:
    """Initialize default agents in the registry"""
    # Claude Code Agent
    claude_code = AgentInfo(
        id="claude_code",
        name="Claude Code",
        avatar="🤖",
        description="AI coding agent for writing and editing code",
        capabilities=[
            AgentCapability(id="coding", name="Coding", description="Write and edit code"),
            AgentCapability(id="file_edit", name="File Edit", description="Create and modify files"),
            AgentCapability(id="refactoring", name="Refactoring", description="Refactor and improve code")
        ]
    )
    registry.register(claude_code)

    # Codex Coding Agent
    codex_coding = AgentInfo(
        id="codex",
        name="Codex",
        avatar="⚡",
        description="AI coding agent for fast code generation (powered by Codex CLI)",
        capabilities=[
            AgentCapability(id="coding", name="Coding", description="Generate and edit code quickly"),
            AgentCapability(id="file_edit", name="File Edit", description="Create and modify files"),
            AgentCapability(id="refactoring", name="Refactoring", description="Refactor and improve code")
        ]
    )
    registry.register(codex_coding)

    # Orchestrator Agent
    orchestrator = AgentInfo(
        id="orchestrator",
        name="Orchestrator",
        avatar="🎯",
        description="AI task orchestrator for planning and coordination",
        capabilities=[
            AgentCapability(id="planning", name="Planning", description="Plan and break down tasks"),
            AgentCapability(id="coordination", name="Coordination", description="Coordinate multiple agents"),
            AgentCapability(id="synthesis", name="Synthesis", description="Synthesize and summarize results")
        ]
    )
    registry.register(orchestrator)
