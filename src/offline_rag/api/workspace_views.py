"""Public DTO projections for workspace / source / operation APIs (Slice 16B)."""

from __future__ import annotations

from typing import Any

from offline_rag.app.workspace.models import (
    ManagedOperationRecord,
    SourceVersionRecord,
    WorkspaceRecord,
)


def workspace_view(record: WorkspaceRecord) -> dict[str, Any]:
    """Product-facing workspace projection (no corpus / vault / lock paths)."""
    active = [s for s in record.sources if s.active]
    return {
        "workspace_id": record.workspace_id,
        "title": record.title,
        "description": record.description,
        "revision": record.revision,
        "status": str(record.status),
        "current_snapshot_id": record.current_snapshot_id,
        "source_count": len(active),
        "created_at": record.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": record.updated_at.isoformat().replace("+00:00", "Z"),
    }


def source_view(record: SourceVersionRecord) -> dict[str, Any]:
    """Current-source projection (no vault_object_id)."""
    return {
        "source_id": record.source_id,
        "version": record.version,
        "display_name": record.display_name,
        "content_type": record.content_type,
        "byte_size": record.byte_size,
        "content_hash": record.content_hash,
        "document_id": record.document_id,
        "created_at": record.created_at.isoformat().replace("+00:00", "Z"),
        "active_from_revision": record.active_from_revision,
        "active_from_snapshot_id": record.active_from_snapshot_id,
    }


def operation_view(record: ManagedOperationRecord) -> dict[str, Any]:
    """Managed-operation projection for 202 / GET operation."""
    result = None
    if record.result is not None:
        result = record.result.model_dump(mode="python", exclude_none=True)
        if "workspace_status" in result:
            result["workspace_status"] = str(result["workspace_status"])
    error = None
    if record.error is not None:
        error = {
            "code": str(record.error.code),
            "message": record.error.message,
            "retryable": record.error.retryable,
            "details": record.error.details,
        }
    return {
        "operation_id": record.operation_id,
        "kind": str(record.kind),
        "workspace_id": record.workspace_id,
        "expected_revision": record.expected_revision,
        "status": str(record.status),
        "progress_stage": (
            str(record.progress_stage) if record.progress_stage is not None else None
        ),
        "created_at": record.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": record.updated_at.isoformat().replace("+00:00", "Z"),
        "result": result,
        "error": error,
    }
