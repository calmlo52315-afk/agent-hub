from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from runtime.harness.validator.schemas import (
    ArtifactAgentOutputModel,
    CodingAgentOutputModel,
    EnvelopeModel,
    ReviewAgentOutputModel,
)


class RuntimeValidationError(ValueError):
    def __init__(self, *, context: dict[str, Any], errors: list[dict[str, Any]]):
        super().__init__(json.dumps({"context": context, "errors": errors}, ensure_ascii=False))
        self.context = context
        self.errors = errors


@dataclass(frozen=True)
class RuntimeValidator:
    expected_envelope_schema_version: str

    def validate_envelope(self, *, envelope: dict[str, Any], direction: str) -> None:
        try:
            model = EnvelopeModel.model_validate(envelope)
        except ValidationError as e:
            raise RuntimeValidationError(
                context={"kind": "envelope", "direction": direction},
                errors=e.errors(),
            ) from e

        if model.schema_version != self.expected_envelope_schema_version:
            raise RuntimeValidationError(
                context={
                    "kind": "envelope",
                    "direction": direction,
                    "expected_schema_version": self.expected_envelope_schema_version,
                },
                errors=[
                    {
                        "type": "value_error.schema_version_mismatch",
                        "loc": ["schema_version"],
                        "msg": f"invalid schema_version: {model.schema_version}",
                        "input": model.schema_version,
                    }
                ],
            )

    def validate_agent_output(self, *, agent_id: str, payload: dict[str, Any]) -> None:
        model_cls = {
            "coding": CodingAgentOutputModel,
            "review": ReviewAgentOutputModel,
            "artifact": ArtifactAgentOutputModel,
        }.get(agent_id)
        if model_cls is None:
            return

        try:
            model_cls.model_validate(payload)
        except ValidationError as e:
            raise RuntimeValidationError(
                context={"kind": "agent_output", "agent_id": agent_id},
                errors=e.errors(),
            ) from e

