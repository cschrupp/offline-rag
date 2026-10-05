"""Durable source version lineage (S16-D09).

``WorkspaceRecord.sources`` holds the ACTIVE desired set only — it is product
state and must stay small and invariant-checked. Superseded versions live here,
under ``workspaces/{workspace_id}/history/sources/{source_id}/``, so lineage
survives arbitrarily many replacements without growing the hot record.

Writes are idempotent on ``(source_id, version)``: coordinator recovery replays
``commit_lineage`` after a crash and must not fork lineage.

``vault_object_id`` stays internal. ``public_projection`` is the only shape that
may reach a client; it never exposes raw-object addressing (S16-D10).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRevision,
)
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

# Zero-padded so lexical directory order equals version order.
_VERSION_WIDTH = 8

# Fields that pin content identity for a given (source_id, version). A replayed
# idempotent write must agree on all of them.
_IDENTITY_FIELDS = (
    "display_name",
    "content_hash",
    "document_id",
    "vault_object_id",
    "byte_size",
)

_PUBLIC_FIELDS = (
    "source_id",
    "version",
    "display_name",
    "content_type",
    "byte_size",
    "content_hash",
    "document_id",
    "active",
    "created_at",
    "active_from_revision",
    "active_from_snapshot_id",
    "active_through_revision",
    "active_through_snapshot_id",
)


def _validate_id(value: str, *, reason: str) -> str:
    if (
        not value
        or not isinstance(value, str)
        or "/" in value
        or "\\" in value
        or ".." in value
    ):
        raise AppError(
            ErrorCode.REQUEST_INVALID, details=SafeErrorDetails(reason=reason)
        )
    return value


class SourceHistoryStore:
    """Append-only per-source lineage log under the workspace directory."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.root = settings.paths.workspaces

    def history_root(self, workspace_id: str) -> Path:
        _validate_id(workspace_id, reason="invalid_workspace_id")
        return self.root / workspace_id / "history" / "sources"

    def source_dir(self, workspace_id: str, source_id: str) -> Path:
        _validate_id(source_id, reason="invalid_source_id")
        return self.history_root(workspace_id) / source_id

    def version_path(
        self, workspace_id: str, source_id: str, version: int
    ) -> Path:
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_source_version"),
            )
        name = f"v{version:0{_VERSION_WIDTH}d}.json"
        return self.source_dir(workspace_id, source_id) / name

    def append(
        self, workspace_id: str, record: SourceVersionRecord
    ) -> SourceVersionRecord:
        """Record one lineage event. Idempotent on ``(source_id, version)``.

        A replay that agrees on content identity returns the stored record so
        recovery converges; a replay that disagrees is a lineage fork and fails
        closed.
        """
        path = self.version_path(workspace_id, record.source_id, record.version)
        if path.exists():
            existing = self._read(path, workspace_id=workspace_id)
            for field in _IDENTITY_FIELDS:
                if getattr(existing, field) != getattr(record, field):
                    raise AppError(
                        ErrorCode.WORKSPACE_CONFLICT,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id,
                            source_id=record.source_id,
                            reason="source_version_identity_conflict",
                        ),
                    )
            return existing
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, record.model_dump_json())
        return record

    def supersede(
        self,
        workspace_id: str,
        source_id: str,
        version: int,
        *,
        active_through_revision: WorkspaceRevision,
        active_through_snapshot_id: str | None,
    ) -> SourceVersionRecord:
        """Close out an active version. Idempotent; already-closed stays closed.

        The first recorded close-out wins so a recovery replay cannot rewrite the
        revision at which a version stopped being current.
        """
        path = self.version_path(workspace_id, source_id, version)
        if not path.exists():
            raise AppError(
                ErrorCode.SOURCE_UNKNOWN,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    reason="source_version_unknown",
                ),
            )
        existing = self._read(path, workspace_id=workspace_id)
        if not existing.active and existing.active_through_revision is not None:
            return existing
        superseded = existing.model_copy(
            update={
                "active": False,
                "active_through_revision": active_through_revision,
                "active_through_snapshot_id": active_through_snapshot_id,
            }
        )
        atomic_write_text(path, superseded.model_dump_json())
        return superseded

    def get(
        self, workspace_id: str, source_id: str, version: int
    ) -> SourceVersionRecord:
        path = self.version_path(workspace_id, source_id, version)
        if not path.exists():
            raise AppError(
                ErrorCode.SOURCE_UNKNOWN,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    source_id=source_id,
                    reason="source_version_unknown",
                ),
            )
        return self._read(path, workspace_id=workspace_id)

    def list_for_source(
        self, workspace_id: str, source_id: str
    ) -> list[SourceVersionRecord]:
        """All recorded versions for one logical source, oldest version first."""
        directory = self.source_dir(workspace_id, source_id)
        if not directory.exists():
            return []
        records = [
            self._read(path, workspace_id=workspace_id)
            for path in sorted(directory.glob("v*.json"))
            if path.is_file()
        ]
        return sorted(records, key=lambda item: item.version)

    def list_source_ids(self, workspace_id: str) -> list[str]:
        root = self.history_root(workspace_id)
        if not root.exists():
            return []
        return sorted(child.name for child in root.iterdir() if child.is_dir())

    def next_version(self, workspace_id: str, source_id: str) -> int:
        """Next lineage version for a logical source (1 when none recorded)."""
        versions = [record.version for record in self.list_for_source(workspace_id, source_id)]
        return (max(versions) + 1) if versions else 1

    @staticmethod
    def public_projection(record: SourceVersionRecord) -> dict[str, Any]:
        """Client-facing lineage shape. Never includes ``vault_object_id``."""
        return {field: getattr(record, field) for field in _PUBLIC_FIELDS}

    def _read(self, path: Path, *, workspace_id: str) -> SourceVersionRecord:
        try:
            return SourceVersionRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="source_history_corrupt"
                ),
            ) from exc
