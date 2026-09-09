"""Generation-facing domain models owned by the application core."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, PositiveInt


class Citation(BaseModel):
    """A citation that resolves to a concrete document/chunk identity."""

    model_config = ConfigDict(extra="forbid")

    citation_id: NonEmptyStr
    chunk_id: NonEmptyStr
    document_id: NonEmptyStr
    page: PositiveInt | None = None
    section_path: list[str] = Field(default_factory=list)
    claim_span: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
