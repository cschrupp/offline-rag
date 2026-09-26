"""Typed recovery state / protocol contracts (Slice 12A; OD-12-1/2/3).

No LangGraph, rewriter, retrieval, or generation. Diagnostics are allowlisted
scalars/enums only — no corpus-derived free text.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonNegativeInt
from offline_rag.sufficiency.contracts import ExactNonBlankStr

RECOVERY_STATE_V1 = "recovery-state-v1"
RECOVERY_PROTOCOL_V1 = "recovery-protocol-v1"
RECOVERY_ATTEMPT_ROLE_INITIAL = "initial"
RECOVERY_ATTEMPT_ROLE_RECOVERY = "recovery"

MAX_RECOVERY_RETRIES_V1 = 1
MAX_ATTEMPT_NUMBER_V1 = 1  # attempt 0 initial + attempt 1 recovery


class RecoveryErrorCodeV1(str, Enum):
    """Stable machine-readable recovery protocol error codes."""

    INVALID_STATE = "invalid_state"
    INVALID_TRANSITION = "invalid_transition"
    ORIGINAL_QUERY_MUTATION = "original_query_mutation"
    INVALID_ATTEMPT_NUMBER = "invalid_attempt_number"
    INVALID_ATTEMPT_ROLE = "invalid_attempt_role"
    NON_CONTIGUOUS_ATTEMPTS = "non_contiguous_attempts"
    DUPLICATE_ATTEMPT = "duplicate_attempt"
    RECOVERY_WITHOUT_INITIAL_INSUFFICIENCY = "recovery_without_initial_insufficiency"
    SECOND_RECOVERY_ATTEMPT = "second_recovery_attempt"
    TERMINAL_STATE_TRANSITION = "terminal_state_transition"
    INCONSISTENT_SUFFICIENCY = "inconsistent_sufficiency"
    ACTIVE_QUERY_MUTATION = "active_query_mutation"
    CORPUS_FREE_TEXT_FORBIDDEN = "corpus_free_text_forbidden"
    INVALID_EVENT = "invalid_event"


class RecoveryErrorDetailsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str | None = None
    expected: str | float | bool | None = None
    actual: str | float | bool | None = None


class RecoveryProtocolError(Exception):
    """Fail-closed recovery protocol / state error (no repair)."""

    def __init__(
        self,
        code: RecoveryErrorCodeV1,
        message: str,
        *,
        details: RecoveryErrorDetailsV1 | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class RecoveryPhaseV1(str, Enum):
    """Current recovery protocol phase."""

    AWAITING_INITIAL_SUFFICIENCY = "awaiting_initial_sufficiency"
    RECOVERY_ELIGIBLE = "recovery_eligible"
    RECOVERY_ATTEMPT_PENDING = "recovery_attempt_pending"
    TERMINAL = "terminal"


class RecoveryTerminalOutcomeV1(str, Enum):
    """Machine-readable terminal outcomes (not a Boolean)."""

    INITIAL_EVIDENCE_SUFFICIENT = "initial_evidence_sufficient"
    RECOVERED_EVIDENCE_SUFFICIENT = "recovered_evidence_sufficient"
    INSUFFICIENT_AFTER_BOUNDED_RECOVERY = "insufficient_after_bounded_recovery"
    RECOVERY_PREPARATION_OR_EXECUTION_FAILED = (
        "recovery_preparation_or_execution_failed"
    )


class RecoveryFailureReasonV1(str, Enum):
    """Machine-readable failure reasons when terminal outcome is recovery failure."""

    REWRITE_PREPARATION_FAILED = "rewrite_preparation_failed"
    RECOVERY_EXECUTION_FAILED = "recovery_execution_failed"
    PROTOCOL_VIOLATION = "protocol_violation"


class AssemblyStopReasonV1(str, Enum):
    """Closed stop-state enums allowed in typed recovery diagnostics."""

    COMPLETED = "completed"
    NO_ANCHORS = "no_anchors"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EMPTY_CONTEXT = "empty_context"


class RecoveryDiagnosticsV1(BaseModel):
    """Allowlisted deterministic diagnostics (OD-12-2). No corpus free text."""

    model_config = ConfigDict(extra="forbid")

    anchor_count: NonNegativeInt | None = None
    evidence_unit_count: NonNegativeInt | None = None
    top_reranker_score: float | None = None
    top1_top2_margin: float | None = None
    top_anchor_cross_retriever_support: bool | None = None
    distinct_document_count: NonNegativeInt | None = None
    distinct_section_count: NonNegativeInt | None = None
    clipping_occurred: bool | None = None
    budget_exhausted: bool | None = None
    stop_reason: AssemblyStopReasonV1 | None = None


class RecoverySufficiencyDecisionRefV1(BaseModel):
    """Projection of a sufficiency-v1 decision into recovery state (no Gold)."""

    model_config = ConfigDict(extra="forbid")

    policy_contract: ExactNonBlankStr
    policy_version: ExactNonBlankStr
    sufficient: bool
    triggered_gates: list[ExactNonBlankStr] = Field(default_factory=list)
    empty_context: bool
    evidence_unit_count: NonNegativeInt


class RecoveryAttemptRecordV1(BaseModel):
    """One retrieval/context attempt represented in recovery history."""

    model_config = ConfigDict(extra="forbid")

    attempt_number: NonNegativeInt
    attempt_role: Literal["initial", "recovery"]
    active_retrieval_query: ExactNonBlankStr
    sufficiency: RecoverySufficiencyDecisionRefV1
    diagnostics: RecoveryDiagnosticsV1 | None = None


class RecoveryStateV1(BaseModel):
    """Project-owned recovery state (OD-12-3). No evidence/corpus text."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["recovery-state-v1"] = RECOVERY_STATE_V1
    protocol_contract: Literal["recovery-protocol-v1"] = RECOVERY_PROTOCOL_V1
    case_id: ExactNonBlankStr | None = None
    original_query: ExactNonBlankStr
    active_retrieval_query: ExactNonBlankStr
    current_attempt_number: NonNegativeInt
    current_attempt_role: Literal["initial", "recovery"]
    max_retries: Literal[1] = MAX_RECOVERY_RETRIES_V1
    phase: RecoveryPhaseV1
    attempts: list[RecoveryAttemptRecordV1] = Field(default_factory=list)
    current_sufficiency: RecoverySufficiencyDecisionRefV1 | None = None
    terminal_outcome: RecoveryTerminalOutcomeV1 | None = None
    failure_reason: RecoveryFailureReasonV1 | None = None


class RecoveryEventKindV1(str, Enum):
    """Deterministic protocol events (hand-applied in 12A; no providers)."""

    RECORD_INITIAL_SUFFICIENCY = "record_initial_sufficiency"
    PREPARE_RECOVERY_QUERY = "prepare_recovery_query"
    RECORD_RECOVERY_SUFFICIENCY = "record_recovery_sufficiency"
    FAIL_RECOVERY = "fail_recovery"


class RecoveryEventV1(BaseModel):
    """One ordered recovery protocol event for apply/replay."""

    model_config = ConfigDict(extra="forbid")

    kind: RecoveryEventKindV1
    sufficiency: RecoverySufficiencyDecisionRefV1 | None = None
    diagnostics: RecoveryDiagnosticsV1 | None = None
    prepared_retrieval_query: ExactNonBlankStr | None = None
    failure_reason: RecoveryFailureReasonV1 | None = None

    @field_validator("prepared_retrieval_query", mode="before")
    @classmethod
    def _blank_prepared_to_none(cls, value: Any) -> Any:
        if value is None:
            return None
        return value
