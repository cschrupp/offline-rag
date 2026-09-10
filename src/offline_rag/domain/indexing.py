"""Dense indexing domain models (embeddings, manifests, reports)."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt, Score


class IndexingStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    NO_OP = "no_op"


class DocumentIndexStatus(StrEnum):
    INDEXED = "indexed"
    REUSED = "reused"
    FAILED = "failed"


class EmbeddingArtifact(BaseModel):
    """Content-addressed per-child dense vector derivation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-embedding-artifact-v1"
    embedding_id: NonEmptyStr
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    embedding_text_hash: NonEmptyStr
    embedding_config_hash: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: NonEmptyStr
    dimension: PositiveInt
    normalize: bool
    adapter_contract: NonEmptyStr
    vector: list[float]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("vector")
    @classmethod
    def _finite_vector(cls, value: list[float]) -> list[float]:
        if not value:
            raise ValueError("vector must be non-empty")
        for item in value:
            if not math.isfinite(item):
                raise ValueError("vector must contain only finite values")
        return value


class DenseIndexManifest(BaseModel):
    """Immutable description of one dense index derivation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-dense-index-manifest-v1"
    index_id: NonEmptyStr
    corpus_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    embedding_config_hash: NonEmptyStr
    index_config_hash: NonEmptyStr
    index_contract_version: NonEmptyStr
    embedding_text_strategy: NonEmptyStr
    embedding_text_contract: NonEmptyStr
    embedding_model_id: NonEmptyStr
    embedding_model_revision: NonEmptyStr
    embedding_dimension: PositiveInt
    normalize: bool
    similarity_metric: NonEmptyStr
    backend: NonEmptyStr
    backend_contract: NonEmptyStr
    collection_name: NonEmptyStr
    expected_child_count: NonNegativeInt
    indexed_child_count: NonNegativeInt
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexState(BaseModel):
    """Mutable pointer to the active dense index for a logical corpus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-index-state-v1"
    corpus_name: NonEmptyStr
    source_corpus_id: NonEmptyStr
    source_chunk_set_id: NonEmptyStr
    current_index_id: NonEmptyStr
    current_index_manifest: NonEmptyStr
    index_config_hash: NonEmptyStr
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    corpus_name: NonEmptyStr
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None
    embedding_config_hash: NonEmptyStr | None = None
    index_config_hash: NonEmptyStr | None = None
    status: IndexingStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: NonNegativeInt
    children_total: NonNegativeInt = 0
    embeddings_generated: NonNegativeInt = 0
    embeddings_reused: NonNegativeInt = 0
    embeddings_failed: NonNegativeInt = 0
    vectors_materialized: NonNegativeInt = 0
    documents_total: NonNegativeInt = 0
    index_id: NonEmptyStr | None = None
    collection_name: NonEmptyStr | None = None
    index_manifest_path: str | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DenseCandidate(BaseModel):
    """Project-owned dense retrieval hit with resolved provenance."""

    model_config = ConfigDict(extra="forbid")

    rank: PositiveInt
    score: Score
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    parent_chunk_id: NonEmptyStr | None = None
    previous_chunk_id: NonEmptyStr | None = None
    next_chunk_id: NonEmptyStr | None = None
    text: NonEmptyStr
    section_path: list[str] = Field(default_factory=list)
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None
    token_count: NonNegativeInt = 0
    point_id: NonEmptyStr | None = None
    embedding_id: NonEmptyStr | None = None
    chunk_artifact_id: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DenseRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    index_id: NonEmptyStr
    top_k: PositiveInt
    candidates: list[DenseCandidate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonEmptyStr
    query: NonEmptyStr
    relevant_chunk_ids: list[NonEmptyStr] = Field(default_factory=list)
    relevant_document_ids: list[NonEmptyStr] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def _nonempty_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be non-empty")
        return value


class RetrievalEvalDatasetMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    first_relevant_rank: PositiveInt | None = None
    reciprocal_rank: Score = 0.0
    recall_at_1: Score = 0.0
    recall_at_5: Score = 0.0
    recall_at_10: Score = 0.0
    latency_ms: NonNegativeInt = 0
    error: str | None = None


class DenseRetrievalEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    evaluation_type: NonEmptyStr = "dense_retrieval"
    dataset_id: NonEmptyStr
    case_count: NonNegativeInt
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr
    index_id: NonEmptyStr
    embedding_config_hash: NonEmptyStr
    index_config_hash: NonEmptyStr
    model_id: NonEmptyStr
    model_revision: NonEmptyStr
    top_k: PositiveInt
    recall_at_1: Score
    recall_at_5: Score
    recall_at_10: Score
    mrr: Score
    latency_mean_ms: Score
    latency_p50_ms: Score
    latency_p95_ms: Score
    cases: list[RetrievalCaseResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmbeddingModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    artifact_type: NonEmptyStr = "embedding_model"
    provider_source: NonEmptyStr = "huggingface"
    model_id: NonEmptyStr
    requested_revision: NonEmptyStr
    resolved_revision: NonEmptyStr
    runtime: NonEmptyStr = "sentence-transformers"
    expected_dimension: PositiveInt = 1024
    artifact_contract: NonEmptyStr
    provisioned_at: datetime
    required_files: list[str] = Field(default_factory=list)
    file_digests: dict[str, str] = Field(default_factory=dict)
    artifact_id: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvisioningStatus(StrEnum):
    READY = "ready"
    ALREADY_PROVISIONED = "already_provisioned"
    FAILED = "failed"


class EmbeddingProvisionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProvisioningStatus
    model_id: NonEmptyStr
    requested_revision: NonEmptyStr
    resolved_revision: NonEmptyStr | None = None
    destination: NonEmptyStr
    artifact_id: NonEmptyStr | None = None
    manifest_path: str | None = None
    files_downloaded: NonNegativeInt = 0
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalIndexManifest(BaseModel):
    """Immutable description of one lexical (BM25) index derivation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-lexical-index-manifest-v1"
    lexical_index_id: NonEmptyStr
    corpus_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    lexical_config_hash: NonEmptyStr
    text_strategy: NonEmptyStr
    text_contract: NonEmptyStr
    analyzer_strategy: NonEmptyStr
    analyzer_contract: NonEmptyStr
    bm25_contract: NonEmptyStr
    bm25_k1: Score
    bm25_b: Score
    bm25_idf: NonEmptyStr
    bm25_query_tf: NonEmptyStr
    backend: NonEmptyStr
    backend_contract: NonEmptyStr
    expected_child_count: NonNegativeInt
    indexed_child_count: NonNegativeInt
    document_count: NonNegativeInt
    vocabulary_size: NonNegativeInt
    avgdl: Score
    physical_index_relpath: NonEmptyStr
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalIndexState(BaseModel):
    """Mutable pointer to the active lexical index for a logical corpus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-lexical-index-state-v1"
    corpus_name: NonEmptyStr
    source_corpus_id: NonEmptyStr
    source_chunk_set_id: NonEmptyStr
    current_lexical_index_id: NonEmptyStr
    current_lexical_index_manifest: NonEmptyStr
    lexical_config_hash: NonEmptyStr
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalIndexingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    corpus_name: NonEmptyStr
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None
    lexical_config_hash: NonEmptyStr | None = None
    status: IndexingStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: NonNegativeInt
    children_total: NonNegativeInt = 0
    indexed_child_count: NonNegativeInt = 0
    documents_total: NonNegativeInt = 0
    vocabulary_size: NonNegativeInt = 0
    lexical_index_id: NonEmptyStr | None = None
    lexical_index_manifest_path: str | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalCandidate(BaseModel):
    """Project-owned lexical retrieval hit with resolved provenance."""

    model_config = ConfigDict(extra="forbid")

    rank: PositiveInt
    score: Score
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    parent_chunk_id: NonEmptyStr | None = None
    previous_chunk_id: NonEmptyStr | None = None
    next_chunk_id: NonEmptyStr | None = None
    text: NonEmptyStr
    section_path: list[str] = Field(default_factory=list)
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None
    token_count: NonNegativeInt = 0
    chunk_artifact_id: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    method: NonEmptyStr = "lexical"
    index_id: NonEmptyStr
    top_k: PositiveInt
    candidates: list[LexicalCandidate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LexicalRetrievalEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    evaluation_type: NonEmptyStr = "lexical_retrieval"
    method: NonEmptyStr = "lexical"
    dataset_id: NonEmptyStr
    case_count: NonNegativeInt
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr
    index_id: NonEmptyStr
    lexical_config_hash: NonEmptyStr
    top_k: PositiveInt
    recall_at_1: Score
    recall_at_5: Score
    recall_at_10: Score
    mrr: Score
    latency_mean_ms: Score
    latency_p50_ms: Score
    latency_p95_ms: Score
    cases: list[RetrievalCaseResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class FusionProvenance(BaseModel):
    """Branch ranks/scores and RRF contribution for one hybrid candidate."""

    model_config = ConfigDict(extra="forbid")

    rrf_score: Score
    dense_rank: PositiveInt | None = None
    dense_score: Score | None = None
    lexical_rank: PositiveInt | None = None
    lexical_score: Score | None = None


class HybridCandidate(BaseModel):
    """Project-owned hybrid retrieval hit with fusion provenance."""

    model_config = ConfigDict(extra="forbid")

    rank: PositiveInt
    score: Score
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    parent_chunk_id: NonEmptyStr | None = None
    previous_chunk_id: NonEmptyStr | None = None
    next_chunk_id: NonEmptyStr | None = None
    text: NonEmptyStr
    section_path: list[str] = Field(default_factory=list)
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None
    token_count: NonNegativeInt = 0
    chunk_artifact_id: NonEmptyStr | None = None
    fusion: FusionProvenance
    metadata: dict[str, Any] = Field(default_factory=dict)


class HybridRetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    method: NonEmptyStr = "hybrid"
    top_k: PositiveInt
    candidates: list[HybridCandidate] = Field(default_factory=list)
    dense_index_id: NonEmptyStr
    lexical_index_id: NonEmptyStr
    fusion_config_hash: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class HybridRetrievalEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    evaluation_type: NonEmptyStr = "hybrid_retrieval"
    method: NonEmptyStr = "hybrid"
    dataset_id: NonEmptyStr
    case_count: NonNegativeInt
    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr
    dense_index_id: NonEmptyStr
    lexical_index_id: NonEmptyStr
    fusion_config_hash: NonEmptyStr
    dense_top_k: PositiveInt
    lexical_top_k: PositiveInt
    top_k: PositiveInt
    recall_at_1: Score
    recall_at_5: Score
    recall_at_10: Score
    mrr: Score
    latency_mean_ms: Score
    latency_p50_ms: Score
    latency_p95_ms: Score
    cases: list[RetrievalCaseResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
