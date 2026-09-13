"""Lean silver/run models for offline-rag-gold-authoring-v1 (Slices 9A–9B)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt
from offline_rag.gold_authoring.contracts import (
    ATTEMPT_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    CONTEXT_CONTRACT,
    QUALITY_GATE_CONTRACT,
    SAMPLING_CONTRACT,
)


class HumanReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


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


class CandidateRef(BaseModel):
    """Minimal candidate placeholder; pooling diagnostics arrive in 9C."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr


class ModelJudgmentPlaceholder(BaseModel):
    """Minimal judgment placeholder; prelabel semantics arrive in 9D."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr | None = None
    relevance: Literal[0, 1, 2] | None = None
    pass_id: NonEmptyStr | None = None
    rationale: str | None = None


class ProposedQueryFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    rationale: str | None = None


class SilverCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_case_id: NonEmptyStr
    human_status: HumanReviewStatus = HumanReviewStatus.PENDING
    proposed_query: str | None = None
    proposed_category: str | None = None
    proposed_tags: list[str] = Field(default_factory=list)
    proposal_rationale: str | None = None
    source_seed: SourceSeed | None = None
    candidates: list[CandidateRef] = Field(default_factory=list)
    model_judgments: list[ModelJudgmentPlaceholder] = Field(default_factory=list)

    @field_validator("proposed_query", mode="before")
    @classmethod
    def _normalize_query(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("proposed_query must be a string or null")
        text = value.strip()
        return text or None


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
        return len(self.cases)

    @property
    def failed_count(self) -> int:
        return sum(1 for a in self.attempts if a.status != ProposalAttemptStatus.SUCCEEDED)
