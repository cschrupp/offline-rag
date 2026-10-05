"""Workspace / source / managed-operation domain contracts (Slice 16A)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.core.ids import document_id_from_bytes

WORKSPACE_SCHEMA_VERSION = "offline-rag-workspace-v1"
SOURCE_VERSION_SCHEMA_VERSION = "offline-rag-source-version-v1"
MANAGED_OP_SCHEMA_VERSION = "offline-rag-managed-op-v1"

WorkspaceRevision = int  # monotonic positive integer; serialized for If-Match as decimal


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    EMPTY = "empty"
    TOMBSTONED = "tombstoned"


class ManagedOperationKind(StrEnum):
    """Kinds reserved for future 16B orchestration (persisted in 16A)."""

    WORKSPACE_CREATE = "workspace_create"
    WORKSPACE_METADATA_PATCH = "workspace_metadata_patch"
    WORKSPACE_DELETE = "workspace_delete"
    SOURCE_ADD = "source_add"
    SOURCE_REMOVE = "source_remove"
    SOURCE_REPLACE = "source_replace"
    SOURCE_METADATA_PATCH = "source_metadata_patch"
    EMPTY_TRANSITION = "empty_transition"


class ManagedOperationStatus(StrEnum):
    PENDING = "pending"
    PREPARING = "preparing"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class OperationProgressStage(StrEnum):
    """Coarse user-facing progress stage (presentation only, not a state machine).

    Progress stages are advisory UI detail. ``ManagedOperationStatus`` remains the
    authoritative durable operation state.
    """

    PREPARING = "preparing"
    PROCESSING = "processing"
    BUILDING_INDEXES = "building_indexes"
    PUBLISHING = "publishing"
    FINALIZING = "finalizing"
    READY = "ready"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def new_workspace_id() -> str:
    return f"ws_{uuid.uuid4().hex}"


def new_source_id() -> str:
    return f"src_{uuid.uuid4().hex}"


def new_operation_id() -> str:
    return f"wop_{uuid.uuid4().hex}"


def new_vault_object_id() -> str:
    return f"vobj_{uuid.uuid4().hex}"


def backing_corpus_name_for(workspace_id: str) -> str:
    """Stable server-generated product corpus name for a workspace."""
    if not workspace_id.startswith("ws_") or len(workspace_id) < 6:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_id"),
        )
    hex_part = workspace_id.removeprefix("ws_")
    # Keep within product corpus grammar / length.
    name = f"wsc_{hex_part[:48]}"
    return validate_product_corpus_name(name)


def serialize_revision(revision: WorkspaceRevision) -> str:
    """Deterministic revision representation for future If-Match / ETag."""
    if not isinstance(revision, int) or revision < 1:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )
    return str(revision)


def parse_revision(value: str) -> WorkspaceRevision:
    text = value.strip()
    if not text.isdigit():
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )
    revision = int(text)
    if revision < 1:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )
    return revision


def advance_revision(current: WorkspaceRevision) -> WorkspaceRevision:
    if current < 1:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )
    return current + 1


def content_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_id_for_content(data: bytes) -> str:
    return document_id_from_bytes(data)


def canonical_request_fingerprint(payload: dict[str, Any]) -> str:
    """Deterministic fingerprint of a canonical JSON object."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"reqfp_{digest}"


def canonical_operation_fingerprint(
    *,
    kind: ManagedOperationKind | str,
    expected_revision: WorkspaceRevision | None,
    payload: dict[str, Any],
) -> str:
    """Idempotency identity: kind + expected_revision + payload envelope."""
    envelope = {
        "kind": str(kind),
        "expected_revision": expected_revision,
        "payload": payload,
    }
    return canonical_request_fingerprint(envelope)


class SourceVersionRecord(BaseModel):
    """One workspace-level lineage event for a logical source."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-source-version-v1"] = SOURCE_VERSION_SCHEMA_VERSION
    source_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=512)
    content_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    content_hash: str | None = None
    document_id: str | None = None
    vault_object_id: str = Field(min_length=1)
    active: bool = True
    created_at: datetime
    active_from_revision: WorkspaceRevision = Field(ge=1)
    active_from_snapshot_id: str | None = None
    active_through_revision: WorkspaceRevision | None = Field(default=None, ge=1)
    active_through_snapshot_id: str | None = None

    @field_validator("source_id", "vault_object_id", "document_id", "content_hash", mode="before")
    @classmethod
    def _safe_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identity fields must be non-empty strings")
        text = value.strip()
        if "/" in text or "\\" in text or ".." in text:
            raise ValueError("identity fields must not contain path elements")
        return text


class WorkspaceRecord(BaseModel):
    """Durable workspace catalog record."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-workspace-v1"] = WORKSPACE_SCHEMA_VERSION
    workspace_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    revision: WorkspaceRevision = Field(ge=1)
    backing_corpus_name: str = Field(min_length=1, max_length=64)
    current_snapshot_id: str | None = None
    status: WorkspaceStatus
    created_at: datetime
    updated_at: datetime
    sources: list[SourceVersionRecord] = Field(default_factory=list)

    @field_validator("workspace_id", "backing_corpus_name", "current_snapshot_id", mode="before")
    @classmethod
    def _safe_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identity fields must be non-empty strings")
        text = value.strip()
        if "/" in text or "\\" in text or ".." in text:
            raise ValueError("identity fields must not contain path elements")
        return text

    @model_validator(mode="after")
    def _enforce_status_invariants(self) -> WorkspaceRecord:
        active_sources = [s for s in self.sources if s.active]
        if self.status is WorkspaceStatus.EMPTY:
            if self.sources:
                raise ValueError("empty workspace must have sources == []")
            if self.current_snapshot_id is not None:
                raise ValueError("empty workspace must have current_snapshot_id == null")
        elif self.status is WorkspaceStatus.ACTIVE:
            if not active_sources:
                raise ValueError("active workspace must have at least one active source")
            if self.current_snapshot_id is None:
                raise ValueError("active workspace must have current_snapshot_id set")
        elif self.status is WorkspaceStatus.TOMBSTONED:
            # Tombstone may retain historical source metadata; current pointer must be null.
            if self.current_snapshot_id is not None:
                raise ValueError("tombstoned workspace must have current_snapshot_id == null")
        if self.title == self.backing_corpus_name:
            raise ValueError("workspace title must not equal backing corpus identity")
        validate_product_corpus_name(self.backing_corpus_name)
        return self


def assert_empty_invariant(record: WorkspaceRecord) -> None:
    if record.status is not WorkspaceStatus.EMPTY:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, reason="expected_empty_status"
            ),
        )
    if record.sources or record.current_snapshot_id is not None:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, reason="empty_invariant_violated"
            ),
        )


def assert_non_empty_invariant(record: WorkspaceRecord) -> None:
    if record.status is not WorkspaceStatus.ACTIVE:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, reason="expected_active_status"
            ),
        )
    if not any(s.active for s in record.sources) or record.current_snapshot_id is None:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, reason="active_invariant_violated"
            ),
        )


def new_empty_workspace(
    *,
    title: str,
    description: str = "",
    workspace_id: str | None = None,
) -> WorkspaceRecord:
    """Build a fresh EMPTY workspace.

    ``workspace_id`` lets a durable create reservation reuse an already-allocated
    identity so a crashed POST retry reconstructs the same workspace instead of
    leaking a second one.
    """
    if workspace_id is None:
        workspace_id = new_workspace_id()
    elif (
        "/" in workspace_id
        or "\\" in workspace_id
        or ".." in workspace_id
        or not workspace_id.startswith("ws_")
    ):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_id"),
        )
    now = utc_now()
    return WorkspaceRecord(
        workspace_id=workspace_id,
        title=title,
        description=description,
        revision=1,
        backing_corpus_name=backing_corpus_name_for(workspace_id),
        current_snapshot_id=None,
        status=WorkspaceStatus.EMPTY,
        created_at=now,
        updated_at=now,
        sources=[],
    )


class ManagedOperationResult(BaseModel):
    """Terminal success projection of a managed mutation.

    Lets a client that lost its connection recover the authoritative post-mutation
    revision / publication identity without replaying the mutation.
    """

    model_config = ConfigDict(extra="forbid")

    workspace_revision: WorkspaceRevision = Field(ge=1)
    workspace_status: WorkspaceStatus
    snapshot_id: str | None = None
    source_id: str | None = None
    source_ids: list[str] | None = None
    source_version: int | None = Field(default=None, ge=1)

    @field_validator("snapshot_id", "source_id", mode="before")
    @classmethod
    def _safe_ids(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identity fields must be non-empty strings")
        text = value.strip()
        if "/" in text or "\\" in text or ".." in text:
            raise ValueError("identity fields must not contain path elements")
        return text

    @field_validator("source_ids", mode="before")
    @classmethod
    def _safe_id_list(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, list) or len(value) > 1024:
            raise ValueError("source_ids must be a bounded list")
        cleaned: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("source_ids entries must be non-empty strings")
            text = item.strip()
            if "/" in text or "\\" in text or ".." in text:
                raise ValueError("source_ids entries must not contain path elements")
            cleaned.append(text)
        return cleaned


class ManagedOperationSafeError(BaseModel):
    """Terminal failure projection using the D08 safe error vocabulary.

    Mirrors ``ErrorResponse`` so a polled operation surfaces the same product
    error the synchronous call would have returned. Free-form provider text is
    never persisted here.
    """

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(min_length=1, max_length=512)
    retryable: bool
    details: dict[str, str] | None = None

    @field_validator("details", mode="before")
    @classmethod
    def _bounded_details(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, dict) or len(value) > 16:
            raise ValueError("details must be a bounded mapping")
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                raise ValueError("detail keys must be bounded strings")
            if not isinstance(item, str) or len(item) > 200:
                raise ValueError("detail values must be bounded strings")
            cleaned[key] = item
        return cleaned or None

    @classmethod
    def from_app_error(cls, error: AppError) -> ManagedOperationSafeError:
        raw = error.details or {}
        details = {
            key: str(value)
            for key, value in raw.items()
            if isinstance(value, str | int | float | bool)
        }
        return cls(
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            details=details or None,
        )


class ManagedOperationRecord(BaseModel):
    """Durable managed-mutation operation record (not a job queue)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-managed-op-v1"] = MANAGED_OP_SCHEMA_VERSION
    operation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=256)
    kind: ManagedOperationKind
    workspace_id: str = Field(min_length=1)
    request_fingerprint: str = Field(min_length=1)
    expected_revision: WorkspaceRevision | None = Field(default=None, ge=1)
    status: ManagedOperationStatus
    created_at: datetime
    updated_at: datetime
    result_summary: str | None = Field(default=None, max_length=512)
    failure_summary: str | None = Field(default=None, max_length=512)
    recovery_note: str | None = Field(default=None, max_length=512)
    # 16B additions. Optional with ``None`` defaults so 16A records on disk keep
    # validating unchanged.
    progress_stage: OperationProgressStage | None = None
    result: ManagedOperationResult | None = None
    error: ManagedOperationSafeError | None = None

    @field_validator(
        "operation_id",
        "workspace_id",
        "request_fingerprint",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _non_empty(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        text = value.strip()
        if len(text) > 256:
            raise ValueError("string too long")
        return text
