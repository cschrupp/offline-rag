"""Generation-facing domain models owned by the application core."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt, Score


class Citation(BaseModel):
    """Legacy citation shape retained for domain compatibility."""

    model_config = ConfigDict(extra="forbid")

    citation_id: NonEmptyStr
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    page: PositiveInt | None = None
    section_path: list[str] = Field(default_factory=list)
    claim_span: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResolvedCitation(BaseModel):
    """Application-owned citation resolved from a current-query EvidenceUnit."""

    model_config = ConfigDict(extra="forbid")

    evidence_unit_id: NonEmptyStr
    source_chunk_id: NonEmptyStr
    kind: Literal["parent", "child"]
    document_id: NonEmptyStr
    representation: NonEmptyStr = "full"
    clipped: bool = False
    section_path: list[str] = Field(default_factory=list)
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None
    clip: dict[str, Any] | None = None
    primary_anchor_chunk_id: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


AnswerStatus = Literal[
    "answered",
    "insufficient_evidence",
    "generation_failed",
    "citation_invalid",
]

AbstentionReason = Literal["empty_context", "model_abstain"]


class GroundedAnswerResult(BaseModel):
    """Validator-owned public Slice 8 answer envelope."""

    model_config = ConfigDict(extra="forbid")

    method: NonEmptyStr = "query"
    query: NonEmptyStr
    status: AnswerStatus
    answer_text: str | None = None
    citations: list[ResolvedCitation] = Field(default_factory=list)
    abstention_reason: AbstentionReason | None = None
    generation_failure_reason: NonEmptyStr | None = None
    generator_invoked: bool = False
    attempt_count: NonNegativeInt = 0
    generation_config_hash: NonEmptyStr
    context_config_hash: NonEmptyStr | None = None
    dense_index_id: NonEmptyStr | None = None
    lexical_index_id: NonEmptyStr | None = None
    fusion_config_hash: NonEmptyStr | None = None
    reranker_config_hash: NonEmptyStr | None = None
    effective_generation_semantics: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def evidence_unit_ids_used(self) -> list[str]:
        return [citation.evidence_unit_id for citation in self.citations]


class QueryEvaluationOutcomes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answered: NonNegativeInt = 0
    insufficient_evidence: NonNegativeInt = 0
    empty_context: NonNegativeInt = 0
    model_abstain: NonNegativeInt = 0
    generation_failed: NonNegativeInt = 0
    citation_invalid: NonNegativeInt = 0


class QueryEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    evaluation_type: NonEmptyStr = "query"
    method: NonEmptyStr = "query"
    dataset_id: NonEmptyStr
    case_count: NonNegativeInt
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None
    dense_index_id: NonEmptyStr | None = None
    lexical_index_id: NonEmptyStr | None = None
    fusion_config_hash: NonEmptyStr | None = None
    reranker_config_hash: NonEmptyStr | None = None
    context_config_hash: NonEmptyStr | None = None
    generation_config_hash: NonEmptyStr
    outcomes: QueryEvaluationOutcomes = Field(default_factory=QueryEvaluationOutcomes)
    answered_rate: Score = 0.0
    insufficient_evidence_rate: Score = 0.0
    empty_context_rate: Score = 0.0
    model_abstain_rate: Score = 0.0
    generation_failed_rate: Score = 0.0
    citation_invalid_rate: Score = 0.0
    generator_invoked_case_count: NonNegativeInt = 0
    generator_not_invoked_case_count: NonNegativeInt = 0
    total_generator_attempts: NonNegativeInt = 0
    latency_mean_ms: Score = 0.0
    latency_p50_ms: Score = 0.0
    latency_p95_ms: Score = 0.0
    generation_latency_mean_ms: Score = 0.0
    cases: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
