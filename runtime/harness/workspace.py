from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.harness.ownership import OwnershipManager
from runtime.harness.permissions import PermissionManager


class VersionMismatch(RuntimeError):
    pass


class WorkspaceError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


@dataclass(frozen=True)
class FileChange:
    action: str
    path: str
    content: str | None = None
    base_hash: str | None = None


@dataclass(frozen=True)
class AppliedChange:
    action: str
    path: str
    base_hash: str | None
    new_hash: str | None


@dataclass
class Workspace:
    """Session-scoped workspace — one per conversation.

    Stage 8 V2 refactor: Workspace is now tied to a Session, not a Task.
    Supports three workspace types: scratch, project, imported.

    - scratch:  Short-lived, for scripts/demos/tests. Auto-created.
    - project:  Long-lived, for multi-task development projects.
    - imported: Brings in an existing directory or cloned repo.
    """

    repo_root: Path
    permission: PermissionManager
    ownership: OwnershipManager
    ruleset_ownership: dict[str, Any]

    # Stage 8: Session-scoped workspace fields
    session_id: str = "default"
    session_root: Path | None = None
    source_root: Path | None = None

    # Stage 8 V2: Workspace type
    workspace_type: str = "scratch"   # "scratch" | "project" | "imported"
    source_path: str | None = None    # original path for imported workspaces

    def __post_init__(self):
        """Derive session_root and source_root from session_id or source_path.

        ⭐ Stage 9: For "imported" workspaces, source_root IS the original directory.
        No copying — Agent writes directly into the user's actual project folder.
        For "scratch" and "project", source_root defaults to workspace/{session_id}/source/.
        """
        if self.session_root is None:
            self.session_root = self.repo_root / "workspace" / self.session_id
        if self.source_root is None:
            # ⭐ imported 工作区：直接在用户的原路径下读写代码
            if self.workspace_type == "imported" and self.source_path:
                self.source_root = Path(self.source_path).resolve()
            else:
                self.source_root = self.session_root / "source"

    # ---------------------------------------------------------------
    # Factory & lifecycle
    # ---------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        repo_root: Path,
        session_id: str,
        permission: PermissionManager,
        ownership: OwnershipManager,
        ruleset_ownership: dict[str, Any],
        workspace_type: str = "scratch",
        source_path: str | None = None,
    ) -> "Workspace":
        """Create a new session-scoped workspace with standard directory layout.

        Directory structure::

            workspace/{session_id}/
                source/           # shared source files (all tasks)
                tasks/            # per-task artifact archive
                snapshots/        # version snapshots for rollback
                bundles/          # session-level packages
                preview/          # preview resources
                workspace_meta.json

        Args:
            workspace_type: "scratch", "project", or "imported"
            source_path: For "imported" type, the original directory path
        """
        session_root = repo_root / "workspace" / session_id
        source_root = session_root / "source"

        # Ensure directory structure
        (source_root).mkdir(parents=True, exist_ok=True)
        (session_root / "tasks").mkdir(parents=True, exist_ok=True)
        (session_root / "snapshots").mkdir(parents=True, exist_ok=True)
        (session_root / "bundles").mkdir(parents=True, exist_ok=True)
        (session_root / "preview").mkdir(parents=True, exist_ok=True)

        # For imported workspaces, record the source
        resolved_source = source_path
        if workspace_type == "imported" and source_path:
            import os
            resolved_source = str(Path(source_path).resolve())
            # Write a .source file for reference
            (session_root / ".source").write_text(resolved_source)

        # Write workspace metadata
        meta = {
            "workspace_id": session_id,
            "session_id": session_id,
            "root_path": str(session_root),
            "workspace_type": workspace_type,
            "source_path": resolved_source,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        (session_root / "workspace_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )

        return cls(
            repo_root=repo_root,
            permission=permission,
            ownership=ownership,
            ruleset_ownership=ruleset_ownership,
            session_id=session_id,
            session_root=session_root,
            source_root=source_root,
            workspace_type=workspace_type,
            source_path=resolved_source,
        )

    @classmethod
    def load(
        cls,
        *,
        repo_root: Path,
        session_id: str,
        permission: PermissionManager,
        ownership: OwnershipManager,
        ruleset_ownership: dict[str, Any],
        workspace_type: str = "scratch",
        source_path: str | None = None,
    ) -> "Workspace":
        """Load an existing session workspace (creates if not exists)."""
        session_root = repo_root / "workspace" / session_id
        if not session_root.exists():
            return cls.create(
                repo_root=repo_root,
                session_id=session_id,
                permission=permission,
                ownership=ownership,
                ruleset_ownership=ruleset_ownership,
                workspace_type=workspace_type,
                source_path=source_path,
            )

        # Read existing metadata if available
        meta_path = session_root / "workspace_meta.json"
        existing_type = workspace_type
        existing_source = source_path
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                existing_type = meta.get("workspace_type", workspace_type)
                existing_source = meta.get("source_path", source_path)
            except Exception:
                pass

        return cls(
            repo_root=repo_root,
            permission=permission,
            ownership=ownership,
            ruleset_ownership=ruleset_ownership,
            session_id=session_id,
            session_root=session_root,
            source_root=session_root / "source",
            workspace_type=existing_type,
            source_path=existing_source,
        )

    # ---------------------------------------------------------------
    # Path helpers
    # ---------------------------------------------------------------

    def task_dir(self, task_id: str) -> Path:
        """Return the per-task sub-directory within this workspace."""
        d = self.session_root / "tasks" / task_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def task_artifact_dir(self, task_id: str) -> Path:
        """Return the artifact sub-directory for a task."""
        d = self.task_dir(task_id) / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def task_diff_dir(self, task_id: str) -> Path:
        """Return the diff sub-directory for a task."""
        d = self.task_dir(task_id) / "diffs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def snapshot_dir(self) -> Path:
        return self.session_root / "snapshots"

    def bundle_dir(self) -> Path:
        return self.session_root / "bundles"

    def preview_dir(self) -> Path:
        return self.session_root / "preview"

    # ---------------------------------------------------------------
    # Source file paths
    # ---------------------------------------------------------------

    def _abs(self, rel_path: str) -> Path:
        """Resolve a relative path against the source_root (shared working dir)."""
        return (self.source_root / rel_path).resolve()

    def _abs_repo(self, rel_path: str) -> Path:
        """Resolve a relative path against the repo_root (for backwards compat)."""
        return (self.repo_root / rel_path).resolve()

    def read_text(self, *, role: str, rel_path: str) -> str:
        path = self._abs(rel_path)
        self.permission.check(role=role, op="read", path=path)
        return path.read_text(encoding="utf-8")

    def file_hash(self, *, rel_path: str) -> str | None:
        path = self._abs(rel_path)
        if not path.exists() or not path.is_file():
            return None
        return sha256_file(path)

    # ---------------------------------------------------------------
    # File change application (core logic, unchanged safety semantics)
    # ---------------------------------------------------------------

    def apply_change(self, *, role: str, change: FileChange) -> AppliedChange:
        """Apply a file change within the session source directory.

        Permission checks, version validation, and file locking are enforced
        exactly as before — the only difference is that paths resolve under
        ``source_root`` (workspace/{session_id}/source/) instead of repo_root.
        """
        if change.action not in ("create", "update", "delete"):
            raise WorkspaceError(f"unsupported action: {change.action}")

        path = self._abs(change.path)
        op = "delete" if change.action == "delete" else "write"
        self.permission.check(role=role, op=op, path=path)

        version_check = (self.ruleset_ownership.get("rules") or {}).get("version_check") or {}
        version_enabled = bool(version_check.get("enabled"))
        on_mismatch = version_check.get("on_mismatch") or "fail_with_error"

        minimal_merge = (self.ruleset_ownership.get("rules") or {}).get("minimal_merge") or {}
        minimal_enabled = bool(minimal_merge.get("enabled"))
        minimal_policy = minimal_merge.get("policy") or "reject_if_base_changed"

        if change.action in ("create", "update"):
            self.ownership.assert_write_allowed(role=role, path=path)

        with self.ownership.acquire_write_lock(role=role, path=path):
            exists = path.exists()
            current_hash = sha256_file(path) if exists and path.is_file() else None

            # Auto-correct action based on actual file state
            actual_action = change.action
            if change.action == "create" and exists:
                actual_action = "update"
            elif change.action == "update" and not exists:
                actual_action = "create"

            if actual_action == "create":
                if change.content is None:
                    raise WorkspaceError("create requires content")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(change.content, encoding="utf-8")
                new_hash = sha256_file(path)
                return AppliedChange(action="create", path=change.path, base_hash=None, new_hash=new_hash)

            if actual_action == "update":
                if change.content is None:
                    raise WorkspaceError("update requires content")
                if version_enabled and change.base_hash is not None and current_hash != change.base_hash:
                    if on_mismatch == "fail_with_error":
                        raise VersionMismatch(
                            f"version mismatch: {change.path} current={current_hash} base={change.base_hash}"
                        )
                if minimal_enabled and minimal_policy == "reject_if_base_changed":
                    if change.base_hash is not None and current_hash != change.base_hash:
                        raise VersionMismatch(
                            f"base changed (minimal_merge): {change.path} current={current_hash} base={change.base_hash}"
                        )

                path.write_text(change.content, encoding="utf-8")
                new_hash = sha256_file(path)
                return AppliedChange(action="update", path=change.path, base_hash=change.base_hash, new_hash=new_hash)

            if change.action == "delete":
                self.ownership.assert_write_allowed(role=role, path=path)
                if not exists:
                    return AppliedChange(action="delete", path=change.path, base_hash=None, new_hash=None)
                if path.is_dir():
                    raise WorkspaceError(f"delete refused: path is dir: {change.path}")
                if version_enabled and change.base_hash is not None and current_hash != change.base_hash:
                    if on_mismatch == "fail_with_error":
                        raise VersionMismatch(
                            f"version mismatch: {change.path} current={current_hash} base={change.base_hash}"
                        )
                path.unlink()
                return AppliedChange(action="delete", path=change.path, base_hash=change.base_hash, new_hash=None)

        raise WorkspaceError("unreachable")

    # ---------------------------------------------------------------
    # Workspace metadata
    # ---------------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        """Return workspace metadata as a dict."""
        meta_path = self.session_root / "workspace_meta.json"
        if meta_path.exists():
            return json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "workspace_id": self.session_id,
            "session_id": self.session_id,
            "root_path": str(self.session_root),
            "status": "active",
        }

    def touch(self):
        """Update the workspace updated_at timestamp."""
        meta = self.meta()
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        (self.session_root / "workspace_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )

    def source_file_count(self) -> int:
        """Count files in the shared source directory."""
        if not self.source_root or not self.source_root.exists():
            return 0
        return sum(1 for _ in self.source_root.rglob("*") if _.is_file())

    def seed_files(self, files: list[dict[str, str]]) -> dict[str, any]:
        """Write multiple files into the source directory.

        Used by the frontend to populate an imported workspace with the
        user's actual directory contents.

        Args:
            files: List of {path, content} dicts with paths relative to source_root.

        Returns:
            dict with 'seeded', 'skipped', 'errors' counts.
        """
        seeded = 0
        skipped = 0
        errors: list[dict[str, str]] = []
        resolved_root = self.source_root.resolve()

        for f in files:
            rel_path = f["path"]
            content = f.get("content", "")
            abs_path = self._abs(rel_path)

            # Path traversal protection
            try:
                abs_path.resolve().relative_to(resolved_root)
            except ValueError:
                errors.append({"path": rel_path, "error": "path_traversal"})
                continue

            abs_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                abs_path.write_text(content, encoding="utf-8")
                seeded += 1
            except Exception as exc:
                errors.append({"path": rel_path, "error": str(exc)})
                skipped += 1

        return {"seeded": seeded, "skipped": skipped, "errors": errors}

    def cleanup(self, *, keep_snapshots: bool = False):
        """Remove the workspace directory.

        Args:
            keep_snapshots: If True, preserve the snapshots/ directory.
        """
        if not self.session_root or not self.session_root.exists():
            return
        if keep_snapshots:
            # Only remove source, tasks, bundles, preview; keep snapshots
            for sub in ("source", "tasks", "bundles", "preview"):
                p = self.session_root / sub
                if p.exists():
                    import shutil
                    shutil.rmtree(p)
        else:
            import shutil
            shutil.rmtree(self.session_root)
