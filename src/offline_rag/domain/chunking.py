"""Chunking domain models (artifacts, manifests, reports)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.documents import Chunk
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt


class DocumentChunkStatus(StrEnum):
    CHUNKED = "chunked"
    REUSED = "reused"
    FAILED = "failed"


class ChunkingStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    NO_OP = "no_op"


class DocumentChunkArtifact(BaseModel):
    """Immutable content-addressed chunk derivation for one ParsedDocument."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-chunk-artifact-v1"
    chunk_artifact_id: NonEmptyStr
    parsed_artifact_id: NonEmptyStr
    document_id: NonEmptyStr
    chunk_config_hash: NonEmptyStr
    chunker_version: NonEmptyStr
    tokenizer_name: NonEmptyStr
    tokenizer_encoding: NonEmptyStr
    parents: list[Chunk] = Field(default_factory=list)
    children: list[Chunk] = Field(default_factory=list)
    parent_count: NonNegativeInt = 0
    child_count: NonNegativeInt = 0
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkSetDocumentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyStr
    parsed_artifact_id: NonEmptyStr
    chunk_artifact_id: NonEmptyStr
    chunk_artifact: NonEmptyStr
    chunk_artifact_hash: NonEmptyStr
    parent_count: NonNegativeInt
    child_count: NonNegativeInt


class ChunkSetManifest(BaseModel):
    """Immutable complete chunk derivation for one corpus snapshot + config."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-chunkset-manifest-v1"
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr
    chunk_config_hash: NonEmptyStr
    chunker_version: NonEmptyStr
    tokenizer_name: NonEmptyStr
    tokenizer_encoding: NonEmptyStr
    documents: list[ChunkSetDocumentEntry] = Field(default_factory=list)
    total_parent_count: NonNegativeInt = 0
    total_child_count: NonNegativeInt = 0
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkState(BaseModel):
    """Mutable pointer to the active chunk derivation for a logical corpus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-chunk-state-v1"
    corpus_name: NonEmptyStr
    source_corpus_id: NonEmptyStr
    current_chunk_set_id: NonEmptyStr
    current_chunk_manifest: NonEmptyStr
    chunk_config_hash: NonEmptyStr
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunkResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyStr
    parsed_artifact_id: NonEmptyStr | None = None
    chunk_artifact_id: NonEmptyStr | None = None
    status: DocumentChunkStatus
    parent_count: NonNegativeInt = 0
    child_count: NonNegativeInt = 0
    duration_ms: NonNegativeInt = 0
    error: str | None = None


class ChunkingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    corpus_name: NonEmptyStr
    corpus_id: NonEmptyStr | None = None
    chunk_config_hash: NonEmptyStr | None = None
    status: ChunkingStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: NonNegativeInt
    documents_total: NonNegativeInt = 0
    documents_chunked: NonNegativeInt = 0
    documents_reused: NonNegativeInt = 0
    documents_failed: NonNegativeInt = 0
    parent_chunks: NonNegativeInt = 0
    child_chunks: NonNegativeInt = 0
    chunk_set_id: NonEmptyStr | None = None
    chunk_manifest_path: str | None = None
    documents: list[DocumentChunkResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
