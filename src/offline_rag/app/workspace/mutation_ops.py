"""Durable managed-mutation operation / idempotency store (Slice 16A)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationStatus,
    WorkspaceRevision,
    canonical_operation_fingerprint,
    new_operation_id,
    utc_now,
)
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

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


class ManagedOperationStore:
    """Per-workspace durable operation records + idempotency index.

    Not a queue. No workers.

    Idempotency identity is the canonical envelope fingerprint of
    ``{kind, expected_revision, payload}``. Same key + same envelope recovers
    the same operation; any difference conflicts.
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

    def begin(
        self,
        *,
        workspace_id: str,
        idempotency_key: str,
        kind: ManagedOperationKind,
        request_payload: dict,
        expected_revision: WorkspaceRevision | None = None,
        status: ManagedOperationStatus = ManagedOperationStatus.PENDING,
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
        idem_path = self._idem_path(workspace_id, idempotency_key)
        if idem_path.exists():
            try:
                pointer = idem_path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="idempotency_index_unreadable"
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
        op_path.parent.mkdir(parents=True, exist_ok=True)
        idem_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(op_path, record.model_dump_json())
        # Index after durable op write so crash leaves orphan op (recoverable) not
        # dangling index.
        atomic_write_text(idem_path, record.operation_id)
        return record

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
    ) -> ManagedOperationRecord:
        record = self.get(workspace_id, operation_id)
        assert_legal_status_transition(record.status, status)
        if record.status is status and status in _TERMINAL:
            # Idempotent terminal rewrite.
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
            }
        )
        atomic_write_text(
            self._op_path(workspace_id, operation_id), updated.model_dump_json()
        )
        return updated
