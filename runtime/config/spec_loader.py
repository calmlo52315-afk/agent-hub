from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Spec:
    index: dict[str, Any]
    agents: dict[str, dict[str, Any]]
    message_envelope: dict[str, Any]
    schemas: dict[str, dict[str, Any]]
    registries: dict[str, dict[str, Any]]
    skills: dict[str, dict[str, Any]]


class SpecLoadError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SpecLoadError(f"spec file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise SpecLoadError(f"invalid json: {path}") from e


def _require(obj: dict[str, Any], key: str, expected: object | None = None) -> Any:
    if key not in obj:
        raise SpecLoadError(f"missing key: {key}")
    value = obj[key]
    if expected is not None and value != expected:
        raise SpecLoadError(f"invalid {key}: {value} (expected {expected})")
    return value


def _load_documents(spec_dir: Path, index_entries: dict[str, Any], *, field_name: str) -> dict[str, dict[str, Any]]:
    if not isinstance(index_entries, dict):
        raise SpecLoadError(f"{field_name} must be an object")

    documents: dict[str, dict[str, Any]] = {}
    for name, meta in index_entries.items():
        if not isinstance(meta, dict):
            raise SpecLoadError(f"{field_name}.{name} must be an object")
        path_value = _require(meta, "path")
        if not isinstance(path_value, str) or not path_value:
            raise SpecLoadError(f"{field_name}.{name}.path must be a non-empty string")
        doc = _read_json(spec_dir / path_value)
        if not isinstance(doc, dict):
            raise SpecLoadError(f"{field_name}.{name} must resolve to an object")
        documents[name] = doc
    return documents


def load_spec(repo_root: Path | None = None) -> Spec:
    root = repo_root or Path(__file__).resolve().parents[2]
    spec_dir = root / "runtime" / "specs" 
    index_path = spec_dir / "index.json"

    #元信息，系统版本
    index = _read_json(index_path)
    _require(index, "schema_version", "1.0")
    _require(index, "kind", "spec-index")

    agents = _require(index, "agents")
    if not isinstance(agents, dict):
        raise SpecLoadError("agents must be an object")

    #加载通信协议,agent 通信的标准格式
    message_envelope = _require(index, "message_envelope")
    if not isinstance(message_envelope, dict):
        raise SpecLoadError("message_envelope must be an object")
    _require(message_envelope, "schema_version", "1.0")
    schemas_index = _require(index, "schemas")
    registries_index = _require(index, "registries")
    schemas = _load_documents(spec_dir, schemas_index, field_name="schemas")
    registries = _load_documents(spec_dir, registries_index, field_name="registries")

    skills_registry = registries.get("skills") or {}
    skills = skills_registry.get("skills") if isinstance(skills_registry, dict) else {}
    if not isinstance(skills, dict):
        raise SpecLoadError("registries.skills.skills must be an object")

    return Spec(
        index=index,
        agents=agents,
        message_envelope=message_envelope,
        schemas=schemas,
        registries=registries,
        skills=skills,
    )
