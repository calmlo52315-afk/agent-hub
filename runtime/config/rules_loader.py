from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from runtime.config.rules_schema import validate_policy


@dataclass(frozen=True)
class Ruleset:
    #四类规则，执行规则，权限规则，数据归属规则，agent 通信规则
    execution: dict[str, Any]
    permission: dict[str, Any]
    ownership: dict[str, Any]
    communication: dict[str, Any]

#自定义错误类型
class RulesLoadError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise RulesLoadError(f"rules file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise RulesLoadError(f"invalid json: {path}") from e


def _require(obj: dict[str, Any], key: str, expected: object | None = None) -> Any:
    #强制检查字段必须存在，值必须正确
    if key not in obj:
        raise RulesLoadError(f"missing key: {key}")
    value = obj[key]
    if expected is not None and value != expected:
        raise RulesLoadError(f"invalid {key}: {value} (expected {expected})")
    return value


def load_ruleset(repo_root: Path | None = None) -> Ruleset:
    
    root = repo_root or Path(__file__).resolve().parents[2]
    rules_dir = root / "rules"
    index_path = rules_dir / "index.json"

    index = _read_json(index_path)
    _require(index, "schema_version", "1.0")
    _require(index, "kind", "rules-index")

    policies = _require(index, "policies")
    if not isinstance(policies, dict):
        raise RulesLoadError("policies must be an object")

    def load_policy(kind: str) -> dict[str, Any]:
        rel_path = policies.get(kind)
        if not isinstance(rel_path, str):
            raise RulesLoadError(f"missing policy path for: {kind}")
        policy_path = (rules_dir / rel_path).resolve()
        policy = _read_json(policy_path)
        _require(policy, "schema_version", "1.0")
        _require(policy, "kind", kind)
        _require(policy, "policy_id")
        _require(policy, "rules")
        try:
            validate_policy(policy, kind=kind)
        except ValidationError as e:
            raise RulesLoadError(f"invalid {kind} rules: {e.errors()}") from e
        except ValueError as e:
            raise RulesLoadError(f"invalid {kind} rules: {e}") from e
        return policy

    return Ruleset(
        execution=load_policy("execution"),
        permission=load_policy("permission"),
        ownership=load_policy("ownership"),
        communication=load_policy("communication"),
    )
