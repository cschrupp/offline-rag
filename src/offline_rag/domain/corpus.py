"""Corpus inventory and active-library state models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt


class CorpusDocumentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyStr
    source_path: NonEmptyStr
    source_name: NonEmptyStr
    source_content_hash: NonEmptyStr
    source_size_bytes: NonNegativeInt
    source_media_type: NonEmptyStr
    parser_name: NonEmptyStr
    parser_version: NonEmptyStr
    block_count: NonNegativeInt
    processed_artifact: NonEmptyStr
    processed_artifact_hash: NonEmptyStr
    parsed_artifact_id: NonEmptyStr
    parse_config_hash: NonEmptyStr
    warnings_count: NonNegativeInt = 0


class CorpusManifest(BaseModel):
    """Immutable deterministic snapshot of one complete active corpus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-corpus-manifest-v1"
    corpus_id: NonEmptyStr
    corpus_hash: NonEmptyStr
    created_at: datetime
    config_hash: NonEmptyStr
    documents: list[CorpusDocumentEntry] = Field(default_factory=list)
    parser_environment: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CorpusSourceEntry(BaseModel):
    """One active source path in a mutable logical library."""

    model_config = ConfigDict(extra="forbid")

    source_path: NonEmptyStr
    source_content_hash: NonEmptyStr
    document_id: NonEmptyStr
    parsed_artifact_id: NonEmptyStr
    parse_config_hash: NonEmptyStr
    processed_artifact: NonEmptyStr
    source_name: NonEmptyStr
    source_media_type: NonEmptyStr
    parser_name: NonEmptyStr
    parser_version: NonEmptyStr
    block_count: NonNegativeInt
    processed_artifact_hash: NonEmptyStr
    warnings_count: NonNegativeInt = 0


class CorpusState(BaseModel):
    """Mutable pointer to the current logical corpus inventory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = "offline-rag-corpus-state-v1"
    corpus_name: NonEmptyStr
    current_corpus_id: NonEmptyStr
    current_manifest: NonEmptyStr
    sources: dict[str, CorpusSourceEntry] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
