"""Document and chunk domain models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt


class Document(BaseModel):
    """One ingested source artifact."""

    model_config = ConfigDict(extra="forbid")

    document_id: NonEmptyStr
    source_uri: NonEmptyStr
    title: str | None = None
    mime_type: str | None = None
    content_hash: NonEmptyStr
    ingested_at: datetime
    parser_version: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkKind(StrEnum):
    PARENT = "parent"
    CHILD = "child"


class Chunk(BaseModel):
    """One retrieval/context unit produced by structure-aware chunking."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    kind: ChunkKind = ChunkKind.CHILD
    parent_chunk_id: NonEmptyStr | None = None
    text: NonEmptyStr
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None
    section_path: list[str] = Field(default_factory=list)
    order: NonNegativeInt
    token_count: NonNegativeInt
    content_type: NonEmptyStr = "text"
    content_hash: NonEmptyStr
    source_block_ids: list[NonEmptyStr] = Field(default_factory=list)
    previous_chunk_id: NonEmptyStr | None = None
    next_chunk_id: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_chunk(self) -> Chunk:
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        if not self.source_block_ids:
            raise ValueError("source_block_ids must be non-empty")
        if self.kind == ChunkKind.PARENT:
            if self.parent_chunk_id is not None:
                raise ValueError("parent chunks cannot have parent_chunk_id")
            if self.previous_chunk_id is not None or self.next_chunk_id is not None:
                raise ValueError("parent chunks cannot have neighbor links")
        return self
