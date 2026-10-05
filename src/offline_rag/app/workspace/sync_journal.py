"""Minimal sync-mutation journal for crash-atomic idempotency receipts (F10/F13).

Phases:

- ``intent_recorded`` — durable op reserved; expected post-state/result prepared;
  workspace.json may or may not yet reflect that post-state
- ``workspace_committed`` — workspace mutation and frozen result are both durable;
  op may still be nonterminal

Recovery distinguishes A vs B even when the process dies after ``workspace.json``
lands but before the journal phase flips to ``workspace_committed``: the INTENT
record already carries the exact expected ``ManagedOperationResult``, and live
workspace state is matched against that mutation-specific receipt.

Startup recovers B to exact SUCCEEDED from the frozen result, and A to
INTERRUPTED. Sync recovery runs before generic ``interrupt_all_nonterminal``.
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
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
    utc_now,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.store import WorkspaceStore
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
    # Prepared exact success receipt, written at INTENT before workspace.json.
    result_json: str
    created_at: datetime
    updated_at: datetime

    def result(self) -> ManagedOperationResult:
        return ManagedOperationResult.model_validate_json(self.result_json)


def workspace_matches_expected_result(
    workspace: WorkspaceRecord,
    result: ManagedOperationResult,
    *,
    kind: ManagedOperationKind,
) -> bool:
    """True when live workspace.json matches the prepared post-mutation receipt."""
    if workspace.revision != result.workspace_revision:
        return False
    if workspace.status != result.workspace_status:
        return False
    if workspace.current_snapshot_id != result.snapshot_id:
        return False
    active = [s for s in workspace.sources if s.active]
    if result.source_count is not None and len(active) != result.source_count:
        return False
    if kind in {
        ManagedOperationKind.WORKSPACE_METADATA_PATCH,
        ManagedOperationKind.WORKSPACE_DELETE,
    }:
        if result.title is not None and workspace.title != result.title:
            return False
        if result.description is not None and workspace.description != result.description:
            return False
        if result.created_at is not None and workspace.created_at != result.created_at:
            return False
        return not (
            result.updated_at is not None and workspace.updated_at != result.updated_at
        )
    if kind is ManagedOperationKind.SOURCE_METADATA_PATCH:
        if result.source_id is None or result.source_version is None:
            return False
        match = next(
            (
                s
                for s in workspace.sources
                if s.active
                and s.source_id == result.source_id
                and s.version == result.source_version
            ),
            None,
        )
        if match is None:
            return False
        if result.display_name is not None and match.display_name != result.display_name:
            return False
        if result.content_type is not None and match.content_type != result.content_type:
            return False
        if result.byte_size is not None and match.byte_size != result.byte_size:
            return False
        if result.content_hash is not None and match.content_hash != result.content_hash:
            return False
        if result.document_id is not None and match.document_id != result.document_id:
            return False
        if (
            result.active_from_revision is not None
            and match.active_from_revision != result.active_from_revision
        ):
            return False
        if (
            result.active_from_snapshot_id is not None
            and match.active_from_snapshot_id != result.active_from_snapshot_id
        ):
            return False
        return not (
            result.created_at is not None and match.created_at != result.created_at
        )
    return False


class SyncMutationCoordinator:
    """Fence between sync workspace mutation and durable operation SUCCEEDED."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.operations = ManagedOperationStore(settings)
        self.store = WorkspaceStore(settings)

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
        expected_result: ManagedOperationResult,
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
            result_json=expected_result.model_dump_json(),
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
        prepared = journal.result()
        if prepared.model_dump_json() != result.model_dump_json():
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="sync_result_mismatch"
                ),
            )
        updated = journal.model_copy(
            update={
                "phase": SyncMutationPhase.WORKSPACE_COMMITTED,
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

    def reconcile(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease,
        failure: AppError | None = None,
    ) -> str:
        """Reconcile an open sync journal under an already-held workspace lease (F17).

        Returns ``A`` / ``B`` / ``clean``. Ambiguous post-state raises
        ``WORKSPACE_STATE_UNAVAILABLE`` and **retains** the journal.

        When ``failure`` is provided (live AppError path), outcome A terminalizes
        the operation as FAILED with that error. Startup recovery passes
        ``failure=None`` and uses INTERRUPTED for A.
        """
        if lease.workspace_id != workspace_id or not lease.held:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="lease_not_held"
                ),
            )
        journal = self.load(workspace_id)
        if journal is None:
            return "clean"
        result = journal.result()
        if journal.phase is SyncMutationPhase.WORKSPACE_COMMITTED:
            self._complete_succeeded(journal, result=result, lease=lease)
            self.drop(workspace_id, lease=lease)
            return "B"

        workspace = self.store.get(workspace_id, include_tombstoned=True)
        if workspace_matches_expected_result(workspace, result, kind=journal.kind):
            self._complete_succeeded(journal, result=result, lease=lease)
            self.drop(workspace_id, lease=lease)
            return "B"
        if workspace.revision == journal.expected_revision and (
            journal.kind is not ManagedOperationKind.WORKSPACE_DELETE
            or workspace.status is not WorkspaceStatus.TOMBSTONED
        ):
            if failure is not None:
                self._fail(journal, failure=failure, lease=lease)
            else:
                self._interrupt(journal, lease=lease)
            self.drop(workspace_id, lease=lease)
            return "A"
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                reason="sync_post_state_unrecognized",
            ),
        )

    def recover(self, workspace_id: str) -> str:
        """Startup recovery for one workspace sync journal. Returns A/B/clean."""
        lease = WorkspaceMutationLease(self.settings, workspace_id)
        lease.acquire(blocking=True)
        try:
            return self.reconcile(workspace_id, lease=lease, failure=None)
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

    def _fail(
        self,
        journal: SyncMutationJournal,
        *,
        failure: AppError,
        lease: WorkspaceMutationLease,
    ) -> None:
        from offline_rag.app.workspace.models import ManagedOperationSafeError

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
            ManagedOperationStatus.FAILED,
            error=ManagedOperationSafeError.from_app_error(failure),
            failure_summary=str(failure.code),
            recovery_note="reconciled_sync_A",
            lease=lease,
        )
