"""Durable workspace catalog persistence (Slice 16A)."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import (
    WorkspaceRecord,
    WorkspaceStatus,
    advance_revision,
    utc_now,
)
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text


class WorkspaceStore:
    """Filesystem-backed workspace catalog under ``settings.paths.workspaces``."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.root = settings.paths.workspaces

    def workspace_dir(self, workspace_id: str) -> Path:
        self._validate_workspace_id(workspace_id)
        return self.root / workspace_id

    def workspace_path(self, workspace_id: str) -> Path:
        return self.workspace_dir(workspace_id) / "workspace.json"

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> None:
        if (
            not workspace_id
            or "/" in workspace_id
            or "\\" in workspace_id
            or ".." in workspace_id
            or not workspace_id.startswith("ws_")
        ):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_workspace_id"),
            )

    def create(self, record: WorkspaceRecord) -> WorkspaceRecord:
        path = self.workspace_path(record.workspace_id)
        if path.exists():
            raise AppError(
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=record.workspace_id, reason="workspace_exists"
                ),
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write(record)
        return record

    def get(self, workspace_id: str, *, include_tombstoned: bool = False) -> WorkspaceRecord:
        path = self.workspace_path(workspace_id)
        if not path.exists():
            raise AppError(
                ErrorCode.WORKSPACE_UNKNOWN,
                details=SafeErrorDetails(workspace_id=workspace_id),
            )
        record = self._read(path, workspace_id=workspace_id)
        if record.status is WorkspaceStatus.TOMBSTONED and not include_tombstoned:
            raise AppError(
                ErrorCode.WORKSPACE_UNKNOWN,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="workspace_tombstoned"
                ),
            )
        return record

    def save(self, record: WorkspaceRecord) -> WorkspaceRecord:
        path = self.workspace_path(record.workspace_id)
        if not path.exists():
            raise AppError(
                ErrorCode.WORKSPACE_UNKNOWN,
                details=SafeErrorDetails(workspace_id=record.workspace_id),
            )
        self._write(record)
        return record

    def apply_metadata_patch(
        self,
        workspace_id: str,
        *,
        expected_revision: int,
        title: str | None = None,
        description: str | None = None,
    ) -> WorkspaceRecord:
        """Display-only mutation: advances revision; snapshot_id unchanged."""
        record = self.get(workspace_id)
        if record.revision != expected_revision:
            raise AppError(
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="revision_conflict"
                ),
            )
        updates: dict[str, object] = {
            "revision": advance_revision(record.revision),
            "updated_at": utc_now(),
        }
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        patched = record.model_copy(update=updates)
        return self.save(patched)

    def tombstone(self, workspace_id: str, *, expected_revision: int) -> WorkspaceRecord:
        record = self.get(workspace_id)
        if record.revision != expected_revision:
            raise AppError(
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="revision_conflict"
                ),
            )
        tombstoned = record.model_copy(
            update={
                "status": WorkspaceStatus.TOMBSTONED,
                "current_snapshot_id": None,
                "revision": advance_revision(record.revision),
                "updated_at": utc_now(),
            }
        )
        return self.save(tombstoned)

    def list_active(self) -> list[WorkspaceRecord]:
        if not self.root.exists():
            return []
        records: list[WorkspaceRecord] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir() or not child.name.startswith("ws_"):
                continue
            path = child / "workspace.json"
            if not path.exists():
                continue
            try:
                record = self._read(path, workspace_id=child.name)
            except AppError:
                continue
            if record.status is WorkspaceStatus.TOMBSTONED:
                continue
            records.append(record)
        return records

    def _write(self, record: WorkspaceRecord) -> None:
        path = self.workspace_path(record.workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, record.model_dump_json())

    def _read(self, path: Path, *, workspace_id: str) -> WorkspaceRecord:
        try:
            text = path.read_text(encoding="utf-8")
            record = WorkspaceRecord.model_validate_json(text)
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="workspace_state_corrupt"
                ),
            ) from exc
        if record.workspace_id != workspace_id:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="workspace_id_mismatch"
                ),
            )
        return record
