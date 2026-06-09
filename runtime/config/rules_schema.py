from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _BaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkflowTransitionModel(_BaseModel):
    from_: str = Field(min_length=1, alias="from")
    to: str = Field(min_length=1)
    on: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class WorkflowModel(_BaseModel):
    states: list[str] = Field(min_length=1)
    transitions: list[WorkflowTransitionModel] = Field(min_length=1)
    terminal_states: list[str] = Field(min_length=1)


class ExecutionTimeoutsModel(_BaseModel):
    coding_seconds: int = Field(gt=0)
    review_seconds: int = Field(gt=0)
    artifact_seconds: int = Field(gt=0)


class ExecutionRetryModel(_BaseModel):
    max_attempts: int = Field(ge=0)
    backoff_seconds: list[int]
    retryable_error_codes: list[str]


class ExecutionSkillBudgetModel(_BaseModel):
    max_tokens: int = Field(ge=0)
    max_cost_usd: float = Field(ge=0)


class ExecutionSkillsModel(_BaseModel):
    model_config = ConfigDict(extra="allow")  # ⭐ Stage 10: 允许 process_pool, batch_merge 等扩展字段

    default_timeout_seconds: int = Field(gt=0)
    skill_timeouts: dict[str, int]
    cost_budget: ExecutionSkillBudgetModel
    process_pool: dict[str, Any] = Field(default_factory=dict)
    batch_merge: dict[str, Any] = Field(default_factory=dict)


class FailureSemanticsModel(_BaseModel):
    on_failed: Literal["stop_workflow"]
    produce_error_artifact: bool


class ExecutionRulesModel(_BaseModel):
    workflow: WorkflowModel
    timeouts: ExecutionTimeoutsModel
    retry: ExecutionRetryModel
    skills: ExecutionSkillsModel
    failure_semantics: FailureSemanticsModel


class FsDenyOperationModel(_BaseModel):
    op: Literal["delete", "read", "write"]
    paths: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class FsAllowOperationConstraintModel(_BaseModel):
    must_pass_ownership_lock: bool | None = None


class FsAllowOperationModel(_BaseModel):
    op: Literal["delete", "read", "write"]
    paths: list[str] = Field(min_length=1)
    constraints: FsAllowOperationConstraintModel | None = None


class FilesystemRulesModel(_BaseModel):
    repo_root_only: bool
    deny_paths: list[str]
    deny_operations: list[FsDenyOperationModel]
    allow_operations: list[FsAllowOperationModel]


class DangerousOperationsModel(_BaseModel):
    deny_shell: bool
    deny_network: bool
    deny_secret_logging: bool


class ArtifactPermissionModel(_BaseModel):
    artifact_root: str = Field(min_length=1)
    artifact_write_allowed_roles: list[str] = Field(min_length=1)


class SkillPermissionRulesModel(_BaseModel):
    enabled: bool
    allowed_skills: list[str] = Field(min_length=1)
    role_skill_whitelist: dict[str, list[str]]
    deny_dangerous_operations: list[Literal["shell", "network", "secret_logging"]]


class PermissionRulesModel(_BaseModel):
    filesystem: FilesystemRulesModel
    dangerous_operations: DangerousOperationsModel
    artifact: ArtifactPermissionModel
    skills: SkillPermissionRulesModel


class OwnerRuleModel(_BaseModel):
    glob: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    write_roles: list[str] = Field(min_length=1)


class LockingRulesModel(_BaseModel):
    mode: str = Field(min_length=1)
    required_for_ops: list[str] = Field(min_length=1)
    default_timeout_seconds: int = Field(gt=0)


class VersionCheckRulesModel(_BaseModel):
    enabled: bool
    strategy: str = Field(min_length=1)
    on_mismatch: str = Field(min_length=1)


class MinimalMergeRulesModel(_BaseModel):
    enabled: bool
    policy: str = Field(min_length=1)
    allowed_actions: list[str] = Field(min_length=1)


class OwnershipRulesModel(_BaseModel):
    owners: list[OwnerRuleModel] = Field(min_length=1)
    locking: LockingRulesModel
    version_check: VersionCheckRulesModel
    minimal_merge: MinimalMergeRulesModel


class RoutingRulesModel(_BaseModel):
    orchestrator_required: bool
    deny_direct_agent_to_agent: bool
    allowed_receivers: list[str] = Field(min_length=1)


class SharedStateRulesModel(_BaseModel):
    read_via_orchestrator_only: bool
    state_keys: list[str] = Field(min_length=1)


class MessageConstraintsRulesModel(_BaseModel):
    require_envelope: bool
    envelope_schema_version: str = Field(min_length=1)
    max_payload_bytes: int = Field(gt=0)


class CommunicationRulesModel(_BaseModel):
    routing: RoutingRulesModel
    shared_state: SharedStateRulesModel
    message_constraints: MessageConstraintsRulesModel


class PolicyBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    description: str | None = None
    rules: dict[str, Any]


def validate_policy(policy: dict[str, Any], *, kind: str) -> None:
    PolicyBaseModel.model_validate(policy)

    rules = policy.get("rules")
    if kind == "execution":
        ExecutionRulesModel.model_validate(rules)
    elif kind == "permission":
        PermissionRulesModel.model_validate(rules)
    elif kind == "ownership":
        OwnershipRulesModel.model_validate(rules)
    elif kind == "communication":
        CommunicationRulesModel.model_validate(rules)
