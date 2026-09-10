"""Query trace contracts for local debugging and evaluation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.generation import Citation
from offline_rag.domain.retrieval import RetrievalCandidate
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, Score


class TraceStatus(StrEnum):
    """High-level outcome of a query execution."""

    OK = "ok"
    ABSTAINED = "abstained"
    FAILED = "failed"
    PARTIAL = "partial"


class QueryInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: NonEmptyStr
    normalized: str | None = None
    rewrites: list[str] = Field(default_factory=list)


class RetrievalStages(BaseModel):
    """Stage-local candidate lists. Keep stage names stable; avoid graph-node sprawl."""

    model_config = ConfigDict(extra="forbid")

    dense: list[RetrievalCandidate] = Field(default_factory=list)
    lexical: list[RetrievalCandidate] = Field(default_factory=list)
    fused: list[RetrievalCandidate] = Field(default_factory=list)
    reranked: list[RetrievalCandidate] = Field(default_factory=list)


class ContextInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_chunk_ids: list[NonEmptyStr] = Field(default_factory=list)
    expanded_chunk_ids: list[NonEmptyStr] = Field(default_factory=list)
    token_count: NonNegativeInt = 0


class DecisionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_sufficient: bool | None = None
    abstained: bool = False
    reason: str | None = None


class GenerationInfo(BaseModel):
    """Optional generation summary; no model/runtime dependency required."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    prompt_version: str | None = None
    answer: str | None = None
    citation_ids: list[NonEmptyStr] = Field(default_factory=list)


class CitationValidationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool | None = None
    errors: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class TimingInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dense: NonNegativeInt = 0
    lexical: NonNegativeInt = 0
    fusion: NonNegativeInt = 0
    rerank: NonNegativeInt = 0
    context: NonNegativeInt = 0
    generation: NonNegativeInt = 0
    total: NonNegativeInt = 0


class QueryTrace(BaseModel):
    """Primary local debugging artifact for one query invocation.

    ``trace_id`` is a runtime execution identity. Durable document/chunk identity
    must come from deterministic corpus IDs on candidates and citations.
    """

    model_config = ConfigDict(extra="forbid")

    trace_id: NonEmptyStr
    query: QueryInfo
    retrieval: RetrievalStages = Field(default_factory=RetrievalStages)
    context: ContextInfo = Field(default_factory=ContextInfo)
    decision: DecisionInfo = Field(default_factory=DecisionInfo)
    generation: GenerationInfo | None = None
    citation_validation: CitationValidationInfo = Field(default_factory=CitationValidationInfo)
    timing_ms: TimingInfo = Field(default_factory=TimingInfo)
    status: TraceStatus = TraceStatus.OK
    errors: list[str] = Field(default_factory=list)
    experiment_id: NonEmptyStr | None = None
    confidence: Score | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
