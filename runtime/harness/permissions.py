from __future__ import annotations

"""
最细粒度，最底层的安全约束层
文件系统权限，目录权限，危险操作，aitifact 产物的权限
白名单，黑名单
"""
import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PermissionDenied(PermissionError):
    pass


def _rel_posix(repo_root: Path, path: Path) -> str:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
    except ValueError as e:
        raise PermissionDenied(f"path out of repo_root: {path}") from e
    return rel.as_posix()


@dataclass(frozen=True)
class PermissionManager:
    repo_root: Path
    policy: dict[str, Any]

    def check(self, *, role: str, op: str, path: Path) -> None:
        rules = self.policy.get("rules") or {}
        fs = rules.get("filesystem") or {}

        rel_posix = _rel_posix(self.repo_root, path)

        if fs.get("repo_root_only", True):
            _rel_posix(self.repo_root, path)

        for denied in fs.get("deny_paths") or []:
            if fnmatch.fnmatch(rel_posix, denied):
                raise PermissionDenied(f"permission deny_path matched: {rel_posix} ({denied})")

        for entry in fs.get("deny_operations") or []:
            if entry.get("op") != op:
                continue
            for pat in entry.get("paths") or []:
                if fnmatch.fnmatch(rel_posix, pat):
                    raise PermissionDenied(entry.get("reason") or f"permission denied: {op} {rel_posix}")

        artifact = rules.get("artifact") or {}
        artifact_root = artifact.get("artifact_root")
        if isinstance(artifact_root, str):
            if rel_posix == artifact_root or rel_posix.startswith(artifact_root.rstrip("/") + "/"):
                allowed = artifact.get("artifact_write_allowed_roles") or []
                if op in ("write", "delete", "mkdir") and role not in allowed:
                    raise PermissionDenied(f"artifact write not allowed for role={role}")

        allow_ops = fs.get("allow_operations") or []
        if allow_ops:
            allowed = False
            for rule in allow_ops:
                if rule.get("op") != op:
                    continue
                for pat in rule.get("paths") or []:
                    if fnmatch.fnmatch(rel_posix, pat):
                        allowed = True
                        break
                if allowed:
                    break
            if not allowed:
                raise PermissionDenied(f"operation not allowed: {op} {rel_posix}")

    def check_dangerous(self, *, role: str, op: str) -> None:
        rules = self.policy.get("rules") or {}
        dangerous = rules.get("dangerous_operations") or {}
        if op == "shell" and bool(dangerous.get("deny_shell")):
            raise PermissionDenied(f"dangerous operation denied: shell (role={role})")
        if op == "network" and bool(dangerous.get("deny_network")):
            raise PermissionDenied(f"dangerous operation denied: network (role={role})")
        if op == "secret_logging" and bool(dangerous.get("deny_secret_logging")):
            raise PermissionDenied(f"dangerous operation denied: secret_logging (role={role})")
