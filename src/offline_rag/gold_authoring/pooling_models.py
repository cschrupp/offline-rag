"""Candidate pooling models (Slice 9C)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt
from offline_rag.gold_authoring.contracts import (
    POOLING_CONTRACT,
    POOLING_DEPTHS,
    POOLING_RETRIEVER_IDS,
)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retriever: NonEmptyStr
    chunk_id: NonEmptyStr
    rank: PositiveInt
    score: float | None = None


class PoolCandidate(BaseModel):
    """Deduplicated retrieval candidate (no chunk body text)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr | None = None
    document_title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    retrieval_hits: list[RetrievalHit] = Field(default_factory=list)


# Backward-compatible alias used by earlier lean 9A/9B shapes.
CandidateRef = PoolCandidate


class PoolCaseStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PoolFailureReason(StrEnum):
    INVALID_CASE_QUERY = "invalid_case_query"
    RETRIEVER_ERROR = "retriever_error"
    LEXICAL_RETRIEVAL_FAILED = "lexical_retrieval_failed"
    DENSE_BASELINE_FAILED = "dense_baseline_failed"
    DENSE_QUERY_PROMPT_FAILED = "dense_query_prompt_failed"
    DENSE_ARM_H_FAILED = "dense_arm_h_failed"
    HYBRID_RRF_FAILED = "hybrid_rrf_failed"
    HYBRID_RERANK_FAILED = "hybrid_rerank_failed"
    CANDIDATE_IDENTITY_INVALID = "candidate_identity_invalid"
    CANDIDATE_PROVENANCE_UNAVAILABLE = "candidate_provenance_unavailable"
    EMPTY_CANDIDATE_POOL = "empty_candidate_pool"
    POOL_CONSTRUCTION_FAILED = "pool_construction_failed"


class PoolFailureStage(StrEnum):
    RETRIEVER_EXECUTION = "retriever_execution"
    INDEX_PREFLIGHT = "index_preflight"
    EMBEDDING_RUNTIME_INITIALIZATION = "embedding_runtime_initialization"
    QUERY_EMBEDDING = "query_embedding"
    VECTOR_SEARCH = "vector_search"
    CANDIDATE_IDENTITY = "candidate_identity"
    CANDIDATE_PROVENANCE = "candidate_provenance"
    POOL_CONSTRUCTION = "pool_construction"
    HYBRID_FUSION = "hybrid_fusion"
    RERANK = "rerank"


class PoolExceptionCategory(StrEnum):
    EMBEDDING_ERROR = "embedding_error"
    CUDA_MEMORY_EXHAUSTED = "cuda_memory_exhausted"
    ARTIFACT_MISSING = "artifact_missing"
    INVALID_CANDIDATE = "invalid_candidate"
    STORAGE_ERROR = "storage_error"
    INVALID_INPUT = "invalid_input"
    UNEXPECTED_ERROR = "unexpected_error"


class PoolCaseOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_case_id: NonEmptyStr
    status: PoolCaseStatus
    failure_reason: PoolFailureReason | None = None
    candidate_count: NonNegativeInt = 0
    failed_retriever: str | None = None
    failure_stage: PoolFailureStage | None = None
    exception_category: PoolExceptionCategory | None = None


class PoolingProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pooling_contract: NonEmptyStr = POOLING_CONTRACT
    source_chunk_set_id: NonEmptyStr
    retrievers: list[str] = Field(default_factory=lambda: list(POOLING_RETRIEVER_IDS))
    retrieval_depths: dict[str, int] = Field(
        default_factory=lambda: dict(POOLING_DEPTHS)
    )
    artifact_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("pooling_contract")
    @classmethod
    def _contract(cls, value: str) -> str:
        if value != POOLING_CONTRACT:
            raise ValueError(f"unsupported pooling_contract: {value!r}")
        return value
