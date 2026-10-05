"""Durable managed-mutation operation / idempotency store (Slice 16A)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationResult,
    ManagedOperationSafeError,
    ManagedOperationStatus,
    OperationProgressStage,
    WorkspaceRevision,
    canonical_operation_fingerprint,
    new_operation_id,
    utc_now,
)
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

T = TypeVar("T")

# Operation ids are globally unique but records are stored per workspace. The
# locator lets GET /v1/operations/{id} find the owning workspace in one read
# instead of scanning the catalog.
OPERATION_INDEX_DIRNAME = "_operation_index"

# Legal managed-operation transitions (16A). Terminal states are immutable except
# idempotent same-status rewrite.
_TERMINAL = frozenset(
    {
        ManagedOperationStatus.SUCCEEDED,
        ManagedOperationStatus.FAILED,
        ManagedOperationStatus.INTERRUPTED,
    }
)

_LEGAL_TRANSITIONS: dict[ManagedOperationStatus, frozenset[ManagedOperationStatus]] = {
    ManagedOperationStatus.PENDING: frozenset(
        {
            ManagedOperationStatus.PREPARING,
            ManagedOperationStatus.RUNNING,
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }
    ),
    ManagedOperationStatus.PREPARING: frozenset(
        {
            ManagedOperationStatus.RUNNING,
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }
    ),
    ManagedOperationStatus.RUNNING: frozenset(
        {
            ManagedOperationStatus.SUCCEEDED,
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }
    ),
    ManagedOperationStatus.SUCCEEDED: frozenset(),
    ManagedOperationStatus.FAILED: frozenset(),
    ManagedOperationStatus.INTERRUPTED: frozenset(),
}


def assert_legal_status_transition(
    current: ManagedOperationStatus, nxt: ManagedOperationStatus
) -> None:
    if current is nxt:
        return
    allowed = _LEGAL_TRANSITIONS[current]
    if nxt not in allowed:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(reason="illegal_operation_status_transition"),
        )


def _idempotency_filename(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"idem_{digest}.json"


class OperationLocator(BaseModel):
    """Global operation_id → owning workspace pointer."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    workspace_id: str


class ManagedOperationStore:
    """Per-workspace durable operation records + idempotency index.

    Not a queue. No workers.

    Idempotency identity is the canonical envelope fingerprint of
    ``{kind, expected_revision, payload}``. Same key + same envelope recovers
    the same operation; any difference conflicts.

    ``begin`` / ``update_status`` serialize on ``WorkspaceMutationLease`` (optional
    already-held lease supported for 16B composition).
    """

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.root = settings.paths.workspaces

    def _ops_root(self, workspace_id: str) -> Path:
        if "/" in workspace_id or "\\" in workspace_id or ".." in workspace_id:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_workspace_id"),
            )
        return self.root / workspace_id / "operations"

    def _op_path(self, workspace_id: str, operation_id: str) -> Path:
        if "/" in operation_id or "\\" in operation_id or ".." in operation_id:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_operation_id"),
            )
        return self._ops_root(workspace_id) / "by_id" / f"{operation_id}.json"

    def _idem_path(self, workspace_id: str, idempotency_key: str) -> Path:
        return self._ops_root(workspace_id) / "by_idempotency" / _idempotency_filename(
            idempotency_key
        )

    def locator_path(self, operation_id: str) -> Path:
        if "/" in operation_id or "\\" in operation_id or ".." in operation_id:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_operation_id"),
            )
        return self.root / OPERATION_INDEX_DIRNAME / f"{operation_id}.json"

    def _with_lease(
        self,
        workspace_id: str,
        fn: Callable[[], T],
        *,
        lease: WorkspaceMutationLease | None,
    ) -> T:
        if lease is not None:
            if lease.workspace_id != workspace_id or not lease.held:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="lease_not_held"
                    ),
                )
            return fn()
        # Blocking acquire: concurrent begin/update_status must serialize into
        # one critical section, not fail-fast BUSY past each other.
        owned = WorkspaceMutationLease(self.settings, workspace_id)
        owned.acquire(blocking=True)
        try:
            return fn()
        finally:
            owned.release()

    def begin(
        self,
        *,
        workspace_id: str,
        idempotency_key: str,
        kind: ManagedOperationKind,
        request_payload: dict,
        expected_revision: WorkspaceRevision | None = None,
        status: ManagedOperationStatus = ManagedOperationStatus.PENDING,
        lease: WorkspaceMutationLease | None = None,
    ) -> ManagedOperationRecord:
        if status is not ManagedOperationStatus.PENDING:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="operation_must_begin_pending"),
            )
        fingerprint = canonical_operation_fingerprint(
            kind=kind,
            expected_revision=expected_revision,
            payload=request_payload,
        )

        def _body() -> ManagedOperationRecord:
            idem_path = self._idem_path(workspace_id, idempotency_key)
            if idem_path.exists():
                try:
                    pointer = idem_path.read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise AppError(
                        ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id,
                            reason="idempotency_index_unreadable",
                        ),
                    ) from exc
                existing = self.get(workspace_id, pointer)
                if (
                    existing.request_fingerprint != fingerprint
                    or existing.kind != kind
                    or existing.expected_revision != expected_revision
                ):
                    raise AppError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id,
                            operation_id=existing.operation_id,
                            reason="idempotency_identity_mismatch",
                        ),
                    )
                return existing

            now = utc_now()
            record = ManagedOperationRecord(
                operation_id=new_operation_id(),
                idempotency_key=idempotency_key,
                kind=kind,
                workspace_id=workspace_id,
                request_fingerprint=fingerprint,
                expected_revision=expected_revision,
                status=status,
                created_at=now,
                updated_at=now,
            )
            op_path = self._op_path(workspace_id, record.operation_id)
            locator = self.locator_path(record.operation_id)
            op_path.parent.mkdir(parents=True, exist_ok=True)
            locator.parent.mkdir(parents=True, exist_ok=True)
            idem_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(op_path, record.model_dump_json())
            # Indexes after the durable op write so a crash leaves an orphan op
            # (recoverable by scan) rather than a dangling index.
            atomic_write_text(
                locator,
                OperationLocator(
                    operation_id=record.operation_id, workspace_id=workspace_id
                ).model_dump_json(),
            )
            atomic_write_text(idem_path, record.operation_id)
            return record

        return self._with_lease(workspace_id, _body, lease=lease)

    def find_by_idempotency(
        self, workspace_id: str, idempotency_key: str
    ) -> ManagedOperationRecord | None:
        """Return the operation for a key if the durable index exists."""
        path = self._idem_path(workspace_id, idempotency_key)
        if not path.exists():
            return None
        try:
            operation_id = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not operation_id:
            return None
        try:
            return self.get(workspace_id, operation_id)
        except AppError:
            return None

    def get(self, workspace_id: str, operation_id: str) -> ManagedOperationRecord:
        path = self._op_path(workspace_id, operation_id)
        if not path.exists():
            raise AppError(
                ErrorCode.OPERATION_UNKNOWN,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, operation_id=operation_id
                ),
            )
        try:
            record = ManagedOperationRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    reason="operation_state_corrupt",
                ),
            ) from exc
        if record.workspace_id != workspace_id or record.operation_id != operation_id:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id,
                    operation_id=operation_id,
                    reason="operation_id_mismatch",
                ),
            )
        return record

    def update_status(
        self,
        workspace_id: str,
        operation_id: str,
        status: ManagedOperationStatus,
        *,
        result_summary: str | None = None,
        failure_summary: str | None = None,
        recovery_note: str | None = None,
        progress_stage: OperationProgressStage | None = None,
        result: ManagedOperationResult | None = None,
        error: ManagedOperationSafeError | None = None,
        lease: WorkspaceMutationLease | None = None,
    ) -> ManagedOperationRecord:
        """Advance operation state and/or attach progress and terminal payloads.

        Passing the same non-terminal status is how progress is published: the
        status machine is unchanged, only ``progress_stage`` moves.
        """

        def _body() -> ManagedOperationRecord:
            record = self.get(workspace_id, operation_id)
            assert_legal_status_transition(record.status, status)
            if record.status is status and status in _TERMINAL:
                return record
            updated = record.model_copy(
                update={
                    "status": status,
                    "updated_at": utc_now(),
                    "result_summary": result_summary
                    if result_summary is not None
                    else record.result_summary,
                    "failure_summary": failure_summary
                    if failure_summary is not None
                    else record.failure_summary,
                    "recovery_note": recovery_note
                    if recovery_note is not None
                    else record.recovery_note,
                    "progress_stage": progress_stage
                    if progress_stage is not None
                    else record.progress_stage,
                    "result": result if result is not None else record.result,
                    "error": error if error is not None else record.error,
                }
            )
            atomic_write_text(
                self._op_path(workspace_id, operation_id), updated.model_dump_json()
            )
            return updated

        return self._with_lease(workspace_id, _body, lease=lease)

    def get_by_operation_id(self, operation_id: str) -> ManagedOperationRecord:
        """Resolve an operation without knowing its workspace.

        Uses the global locator; falls back to a catalog scan when the locator
        write was lost to a crash. An ambiguous scan fails closed rather than
        guessing an owner.
        """
        locator = self.locator_path(operation_id)
        if locator.exists():
            try:
                pointer = OperationLocator.model_validate_json(
                    locator.read_text(encoding="utf-8")
                )
            except (OSError, ValidationError, ValueError) as exc:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        operation_id=operation_id, reason="operation_index_unreadable"
                    ),
                ) from exc
            if pointer.operation_id != operation_id:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        operation_id=operation_id, reason="operation_id_mismatch"
                    ),
                )
            return self.get(pointer.workspace_id, operation_id)

        owners = [
            workspace_id
            for workspace_id in self._workspace_ids()
            if self._op_path(workspace_id, operation_id).exists()
        ]
        if not owners:
            raise AppError(
                ErrorCode.OPERATION_UNKNOWN,
                details=SafeErrorDetails(operation_id=operation_id),
            )
        if len(owners) > 1:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    operation_id=operation_id, reason="operation_owner_ambiguous"
                ),
            )
        return self.get(owners[0], operation_id)

    def list_for_workspace(self, workspace_id: str) -> list[ManagedOperationRecord]:
        directory = self._ops_root(workspace_id) / "by_id"
        if not directory.exists():
            return []
        records: list[ManagedOperationRecord] = []
        for path in sorted(directory.glob("wop_*.json")):
            if not path.is_file():
                continue
            records.append(self.get(workspace_id, path.stem))
        return sorted(records, key=lambda item: item.created_at)

    def interrupt_all_nonterminal(
        self, *, recovery_note: str = "process_restart"
    ) -> list[ManagedOperationRecord]:
        """Mark operations left non-terminal by a crash as INTERRUPTED (S16-D15).

        Scientific ingest is never auto-resumed; the prior published snapshot
        stays valid. This only stops the UI from showing work that no longer has
        a worker behind it.
        """
        interrupted: list[ManagedOperationRecord] = []
        for workspace_id in self._workspace_ids():
            if not (self._ops_root(workspace_id) / "by_id").exists():
                continue
            owned = WorkspaceMutationLease(self.settings, workspace_id)
            owned.acquire(blocking=True)
            try:
                # Re-read under the lease: a live worker may have reached a
                # terminal status since the scan above.
                for record in self.list_for_workspace(workspace_id):
                    if record.status in _TERMINAL:
                        continue
                    interrupted.append(
                        self.update_status(
                            workspace_id,
                            record.operation_id,
                            ManagedOperationStatus.INTERRUPTED,
                            recovery_note=recovery_note,
                            lease=owned,
                        )
                    )
            finally:
                owned.release()
        return interrupted

    def _workspace_ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_dir() and child.name.startswith("ws_")
        )
