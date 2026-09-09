"""Retrieval domain models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, PositiveInt, Score


class RetrievalCandidate(BaseModel):
    """One ranked evidence candidate with enough identity to resolve provenance."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    dense_rank: PositiveInt | None = None
    dense_score: Score | None = None
    sparse_rank: PositiveInt | None = None
    sparse_score: Score | None = None
    fusion_rank: PositiveInt | None = None
    fusion_score: Score | None = None
    rerank_score: Score | None = None
    retrieval_stage: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Ordered retrieval output for a single query."""

    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    stage: NonEmptyStr = "retrieval"
    metadata: dict[str, Any] = Field(default_factory=dict)
