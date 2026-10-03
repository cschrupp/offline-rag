"""D08 application error catalog and safe product error DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorCode(StrEnum):
    REQUEST_INVALID = "request_invalid"
    DOCUMENT_INVALID = "document_invalid"
    DOCUMENT_UNKNOWN = "document_unknown"
    CORPUS_UNKNOWN = "corpus_unknown"
    CORPUS_NOT_READY = "corpus_not_ready"
    CORPUS_BUSY = "corpus_busy"
    SNAPSHOT_UNAVAILABLE = "snapshot_unavailable"
    INGEST_FAILED = "ingest_failed"
    GENERATION_UNAVAILABLE = "generation_unavailable"
    GENERATION_TIMEOUT = "generation_timeout"
    GENERATION_FAILED = "generation_failed"
    RESPONSE_PARSE_ERROR = "response_parse_error"
    CITATION_INVALID = "citation_invalid"
    RUNTIME_NOT_READY = "runtime_not_ready"
    SERVICE_OVERLOADED = "service_overloaded"
    REQUEST_TIMEOUT = "request_timeout"
    REQUEST_CANCELLED = "request_cancelled"
    TRACE_UNKNOWN = "trace_unknown"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """Catalog entry for one product error code."""

    http_status: int | None
    retryable: bool
    default_message: str


ERROR_CATALOG: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.REQUEST_INVALID: ErrorSpec(422, False, "Request validation failed"),
    ErrorCode.DOCUMENT_INVALID: ErrorSpec(422, False, "Submitted document is invalid"),
    ErrorCode.DOCUMENT_UNKNOWN: ErrorSpec(404, False, "Document not found in published snapshot"),
    ErrorCode.CORPUS_UNKNOWN: ErrorSpec(404, False, "Corpus does not exist"),
    ErrorCode.CORPUS_NOT_READY: ErrorSpec(
        409, False, "Corpus has no published grounded-capable snapshot"
    ),
    ErrorCode.CORPUS_BUSY: ErrorSpec(409, True, "Corpus mutation lease already held"),
    ErrorCode.SNAPSHOT_UNAVAILABLE: ErrorSpec(
        409, False, "Published snapshot cannot be bound safely"
    ),
    ErrorCode.INGEST_FAILED: ErrorSpec(500, False, "Ingest failed"),
    ErrorCode.GENERATION_UNAVAILABLE: ErrorSpec(
        502, True, "Local generation provider is unavailable"
    ),
    ErrorCode.GENERATION_TIMEOUT: ErrorSpec(504, True, "Generation request timed out"),
    ErrorCode.GENERATION_FAILED: ErrorSpec(502, False, "Generation failed"),
    ErrorCode.RESPONSE_PARSE_ERROR: ErrorSpec(
        502, False, "Generated response failed the structured output contract"
    ),
    ErrorCode.CITATION_INVALID: ErrorSpec(502, False, "Citation validation failed"),
    ErrorCode.RUNTIME_NOT_READY: ErrorSpec(503, True, "OfflineRAG runtime is not ready"),
    ErrorCode.SERVICE_OVERLOADED: ErrorSpec(503, True, "Service is temporarily overloaded"),
    ErrorCode.REQUEST_TIMEOUT: ErrorSpec(504, True, "Request deadline exceeded"),
    # Trace/application-terminal only — no normative HTTP status (D18).
    ErrorCode.REQUEST_CANCELLED: ErrorSpec(None, True, "Request was cancelled"),
    ErrorCode.TRACE_UNKNOWN: ErrorSpec(404, False, "Trace not found"),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(500, False, "Internal application error"),
}


def http_status_for(code: ErrorCode | str) -> int | None:
    return ERROR_CATALOG[ErrorCode(code)].http_status


def retryable_for(code: ErrorCode | str) -> bool:
    return ERROR_CATALOG[ErrorCode(code)].retryable


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str


class ErrorResponse(BaseModel):
    """Canonical product error envelope (D08)."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody
    retryable: bool
    trace_id: str | None = None
    details: dict[str, Any] | None = None


class AppError(Exception):
    """Application-owned product error."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        spec = ERROR_CATALOG[code]
        self.code = code
        self.message = message if message is not None else spec.default_message
        self.details = details
        self.trace_id = trace_id
        self.retryable = spec.retryable
        self.http_status = spec.http_status
        super().__init__(self.message)

    def to_error_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message),
            retryable=self.retryable,
            trace_id=self.trace_id,
            details=self.details,
        )


def error_response_from_app_error(error: AppError) -> ErrorResponse:
    return error.to_error_response()
