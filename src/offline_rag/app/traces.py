"""Durable product query trace store (15E / D11)."""

from __future__ import annotations

import re
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

TRACE_SCHEMA_VERSION = "offline-rag-product-query-trace-v1"
TRACE_ID_RE = re.compile(r"^trace_[0-9a-f]{32}$")
MAX_RETAINED_TRACES = 1000
MAX_TRACE_AGE = timedelta(days=7)

TerminalStatus = Literal["answered", "insufficient_evidence", "model_abstain"]

ProductTraceFailureStage = Literal[
    "dense_query",
    "hybrid_retrieval",
    "rerank",
    "context_assembly",
    "generation",
    "projection",
    "trace_persistence",
    "unknown",
]

ProductTraceFailureClass = Literal[
    "dense_query_failure",
    "hybrid_retrieval_failure",
    "reranker_failure",
    "context_assembly_failure",
    "generation_failure",
    "projection_failure",
    "trace_persistence_failure",
    "cuda_runtime_failure",
    "unexpected_internal_failure",
]

ProductTraceCudaFailureClass = Literal[
    "out_of_memory",
    "cublas",
    "allocation",
    "execution",
    "unknown_cuda",
]

# Explicit GET /v1/trace/{id} allowlist — never include internal_failure.
_PUBLIC_TRACE_KEYS: tuple[str, ...] = (
    "schema_version",
    "trace_id",
    "created_at",
    "corpus",
    "snapshot_id",
    "product_mode_id",
    "request",
    "identity",
    "status",
    "error_code",
    "execution",
)


def allocate_trace_id() -> str:
    """Opaque execution identity — not a scientific identity."""
    return f"trace_{uuid.uuid4().hex}"


def is_valid_trace_id(trace_id: str) -> bool:
    return bool(TRACE_ID_RE.fullmatch(trace_id))


class ProductTraceRequestSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_sha256: str = Field(min_length=1)
    question_char_count: int = Field(ge=0)
    source_scope: ProductTraceSourceScope | None = None


class ProductTraceSourceScope(BaseModel):
    """Effective workspace source scope for a product query (16D-A)."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1)
    workspace_revision: int = Field(ge=0)
    mode: Literal["all_active", "selected"]
    source_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)


class ProductTraceIdentitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    chunk_set_id: str
    dense_index_id: str
    lexical_index_id: str
    fusion_config_hash: str
    reranker_config_hash: str
    context_config_hash: str
    generation_config_hash: str


class ProductTraceExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_evidence_unit_ids: list[str] = Field(default_factory=list)
    citation_document_ids: list[str] = Field(default_factory=list)
    citation_chunk_ids: list[str] = Field(default_factory=list)
    citation_count: int = Field(ge=0, default=0)
    generator_invoked: bool = False
    attempt_count: int = Field(ge=0, default=0)
    context_latency_ms: int | None = None
    generation_latency_ms: int | None = None
    total_latency_ms: int | None = None


_EXCEPTION_TYPE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class ProductTraceInternalFailure(BaseModel):
    """Bounded durable classification for grounded-query internal_error.

    Internal-only: omitted from GET /v1/trace/{id} public projection.
    """

    model_config = ConfigDict(extra="forbid")

    stage: ProductTraceFailureStage
    failure_class: ProductTraceFailureClass
    exception_type: str = Field(min_length=1, max_length=128)
    causal_exception_types: list[str] = Field(default_factory=list, max_length=16)
    cuda_related: bool = False
    cuda_failure_class: ProductTraceCudaFailureClass | None = None

    @field_validator("exception_type")
    @classmethod
    def _validate_exception_type(cls, value: str) -> str:
        if not _EXCEPTION_TYPE_NAME_RE.fullmatch(value):
            raise ValueError("invalid exception_type")
        return value

    @field_validator("causal_exception_types")
    @classmethod
    def _validate_causal_exception_types(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str) or not _EXCEPTION_TYPE_NAME_RE.fullmatch(item):
                raise ValueError("invalid causal_exception_types entry")
            if item not in cleaned:
                cleaned.append(item)
        return cleaned


class ProductQueryTrace(BaseModel):
    """Durable product-query audit record (D11).

    Public GET projection is an explicit allowlist via
    ``ProductTraceStore.public_projection`` and never includes
    ``internal_failure``.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = TRACE_SCHEMA_VERSION
    trace_id: str
    created_at: datetime
    corpus: str
    snapshot_id: str
    product_mode_id: str
    request: ProductTraceRequestSummary
    identity: ProductTraceIdentitySummary
    status: TerminalStatus | None = None
    error_code: str | None = None
    execution: ProductTraceExecutionSummary = Field(
        default_factory=ProductTraceExecutionSummary
    )
    internal_failure: ProductTraceInternalFailure | None = None

    @field_validator("trace_id")
    @classmethod
    def _validate_trace_id(cls, value: str) -> str:
        if not is_valid_trace_id(value):
            raise ValueError("invalid trace_id")
        return value

    def model_post_init(self, context: Any, /) -> None:
        has_status = self.status is not None
        has_error = self.error_code is not None
        if has_status == has_error:
            raise ValueError("trace must have exactly one of status or error_code")


class ProductTraceStore:
    """Process-local durable store under ``settings.paths.traces``."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._root = settings.paths.traces
        self._lock = threading.Lock()

    def _path(self, trace_id: str) -> Path:
        if not is_valid_trace_id(trace_id):
            raise AppError(ErrorCode.TRACE_UNKNOWN)
        # Filename derives only from validated opaque IDs — no path traversal.
        return self._root / f"{trace_id}.json"

    def commit(self, record: ProductQueryTrace) -> None:
        """Atomically persist a validated trace and enforce retention."""
        validated = ProductQueryTrace.model_validate(record.model_dump(mode="python"))
        path = self._path(validated.trace_id)
        # Omit null internal_failure so successful/historical shapes stay lean.
        exclude: set[str] | None = (
            None if validated.internal_failure is not None else {"internal_failure"}
        )
        with self._lock:
            self._root.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, validated.model_dump_json(exclude=exclude))
            self._enforce_retention_unlocked()

    def get(self, trace_id: str) -> ProductQueryTrace | None:
        """Return a retained durable trace, or None → trace_unknown."""
        if not is_valid_trace_id(trace_id):
            return None
        path = self._path(trace_id)
        with self._lock:
            if not path.is_file():
                return None
            try:
                record = ProductQueryTrace.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                return None
            if not self._is_retained(record, now=datetime.now(tz=UTC)):
                return None
            return record

    def public_projection(self, record: ProductQueryTrace) -> dict[str, Any]:
        """Explicit allowlisted GET /v1/trace/{id} body (no internal_failure)."""
        dumped = record.model_dump(mode="json")
        return {key: dumped[key] for key in _PUBLIC_TRACE_KEYS}

    def _is_retained(self, record: ProductQueryTrace, *, now: datetime) -> bool:
        created = record.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return now - created <= MAX_TRACE_AGE

    def _enforce_retention_unlocked(self) -> None:
        now = datetime.now(tz=UTC)
        entries: list[tuple[datetime, Path]] = []
        for path in self._root.glob("trace_*.json"):
            name = path.stem
            if not is_valid_trace_id(name):
                continue
            try:
                record = ProductQueryTrace.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                path.unlink(missing_ok=True)
                continue
            created = record.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            if now - created > MAX_TRACE_AGE:
                path.unlink(missing_ok=True)
                continue
            entries.append((created, path))

        # Newest 1000 by persisted timestamp ordering — not opaque ID lexical order.
        entries.sort(key=lambda item: item[0], reverse=True)
        for _, path in entries[MAX_RETAINED_TRACES:]:
            path.unlink(missing_ok=True)
