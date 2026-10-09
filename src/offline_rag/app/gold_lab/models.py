"""Strict Gold Lab persistence contracts (16F-A)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    ABSOLUTE_RELEVANCE_CONTRACT,
    AUXILIARY_PREFERENCE_CONTRACT,
    HARD_CALL_DESIGNATION_CONTRACT,
    HARD_CALLS_SCHEMA,
    LEDGER_SCHEMA,
    QUESTION_CHECK_CONTRACT,
    SELECTION_POLICY_CONTRACT,
    hard_call_designation_id,
    validate_campaign_id,
    validate_hard_call_designation_id,
    validate_judgment_id,
    validate_project_id,
    validate_query_fingerprint,
    validate_record_id,
    validate_request_fingerprint,
    validate_selection_policy_fingerprint,
    validate_task_id,
)
from offline_rag.core.ids import canonical_config_hash
from offline_rag.domain.types import NonEmptyStr


class GoldProjectType(StrEnum):
    BENCHMARK = "benchmark"
    IMPROVEMENT = "improvement"


class GoldProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class GoldCampaignStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class GoldLedgerRecordType(StrEnum):
    QUESTION_CHECK = "question_check"
    ABSOLUTE_RELEVANCE = "absolute_relevance"
    AUXILIARY_PREFERENCE = "auxiliary_preference"


def _assert_json_compatible(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GoldLabError(
                "selection_policy_parameters_invalid",
                f"non-finite float at {path}",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_compatible(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise GoldLabError(
                    "selection_policy_parameters_invalid",
                    f"non-string object key at {path}",
                )
            _assert_json_compatible(item, path=f"{path}.{key}")
        return
    raise GoldLabError(
        "selection_policy_parameters_invalid",
        f"non-JSON-compatible value at {path}: {type(value).__name__}",
    )


def selection_policy_fingerprint(
    *,
    selection_policy_id: str,
    project_type: GoldProjectType | str,
    parameters: Mapping[str, Any],
) -> str:
    _assert_json_compatible(parameters, path="parameters")
    return canonical_config_hash(
        {
            "contract": SELECTION_POLICY_CONTRACT,
            "selection_policy_id": selection_policy_id,
            "project_type": str(project_type),
            "parameters": dict(parameters),
        }
    )


class GoldSelectionPolicy(BaseModel):
    """gold-selection-policy-v1."""

    model_config = ConfigDict(extra="forbid")

    selection_policy_id: NonEmptyStr
    project_type: GoldProjectType
    parameters: dict[str, Any] = Field(default_factory=dict)
    selection_policy_fingerprint: NonEmptyStr

    @model_validator(mode="after")
    def _validate_fingerprint(self) -> GoldSelectionPolicy:
        _assert_json_compatible(self.parameters, path="parameters")
        expected = selection_policy_fingerprint(
            selection_policy_id=self.selection_policy_id,
            project_type=self.project_type,
            parameters=self.parameters,
        )
        try:
            validate_selection_policy_fingerprint(self.selection_policy_fingerprint)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc
        if self.selection_policy_fingerprint != expected:
            raise ValueError("selection_policy_fingerprint does not match recomputation")
        return self


def build_selection_policy(
    *,
    selection_policy_id: str,
    project_type: GoldProjectType | str,
    parameters: Mapping[str, Any] | None = None,
) -> GoldSelectionPolicy:
    params = dict(parameters or {})
    fingerprint = selection_policy_fingerprint(
        selection_policy_id=selection_policy_id,
        project_type=project_type,
        parameters=params,
    )
    return GoldSelectionPolicy(
        selection_policy_id=selection_policy_id,
        project_type=GoldProjectType(project_type),
        parameters=params,
        selection_policy_fingerprint=fingerprint,
    )


class GoldProject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: NonEmptyStr
    workspace_id: NonEmptyStr
    title: NonEmptyStr
    description: str = ""
    project_type: GoldProjectType
    created_at: datetime
    status: GoldProjectStatus = GoldProjectStatus.ACTIVE

    @field_validator("project_id")
    @classmethod
    def _project_id_grammar(cls, value: str) -> str:
        try:
            return validate_project_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("workspace_id")
    @classmethod
    def _workspace_id_safe(cls, value: str) -> str:
        text = value.strip()
        if not text or "/" in text or "\\" in text or ".." in text:
            raise ValueError("invalid workspace_id")
        return text


class GoldCampaign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: NonEmptyStr
    project_id: NonEmptyStr
    workspace_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr
    corpus_name: NonEmptyStr
    selection_policy: GoldSelectionPolicy
    baseline_authoring_run_id: NonEmptyStr
    baseline_sha256: NonEmptyStr
    workspace_revision_at_creation: int = Field(ge=1)
    created_at: datetime
    status: GoldCampaignStatus = GoldCampaignStatus.OPEN

    @field_validator("campaign_id")
    @classmethod
    def _campaign_id_grammar(cls, value: str) -> str:
        try:
            return validate_campaign_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("project_id")
    @classmethod
    def _project_id_grammar(cls, value: str) -> str:
        try:
            return validate_project_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("baseline_sha256")
    @classmethod
    def _sha256_hex(cls, value: str) -> str:
        text = value.strip().lower()
        if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
            raise ValueError("baseline_sha256 must be 64 lowercase hex chars")
        return text


class HardCallDesignation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    designation_id: NonEmptyStr
    target_task_id: NonEmptyStr
    reason_code: NonEmptyStr

    @field_validator("designation_id")
    @classmethod
    def _designation_id_grammar(cls, value: str) -> str:
        try:
            return validate_hard_call_designation_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("target_task_id")
    @classmethod
    def _target_task_id_grammar(cls, value: str) -> str:
        try:
            return validate_task_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc


class HardCallsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-gold-hard-calls-v1"] = HARD_CALLS_SCHEMA
    campaign_id: NonEmptyStr
    designation_contract: Literal["gold-hard-call-designation-v1"] = (
        HARD_CALL_DESIGNATION_CONTRACT
    )
    designations: list[HardCallDesignation] = Field(default_factory=list)

    @field_validator("campaign_id")
    @classmethod
    def _campaign_id_grammar(cls, value: str) -> str:
        try:
            return validate_campaign_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _validate_designations(self) -> HardCallsArtifact:
        if self.schema_version != HARD_CALLS_SCHEMA:
            raise GoldLabError(
                "hard_calls_schema_invalid",
                f"expected {HARD_CALLS_SCHEMA}",
            )
        if self.designation_contract != HARD_CALL_DESIGNATION_CONTRACT:
            raise GoldLabError(
                "hard_calls_contract_invalid",
                f"expected {HARD_CALL_DESIGNATION_CONTRACT}",
            )
        seen: set[str] = set()
        for item in self.designations:
            if not item.reason_code.strip():
                raise GoldLabError(
                    "hard_call_reason_empty",
                    "reason_code must be non-empty",
                )
            expected = hard_call_designation_id(
                campaign_id=self.campaign_id,
                target_task_id=item.target_task_id,
            )
            if item.designation_id != expected:
                raise GoldLabError(
                    "hard_call_designation_id_mismatch",
                    "designation_id does not match recomputation",
                )
            if item.target_task_id in seen:
                raise GoldLabError(
                    "hard_call_duplicate_target",
                    f"duplicate Hard Call target: {item.target_task_id}",
                )
            seen.add(item.target_task_id)
        return self


class AbsoluteRelevancePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: Literal[0, 1, 2]

    @field_validator("relevance", mode="before")
    @classmethod
    def _strict_int(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("relevance must be a strict integer 0|1|2")
        return value


class QuestionCheckDecision(StrEnum):
    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class QuestionCheckPayload(BaseModel):
    """Strict Question Check decision body (16F-B durable semantics)."""

    model_config = ConfigDict(extra="forbid")

    decision: QuestionCheckDecision
    effective_query: str | None = None
    effective_category: str | None = None
    effective_tags: list[str] | None = None

    @model_validator(mode="after")
    def _decision_shape(self) -> QuestionCheckPayload:
        if self.decision is QuestionCheckDecision.ACCEPT:
            if (
                self.effective_query is not None
                or self.effective_category is not None
                or self.effective_tags is not None
            ):
                raise ValueError("accept payload must not include edit fields")
            return self
        if self.decision is QuestionCheckDecision.REJECT:
            if (
                self.effective_query is not None
                or self.effective_category is not None
                or self.effective_tags is not None
            ):
                raise ValueError("reject payload must not include edit fields")
            return self
        # edit
        if self.effective_query is None or not str(self.effective_query).strip():
            raise ValueError("edit requires non-empty effective_query")
        if self.effective_tags is None:
            raise ValueError("edit requires effective_tags list")
        return self


class AuxiliaryPreferencePayload(BaseModel):
    """Typed auxiliary preference body (non-canonical; no promotion in 16F-A)."""

    model_config = ConfigDict(extra="forbid")

    preferred_chunk_id: NonEmptyStr
    other_chunk_id: NonEmptyStr


class IdempotencyStatus(StrEnum):
    PENDING = "pending"
    COMMITTED = "committed"


class IdempotencyCommandKind(StrEnum):
    QUESTION_CHECK = "question_check"
    ABSOLUTE_RELEVANCE = "absolute_relevance"
    AUXILIARY_PREFERENCE = "auxiliary_preference"


class IdempotencyEntry(BaseModel):
    """offline-rag-gold-idempotency-v1 campaign-local catalog entry."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-gold-idempotency-v1"] = (
        "offline-rag-gold-idempotency-v1"
    )
    campaign_id: NonEmptyStr
    idempotency_key: NonEmptyStr
    request_fingerprint: NonEmptyStr
    command_kind: IdempotencyCommandKind
    status: IdempotencyStatus
    record_id: NonEmptyStr
    judgment_id: NonEmptyStr
    created_at: datetime
    committed_at: datetime | None = None

    @field_validator("campaign_id")
    @classmethod
    def _campaign_id_grammar(cls, value: str) -> str:
        try:
            return validate_campaign_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("record_id")
    @classmethod
    def _record_id_grammar(cls, value: str) -> str:
        try:
            return validate_record_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("judgment_id")
    @classmethod
    def _judgment_id_grammar(cls, value: str) -> str:
        try:
            return validate_judgment_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("request_fingerprint")
    @classmethod
    def _reqfp_grammar(cls, value: str) -> str:
        try:
            return validate_request_fingerprint(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _status_committed_at(self) -> IdempotencyEntry:
        if self.schema_version != "offline-rag-gold-idempotency-v1":
            raise GoldLabError(
                "idempotency_schema_invalid",
                "expected offline-rag-gold-idempotency-v1",
            )
        if self.status is IdempotencyStatus.COMMITTED and self.committed_at is None:
            raise GoldLabError(
                "idempotency_entry_invalid",
                "committed entry requires committed_at",
            )
        if self.status is IdempotencyStatus.PENDING and self.committed_at is not None:
            raise GoldLabError(
                "idempotency_entry_invalid",
                "pending entry must not set committed_at",
            )
        return self


class GoldLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-gold-lab-ledger-v1"] = LEDGER_SCHEMA
    sequence: int = Field(ge=1)
    record_id: NonEmptyStr
    record_type: GoldLedgerRecordType
    judgment_id: NonEmptyStr
    task_id: NonEmptyStr
    project_id: NonEmptyStr
    campaign_id: NonEmptyStr
    workspace_id: NonEmptyStr
    snapshot_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    authoring_run_id: NonEmptyStr
    case_id: NonEmptyStr
    query_fingerprint: str | None = None
    candidate_chunk_id: str | None = None
    semantic_contract: NonEmptyStr
    selection_policy_id: NonEmptyStr
    selection_policy_fingerprint: NonEmptyStr
    game_id: str | None = None
    presentation_id: str | None = None
    idempotency_key: NonEmptyStr
    request_fingerprint: NonEmptyStr
    created_at: datetime
    supersedes_judgment_id: str | None = None
    payload: dict[str, Any]

    @field_validator("record_id")
    @classmethod
    def _record_id_grammar(cls, value: str) -> str:
        try:
            return validate_record_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("judgment_id")
    @classmethod
    def _judgment_id_grammar(cls, value: str) -> str:
        try:
            return validate_judgment_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("task_id")
    @classmethod
    def _task_id_grammar(cls, value: str) -> str:
        try:
            return validate_task_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("project_id")
    @classmethod
    def _project_id_grammar(cls, value: str) -> str:
        try:
            return validate_project_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("campaign_id")
    @classmethod
    def _campaign_id_grammar(cls, value: str) -> str:
        try:
            return validate_campaign_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("request_fingerprint")
    @classmethod
    def _reqfp_grammar(cls, value: str) -> str:
        try:
            return validate_request_fingerprint(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("selection_policy_fingerprint")
    @classmethod
    def _cfg_grammar(cls, value: str) -> str:
        try:
            return validate_selection_policy_fingerprint(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("query_fingerprint")
    @classmethod
    def _query_fp_grammar(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_query_fingerprint(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("supersedes_judgment_id")
    @classmethod
    def _supersedes_judgment_id_grammar(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return validate_judgment_id(value)
        except GoldLabError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _validate_typed_payload_and_contracts(self) -> GoldLedgerRecord:
        if self.schema_version != LEDGER_SCHEMA:
            raise GoldLabError(
                "ledger_schema_invalid",
                f"expected {LEDGER_SCHEMA}",
            )
        if self.record_type is GoldLedgerRecordType.ABSOLUTE_RELEVANCE:
            if self.semantic_contract != ABSOLUTE_RELEVANCE_CONTRACT:
                raise GoldLabError(
                    "ledger_semantic_contract_mismatch",
                    "absolute_relevance requires gold-absolute-relevance-v1",
                )
            AbsoluteRelevancePayload.model_validate(self.payload)
        elif self.record_type is GoldLedgerRecordType.QUESTION_CHECK:
            if self.semantic_contract != QUESTION_CHECK_CONTRACT:
                raise GoldLabError(
                    "ledger_semantic_contract_mismatch",
                    "question_check requires gold-question-check-v1",
                )
            try:
                QuestionCheckPayload.model_validate(self.payload)
            except Exception as exc:
                raise GoldLabError(
                    "ledger_record_invalid",
                    f"invalid question_check payload: {exc}",
                ) from exc
        elif self.record_type is GoldLedgerRecordType.AUXILIARY_PREFERENCE:
            if self.semantic_contract != AUXILIARY_PREFERENCE_CONTRACT:
                raise GoldLabError(
                    "ledger_semantic_contract_mismatch",
                    "auxiliary_preference requires gold-auxiliary-preference-v1",
                )
            AuxiliaryPreferencePayload.model_validate(self.payload)
        return self
