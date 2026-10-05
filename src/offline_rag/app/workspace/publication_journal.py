"""Non-empty publication transition journal and recovery (Slice 16B).

Add / remove / replace that leaves at least one active source must publish a new
immutable snapshot *and* advance workspace state. Those are two registries, so
"ingest then save the workspace" is not a transaction: a crash in between leaves
the workspace pointing at a snapshot that is not current, or a current snapshot
no workspace claims. This journal makes the pair recoverable, exactly as
``EmptyTransitionCoordinator`` does for the EMPTY transition.

Phases::

    intent_recorded      prior state captured; ingest may run
    publication_observed new snapshot became current
    workspace_committed  workspace.json now claims the new snapshot
    lineage_committed    source history reflects the new/retired versions
    committed            journal may be dropped

Recovery lands in exactly one legal state:

A: prior workspace record + prior publication current (mutation never happened)
B: new workspace record + new publication current (mutation happened)

The decision rule is "did the workspace commit?", because ``workspace.json`` is
the product-visible authority for a workspace. If it committed, finish forward
to B; otherwise roll the publication pointer back to A. Immutable snapshot
manifests are never deleted by recovery — only ``current.json`` moves.

Lock order (frozen in 16A): workspace lease → corpus lease. The corpus lease is
taken only while restoring or retiring a publication pointer.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
    new_operation_id,
    utc_now,
)
from offline_rag.app.workspace.retirement import (
    clear_retirement_marker,
    restore_current_publication_pointer,
    retire_current_publication,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

PUBLICATION_JOURNAL_SCHEMA_VERSION = "offline-rag-publication-transition-journal-v1"
T = TypeVar("T")


class NonEmptyPublicationPhase(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    PUBLICATION_OBSERVED = "publication_observed"
    WORKSPACE_COMMITTED = "workspace_committed"
    LINEAGE_COMMITTED = "lineage_committed"
    COMMITTED = "committed"


class PublicationMutationKind(StrEnum):
    SOURCE_ADD = "source_add"
    SOURCE_REMOVE = "source_remove"
    SOURCE_REPLACE = "source_replace"


_FORWARD_PHASES = (
    NonEmptyPublicationPhase.WORKSPACE_COMMITTED,
    NonEmptyPublicationPhase.LINEAGE_COMMITTED,
    NonEmptyPublicationPhase.COMMITTED,
)


class SourceVersionRef(BaseModel):
    """Identity of one lineage event, without duplicating its payload."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)


class LineageDelta(BaseModel):
    """Which source versions this mutation starts and ends.

    Payloads are intentionally absent: appended records are read back from the
    committed workspace record (so ``active_from_*`` is the real committed
    revision), and superseded records are closed out at the journal's prior
    revision / snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    appended: list[SourceVersionRef] = Field(default_factory=list)
    superseded: list[SourceVersionRef] = Field(default_factory=list)


class NonEmptyPublicationJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-publication-transition-journal-v1"] = (
        PUBLICATION_JOURNAL_SCHEMA_VERSION
    )
    journal_id: str
    operation_id: str
    workspace_id: str
    backing_corpus: str
    mutation_kind: PublicationMutationKind
    prior_revision: WorkspaceRevision = Field(ge=1)
    prior_snapshot_id: str | None = None
    prior_workspace_json: str
    desired_sources_json: str
    lineage_delta_json: str
    new_snapshot_id: str | None = None
    phase: NonEmptyPublicationPhase
    created_at: datetime
    updated_at: datetime

    def prior_workspace(self) -> WorkspaceRecord:
        return WorkspaceRecord.model_validate_json(self.prior_workspace_json)

    def desired_sources(self) -> list[SourceVersionRecord]:
        payload = json.loads(self.desired_sources_json)
        return [SourceVersionRecord.model_validate(item) for item in payload]

    def lineage_delta(self) -> LineageDelta:
        return LineageDelta.model_validate_json(self.lineage_delta_json)


def _state_error(workspace_id: str, reason: str) -> AppError:
    return AppError(
        ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
        details=SafeErrorDetails(workspace_id=workspace_id, reason=reason),
    )


class NonEmptyPublicationCoordinator:
    """Durable coordinator for publication + workspace commit of one mutation."""

    def __init__(
        self,
        settings: AppSettings,
        store: WorkspaceStore | None = None,
        history: SourceHistoryStore | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or WorkspaceStore(settings)
        self.history = history or SourceHistoryStore(settings)

    def journal_path(self, workspace_id: str) -> Path:
        return self.store.publication_transition_journal_path(workspace_id)

    # ------------------------------------------------------------------ leases

    def _with_lease(
        self,
        workspace_id: str,
        fn: Callable[[WorkspaceMutationLease], T],
        *,
        lease: WorkspaceMutationLease | None,
    ) -> T:
        if lease is not None:
            if lease.workspace_id != workspace_id or not lease.held:
                raise _state_error(workspace_id, "lease_not_held")
            return fn(lease)
        with WorkspaceMutationLease(self.settings, workspace_id) as owned:
            return fn(owned)

    def _with_corpus_lease(
        self,
        corpus_name: str,
        fn: Callable[[], T],
        *,
        corpus_lease: CorpusMutationLease | None = None,
    ) -> T:
        """Use an already-held corpus lease, or acquire one (startup recovery)."""
        if corpus_lease is not None:
            if not corpus_lease.held or corpus_lease.corpus_name != corpus_name:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        corpus=corpus_name, reason="corpus_lease_not_held"
                    ),
                )
            return fn()
        with CorpusMutationLease(self.settings, corpus_name):
            return fn()

    # ----------------------------------------------------------------- journal

    def load_journal(self, workspace_id: str) -> NonEmptyPublicationJournal | None:
        path = self.journal_path(workspace_id)
        if not path.exists():
            return None
        try:
            return NonEmptyPublicationJournal.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise _state_error(workspace_id, "publication_journal_corrupt") from exc

    def _require_journal(self, workspace_id: str) -> NonEmptyPublicationJournal:
        journal = self.load_journal(workspace_id)
        if journal is None:
            raise _state_error(workspace_id, "publication_journal_missing")
        return journal

    def _save_journal(
        self, journal: NonEmptyPublicationJournal
    ) -> NonEmptyPublicationJournal:
        updated = journal.model_copy(update={"updated_at": utc_now()})
        path = self.journal_path(journal.workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, updated.model_dump_json())
        return updated

    def _drop_journal(self, workspace_id: str) -> None:
        self.journal_path(workspace_id).unlink(missing_ok=True)

    # ------------------------------------------------------------------- steps

    def begin(
        self,
        workspace_id: str,
        *,
        operation_id: str,
        mutation_kind: PublicationMutationKind,
        expected_revision: WorkspaceRevision,
        desired_sources: Sequence[SourceVersionRecord],
        lineage_delta: LineageDelta,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Capture prior state before any product-visible mutation starts."""

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            _ = held
            if not desired_sources:
                # Zero active sources is the EMPTY transition (S16-D13), which
                # must not run an empty Slice-15 ingest.
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id,
                        reason="publication_requires_active_source",
                    ),
                )
            if self.journal_path(workspace_id).exists():
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id,
                        reason="publication_transition_in_progress",
                    ),
                )
            if self.store.empty_transition_journal_path(workspace_id).exists():
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id,
                        reason="empty_transition_in_progress",
                    ),
                )

            record = self.store.get(workspace_id)
            if record.revision != expected_revision:
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="revision_conflict"
                    ),
                )
            if record.status not in {WorkspaceStatus.ACTIVE, WorkspaceStatus.EMPTY}:
                raise AppError(
                    ErrorCode.WORKSPACE_NOT_READY,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="workspace_not_mutable"
                    ),
                )

            now = utc_now()
            journal = NonEmptyPublicationJournal(
                journal_id=new_operation_id().replace("wop_", "jrn_", 1),
                operation_id=operation_id,
                workspace_id=workspace_id,
                backing_corpus=record.backing_corpus_name,
                mutation_kind=mutation_kind,
                prior_revision=record.revision,
                prior_snapshot_id=record.current_snapshot_id,
                prior_workspace_json=record.model_dump_json(),
                desired_sources_json=json.dumps(
                    [item.model_dump(mode="json") for item in desired_sources]
                ),
                lineage_delta_json=lineage_delta.model_dump_json(),
                new_snapshot_id=None,
                phase=NonEmptyPublicationPhase.INTENT_RECORDED,
                created_at=now,
                updated_at=now,
            )
            return self._save_journal(journal)

        return self._with_lease(workspace_id, _body, lease=lease)

    def mark_publication_observed(
        self,
        workspace_id: str,
        snapshot_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Record that ``snapshot_id`` became the current publication."""

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            _ = held
            journal = self._require_journal(workspace_id)
            if journal.new_snapshot_id is not None:
                if journal.new_snapshot_id != snapshot_id:
                    raise AppError(
                        ErrorCode.WORKSPACE_CONFLICT,
                        details=SafeErrorDetails(
                            workspace_id=workspace_id,
                            snapshot_id=snapshot_id,
                            reason="publication_snapshot_conflict",
                        ),
                    )
                return journal
            if journal.phase is not NonEmptyPublicationPhase.INTENT_RECORDED:
                raise _state_error(workspace_id, "publication_journal_phase_invalid")
            return self._save_journal(
                journal.model_copy(
                    update={
                        "new_snapshot_id": snapshot_id,
                        "phase": NonEmptyPublicationPhase.PUBLICATION_OBSERVED,
                    }
                )
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def commit_workspace(
        self,
        workspace_id: str,
        new_record: WorkspaceRecord,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Make the workspace claim the new publication. This is the A/B pivot."""

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            journal = self._require_journal(workspace_id)
            if journal.phase in _FORWARD_PHASES:
                return journal
            if journal.phase is not NonEmptyPublicationPhase.PUBLICATION_OBSERVED:
                raise _state_error(workspace_id, "publication_journal_phase_invalid")
            if new_record.workspace_id != workspace_id:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="workspace_id_mismatch"
                    ),
                )
            if new_record.revision != journal.prior_revision + 1:
                raise _state_error(workspace_id, "unexpected_committed_revision")
            if new_record.current_snapshot_id != journal.new_snapshot_id:
                raise _state_error(workspace_id, "unexpected_committed_snapshot")
            if new_record.status is not WorkspaceStatus.ACTIVE:
                raise _state_error(workspace_id, "unexpected_committed_status")

            self.store.save(new_record, lease=held, allow_during_journal=True)
            return self._save_journal(
                journal.model_copy(
                    update={"phase": NonEmptyPublicationPhase.WORKSPACE_COMMITTED}
                )
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def commit_lineage(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Apply the lineage delta to durable source history (idempotent)."""

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            _ = held
            journal = self._require_journal(workspace_id)
            if journal.phase in {
                NonEmptyPublicationPhase.LINEAGE_COMMITTED,
                NonEmptyPublicationPhase.COMMITTED,
            }:
                return journal
            if journal.phase is not NonEmptyPublicationPhase.WORKSPACE_COMMITTED:
                raise _state_error(workspace_id, "publication_journal_phase_invalid")

            committed = self.store.get(workspace_id, include_tombstoned=True)
            delta = journal.lineage_delta()
            active_by_key = {
                (item.source_id, item.version): item for item in committed.sources
            }
            prior_by_key = {
                (item.source_id, item.version): item
                for item in journal.prior_workspace().sources
            }

            for ref in delta.appended:
                record = active_by_key.get((ref.source_id, ref.version))
                if record is None:
                    raise _state_error(workspace_id, "lineage_source_missing")
                self.history.append(workspace_id, record)

            for ref in delta.superseded:
                key = (ref.source_id, ref.version)
                if not self.history.version_path(
                    workspace_id, ref.source_id, ref.version
                ).exists():
                    # Backfill from the captured prior record so lineage works
                    # for workspaces created before history existed.
                    seed = prior_by_key.get(key)
                    if seed is None:
                        raise _state_error(workspace_id, "lineage_source_missing")
                    self.history.append(workspace_id, seed)
                self.history.supersede(
                    workspace_id,
                    ref.source_id,
                    ref.version,
                    active_through_revision=journal.prior_revision,
                    active_through_snapshot_id=journal.prior_snapshot_id,
                )

            return self._save_journal(
                journal.model_copy(
                    update={"phase": NonEmptyPublicationPhase.LINEAGE_COMMITTED}
                )
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def finalize(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Ensure lineage + COMMITTED phase, then drop the journal.

        Prefer ``mark_committed`` + ``drop_journal`` when the managed operation
        must become SUCCEEDED *before* the fence is released (F5).
        """

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            journal = self.mark_committed(workspace_id, lease=held)
            self.drop_journal(workspace_id, lease=held)
            return journal

        return self._with_lease(workspace_id, _body, lease=lease)

    def mark_committed(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> NonEmptyPublicationJournal:
        """Commit lineage and advance to COMMITTED without deleting the journal."""

        def _body(held: WorkspaceMutationLease) -> NonEmptyPublicationJournal:
            journal = self.commit_lineage(workspace_id, lease=held)
            if journal.phase is NonEmptyPublicationPhase.LINEAGE_COMMITTED:
                journal = self._save_journal(
                    journal.model_copy(
                        update={"phase": NonEmptyPublicationPhase.COMMITTED}
                    )
                )
            return journal

        return self._with_lease(workspace_id, _body, lease=lease)

    def drop_journal(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> None:
        """Remove the journal fence after COMMITTED (and op terminalization)."""

        def _body(held: WorkspaceMutationLease) -> None:
            _ = held
            journal = self.load_journal(workspace_id)
            if journal is None:
                return
            if journal.phase is not NonEmptyPublicationPhase.COMMITTED:
                raise _state_error(workspace_id, "publication_journal_phase_invalid")
            self._drop_journal(workspace_id)

        self._with_lease(workspace_id, _body, lease=lease)

    # ---------------------------------------------------------------- recovery

    def _live_snapshot_id(self, corpus_name: str) -> str | None:
        pointer_path = current_pointer_path(self.settings.paths.corpora, corpus_name)
        if not pointer_path.exists():
            return None
        try:
            pointer = PublishedPointer.model_validate_json(
                pointer_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError):
            return None
        return pointer.snapshot_id

    @staticmethod
    def _workspace_committed(
        journal: NonEmptyPublicationJournal, workspace: WorkspaceRecord | None
    ) -> bool:
        """Did ``workspace.json`` durably claim the new publication?

        The phase marker is advanced only after the workspace write returns, so
        durable workspace evidence is also accepted: a crash between the write
        and the phase update must still complete forward to B rather than roll a
        published, claimed snapshot back.
        """
        if workspace is None:
            return False
        if journal.phase in _FORWARD_PHASES:
            return True
        return (
            journal.new_snapshot_id is not None
            and workspace.current_snapshot_id == journal.new_snapshot_id
            and workspace.revision > journal.prior_revision
        )

    def recover(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
        corpus_lease: CorpusMutationLease | None = None,
    ) -> str:
        """Idempotent recovery to legal A or B. Returns ``A``, ``B``, or ``clean``."""

        def _body(held: WorkspaceMutationLease) -> str:
            journal = self.load_journal(workspace_id)
            if journal is None:
                return "clean"
            corpus = journal.backing_corpus

            try:
                workspace: WorkspaceRecord | None = self.store.get(
                    workspace_id, include_tombstoned=True
                )
            except AppError:
                workspace = None

            if self._workspace_committed(journal, workspace):
                new_snapshot_id = journal.new_snapshot_id
                if new_snapshot_id is not None:

                    def _ensure_new_current() -> None:
                        if self._live_snapshot_id(corpus) != new_snapshot_id:
                            restore_current_publication_pointer(
                                self.settings, corpus, new_snapshot_id
                            )
                        else:
                            clear_retirement_marker(self.settings, corpus)

                    self._with_corpus_lease(
                        corpus, _ensure_new_current, corpus_lease=corpus_lease
                    )
                if journal.phase not in _FORWARD_PHASES:
                    # Workspace write landed but the phase marker did not.
                    journal = self._save_journal(
                        journal.model_copy(
                            update={
                                "phase": NonEmptyPublicationPhase.WORKSPACE_COMMITTED
                            }
                        )
                    )
                self.mark_committed(workspace_id, lease=held)
                self._complete_operation_succeeded(journal, lease=held)
                self.drop_journal(workspace_id, lease=held)
                return "B"

            def _restore_prior_publication() -> None:
                if journal.prior_snapshot_id is not None:
                    restore_current_publication_pointer(
                        self.settings, corpus, journal.prior_snapshot_id
                    )
                elif self._live_snapshot_id(corpus) is not None:
                    # Prior workspace was EMPTY: whatever became current belongs
                    # to the abandoned mutation and must not stay reachable.
                    retire_current_publication(self.settings, corpus)
                else:
                    clear_retirement_marker(self.settings, corpus)

            self._with_corpus_lease(
                corpus, _restore_prior_publication, corpus_lease=corpus_lease
            )
            prior = journal.prior_workspace()
            path = self.store.workspace_path(workspace_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, prior.model_dump_json())
            self._interrupt_operation(journal, lease=held)
            self._drop_journal(workspace_id)
            return "A"

        return self._with_lease(workspace_id, _body, lease=lease)

    def _complete_operation_succeeded(
        self,
        journal: NonEmptyPublicationJournal,
        *,
        lease: WorkspaceMutationLease,
    ) -> None:
        """Idempotently terminalize the managed op for recovery-to-B (F5)."""
        from offline_rag.app.workspace.models import (
            ManagedOperationResult,
            ManagedOperationStatus,
            OperationProgressStage,
            WorkspaceStatus,
        )
        from offline_rag.app.workspace.mutation_ops import ManagedOperationStore

        ops = ManagedOperationStore(self.settings)
        try:
            record = ops.get(journal.workspace_id, journal.operation_id)
        except AppError:
            return
        if record.status is ManagedOperationStatus.SUCCEEDED:
            return
        if record.status in {
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            return
        workspace = self.store.get(journal.workspace_id, include_tombstoned=True)
        lineage = journal.lineage_delta()
        primary_source_id: str | None = None
        primary_version: int | None = None
        if journal.mutation_kind in {
            PublicationMutationKind.SOURCE_ADD,
            PublicationMutationKind.SOURCE_REPLACE,
        } and lineage.appended:
            primary_source_id = lineage.appended[0].source_id
            primary_version = lineage.appended[0].version
        elif (
            journal.mutation_kind is PublicationMutationKind.SOURCE_REMOVE
            and lineage.superseded
        ):
            primary_source_id = lineage.superseded[0].source_id
            primary_version = lineage.superseded[0].version
        ops.update_status(
            journal.workspace_id,
            journal.operation_id,
            ManagedOperationStatus.SUCCEEDED,
            progress_stage=OperationProgressStage.READY,
            result=ManagedOperationResult(
                workspace_revision=workspace.revision,
                workspace_status=workspace.status
                if isinstance(workspace.status, WorkspaceStatus)
                else WorkspaceStatus(workspace.status),
                snapshot_id=workspace.current_snapshot_id,
                source_id=primary_source_id,
                source_ids=[s.source_id for s in workspace.sources if s.active],
                source_version=primary_version,
            ),
            result_summary=str(journal.mutation_kind),
            recovery_note="recovered_B",
            lease=lease,
        )

    def _interrupt_operation(
        self,
        journal: NonEmptyPublicationJournal,
        *,
        lease: WorkspaceMutationLease,
    ) -> None:
        from offline_rag.app.workspace.models import ManagedOperationStatus
        from offline_rag.app.workspace.mutation_ops import ManagedOperationStore

        ops = ManagedOperationStore(self.settings)
        try:
            record = ops.get(journal.workspace_id, journal.operation_id)
        except AppError:
            return
        if record.status in {
            ManagedOperationStatus.SUCCEEDED,
            ManagedOperationStatus.FAILED,
            ManagedOperationStatus.INTERRUPTED,
        }:
            return
        ops.update_status(
            journal.workspace_id,
            journal.operation_id,
            ManagedOperationStatus.INTERRUPTED,
            recovery_note="recovered_A",
            lease=lease,
        )

    def recover_all(self) -> list[tuple[str, str]]:
        """Recover every workspace holding a publication journal."""
        root = self.settings.paths.workspaces
        if not root.exists():
            return []
        results: list[tuple[str, str]] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not child.name.startswith("ws_"):
                continue
            if (child / "journal" / "publication_transition.json").exists():
                results.append((child.name, self.recover(child.name)))
        return results
