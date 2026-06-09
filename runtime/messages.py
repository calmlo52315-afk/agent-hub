from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class MessageValidationError(ValueError):
    """Raised when a message envelope violates the shared protocol schema."""


@dataclass(frozen=True)
class Party:
    """Identify one endpoint that participates in a routed message exchange."""

    type: str
    id: str


@dataclass(frozen=True)
class Envelope:
    """Represent the canonical message envelope used by the runtime.

    The envelope keeps routing metadata and the structured business payload in one
    object so replay, validation and tracing can consume the same shape.
    """

    schema_version: str
    message_id: str
    task_id: str
    trace_id: str
    timestamp: str
    sender: Party
    receiver: Party
    kind: str
    status: str
    in_reply_to: str | None
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the envelope to the JSON-compatible dict used at boundaries."""

        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "sender": {"type": self.sender.type, "id": self.sender.id},
            "receiver": {"type": self.receiver.type, "id": self.receiver.id},
            "kind": self.kind,
            "status": self.status,
            "in_reply_to": self.in_reply_to,
            "payload": self.payload,
        }

    def payload_bytes(self) -> int:
        """Return the UTF-8 payload size used by runtime payload guards."""

        return len(json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def new_trace_id() -> str:
    """Generate a trace identifier shared across one execution chain."""

    return uuid.uuid4().hex


def new_message_id() -> str:
    """Generate a unique message identifier for one envelope instance."""

    return uuid.uuid4().hex


def make_envelope(
    *,
    schema_version: str,
    task_id: str,
    trace_id: str,
    sender_type: str,
    sender_id: str,
    receiver_type: str,
    receiver_id: str,
    kind: str,
    status: str,
    payload: dict[str, Any] | None = None,
    in_reply_to: str | None = None,
) -> Envelope:
    """Build a normalized envelope for cross-component communication."""

    return Envelope(
        schema_version=schema_version,
        message_id=new_message_id(),
        task_id=task_id,
        trace_id=trace_id,
        timestamp=now_iso(),
        sender=Party(type=sender_type, id=sender_id),
        receiver=Party(type=receiver_type, id=receiver_id),
        kind=kind,
        status=status,
        in_reply_to=in_reply_to,
        payload=payload or {},
    )


def validate_envelope(obj: dict[str, Any], *, expected_schema_version: str) -> None:
    """Perform lightweight structural validation for a message envelope."""

    if obj.get("schema_version") != expected_schema_version:
        raise MessageValidationError(
            f"invalid schema_version: {obj.get('schema_version')} (expected {expected_schema_version})"
        )

    for key in (
        "message_id",
        "task_id",
        "trace_id",
        "timestamp",
        "sender",
        "receiver",
        "kind",
        "status",
        "payload",
    ):
        if key not in obj:
            raise MessageValidationError(f"missing field: {key}")

    sender = obj["sender"]
    receiver = obj["receiver"]
    if not isinstance(sender, dict) or "type" not in sender or "id" not in sender:
        raise MessageValidationError("invalid sender")
    if not isinstance(receiver, dict) or "type" not in receiver or "id" not in receiver:
        raise MessageValidationError("invalid receiver")

    payload = obj["payload"]
    if payload is None:
        raise MessageValidationError("payload must not be null")
    if not isinstance(payload, dict):
        raise MessageValidationError("payload must be an object")
