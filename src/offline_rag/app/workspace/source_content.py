"""Read-only source bytes for evidence preview (Slice 16D-B).

Serves ACTIVE current content and exact historical SourceHistoryStore versions
validated against a workspace revision. Never exposes vault_object_id or paths.
"""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config.models import AppSettings


@dataclass(frozen=True, slots=True)
class SourceContentPayload:
    data: bytes
    content_type: str
    content_hash: str
    display_name: str
    source_id: str
    version: int


def _require_active_workspace(
    settings: AppSettings, workspace_id: str
) -> WorkspaceRecord:
    record = WorkspaceStore(settings).get(workspace_id)
    if record.status is WorkspaceStatus.TOMBSTONED:
        raise AppError(
            ErrorCode.WORKSPACE_UNKNOWN,
            details=SafeErrorDetails(workspace_id=workspace_id),
        )
    return record


def load_active_source_content(
    settings: AppSettings, *, workspace_id: str, source_id: str
) -> SourceContentPayload:
    record = _require_active_workspace(settings, workspace_id)
    source = None
    for item in record.sources:
        if item.active and item.source_id == source_id:
            source = item
            break
    if source is None:
        raise AppError(
            ErrorCode.SOURCE_UNKNOWN,
            details=SafeErrorDetails(workspace_id=workspace_id, source_id=source_id),
        )
    vault = RawSourceVault(settings.paths.workspaces)
    data = vault.load_bytes(workspace_id, source.vault_object_id)
    meta = vault.get_meta(workspace_id, source.vault_object_id)
    return SourceContentPayload(
        data=data,
        content_type=meta.content_type or "application/octet-stream",
        content_hash=source.content_hash or meta.content_hash,
        display_name=source.display_name,
        source_id=source.source_id,
        version=source.version,
    )


def _version_active_at_revision(
    record: SourceVersionRecord, workspace_revision: WorkspaceRevision
) -> bool:
    if record.active_from_revision > workspace_revision:
        return False
    through = record.active_through_revision
    return through is None or workspace_revision <= through


def load_versioned_source_content(
    settings: AppSettings,
    *,
    workspace_id: str,
    source_id: str,
    version: int,
    workspace_revision: int,
) -> SourceContentPayload:
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_source_version"),
        )
    if (
        not isinstance(workspace_revision, int)
        or isinstance(workspace_revision, bool)
        or workspace_revision < 1
    ):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )

    _require_active_workspace(settings, workspace_id)
    history = SourceHistoryStore(settings)
    record = history.get(workspace_id, source_id, version)
    if not _version_active_at_revision(record, workspace_revision):
        raise AppError(
            ErrorCode.SOURCE_UNKNOWN,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                source_id=source_id,
                reason="source_version_not_active_at_revision",
            ),
        )
    vault = RawSourceVault(settings.paths.workspaces)
    data = vault.load_bytes(workspace_id, record.vault_object_id)
    meta = vault.get_meta(workspace_id, record.vault_object_id)
    return SourceContentPayload(
        data=data,
        content_type=meta.content_type
        or record.content_type
        or "application/octet-stream",
        content_hash=record.content_hash or meta.content_hash,
        display_name=record.display_name,
        source_id=record.source_id,
        version=record.version,
    )
