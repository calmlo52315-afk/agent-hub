from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.agents.base import AgentContext
from runtime.harness.workspace import FileChange, Workspace


@dataclass(frozen=True)
class ArtifactAgent:
    """Collect stable outputs and materialize the final artifact package.

    The agent only writes artifact metadata and workspace snapshots. It does not
    participate in business-code generation or review decisions.

    Stage 8: Artifact paths are now session-scoped. Files go under
    ``workspace/{session_id}/tasks/{task_id}/artifacts/`` instead of the
    flat ``artifacts/{task_id}/`` structure.
    """

    workspace: Workspace
    agent_id: str = "artifact"
    role: str = "artifact"

    # ---------------------------------------------------------------
    # Path resolution
    # ---------------------------------------------------------------

    def _artifact_dir(self, task_id: str, legacy_root: str | None = None) -> str:
        """Resolve the artifact output directory for a task.

        Prefers the workspace-scoped path when available, falling back to
        the legacy flat ``artifacts/{task_id}`` path for compatibility.
        """
        # Stage 8: Use workspace-scoped directory
        ws_dir = self.workspace.task_artifact_dir(task_id)
        # Return as a relative path string (from repo_root) for consistency
        # with the existing contract
        try:
            rel = str(ws_dir.relative_to(self.workspace.repo_root))
        except ValueError:
            rel = str(ws_dir)
        return rel

    # ---------------------------------------------------------------
    # Main handler
    # ---------------------------------------------------------------

    def handle(self, *, payload: dict[str, Any], ctx: AgentContext) -> dict[str, Any]:
        """Persist artifact metadata and selected workspace snapshots.

        The return payload gives the Orchestrator a deterministic artifact
        directory and the list of files created during archival.
        """

        artifacts_root = payload.get("artifacts_root")
        applied_changes = payload.get("applied_changes") or []
        review = payload.get("review_result") or {}
        snapshots = payload.get("snapshots") or {}
        version = str(payload.get("version") or "v1")

        artifact_dir = self._artifact_dir(ctx.task_id, artifacts_root)

        created_files: list[str] = []

        # Build metadata
        metadata = {
            "schema_version": "1.0",
            "kind": "artifact-metadata",
            "task_id": ctx.task_id,
            "trace_id": ctx.trace_id,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "review": review,
            "applied_changes": applied_changes,
            # Stage 8: Include workspace context
            "workspace_id": self.workspace.session_id,
            "workspace_root": str(self.workspace.session_root),
        }

        # Write metadata.json
        self.workspace.apply_change(
            role=self.role,
            change=FileChange(
                action="create",
                path=f"{artifact_dir}/metadata.json",
                content=json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                base_hash=None,
            ),
        )
        created_files.append(f"{artifact_dir}/metadata.json")

        # Write snapshots (source file copies for archival)
        if isinstance(snapshots, dict):
            for src_path, content in snapshots.items():
                if not isinstance(src_path, str) or not isinstance(content, str):
                    continue
                dst_path = f"{artifact_dir}/workspace/{src_path}"
                self.workspace.apply_change(
                    role=self.role,
                    change=FileChange(action="create", path=dst_path, content=content, base_hash=None),
                )
                created_files.append(dst_path)

        summary = {
            "schema_version": "1.0",
            "kind": "artifact-summary",
            "artifact_dir": artifact_dir,
            "created_files": created_files,
            "version": version,
            "workspace_id": self.workspace.session_id,
        }

        return {
            "agent": self.agent_id,
            "role": self.role,
            "artifact_dir": artifact_dir,
            "created_files": created_files,
            "version": version,
            "summary": summary,
        }
