"""Minimal sync-mutation journal for crash-atomic idempotency receipts (F10).

Phases:

- ``intent_recorded`` — durable op reserved; workspace.json not yet mutated
- ``workspace_committed`` — workspace mutation durable; op may still be nonterminal

Startup recovers ``workspace_committed`` to exact SUCCEEDED from the frozen
result, and ``intent_recorded`` to INTERRUPTED. Sync recovery runs before
generic ``interrupt_all_nonterminal``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationResult,
    ManagedOperationStatus,
    WorkspaceRevision,
    utc_now,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

SYNC_JOURNAL_SCHEMA = "offline-rag-sync-mutation-journal-v1"


class SyncMutationPhase(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    WORKSPACE_COMMITTED = "workspace_committed"


class SyncMutationJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-sync-mutation-journal-v1"] = SYNC_JOURNAL_SCHEMA
    operation_id: str
    workspace_id: str
    kind: ManagedOperationKind
    expected_revision: WorkspaceRevision = Field(ge=1)
    phase: SyncMutationPhase
    result_json: str | None = None
    created_at: datetime
    updated_at: datetime

    def result(self) -> ManagedOperationResult | None:
        if self.result_json is None:
            return None
        return ManagedOperationResult.model_validate_json(self.result_json)


class SyncMutationCoordinator:
    """Fence between sync workspace mutation and durable operation SUCCEEDED."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.operations = ManagedOperationStore(settings)

    def journal_path(self, workspace_id: str) -> Path:
        return (
            self.settings.paths.workspaces
            / workspace_id
            / "journal"
            / "sync_mutation.json"
        )

    def load(self, workspace_id: str) -> SyncMutationJournal | None:
        path = self.journal_path(workspace_id)
        if not path.exists():
            return None
        try:
            return SyncMutationJournal.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="sync_journal_corrupt"
                ),
            ) from exc

    def begin(
        self,
        workspace_id: str,
        *,
        operation_id: str,
        kind: ManagedOperationKind,
        expected_revision: WorkspaceRevision,
        lease: WorkspaceMutationLease,
    ) -> SyncMutationJournal:
        if lease.workspace_id != workspace_id or not lease.held:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="lease_not_held"
                ),
            )
        existing = self.load(workspace_id)
        if existing is not None:
            raise AppError(
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="sync_transition_in_progress"
                ),
            )
        now = utc_now()
        journal = SyncMutationJournal(
            operation_id=operation_id,
            workspace_id=workspace_id,
            kind=kind,
            expected_revision=expected_revision,
            phase=SyncMutationPhase.INTENT_RECORDED,
            created_at=now,
            updated_at=now,
        )
        path = self.journal_path(workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, journal.model_dump_json())
        return journal

    def mark_workspace_committed(
        self,
        workspace_id: str,
        *,
        result: ManagedOperationResult,
        lease: WorkspaceMutationLease,
    ) -> SyncMutationJournal:
        if lease.workspace_id != workspace_id or not lease.held:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="lease_not_held"
                ),
            )
        journal = self.load(workspace_id)
        if journal is None:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="sync_journal_missing"
                ),
            )
        if journal.phase is SyncMutationPhase.WORKSPACE_COMMITTED:
            return journal
        updated = journal.model_copy(
            update={
                "phase": SyncMutationPhase.WORKSPACE_COMMITTED,
                "result_json": result.model_dump_json(),
                "updated_at": datetime.now(tz=UTC),
            }
        )
        atomic_write_text(self.journal_path(workspace_id), updated.model_dump_json())
        return updated

    def drop(self, workspace_id: str, *, lease: WorkspaceMutationLease) -> None:
        if lease.workspace_id != workspace_id or not lease.held:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="lease_not_held"
                ),
            )
        self.journal_path(workspace_id).unlink(missing_ok=True)

    def recover(self, workspace_id: str) -> str:
        """Recover one workspace sync journal. Returns A/B/clean."""
        lease = WorkspaceMutationLease(self.settings, workspace_id)
        lease.acquire(blocking=True)
        try:
            journal = self.load(workspace_id)
            if journal is None:
                return "clean"
            if journal.phase is SyncMutationPhase.WORKSPACE_COMMITTED:
                result = journal.result()
                if result is None:
                    raise AppError(
                        ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id,
                            reason="sync_journal_result_missing",
                        ),
                    )
                self._complete_succeeded(journal, result=result, lease=lease)
                self.drop(workspace_id, lease=lease)
                return "B"
            # Intent only: mutation never committed.
            self._interrupt(journal, lease=lease)
            self.drop(workspace_id, lease=lease)
            return "A"
        finally:
            lease.release()

    def recover_all(self) -> list[tuple[str, str]]:
        root = self.settings.paths.workspaces
        if not root.exists():
            return []
        results: list[tuple[str, str]] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not child.name.startswith("ws_"):
                continue
            if not (child / "journal" / "sync_mutation.json").exists():
                continue
            results.append((child.name, self.recover(child.name)))
        return results

    def _complete_succeeded(
        self,
        journal: SyncMutationJournal,
        *,
        result: ManagedOperationResult,
        lease: WorkspaceMutationLease,
    ) -> None:
        try:
            record = self.operations.get(journal.workspace_id, journal.operation_id)
        except AppError:
            return
        if record.status is ManagedOperationStatus.SUCCEEDED:
            return
        if record.status in {
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            return
        if record.status is ManagedOperationStatus.PENDING:
            self.operations.update_status(
                journal.workspace_id,
                journal.operation_id,
                ManagedOperationStatus.RUNNING,
                lease=lease,
            )
        self.operations.update_status(
            journal.workspace_id,
            journal.operation_id,
            ManagedOperationStatus.SUCCEEDED,
            result=result,
            recovery_note="recovered_sync_B",
            lease=lease,
        )

    def _interrupt(
        self, journal: SyncMutationJournal, *, lease: WorkspaceMutationLease
    ) -> None:
        try:
            record = self.operations.get(journal.workspace_id, journal.operation_id)
        except AppError:
            return
        if record.status in {
            ManagedOperationStatus.SUCCEEDED,
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            return
        self.operations.update_status(
            journal.workspace_id,
            journal.operation_id,
            ManagedOperationStatus.INTERRUPTED,
            recovery_note="recovered_sync_A",
            lease=lease,
        )
