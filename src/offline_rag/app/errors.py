"""D08 application error catalog and safe product error DTOs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Identity-like values permitted from untrusted detail mappings.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

# Top-level keys that may be accepted from arbitrary AppError(details=dict...).
# Free-form text channels (reason, fields[].msg) are NOT accepted this way.
_UNTRUSTED_DETAIL_KEYS = frozenset(
    {
        "corpus",
        "snapshot_id",
        "document_id",
        "field",
        "stage",
        "provider_failure_class",
        "workspace_id",
        "source_id",
        "operation_id",
        "project_id",
        "campaign_id",
        "task_id",
        "dataset_id",
        "case_id",
    }
)

_SECRET_KEY_TOKENS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "credential",
        "private_key",
    }
)


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
    # Slice 16A workspace foundation (HTTP mapping frozen for future 16B).
    WORKSPACE_UNKNOWN = "workspace_unknown"
    WORKSPACE_NOT_READY = "workspace_not_ready"
    WORKSPACE_CONFLICT = "workspace_conflict"
    SOURCE_UNKNOWN = "source_unknown"
    OPERATION_UNKNOWN = "operation_unknown"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    WORKSPACE_STATE_UNAVAILABLE = "workspace_state_unavailable"
    SETTINGS_INVALID = "settings_invalid"
    SETTINGS_LOCKED = "settings_locked"
    SETTINGS_PROBE_FAILED = "settings_probe_failed"
    # Slice 16F-D Gold Lab application / API data plane.
    GOLD_PROJECT_UNKNOWN = "gold_project_unknown"
    GOLD_CAMPAIGN_UNKNOWN = "gold_campaign_unknown"
    GOLD_TASK_UNKNOWN = "gold_task_unknown"
    GOLD_BASELINE_UNKNOWN = "gold_baseline_unknown"
    GOLD_CONFLICT = "gold_conflict"
    GOLD_BUSY = "gold_busy"
    GOLD_STATE_UNAVAILABLE = "gold_state_unavailable"


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
    ErrorCode.WORKSPACE_UNKNOWN: ErrorSpec(404, False, "Workspace not found"),
    ErrorCode.WORKSPACE_NOT_READY: ErrorSpec(
        409, False, "Workspace has no current publication"
    ),
    ErrorCode.WORKSPACE_CONFLICT: ErrorSpec(
        409, False, "Workspace revision or state conflict"
    ),
    ErrorCode.SOURCE_UNKNOWN: ErrorSpec(404, False, "Source not found in workspace"),
    ErrorCode.OPERATION_UNKNOWN: ErrorSpec(404, False, "Managed operation not found"),
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorSpec(
        409, False, "Idempotency key conflicts with a different request"
    ),
    ErrorCode.WORKSPACE_STATE_UNAVAILABLE: ErrorSpec(
        409, False, "Workspace durable state cannot be bound safely"
    ),
    ErrorCode.SETTINGS_INVALID: ErrorSpec(422, False, "Settings validation failed"),
    ErrorCode.SETTINGS_LOCKED: ErrorSpec(
        409, False, "Setting is locked by operator configuration"
    ),
    ErrorCode.SETTINGS_PROBE_FAILED: ErrorSpec(
        409, True, "Generation connection probe failed"
    ),
    ErrorCode.GOLD_PROJECT_UNKNOWN: ErrorSpec(404, False, "Gold project not found"),
    ErrorCode.GOLD_CAMPAIGN_UNKNOWN: ErrorSpec(404, False, "Gold campaign not found"),
    ErrorCode.GOLD_TASK_UNKNOWN: ErrorSpec(404, False, "Gold task not found"),
    ErrorCode.GOLD_BASELINE_UNKNOWN: ErrorSpec(
        404, False, "Gold authoring baseline not found"
    ),
    ErrorCode.GOLD_CONFLICT: ErrorSpec(
        409, False, "Gold Lab state conflicts with the requested operation"
    ),
    ErrorCode.GOLD_BUSY: ErrorSpec(409, True, "Gold Lab resource is busy"),
    ErrorCode.GOLD_STATE_UNAVAILABLE: ErrorSpec(
        409, False, "Gold Lab durable state cannot be bound safely"
    ),
}


def http_status_for(code: ErrorCode | str) -> int | None:
    return ERROR_CATALOG[ErrorCode(code)].http_status


def retryable_for(code: ErrorCode | str) -> bool:
    return ERROR_CATALOG[ErrorCode(code)].retryable


def _normalize_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _is_secret_key(key: object) -> bool:
    token = _normalize_key(key)
    if token in _SECRET_KEY_TOKENS:
        return True
    return any(secret in token for secret in _SECRET_KEY_TOKENS)


def _is_safe_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(_SAFE_ID_RE.fullmatch(value))


def is_safe_identity(value: object) -> bool:
    """Return whether ``value`` is a bounded safe identity token."""
    return _is_safe_id(value)


class ValidationFieldDetail(BaseModel):
    """Trusted validation projection entry (loc / msg / type only)."""

    model_config = ConfigDict(extra="forbid")

    loc: list[str] = Field(default_factory=list)
    msg: str
    type: str


class SafeErrorDetails(BaseModel):
    """Trusted, application-authored product error details.

    Free-form ``reason`` / validation ``fields`` may only be attached through
    this DTO (or factories that produce it). Arbitrary ``AppError(details=dict)``
    input cannot inject those channels.
    """

    model_config = ConfigDict(extra="forbid")

    corpus: str | None = None
    snapshot_id: str | None = None
    document_id: str | None = None
    workspace_id: str | None = None
    source_id: str | None = None
    operation_id: str | None = None
    project_id: str | None = None
    campaign_id: str | None = None
    task_id: str | None = None
    dataset_id: str | None = None
    case_id: str | None = None
    stage: str | None = None
    provider_failure_class: str | None = None
    field: str | None = None
    reason: str | None = None
    fields: list[ValidationFieldDetail] | None = None

    @field_validator(
        "corpus",
        "snapshot_id",
        "document_id",
        "workspace_id",
        "source_id",
        "operation_id",
        "project_id",
        "campaign_id",
        "task_id",
        "dataset_id",
        "case_id",
        "stage",
        "provider_failure_class",
        "field",
        mode="before",
    )
    @classmethod
    def _require_safe_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not _is_safe_id(value):
            raise ValueError("detail identity fields must be safe identifiers")
        return value

    @field_validator("reason", mode="before")
    @classmethod
    def _bound_reason(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("reason must be a string")
        text = value.strip()
        if not text or len(text) > 200:
            raise ValueError("reason must be a non-empty bounded string")
        # Closed application reason codes only (no free-form prose / headers).
        if not _SAFE_ID_RE.fullmatch(text):
            raise ValueError("reason must be a safe application reason code")
        return text

    def to_envelope_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_none=True)


def _sanitize_untrusted_mapping(details: Mapping[str, Any]) -> dict[str, Any] | None:
    cleaned: dict[str, Any] = {}
    for key, value in details.items():
        if _is_secret_key(key):
            continue
        norm = _normalize_key(key)
        # Untrusted mappings cannot carry free-form text channels.
        if norm in {"reason", "fields"}:
            continue
        if norm not in _UNTRUSTED_DETAIL_KEYS:
            continue
        if _is_safe_id(value):
            cleaned[norm] = value
    return cleaned or None


def sanitize_error_details(
    details: SafeErrorDetails | Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Project details for ErrorResponse.

    - ``SafeErrorDetails``: trusted application projection (may include reason/fields)
    - bare mappings: untrusted; identity-like keys only; no free-form reason/msg
    """
    if details is None:
        return None
    if isinstance(details, SafeErrorDetails):
        payload = details.to_envelope_dict()
        return payload or None
    if isinstance(details, Mapping):
        return _sanitize_untrusted_mapping(details)
    return None


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
        details: SafeErrorDetails | Mapping[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        spec = ERROR_CATALOG[code]
        self.code = code
        self.message = message if message is not None else spec.default_message
        # Keep the original trusted/untrusted input so SafeErrorDetails is not
        # downgraded when projecting to the envelope.
        self._details_input: SafeErrorDetails | Mapping[str, Any] | None = details
        self.trace_id = trace_id
        self.retryable = spec.retryable
        self.http_status = spec.http_status
        super().__init__(self.message)

    @property
    def details(self) -> dict[str, Any] | None:
        return sanitize_error_details(self._details_input)

    def to_error_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message),
            retryable=self.retryable,
            trace_id=self.trace_id,
            details=sanitize_error_details(self._details_input),
        )


def error_response_from_app_error(error: AppError) -> ErrorResponse:
    return error.to_error_response()
