"""Ingestion execution report models (runtime, not corpus identity)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.blocks import ParseWarning
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt


class FileIngestionStatus(StrEnum):
    PARSED = "parsed"
    REUSED = "reused"
    FAILED = "failed"


class IngestionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    NO_OP = "no_op"


class FileIngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: NonEmptyStr
    source_name: NonEmptyStr
    absolute_path: str | None = None
    status: FileIngestionStatus
    document_id: NonEmptyStr | None = None
    parsed_artifact_id: NonEmptyStr | None = None
    parser_name: NonEmptyStr | None = None
    parser_version: NonEmptyStr | None = None
    block_count: NonNegativeInt = 0
    warning_count: NonNegativeInt = 0
    warnings: list[ParseWarning] = Field(default_factory=list)
    duration_ms: NonNegativeInt = 0
    processed_artifact: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyStr
    corpus_name: NonEmptyStr
    status: IngestionStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: NonNegativeInt
    files_discovered: NonNegativeInt = 0
    files_parsed: NonNegativeInt = 0
    files_reused: NonNegativeInt = 0
    files_added: NonNegativeInt = 0
    files_updated: NonNegativeInt = 0
    files_unchanged: NonNegativeInt = 0
    files_failed: NonNegativeInt = 0
    files_warned: NonNegativeInt = 0
    blocks_total: NonNegativeInt = 0
    unsupported_files_skipped: NonNegativeInt = 0
    corpus_id: NonEmptyStr | None = None
    manifest_path: str | None = None
    files: list[FileIngestionResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
