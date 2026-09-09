"""Structural parser output models (Slice 1).

ContentBlock represents document structure from parsing.
Retrieval Chunk objects belong to Slice 2 and must not be created here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from offline_rag.domain.documents import Document
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt


class ContentType(StrEnum):
    HEADING = "heading"
    TEXT = "text"
    LIST = "list"
    TABLE = "table"
    CODE = "code"


class WarningCategory(StrEnum):
    UNSUPPORTED_STRUCTURE = "unsupported_structure"
    DEGRADED_LAYOUT = "degraded_layout"
    MALFORMED_INPUT = "malformed_input"
    MALFORMED_STRUCTURE = "malformed_structure"
    ENCODING_FALLBACK = "encoding_fallback"
    MISSING_ARTIFACTS = "missing_artifacts"
    OCR_REQUIRED = "ocr_required"
    LOW_TEXT_CONTENT = "low_text_content"
    CACHE_INTEGRITY = "cache_integrity"


class SourceLocator(BaseModel):
    """Optional physical provenance; only populate reliable fields."""

    model_config = ConfigDict(extra="forbid")

    page_number: PositiveInt | None = None
    bbox: list[float] | None = None
    source_ref: str | None = None
    line_start: PositiveInt | None = None
    line_end: PositiveInt | None = None

    @model_validator(mode="after")
    def _validate_line_range(self) -> SourceLocator:
        if (
            self.line_start is not None
            and self.line_end is not None
            and self.line_end < self.line_start
        ):
            raise ValueError("line_end must be >= line_start")
        return self


class ContentBlock(BaseModel):
    """One ordered structural unit produced by parsing."""

    model_config = ConfigDict(extra="forbid")

    id: NonEmptyStr
    document_id: NonEmptyStr
    order: NonNegativeInt
    content_type: ContentType
    text: NonEmptyStr
    page_number: PositiveInt | None = None
    section_path: list[str] = Field(default_factory=list)
    source_locator: SourceLocator | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParseWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: WarningCategory
    message: NonEmptyStr
    source_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Normalized durable parser output for one source document."""

    model_config = ConfigDict(extra="forbid")

    document: Document
    blocks: list[ContentBlock] = Field(default_factory=list)
    parser_name: NonEmptyStr
    parser_version: NonEmptyStr
    warnings: list[ParseWarning] = Field(default_factory=list)
    parsed_artifact_id: NonEmptyStr | None = None
    parse_config_hash: NonEmptyStr | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_block_consistency(self) -> ParsedDocument:
        for index, block in enumerate(self.blocks):
            if block.document_id != self.document.document_id:
                raise ValueError("block.document_id must match document.document_id")
            if block.order != index:
                raise ValueError("blocks must be ordered with contiguous order indices")
        return self
