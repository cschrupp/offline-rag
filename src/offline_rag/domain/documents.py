"""Document and chunk domain models."""

from __future__ import annotations

from datetime import datetime
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


class Chunk(BaseModel):
    """One searchable retrieval unit."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    parent_chunk_id: NonEmptyStr | None = None
    text: NonEmptyStr
    page_start: PositiveInt | None = None
    page_end: PositiveInt | None = None
    section_path: list[str] = Field(default_factory=list)
    chunk_index: NonNegativeInt
    token_count: NonNegativeInt
    content_type: NonEmptyStr = "text"
    content_hash: NonEmptyStr
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_page_range(self) -> Chunk:
        if self.page_start is not None and self.page_end is not None and self.page_end < self.page_start:
            raise ValueError("page_end must be >= page_start")
        return self
