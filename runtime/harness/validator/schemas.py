from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    id: str = Field(min_length=1)


class EnvelopeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    sender: PartyModel
    receiver: PartyModel
    kind: Literal["task", "result"]
    status: str = Field(min_length=1)
    in_reply_to: str | None = None
    payload: dict[str, Any]


class AgentOutputBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    role: str = Field(min_length=1)


class CodingChangeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["create", "update", "delete"]
    path: str = Field(min_length=1)
    content: str | None = None
    base_hash: str | None = None

    @model_validator(mode="after")
    def _validate_content_by_action(self) -> "CodingChangeModel":
        if self.action in ("create", "update") and not isinstance(self.content, str):
            raise ValueError("content required for create/update")
        return self


class CodingExampleDiffModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    diff: str = Field(min_length=1)


class CodingAgentOutputModel(AgentOutputBaseModel):
    plan: list[str]
    changes: list[CodingChangeModel]
    example_diff: list[CodingExampleDiffModel] | None = None


class ReviewIssueModel(BaseModel):
    """⭐ Stage 9: Allow extra fields for LLM review (severity, type, path, suggestion, line)."""
    model_config = ConfigDict(extra="allow")

    code: str = ""  # ⭐ Optional now — LLM review may not provide "code"
    message: str = Field(min_length=1)


class ReviewSummaryModel(BaseModel):
    """⭐ Stage 9: Allow extra fields (files_reviewed, total_issues)."""
    model_config = ConfigDict(extra="allow")

    task_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    applied_change_count: int = Field(ge=0)


class ReviewAgentOutputModel(AgentOutputBaseModel):
    """⭐ Stage 9: Allow extra fields (score, files_reviewed, skipped)."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass_: bool = Field(alias="pass")
    issues: list[ReviewIssueModel] = []  # ⭐ default empty list
    approval_required: bool = False
    summary: ReviewSummaryModel | None = None  # ⭐ allow None for skipped reviews


class ArtifactSummaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    artifact_dir: str = Field(min_length=1)
    created_files: list[str]
    version: str | None = None


class ArtifactAgentOutputModel(AgentOutputBaseModel):
    artifact_dir: str = Field(min_length=1)
    created_files: list[str]
    version: str | None = None
    summary: ArtifactSummaryModel
