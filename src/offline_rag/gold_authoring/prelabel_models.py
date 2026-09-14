"""Prelabel / agreement models (Slice 9D)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt
from offline_rag.gold_authoring.contracts import (
    BLIND_ORDER_CONTRACT,
    JUDGE_CONTEXT_CONTRACT,
    PASS_1,
    PASS_2,
    PRELABEL_AGREEMENT_CONTRACT,
    PRELABEL_PASS_IDS,
    RELEVANCE_PRELABEL_CONTRACT,
    RATIONALE_MAX_CHARS,
)


class PrelabelPassId(StrEnum):
    PASS_1 = PASS_1
    PASS_2 = PASS_2


class AgreementLabel(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"


class DisagreementSeverity(StrEnum):
    NONE = "none"
    ADJACENT = "adjacent"
    POLAR = "polar"


class ReviewPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PrelabelCaseStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PrelabelFailureReason(StrEnum):
    INVALID_CASE_QUERY = "invalid_case_query"
    CANDIDATE_IDENTITY_INVALID = "candidate_identity_invalid"
    HISTORICAL_CANDIDATE_UNAVAILABLE = "historical_candidate_unavailable"
    CANDIDATE_PROVENANCE_UNAVAILABLE = "candidate_provenance_unavailable"
    AUTHORING_TRANSPORT_FAILED = "authoring_transport_failed"
    MODEL_RESPONSE_INVALID = "model_response_invalid"
    AGREEMENT_DERIVATION_FAILED = "agreement_derivation_failed"
    INTERNAL_PRELABEL_FAILURE = "internal_prelabel_failure"


class ModelJudgment(BaseModel):
    """One validated relevance-prelabel judgment for one (pass, chunk)."""

    model_config = ConfigDict(extra="forbid")

    pass_id: Literal["pass_1", "pass_2"]
    chunk_id: NonEmptyStr
    blind_position: PositiveInt
    grade: Literal[0, 1, 2]
    rationale: NonEmptyStr

    @field_validator("rationale")
    @classmethod
    def _rationale_len(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("rationale must be nonempty")
        if len(text) > RATIONALE_MAX_CHARS:
            raise ValueError(
                f"rationale exceeds {RATIONALE_MAX_CHARS} characters"
            )
        return text


# Backward-compatible name; placeholder semantics retired in 9D.
ModelJudgmentPlaceholder = ModelJudgment


class PrelabelPassOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: Literal["pass_1", "pass_2"]
    candidate_order: list[NonEmptyStr] = Field(default_factory=list)


class CasePrelabelProvenance(BaseModel):
    """Provenance of the coherent attempt that produced durable judgments."""

    model_config = ConfigDict(extra="forbid")

    authorcfg_id: NonEmptyStr
    source_chunk_set_id: NonEmptyStr
    relevance_contract: NonEmptyStr = RELEVANCE_PRELABEL_CONTRACT
    judge_context_contract: NonEmptyStr = JUDGE_CONTEXT_CONTRACT
    blind_order_contract: NonEmptyStr = BLIND_ORDER_CONTRACT
    agreement_contract: NonEmptyStr = PRELABEL_AGREEMENT_CONTRACT
    passes: list[PrelabelPassOrder] = Field(default_factory=list)

    @field_validator("authorcfg_id")
    @classmethod
    def _authorcfg(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("authorcfg_"):
            raise ValueError("authorcfg_id must start with authorcfg_")
        return text


class CandidatePrelabelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    agreement: AgreementLabel
    disagreement_severity: DisagreementSeverity


class PrelabelSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_summaries: list[CandidatePrelabelSummary] = Field(default_factory=list)
    case_has_disagreement: bool = False
    case_has_polar_disagreement: bool = False
    case_has_source_seed_zero: bool = False
    case_has_competing_grade_2: bool = False
    case_has_no_positive_prelabel: bool = False
    review_priority: ReviewPriority = ReviewPriority.LOW


class PrelabelCaseOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_case_id: NonEmptyStr
    status: PrelabelCaseStatus
    failure_reason: PrelabelFailureReason | None = None
    pass_id: Literal["pass_1", "pass_2"] | None = None
    chunk_id: str | None = None


class PrelabelingProvenance(BaseModel):
    """Current/latest gold-prelabel invocation provenance."""

    model_config = ConfigDict(extra="forbid")

    authorcfg_id: NonEmptyStr
    source_chunk_set_id: NonEmptyStr
    relevance_contract: NonEmptyStr = RELEVANCE_PRELABEL_CONTRACT
    judge_context_contract: NonEmptyStr = JUDGE_CONTEXT_CONTRACT
    blind_order_contract: NonEmptyStr = BLIND_ORDER_CONTRACT
    agreement_contract: NonEmptyStr = PRELABEL_AGREEMENT_CONTRACT

    @field_validator("authorcfg_id")
    @classmethod
    def _authorcfg(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("authorcfg_"):
            raise ValueError("authorcfg_id must start with authorcfg_")
        return text


class PrelabelingStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance: PrelabelingProvenance
    outcomes: list[PrelabelCaseOutcome] = Field(default_factory=list)
    targeted_case_count: NonNegativeInt = 0
    successful_case_count: NonNegativeInt = 0
    failed_case_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def _counts(self) -> PrelabelingStage:
        if (
            self.targeted_case_count
            != self.successful_case_count + self.failed_case_count
        ):
            raise ValueError(
                "prelabel targeted_case_count must equal successful + failed"
            )
        return self


def has_complete_prelabel(
    *,
    judgments: list[ModelJudgment],
    summary: PrelabelSummary | None,
    provenance: CasePrelabelProvenance | None,
    candidate_ids: list[str],
) -> bool:
    """Return whether a case has a complete durable 9D prelabel."""
    if summary is None or provenance is None:
        return False
    n = len(candidate_ids)
    if n == 0 or len(judgments) != 2 * n:
        return False
    expected = set(candidate_ids)
    by_key: set[tuple[str, str]] = set()
    for judgment in judgments:
        key = (judgment.pass_id, judgment.chunk_id)
        if key in by_key:
            return False
        by_key.add(key)
        if judgment.chunk_id not in expected:
            return False
    for pass_id in PRELABEL_PASS_IDS:
        present = {j.chunk_id for j in judgments if j.pass_id == pass_id}
        if present != expected:
            return False
    if {s.chunk_id for s in summary.candidate_summaries} != expected:
        return False
    if len(provenance.passes) != 2:
        return False
    return True
