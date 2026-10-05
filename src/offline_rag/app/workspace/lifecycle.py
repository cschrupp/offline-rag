"""Workspace / source lifecycle orchestration (Slice 16B application core).

No HTTP here. This is the single place that knows how a user-facing mutation
becomes durable state, and it keeps three rules from 16A/16B authority:

1. Display-only metadata edits advance the workspace revision and nothing else
   (S16-D11) — no candidate, no ingest, no new ``snapshot_id``.
2. Content / membership mutations that leave at least one active source run the
   whole desired set through Slice-15 full-replace ingest, coordinated by
   ``NonEmptyPublicationCoordinator`` so publication and workspace commit cannot
   diverge across a crash.
3. Removing the final active source is the EMPTY transition (S16-D13), handled
   by ``EmptyTransitionCoordinator``; it must never run an empty ingest.

Lock order is ``WorkspaceMutationLease`` then ``CorpusMutationLease``. The
workspace lease is held for the whole managed mutation, including the journal
critical sections; ``run_product_replace_ingest`` takes the corpus lease
underneath it. Acquisition is fail-fast: capacity stays small and bounded, with
no queue behind it (S16-D15).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import spool_local_files
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.operations import OperationHandle
from offline_rag.app.workspace.create_idempotency import WorkspaceCreateCatalog
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.journal import EmptyTransitionCoordinator
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationRecord,
    ManagedOperationResult,
    ManagedOperationSafeError,
    ManagedOperationStatus,
    OperationProgressStage,
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
    advance_revision,
    content_sha256_hex,
    document_id_for_content,
    new_empty_workspace,
    new_source_id,
    utc_now,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.projection import materialize_desired_sources
from offline_rag.app.workspace.publication_journal import (
    LineageDelta,
    NonEmptyPublicationCoordinator,
    PublicationMutationKind,
    SourceVersionRef,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.sync_journal import SyncMutationCoordinator
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.base import SUPPORTED_EXTENSIONS

if TYPE_CHECKING:
    from offline_rag.app.runtime import ApplicationRuntime

# Slice-15 ingest stage names mapped to coarse user-facing progress.
_STAGE_PROGRESS: dict[str, OperationProgressStage] = {
    "ingest": OperationProgressStage.PROCESSING,
    "chunk": OperationProgressStage.PROCESSING,
    "dense": OperationProgressStage.BUILDING_INDEXES,
    "lexical": OperationProgressStage.BUILDING_INDEXES,
    "publish": OperationProgressStage.PUBLISHING,
}


@dataclass(frozen=True)
class SourceUpload:
    """One raw source submitted by a user.

    Prefer durable ``spool_path`` + ``content_sha256`` for HTTP acceptance so
    request-memory bytes are not the only copy after 202. In-memory ``content``
    remains supported for unit tests and non-HTTP callers.
    """

    display_name: str
    content_type: str | None = None
    content: bytes | None = None
    spool_path: Path | None = None
    content_sha256: str | None = None

    def digest(self) -> str:
        if self.content_sha256 is not None:
            return self.content_sha256
        return content_sha256_hex(self.load_bytes())

    def load_bytes(self) -> bytes:
        if self.content is not None:
            data = self.content
        elif self.spool_path is not None:
            try:
                data = self.spool_path.read_bytes()
            except OSError as exc:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(reason="upload_spool_missing"),
                ) from exc
        else:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="upload_bytes_missing"),
            )
        if self.content_sha256 is not None:
            actual = content_sha256_hex(data)
            if actual != self.content_sha256:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(reason="upload_spool_digest_mismatch"),
                )
        return data


@dataclass(frozen=True)
class _MutationPlan:
    """Fully resolved intent for one content/membership mutation."""

    mutation_kind: PublicationMutationKind
    desired: list[SourceVersionRecord]
    lineage: LineageDelta
    source_id: str
    source_version: int | None


def _conflict(workspace_id: str, reason: str) -> AppError:
    return AppError(
        ErrorCode.WORKSPACE_CONFLICT,
        details=SafeErrorDetails(workspace_id=workspace_id, reason=reason),
    )


def _assert_supported_source(display_name: str) -> None:
    if Path(display_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise AppError(
            ErrorCode.DOCUMENT_INVALID,
            details=SafeErrorDetails(reason="unsupported_source_type"),
        )


class WorkspaceLifecycleService:
    """Application use cases for workspace and source lifecycle."""

    def __init__(self, runtime: ApplicationRuntime) -> None:
        self.runtime = runtime
        self.settings = runtime.settings
        self.store = WorkspaceStore(self.settings)
        self.operations = ManagedOperationStore(self.settings)
        self.history = SourceHistoryStore(self.settings)
        self.vault = RawSourceVault(self.settings.paths.workspaces)
        self.creates = WorkspaceCreateCatalog(self.settings)
        self.publication = NonEmptyPublicationCoordinator(
            self.settings, self.store, self.history
        )
        self.empty_transition = EmptyTransitionCoordinator(self.settings, self.store)
        self.sync_mutations = SyncMutationCoordinator(self.settings)

    # ------------------------------------------------------- synchronous CRUD

    def create_workspace(
        self, *, idempotency_key: str, title: str, description: str = ""
    ) -> WorkspaceRecord:
        """Create an EMPTY workspace idempotently (S16-D07 / S16-D14).

        The workspace id is reserved durably before ``workspace.json`` exists, so
        a retried POST reuses the reservation instead of creating a twin.
        """
        reservation, _ = self.creates.reserve(
            idempotency_key=idempotency_key, title=title, description=description
        )
        workspace_id = reservation.workspace_id
        with WorkspaceMutationLease(self.settings, workspace_id) as lease:
            existing = self._load_optional(workspace_id)
            if existing is not None:
                return existing
            record = new_empty_workspace(
                title=reservation.title,
                description=reservation.description,
                workspace_id=workspace_id,
            )
            return self.store.create(record, lease=lease)

    def patch_workspace_metadata(
        self,
        workspace_id: str,
        *,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        title: str | None = None,
        description: str | None = None,
    ) -> tuple[dict[str, Any], ManagedOperationRecord]:
        """Display-only edit with durable idempotency (S16-D11 / S16-D14)."""
        if title is None and description is None:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="empty_metadata_patch"),
            )
        payload = {"title": title, "description": description}
        with WorkspaceMutationLease(self.settings, workspace_id) as lease:
            op = self.operations.begin(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                request_payload=payload,
                expected_revision=expected_revision,
                lease=lease,
            )
            replay = self._replay_sync_operation(op)
            if replay is not None:
                return replay
            try:
                current = self.store.get(workspace_id)
                if current.revision != expected_revision:
                    raise _conflict(workspace_id, "revision_conflict")
                updates: dict[str, object] = {
                    "revision": advance_revision(current.revision),
                    "updated_at": utc_now(),
                }
                if title is not None:
                    updates["title"] = title
                if description is not None:
                    updates["description"] = description
                prepared = current.model_copy(update=updates)
                result = self._workspace_result_receipt(prepared)
                # F13: persist exact expected receipt before workspace.json lands.
                self.sync_mutations.begin(
                    workspace_id,
                    operation_id=op.operation_id,
                    kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                    expected_revision=expected_revision,
                    expected_result=result,
                    lease=lease,
                )
                record = self.store.save(prepared, lease=lease)
                result = self._workspace_result_receipt(record)
                self.sync_mutations.mark_workspace_committed(
                    workspace_id, result=result, lease=lease
                )
                op = self._succeed_sync_operation(
                    workspace_id, op.operation_id, result=result, lease=lease
                )
                self.sync_mutations.drop(workspace_id, lease=lease)
                return self._workspace_public_from_result(workspace_id, op), op
            except AppError as exc:
                return self._handle_sync_app_error(
                    workspace_id,
                    op,
                    exc,
                    lease=lease,
                    public_from_result=self._workspace_public_from_result,
                )

    def tombstone_workspace(
        self,
        workspace_id: str,
        *,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], ManagedOperationRecord]:
        """Logical delete with durable idempotency (S16-D13 / S16-D14)."""
        payload = {"action": "tombstone"}
        with WorkspaceMutationLease(self.settings, workspace_id) as lease:
            op = self.operations.begin(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                kind=ManagedOperationKind.WORKSPACE_DELETE,
                request_payload=payload,
                expected_revision=expected_revision,
                lease=lease,
            )
            replay = self._replay_sync_operation(op)
            if replay is not None:
                return replay
            try:
                current = self.store.get(workspace_id)
                if current.revision != expected_revision:
                    raise _conflict(workspace_id, "revision_conflict")
                prepared = current.model_copy(
                    update={
                        "status": WorkspaceStatus.TOMBSTONED,
                        "current_snapshot_id": None,
                        "revision": advance_revision(current.revision),
                        "updated_at": utc_now(),
                    }
                )
                result = self._workspace_result_receipt(prepared)
                self.sync_mutations.begin(
                    workspace_id,
                    operation_id=op.operation_id,
                    kind=ManagedOperationKind.WORKSPACE_DELETE,
                    expected_revision=expected_revision,
                    expected_result=result,
                    lease=lease,
                )
                record = self.store.save(prepared, lease=lease)
                result = self._workspace_result_receipt(record)
                self.sync_mutations.mark_workspace_committed(
                    workspace_id, result=result, lease=lease
                )
                op = self._succeed_sync_operation(
                    workspace_id, op.operation_id, result=result, lease=lease
                )
                self.sync_mutations.drop(workspace_id, lease=lease)
                return self._workspace_public_from_result(workspace_id, op), op
            except AppError as exc:
                return self._handle_sync_app_error(
                    workspace_id,
                    op,
                    exc,
                    lease=lease,
                    public_from_result=self._workspace_public_from_result,
                )

    def _handle_sync_app_error(
        self,
        workspace_id: str,
        op: ManagedOperationRecord,
        exc: AppError,
        *,
        lease: WorkspaceMutationLease,
        public_from_result: Callable[[str, ManagedOperationRecord], dict[str, Any]],
    ) -> tuple[dict[str, Any], ManagedOperationRecord]:
        """Reconcile sync journal on AppError; never drop post-write evidence (F17)."""
        if self.sync_mutations.load(workspace_id) is None:
            self.operations.update_status(
                workspace_id,
                op.operation_id,
                ManagedOperationStatus.FAILED,
                error=ManagedOperationSafeError.from_app_error(exc),
                failure_summary=str(exc.code),
                lease=lease,
            )
            raise exc
        # Ambiguous post-state raises workspace_state_unavailable and keeps journal.
        outcome = self.sync_mutations.reconcile(
            workspace_id, lease=lease, failure=exc
        )
        if outcome == "B":
            succeeded = self.operations.get(workspace_id, op.operation_id)
            return public_from_result(workspace_id, succeeded), succeeded
        raise exc

    def _succeed_sync_operation(
        self,
        workspace_id: str,
        operation_id: str,
        *,
        result: ManagedOperationResult,
        lease: WorkspaceMutationLease,
    ) -> ManagedOperationRecord:
        """Terminalize a sync mutation through the legal status machine."""
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            lease=lease,
        )
        return self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.SUCCEEDED,
            result=result,
            lease=lease,
        )

    @staticmethod
    def _workspace_result_receipt(record: WorkspaceRecord) -> ManagedOperationResult:
        active = [s for s in record.sources if s.active]
        return ManagedOperationResult(
            workspace_revision=record.revision,
            workspace_status=record.status,
            snapshot_id=record.current_snapshot_id,
            title=record.title,
            description=record.description,
            source_count=len(active),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _workspace_public_from_result(
        workspace_id: str, op: ManagedOperationRecord
    ) -> dict[str, Any]:
        """Exact public workspace projection from a frozen sync receipt (F9)."""
        assert op.result is not None
        r = op.result
        created = r.created_at or op.created_at
        updated = r.updated_at or op.updated_at
        return {
            "workspace_id": workspace_id,
            "title": r.title or "",
            "description": r.description or "",
            "revision": r.workspace_revision,
            "status": str(r.workspace_status),
            "current_snapshot_id": r.snapshot_id,
            "source_count": int(r.source_count or 0),
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "updated_at": updated.isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _source_public_from_result(op: ManagedOperationRecord) -> dict[str, Any]:
        assert op.result is not None
        r = op.result
        created = r.created_at or op.created_at
        return {
            "source_id": r.source_id,
            "version": r.source_version,
            "display_name": r.display_name,
            "content_type": r.content_type,
            "byte_size": r.byte_size,
            "content_hash": r.content_hash,
            "document_id": r.document_id,
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "active_from_revision": r.active_from_revision,
            "active_from_snapshot_id": r.active_from_snapshot_id,
        }

    def _raise_from_sync_terminal(self, op: ManagedOperationRecord) -> None:
        if op.error is not None:
            details = op.error.details
            raise AppError(
                op.error.code,
                message=op.error.message,
                details=details,
            )
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=op.workspace_id,
                operation_id=op.operation_id,
                reason="operation_interrupted",
            ),
        )

    def _replay_sync_operation(
        self, op: ManagedOperationRecord
    ) -> tuple[dict[str, Any], ManagedOperationRecord] | None:
        if op.status is ManagedOperationStatus.SUCCEEDED and op.result is not None:
            if op.kind is ManagedOperationKind.SOURCE_METADATA_PATCH:
                return self._source_public_from_result(op), op
            return self._workspace_public_from_result(op.workspace_id, op), op
        if op.status in {
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            self._raise_from_sync_terminal(op)
        return None

    # ------------------------------------------------- managed source mutations

    def reserve_and_admit_scientific(
        self,
        workspace_id: str,
        *,
        kind: ManagedOperationKind,
        idempotency_key: str,
        expected_revision: WorkspaceRevision,
        payload: dict[str, Any],
        require_source_id: str | None = None,
    ) -> tuple[ManagedOperationRecord, OperationHandle | None]:
        """Strict idempotency preflight before ingest capacity / worker launch.

        Ordering (F3/F8):
        1. existing matching key → return it (even if If-Match is now stale)
        2. conflicting key → idempotency_conflict
        3. NEW key → validate workspace/revision/source preconditions
        4. reserve + admit + launch
        """
        self.runtime.require_ready()
        from offline_rag.app.workspace.models import canonical_operation_fingerprint

        lease = WorkspaceMutationLease(self.settings, workspace_id)
        lease.acquire(blocking=True)
        try:
            fingerprint = canonical_operation_fingerprint(
                kind=kind,
                expected_revision=expected_revision,
                payload=payload,
            )
            existing = self.operations.find_by_idempotency(workspace_id, idempotency_key)
            if existing is not None:
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
                return existing, None

            # NEW key: cheap preconditions before capacity / reservation.
            record = self.store.get(workspace_id)
            if record.status is WorkspaceStatus.TOMBSTONED:
                raise AppError(
                    ErrorCode.WORKSPACE_UNKNOWN,
                    details=SafeErrorDetails(workspace_id=workspace_id),
                )
            if record.revision != expected_revision:
                raise _conflict(workspace_id, "revision_conflict")
            if require_source_id is not None and not any(
                s.active and s.source_id == require_source_id for s in record.sources
            ):
                raise AppError(
                    ErrorCode.SOURCE_UNKNOWN,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, source_id=require_source_id
                    ),
                )

            operation, created = self.operations.reserve(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                kind=kind,
                request_payload=payload,
                expected_revision=expected_revision,
                lease=lease,
            )
            if not created:
                return operation, None
            try:
                handle = self.runtime.operations.admit_ingest()
            except AppError as exc:
                self.operations.update_status(
                    workspace_id,
                    operation.operation_id,
                    ManagedOperationStatus.FAILED,
                    error=ManagedOperationSafeError.from_app_error(exc),
                    failure_summary=str(exc.code),
                    lease=lease,
                )
                raise
            return operation, handle
        finally:
            lease.release()

    def add_source(
        self,
        workspace_id: str,
        *,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        upload: SourceUpload,
        control: OperationHandle | None = None,
    ) -> ManagedOperationRecord:
        return self.add_sources(
            workspace_id,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            uploads=[upload],
            control=control,
        )

    def add_sources(
        self,
        workspace_id: str,
        *,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        uploads: Sequence[SourceUpload],
        control: OperationHandle | None = None,
    ) -> ManagedOperationRecord:
        """Atomic multi-file add into the desired active set (one mutation)."""
        if not uploads:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="zero_files"),
            )
        for upload in uploads:
            _assert_supported_source(upload.display_name)
        payload = {
            "files": [
                {
                    "display_name": u.display_name,
                    "content_type": u.content_type,
                    "content_sha256": u.digest(),
                }
                for u in uploads
            ]
        }
        return self._run_managed_mutation(
            workspace_id,
            kind=ManagedOperationKind.SOURCE_ADD,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            payload=payload,
            plan=lambda record: self._plan_add(record, uploads),
            control=control,
        )

    def patch_source_metadata(
        self,
        workspace_id: str,
        source_id: str,
        *,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        display_name: str,
    ) -> tuple[dict[str, Any], ManagedOperationRecord]:
        """Display-only rename with durable idempotency."""
        name = display_name.strip()
        if not name:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="empty_display_name"),
            )
        if len(name) > 512:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="display_name_too_long"),
            )
        payload = {"source_id": source_id, "display_name": name}
        with WorkspaceMutationLease(self.settings, workspace_id) as lease:
            op = self.operations.begin(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                kind=ManagedOperationKind.SOURCE_METADATA_PATCH,
                request_payload=payload,
                expected_revision=expected_revision,
                lease=lease,
            )
            replay = self._replay_sync_operation(op)
            if replay is not None:
                return replay
            try:
                record = self.store.get(workspace_id)
                if record.revision != expected_revision:
                    raise _conflict(workspace_id, "revision_conflict")
                found = False
                sources: list[SourceVersionRecord] = []
                updated_source: SourceVersionRecord | None = None
                for item in record.sources:
                    if item.active and item.source_id == source_id:
                        updated_source = item.model_copy(update={"display_name": name})
                        sources.append(updated_source)
                        found = True
                    else:
                        sources.append(item)
                if not found or updated_source is None:
                    raise AppError(
                        ErrorCode.SOURCE_UNKNOWN,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id, source_id=source_id
                        ),
                    )
                patched = record.model_copy(
                    update={
                        "sources": sources,
                        "revision": advance_revision(record.revision),
                        "updated_at": utc_now(),
                    }
                )
                result = ManagedOperationResult(
                    workspace_revision=patched.revision,
                    workspace_status=patched.status,
                    snapshot_id=patched.current_snapshot_id,
                    source_id=source_id,
                    source_version=updated_source.version,
                    display_name=updated_source.display_name,
                    content_type=updated_source.content_type,
                    byte_size=updated_source.byte_size,
                    content_hash=updated_source.content_hash,
                    document_id=updated_source.document_id,
                    active_from_revision=updated_source.active_from_revision,
                    active_from_snapshot_id=updated_source.active_from_snapshot_id,
                    created_at=updated_source.created_at,
                    updated_at=patched.updated_at,
                    source_count=len([s for s in patched.sources if s.active]),
                    title=patched.title,
                    description=patched.description,
                )
                self.sync_mutations.begin(
                    workspace_id,
                    operation_id=op.operation_id,
                    kind=ManagedOperationKind.SOURCE_METADATA_PATCH,
                    expected_revision=expected_revision,
                    expected_result=result,
                    lease=lease,
                )
                saved = self.store.save(patched, lease=lease)
                result = ManagedOperationResult(
                    workspace_revision=saved.revision,
                    workspace_status=saved.status,
                    snapshot_id=saved.current_snapshot_id,
                    source_id=source_id,
                    source_version=updated_source.version,
                    display_name=updated_source.display_name,
                    content_type=updated_source.content_type,
                    byte_size=updated_source.byte_size,
                    content_hash=updated_source.content_hash,
                    document_id=updated_source.document_id,
                    active_from_revision=updated_source.active_from_revision,
                    active_from_snapshot_id=updated_source.active_from_snapshot_id,
                    created_at=updated_source.created_at,
                    updated_at=saved.updated_at,
                    source_count=len([s for s in saved.sources if s.active]),
                    title=saved.title,
                    description=saved.description,
                )
                self.sync_mutations.mark_workspace_committed(
                    workspace_id, result=result, lease=lease
                )
                op = self._succeed_sync_operation(
                    workspace_id, op.operation_id, result=result, lease=lease
                )
                self.sync_mutations.drop(workspace_id, lease=lease)
                return self._source_public_from_result(op), op
            except AppError as exc:
                return self._handle_sync_app_error(
                    workspace_id,
                    op,
                    exc,
                    lease=lease,
                    public_from_result=lambda _wid, record: self._source_public_from_result(
                        record
                    ),
                )

    def replace_source(
        self,
        workspace_id: str,
        *,
        source_id: str,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        upload: SourceUpload,
        control: OperationHandle | None = None,
    ) -> ManagedOperationRecord:
        _assert_supported_source(upload.display_name)
        payload = {
            "source_id": source_id,
            "display_name": upload.display_name,
            "content_type": upload.content_type,
            "content_sha256": upload.digest(),
        }
        return self._run_managed_mutation(
            workspace_id,
            kind=ManagedOperationKind.SOURCE_REPLACE,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            payload=payload,
            plan=lambda record: self._plan_replace(record, source_id, upload),
            control=control,
        )

    def remove_source(
        self,
        workspace_id: str,
        *,
        source_id: str,
        expected_revision: WorkspaceRevision,
        idempotency_key: str,
        control: OperationHandle | None = None,
    ) -> ManagedOperationRecord:
        return self._run_managed_mutation(
            workspace_id,
            kind=ManagedOperationKind.SOURCE_REMOVE,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            payload={"source_id": source_id},
            plan=lambda record: self._plan_remove(record, source_id),
            control=control,
        )

    # ---------------------------------------------------------------- planning

    @staticmethod
    def _active_sources(record: WorkspaceRecord) -> list[SourceVersionRecord]:
        return [item for item in record.sources if item.active]

    def _find_active_source(
        self, record: WorkspaceRecord, source_id: str
    ) -> SourceVersionRecord:
        for item in self._active_sources(record):
            if item.source_id == source_id:
                return item
        raise AppError(
            ErrorCode.SOURCE_UNKNOWN,
            details=SafeErrorDetails(
                workspace_id=record.workspace_id, source_id=source_id
            ),
        )

    def _vault_source_version(
        self,
        record: WorkspaceRecord,
        *,
        source_id: str,
        version: int,
        upload: SourceUpload,
    ) -> SourceVersionRecord:
        """Persist raw bytes and build the lineage event for this version."""
        data = upload.load_bytes()
        meta = self.vault.put_bytes(
            record.workspace_id,
            data,
            display_name=upload.display_name,
            content_type=upload.content_type,
        )
        return SourceVersionRecord(
            source_id=source_id,
            version=version,
            display_name=meta.display_name,
            content_type=meta.content_type,
            byte_size=meta.byte_size,
            content_hash=meta.content_hash,
            document_id=document_id_for_content(data),
            vault_object_id=meta.object_id,
            active=True,
            created_at=utc_now(),
            # Revision is known: the lease is held and the revision was verified.
            # The snapshot is not, until publication succeeds.
            active_from_revision=advance_revision(record.revision),
            active_from_snapshot_id=None,
        )

    def _plan_add(
        self, record: WorkspaceRecord, uploads: Sequence[SourceUpload]
    ) -> _MutationPlan:
        appended: list[SourceVersionRef] = []
        added: list[SourceVersionRecord] = []
        primary_id: str | None = None
        for upload in uploads:
            source_id = new_source_id()
            if primary_id is None:
                primary_id = source_id
            added.append(
                self._vault_source_version(
                    record, source_id=source_id, version=1, upload=upload
                )
            )
            appended.append(SourceVersionRef(source_id=source_id, version=1))
        assert primary_id is not None
        return _MutationPlan(
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
            desired=[*self._active_sources(record), *added],
            lineage=LineageDelta(appended=appended),
            source_id=primary_id,
            source_version=1,
        )

    def _plan_replace(
        self, record: WorkspaceRecord, source_id: str, upload: SourceUpload
    ) -> _MutationPlan:
        current = self._find_active_source(record, source_id)
        # Version monotonicity must account for history, not just the active
        # record, so a replace after recovery cannot reuse a version number.
        next_version = max(
            current.version + 1,
            self.history.next_version(record.workspace_id, source_id),
        )
        replacement = self._vault_source_version(
            record, source_id=source_id, version=next_version, upload=upload
        )
        remaining = [
            item
            for item in self._active_sources(record)
            if item.source_id != source_id
        ]
        return _MutationPlan(
            mutation_kind=PublicationMutationKind.SOURCE_REPLACE,
            desired=[*remaining, replacement],
            lineage=LineageDelta(
                appended=[
                    SourceVersionRef(source_id=source_id, version=next_version)
                ],
                superseded=[
                    SourceVersionRef(source_id=source_id, version=current.version)
                ],
            ),
            source_id=source_id,
            source_version=next_version,
        )

    def _plan_remove(self, record: WorkspaceRecord, source_id: str) -> _MutationPlan:
        current = self._find_active_source(record, source_id)
        remaining = [
            item
            for item in self._active_sources(record)
            if item.source_id != source_id
        ]
        return _MutationPlan(
            mutation_kind=PublicationMutationKind.SOURCE_REMOVE,
            desired=remaining,
            lineage=LineageDelta(
                superseded=[
                    SourceVersionRef(source_id=source_id, version=current.version)
                ]
            ),
            source_id=source_id,
            source_version=current.version,
        )

    # -------------------------------------------------------------- execution

    def _run_managed_mutation(
        self,
        workspace_id: str,
        *,
        kind: ManagedOperationKind,
        idempotency_key: str,
        expected_revision: WorkspaceRevision,
        payload: dict[str, Any],
        plan: Callable[[WorkspaceRecord], _MutationPlan],
        control: OperationHandle | None,
    ) -> ManagedOperationRecord:
        self.runtime.require_ready()
        # Fail-fast: a busy workspace is a conflict, not a queue slot.
        with WorkspaceMutationLease(self.settings, workspace_id) as lease:
            operation = self.operations.begin(
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                kind=kind,
                request_payload=payload,
                expected_revision=expected_revision,
                lease=lease,
            )
            if operation.status in {
                ManagedOperationStatus.SUCCEEDED,
                ManagedOperationStatus.FAILED,
                ManagedOperationStatus.INTERRUPTED,
            }:
                # Same key + same canonical request: recover, never re-run.
                return operation

            operation_id = operation.operation_id
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.PREPARING,
                progress_stage=OperationProgressStage.PREPARING,
                lease=lease,
            )
            try:
                record = self.store.get(workspace_id)
                if record.revision != expected_revision:
                    raise _conflict(workspace_id, "revision_conflict")
                resolved = plan(record)
                if resolved.desired:
                    return self._execute_publication(
                        record,
                        operation_id=operation_id,
                        plan=resolved,
                        lease=lease,
                        control=control,
                    )
                return self._execute_empty_transition(
                    record, operation_id=operation_id, plan=resolved, lease=lease
                )
            except AppError as exc:
                current = self.operations.get(workspace_id, operation_id)
                if current.status not in {
                    ManagedOperationStatus.SUCCEEDED,
                    ManagedOperationStatus.FAILED,
                    ManagedOperationStatus.INTERRUPTED,
                }:
                    self._fail_operation(workspace_id, operation_id, exc, lease=lease)
                raise
            except Exception as exc:
                wrapped = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    details=SafeErrorDetails(reason="workspace_mutation_fault"),
                )
                current = self.operations.get(workspace_id, operation_id)
                if current.status not in {
                    ManagedOperationStatus.SUCCEEDED,
                    ManagedOperationStatus.FAILED,
                    ManagedOperationStatus.INTERRUPTED,
                }:
                    self._fail_operation(
                        workspace_id, operation_id, wrapped, lease=lease
                    )
                raise wrapped from exc

    def _execute_publication(
        self,
        record: WorkspaceRecord,
        *,
        operation_id: str,
        plan: _MutationPlan,
        lease: WorkspaceMutationLease,
        control: OperationHandle | None,
    ) -> ManagedOperationRecord:
        workspace_id = record.workspace_id
        self.publication.begin(
            workspace_id,
            operation_id=operation_id,
            mutation_kind=plan.mutation_kind,
            expected_revision=record.revision,
            desired_sources=plan.desired,
            lineage_delta=plan.lineage,
            lease=lease,
        )
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.PROCESSING,
            lease=lease,
        )

        materialized = materialize_desired_sources(
            self.settings,
            workspace_id=workspace_id,
            desired=plan.desired,
            vault=self.vault,
        )
        try:
            upload = spool_local_files(
                settings=self.settings,
                corpus_name=record.backing_corpus_name,
                files=materialized.spool_inputs(),
            )
        finally:
            materialized.cleanup()

        # F1/F7: hold corpus lease through success OR live failure recovery.
        from offline_rag.app.leases import CorpusMutationLease

        with CorpusMutationLease(
            self.settings, record.backing_corpus_name
        ) as corpus_lease:
            try:
                ingested = run_product_replace_ingest(
                    self.runtime,
                    upload,
                    hooks=self._progress_hooks(workspace_id, operation_id, lease),
                    control=control,
                    corpus_lease=corpus_lease,
                    authorize_workspace_id=workspace_id,
                )
                self.publication.mark_publication_observed(
                    workspace_id, ingested.snapshot_id, lease=lease
                )

                committed = self._committed_record(
                    record, plan=plan, snapshot_id=ingested.snapshot_id
                )
                self.publication.commit_workspace(workspace_id, committed, lease=lease)
                # F5: lineage + COMMITTED phase retained until op SUCCEEDED is durable.
                self.publication.mark_committed(workspace_id, lease=lease)

                succeeded = self.operations.update_status(
                    workspace_id,
                    operation_id,
                    ManagedOperationStatus.SUCCEEDED,
                    progress_stage=OperationProgressStage.READY,
                    result=ManagedOperationResult(
                        workspace_revision=committed.revision,
                        workspace_status=committed.status,
                        snapshot_id=committed.current_snapshot_id,
                        source_id=plan.source_id,
                        source_ids=[item.source_id for item in committed.sources],
                        source_version=plan.source_version,
                    ),
                    result_summary=str(plan.mutation_kind),
                    lease=lease,
                )
                self.publication.drop_journal(workspace_id, lease=lease)
                return succeeded
            except AppError as exc:
                self._fail_operation(
                    workspace_id,
                    operation_id,
                    exc,
                    lease=lease,
                    corpus_lease=corpus_lease,
                )
                raise
            except Exception as exc:
                wrapped = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    details=SafeErrorDetails(reason="workspace_mutation_fault"),
                )
                self._fail_operation(
                    workspace_id,
                    operation_id,
                    wrapped,
                    lease=lease,
                    corpus_lease=corpus_lease,
                )
                raise wrapped from exc

    def _execute_empty_transition(
        self,
        record: WorkspaceRecord,
        *,
        operation_id: str,
        plan: _MutationPlan,
        lease: WorkspaceMutationLease,
    ) -> ManagedOperationRecord:
        """Final-source removal: depublish and go EMPTY, never ingest (S16-D13)."""
        workspace_id = record.workspace_id
        if self.publication.load_journal(workspace_id) is not None:
            raise _conflict(workspace_id, "publication_transition_in_progress")

        removed_json = None
        if plan.lineage.superseded:
            ref = plan.lineage.superseded[0]
            for item in record.sources:
                if item.source_id == ref.source_id and item.version == ref.version:
                    removed_json = item.model_dump_json()
                    break

        self.empty_transition.begin(
            workspace_id,
            expected_revision=record.revision,
            lease=lease,
            operation_id=operation_id,
            removed_source_json=removed_json,
        )
        self.operations.update_status(
            workspace_id,
            operation_id,
            ManagedOperationStatus.RUNNING,
            progress_stage=OperationProgressStage.PUBLISHING,
            lease=lease,
        )

        from offline_rag.app.leases import CorpusMutationLease

        with CorpusMutationLease(
            self.settings, record.backing_corpus_name
        ) as corpus_lease:
            try:
                # Retire + EMPTY workspace + lineage + op success under corpus lease.
                self.empty_transition.step_retire_publication(
                    workspace_id, lease=lease, corpus_lease=corpus_lease
                )
                self.empty_transition.step_empty_workspace(workspace_id, lease=lease)
                emptied = self.store.get(workspace_id)

                self.operations.update_status(
                    workspace_id,
                    operation_id,
                    ManagedOperationStatus.RUNNING,
                    progress_stage=OperationProgressStage.FINALIZING,
                    lease=lease,
                )
                self._close_out_lineage(record, refs=plan.lineage.superseded)
                self.empty_transition.mark_lineage_closed(workspace_id, lease=lease)

                succeeded = self.operations.update_status(
                    workspace_id,
                    operation_id,
                    ManagedOperationStatus.SUCCEEDED,
                    progress_stage=OperationProgressStage.READY,
                    result=ManagedOperationResult(
                        workspace_revision=emptied.revision,
                        workspace_status=emptied.status,
                        snapshot_id=None,
                        source_id=plan.source_id,
                        source_ids=[],
                        source_version=plan.source_version,
                    ),
                    result_summary="empty_transition",
                    lease=lease,
                )
                self.empty_transition.drop_journal(workspace_id, lease=lease)
                return succeeded
            except AppError as exc:
                self._fail_operation(
                    workspace_id,
                    operation_id,
                    exc,
                    lease=lease,
                    corpus_lease=corpus_lease,
                )
                raise
            except Exception as exc:
                wrapped = AppError(
                    ErrorCode.INTERNAL_ERROR,
                    details=SafeErrorDetails(reason="workspace_mutation_fault"),
                )
                self._fail_operation(
                    workspace_id,
                    operation_id,
                    wrapped,
                    lease=lease,
                    corpus_lease=corpus_lease,
                )
                raise wrapped from exc

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _committed_record(
        prior: WorkspaceRecord, *, plan: _MutationPlan, snapshot_id: str
    ) -> WorkspaceRecord:
        """Build the post-publication workspace record.

        Only newly appended versions get ``active_from_snapshot_id``; a source
        carried through the mutation keeps the snapshot it actually became active
        in, which is what lineage is for (S16-D09).
        """
        appended = {(ref.source_id, ref.version) for ref in plan.lineage.appended}
        sources = [
            item.model_copy(update={"active_from_snapshot_id": snapshot_id})
            if (item.source_id, item.version) in appended
            else item
            for item in plan.desired
        ]
        return prior.model_copy(
            update={
                "sources": sources,
                "current_snapshot_id": snapshot_id,
                "status": WorkspaceStatus.ACTIVE,
                "revision": advance_revision(prior.revision),
                "updated_at": utc_now(),
            }
        )

    def _close_out_lineage(
        self, prior: WorkspaceRecord, *, refs: Sequence[SourceVersionRef]
    ) -> None:
        """Record supersession for the EMPTY transition's removed source."""
        by_key = {
            (item.source_id, item.version): item for item in prior.sources
        }
        for ref in refs:
            path = self.history.version_path(
                prior.workspace_id, ref.source_id, ref.version
            )
            if not path.exists():
                seed = by_key.get((ref.source_id, ref.version))
                if seed is None:
                    continue
                self.history.append(prior.workspace_id, seed)
            self.history.supersede(
                prior.workspace_id,
                ref.source_id,
                ref.version,
                active_through_revision=prior.revision,
                active_through_snapshot_id=prior.current_snapshot_id,
            )

    def _progress_hooks(
        self, workspace_id: str, operation_id: str, lease: WorkspaceMutationLease
    ) -> ProductIngestHooks:
        def _before(stage: str) -> None:
            mapped = _STAGE_PROGRESS.get(stage)
            if mapped is None:
                return
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                progress_stage=mapped,
                lease=lease,
            )

        def _after(stage: str) -> None:
            if stage != "publish":
                return
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.RUNNING,
                progress_stage=OperationProgressStage.FINALIZING,
                lease=lease,
            )

        return ProductIngestHooks(before_stage=_before, after_stage=_after)

    def _fail_operation(
        self,
        workspace_id: str,
        operation_id: str,
        error: AppError,
        *,
        lease: WorkspaceMutationLease,
        corpus_lease: CorpusMutationLease | None = None,
    ) -> None:
        """Recover any open journal under the live corpus lease when held (F7)."""
        from offline_rag.app.leases import CorpusMutationLease

        _ = CorpusMutationLease  # typing only
        recovery_note: str | None = None
        try:
            outcome = self.publication.recover(
                workspace_id, lease=lease, corpus_lease=corpus_lease
            )
            if outcome == "clean":
                outcome = self.empty_transition.recover(
                    workspace_id, lease=lease, corpus_lease=corpus_lease
                )
            if outcome != "clean":
                recovery_note = f"recovered_{outcome}"
        except AppError as exc:
            recovery_note = f"recovery_failed_{exc.code}"[:512]
        try:
            self.operations.update_status(
                workspace_id,
                operation_id,
                ManagedOperationStatus.FAILED,
                failure_summary=str(error.code),
                recovery_note=recovery_note,
                error=ManagedOperationSafeError.from_app_error(error),
                lease=lease,
            )
        except AppError as exc:
            # Restart may have already terminalized the op as INTERRUPTED.
            if exc.code is ErrorCode.WORKSPACE_STATE_UNAVAILABLE:
                current = self.operations.get(workspace_id, operation_id)
                if current.status in {
                    ManagedOperationStatus.SUCCEEDED,
                    ManagedOperationStatus.FAILED,
                    ManagedOperationStatus.INTERRUPTED,
                }:
                    return
            raise

    def _load_optional(self, workspace_id: str) -> WorkspaceRecord | None:
        try:
            return self.store.get(workspace_id, include_tombstoned=True)
        except AppError as exc:
            if exc.code is ErrorCode.WORKSPACE_UNKNOWN:
                return None
            raise

    # ---------------------------------------------------------------- recovery

    def recover_pending_transitions(self) -> dict[str, Any]:
        """Startup-time recovery across both journals plus operation cleanup."""
        publication = self.publication.recover_all()
        empty = self.empty_transition.recover_all()
        interrupted = self.operations.interrupt_all_nonterminal()
        return {
            "publication_transitions": publication,
            "empty_transitions": empty,
            "interrupted_operations": [
                item.operation_id for item in interrupted
            ],
        }


def recover_workspace_transactions(settings: AppSettings) -> dict[str, Any]:
    """Recover workspace journals without requiring process scientific resources.

    Called from ``ApplicationRuntime.start`` before READY so mutation/query
    surfaces cannot open against unresolved publication/EMPTY journals.
    """
    from offline_rag.app.workspace.upload_spool import (
        quarantine_orphan_workspace_spools,
    )

    store = WorkspaceStore(settings)
    history = SourceHistoryStore(settings)
    publication = NonEmptyPublicationCoordinator(settings, store, history)
    empty = EmptyTransitionCoordinator(settings, store)
    from offline_rag.app.workspace.sync_journal import SyncMutationCoordinator

    operations = ManagedOperationStore(settings)
    sync = SyncMutationCoordinator(settings)
    pub = publication.recover_all()
    emp = empty.recover_all()
    sync_results = sync.recover_all()
    interrupted = operations.interrupt_all_nonterminal()
    quarantined = quarantine_orphan_workspace_spools(settings)
    return {
        "publication_transitions": pub,
        "empty_transitions": emp,
        "sync_mutations": sync_results,
        "interrupted_operations": [item.operation_id for item in interrupted],
        "quarantined_upload_spools": [str(path) for path in quarantined],
    }
