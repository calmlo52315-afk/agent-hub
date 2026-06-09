from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.harness.ownership import OwnershipDenied, OwnershipManager
from runtime.harness.permissions import PermissionDenied, PermissionManager


@dataclass(frozen=True)
class ForbiddenActionViolation:
    code: str
    message: str
    change: dict[str, Any] | None = None


class ForbiddenActionError(PermissionDenied):
    def __init__(self, *, message: str, violations: list[ForbiddenActionViolation]):
        super().__init__(message)
        self.violations = violations


def enforce_changes_allowed(
    *,
    repo_root: Path,
    permission: PermissionManager,
    ownership: OwnershipManager,
    role: str,
    changes: list[dict[str, Any]],
) -> None:
    violations: list[ForbiddenActionViolation] = []
    for ch in changes:
        if not isinstance(ch, dict):
            continue
        action = ch.get("action")
        path_str = ch.get("path")
        if not isinstance(action, str) or not isinstance(path_str, str):
            continue

        abs_path = (repo_root / path_str).resolve()
        op = "delete" if action == "delete" else "write"

        try:
            if permission is not None:
                permission.check(role=role, op=op, path=abs_path)
        except PermissionDenied as e:
            violations.append(
                ForbiddenActionViolation(code="PERMISSION_DENIED", message=str(e), change={"action": action, "path": path_str})
            )
            continue

        try:
            if ownership is not None:
                ownership.assert_write_allowed(role=role, path=abs_path)
        except OwnershipDenied as e:
            violations.append(
                ForbiddenActionViolation(code="OWNERSHIP_DENIED", message=str(e), change={"action": action, "path": path_str})
            )
            continue

    if violations:
        msg = "; ".join(v.message for v in violations[:5])
        raise ForbiddenActionError(message=f"forbidden actions detected: {msg}", violations=violations)

