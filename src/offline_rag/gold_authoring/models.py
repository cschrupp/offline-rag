"""Lean silver/run models for offline-rag-gold-authoring-v1 (Slices 9A–9E)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt
from offline_rag.gold_authoring.contracts import (
    ATTEMPT_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    CONTEXT_CONTRACT,
    QUALITY_GATE_CONTRACT,
    SAMPLING_CONTRACT,
)
from offline_rag.gold_authoring.pooling_models import (
    PoolCandidate,
    PoolCaseOutcome,
    PoolingProvenance,
)
from offline_rag.gold_authoring.prelabel_models import (
    CasePrelabelProvenance,
    ModelJudgment,
    PrelabelSummary,
    PrelabelingStage,
    has_complete_prelabel,
)
from offline_rag.gold_authoring.review_models import (
    HumanReview,
    HumanReviewStatus,
    canonicalize_category,
    canonicalize_query,
    canonicalize_tags,
    tags_equal,
)

# Backward-compatible name for imports expecting CandidateRef.
CandidateRef = PoolCandidate
ModelJudgmentPlaceholder = ModelJudgment


class ProposalAttemptStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED_TRANSPORT = "failed_transport"
    FAILED_RESPONSE = "failed_response"
    FAILED_SCHEMA = "failed_schema"
    REJECTED_QUALITY = "rejected_quality"
    FAILED_CONTEXT = "failed_context"


class ProposalFailureReason(StrEnum):
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    AUTHENTICATION_ERROR = "authentication_error"
    EMPTY_RESPONSE = "empty_response"
    INVALID_JSON = "invalid_json"
    SCHEMA_INVALID = "schema_invalid"
    DEICTIC_QUERY = "deictic_query"
    SEED_QUOTE_OVERLAP = "seed_quote_overlap"
    DUPLICATE_QUERY_EXACT = "duplicate_query_exact"
    DUPLICATE_QUERY_NEAR = "duplicate_query_near"
    PROPOSAL_CONTEXT_UNAVAILABLE = "proposal_context_unavailable"
    REDIRECT_NOT_ALLOWED = "redirect_not_allowed"


class SourceSeed(BaseModel):
    """Proposal-stage source seed provenance (no seed body text)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr | None = None
    document_title: str | None = None
    section_path: list[str] = Field(default_factory=list)


class ProposedQueryFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    rationale: str | None = None


class SilverCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_case_id: NonEmptyStr
    proposed_query: str | None = None
    proposed_category: str | None = None
    proposed_tags: list[str] = Field(default_factory=list)
    proposal_rationale: str | None = None
    source_seed: SourceSeed | None = None
    candidates: list[PoolCandidate] = Field(default_factory=list)
    model_judgments: list[ModelJudgment] = Field(default_factory=list)
    prelabel_provenance: CasePrelabelProvenance | None = None
    prelabel_summary: PrelabelSummary | None = None
    human_review: HumanReview | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_top_level_human_status(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        legacy = payload.pop("human_status", None)
        if legacy is None:
            return payload
        if payload.get("human_review") is not None:
            raise ValueError(
                "cannot provide both top-level human_status and human_review"
            )
        if legacy == HumanReviewStatus.PENDING.value or legacy == HumanReviewStatus.PENDING:
            return payload
        payload["human_review"] = {
            "status": legacy,
            "judgments": [],
            "query_override": None,
            "category_override": {"is_overridden": False, "value": None},
            "tags_override": None,
            "grade_basis_query": None,
        }
        return payload

    @field_validator("proposed_query", mode="before")
    @classmethod
    def _normalize_query(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("proposed_query must be a string or null")
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def _prelabel_and_review_coherence(self) -> SilverCase:
        has_any = bool(self.model_judgments) or (
            self.prelabel_summary is not None
        ) or (self.prelabel_provenance is not None)
        if has_any:
            candidate_ids = [c.chunk_id for c in self.candidates]
            if not has_complete_prelabel(
                judgments=self.model_judgments,
                summary=self.prelabel_summary,
                provenance=self.prelabel_provenance,
                candidate_ids=candidate_ids,
            ):
                if not (
                    not self.model_judgments
                    and self.prelabel_summary is None
                    and self.prelabel_provenance is None
                ):
                    raise ValueError(
                        f"incomplete or inconsistent 9D prelabel for case "
                        f"{self.draft_case_id}"
                    )
            if self.model_judgments:
                assert self.prelabel_provenance is not None
                order_by_pass = {
                    p.pass_id: list(p.candidate_order)
                    for p in self.prelabel_provenance.passes
                }
                for judgment in self.model_judgments:
                    order = order_by_pass.get(judgment.pass_id)
                    if order is None:
                        raise ValueError("missing pass order in prelabel_provenance")
                    idx = judgment.blind_position - 1
                    if idx < 0 or idx >= len(order) or order[idx] != judgment.chunk_id:
                        raise ValueError(
                            "blind_position does not match candidate_order for "
                            f"{judgment.pass_id}/{judgment.chunk_id}"
                        )

        _validate_human_review_against_case(self)
        return self

    @property
    def human_status(self) -> HumanReviewStatus:
        if self.human_review is None:
            return HumanReviewStatus.PENDING
        return self.human_review.status

    def effective_query(self) -> str | None:
        review = self.human_review
        if review is not None and review.query_override is not None:
            return review.query_override
        if self.proposed_query is None:
            return None
        return canonicalize_query(self.proposed_query)

    def effective_category(self) -> str | None:
        review = self.human_review
        if review is not None and review.category_override.is_overridden:
            return review.category_override.value
        return canonicalize_category(self.proposed_category)

    def effective_tags(self) -> tuple[str, ...]:
        review = self.human_review
        if review is not None and review.tags_override is not None:
            return canonicalize_tags(review.tags_override)
        return canonicalize_tags(self.proposed_tags)

    def proposal_content_changed(self) -> bool:
        proposed_query = (
            canonicalize_query(self.proposed_query)
            if self.proposed_query is not None
            else None
        )
        if proposed_query != self.effective_query():
            return True
        if canonicalize_category(self.proposed_category) != self.effective_category():
            return True
        if not tags_equal(self.proposed_tags, self.effective_tags()):
            return True
        return False

    def human_judgment_map(self) -> dict[str, int]:
        if self.human_review is None:
            return {}
        return {j.chunk_id: int(j.relevance) for j in self.human_review.judgments}

    def review_complete(self) -> bool:
        candidate_ids = {c.chunk_id for c in self.candidates}
        judged = set(self.human_judgment_map())
        return bool(candidate_ids) and judged == candidate_ids

    def human_positive_count(self) -> int:
        return sum(1 for grade in self.human_judgment_map().values() if grade >= 1)

    def quality_eligible_for_gold(self) -> bool:
        return self.review_complete() and self.human_positive_count() >= 1

    def has_complete_durable_prelabel(self) -> bool:
        return has_complete_prelabel(
            judgments=self.model_judgments,
            summary=self.prelabel_summary,
            provenance=self.prelabel_provenance,
            candidate_ids=[c.chunk_id for c in self.candidates],
        )


def _validate_human_review_against_case(case: SilverCase) -> None:
    review = case.human_review
    if review is None:
        return

    candidate_ids = {c.chunk_id for c in case.candidates}
    judged_ids = {j.chunk_id for j in review.judgments}
    unknown = judged_ids - candidate_ids
    if unknown:
        raise ValueError(
            f"human judgment for unknown candidate chunk_id(s): "
            f"{sorted(unknown)}"
        )

    effective_query = case.effective_query()
    if review.judgments:
        if effective_query is None:
            raise ValueError(
                "nonempty human judgments require a non-null effective query"
            )
        if review.grade_basis_query != effective_query:
            raise ValueError(
                "grade_basis_query must equal canonical effective_query "
                "when human judgments are nonempty"
            )

    status = review.status
    if status in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED):
        if not case.review_complete():
            raise ValueError(
                f"{status.value} case requires a complete human grade map"
            )
        if case.human_positive_count() < 1:
            raise ValueError(
                f"{status.value} case requires at least one human grade 1 or 2"
            )
        if review.grade_basis_query != effective_query:
            raise ValueError(
                f"{status.value} case has stale query-grade binding"
            )
        changed = case.proposal_content_changed()
        if status == HumanReviewStatus.ACCEPTED and changed:
            raise ValueError(
                "accepted case must not change proposed query/category/tags"
            )
        if status == HumanReviewStatus.EDITED and not changed:
            raise ValueError(
                "edited case requires a semantic change to query/category/tags"
            )


class ProposalPipelineProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sampling_contract: NonEmptyStr = SAMPLING_CONTRACT
    context_contract: NonEmptyStr = CONTEXT_CONTRACT
    quality_gate_contract: NonEmptyStr = QUALITY_GATE_CONTRACT
    attempt_contract: NonEmptyStr = ATTEMPT_CONTRACT


class ProposalAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_seed: SourceSeed
    status: ProposalAttemptStatus
    failure_reason: ProposalFailureReason | None = None
    draft_case_id: NonEmptyStr | None = None
    proposal: ProposedQueryFields | None = None


class GoldAuthoringRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = AUTHORING_ARTIFACT_CONTRACT
    authoring_run_id: NonEmptyStr
    authorcfg_id: NonEmptyStr
    network_policy: Literal["localhost_only", "private_network"]
    effective_endpoint: str | None = None
    corpus_id: str | None = None
    corpus_name: str | None = None
    chunk_set_id: str | None = None
    created_at: datetime
    proposal_pipeline: ProposalPipelineProvenance | None = None
    sampling_seed: int | None = None
    requested_count: NonNegativeInt | None = None
    selected_chunk_ids: list[str] = Field(default_factory=list)
    eligible_population_count: NonNegativeInt | None = None
    attempts: list[ProposalAttempt] = Field(default_factory=list)
    cases: list[SilverCase] = Field(default_factory=list)
    pooling: PoolingProvenance | None = None
    pool_outcomes: list[PoolCaseOutcome] = Field(default_factory=list)
    pool_targeted_case_count: NonNegativeInt | None = None
    pool_successful_case_count: NonNegativeInt | None = None
    pool_failed_case_count: NonNegativeInt | None = None
    prelabeling: PrelabelingStage | None = None

    @field_validator("schema_version")
    @classmethod
    def _schema_must_be_authoring_v1(cls, value: str) -> str:
        if value != AUTHORING_ARTIFACT_CONTRACT:
            raise ValueError(
                f"unsupported authoring schema_version: {value!r}; "
                f"expected {AUTHORING_ARTIFACT_CONTRACT!r}"
            )
        return value

    @field_validator("authorcfg_id")
    @classmethod
    def _authorcfg_prefix(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("authorcfg_"):
            raise ValueError("authorcfg_id must start with authorcfg_")
        return text

    @property
    def successful_count(self) -> int:
        return sum(
            1
            for attempt in self.attempts
            if attempt.status == ProposalAttemptStatus.SUCCEEDED
        )

    @property
    def failed_count(self) -> int:
        return len(self.attempts) - self.successful_count
