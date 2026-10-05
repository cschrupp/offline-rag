"""Cross-registry EMPTY-transition journal and recovery (Slice 16A).

Supports the future one-source → EMPTY workflow without implementing full
source-removal orchestration. Guarantees recovery lands in legal state A or B:

A: prior non-empty workspace + prior publication current
B: EMPTY workspace + no active current publication

Historical immutable snapshot manifests are never deleted by recovery.

While a journal is present, ``WorkspaceStore`` ordinary mutations fail closed.
Each coordinator step/recover acquires ``WorkspaceMutationLease`` so concurrent
metadata mutations cannot interleave with transition ownership.

Lock order (frozen for 16B): workspace lease → corpus lease.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    WorkspaceRecord,
    WorkspaceStatus,
    advance_revision,
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

JOURNAL_SCHEMA_VERSION = "offline-rag-empty-transition-journal-v1"
T = TypeVar("T")


class EmptyTransitionPhase(StrEnum):
    INTENT_RECORDED = "intent_recorded"
    PUBLICATION_RETIRED = "publication_retired"
    WORKSPACE_EMPTIED = "workspace_emptied"
    COMMITTED = "committed"


class EmptyTransitionJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["offline-rag-empty-transition-journal-v1"] = (
        JOURNAL_SCHEMA_VERSION
    )
    journal_id: str
    workspace_id: str
    backing_corpus_name: str
    phase: EmptyTransitionPhase
    prior_revision: int = Field(ge=1)
    prior_snapshot_id: str
    prior_workspace_json: str
    created_at: datetime
    updated_at: datetime


class EmptyTransitionCoordinator:
    """Filesystem journal coordinating workspace EMPTY vs publication retirement."""

    def __init__(self, settings: AppSettings, store: WorkspaceStore | None = None) -> None:
        self.settings = settings
        self.store = store or WorkspaceStore(settings)

    def journal_path(self, workspace_id: str) -> Path:
        return self.store.empty_transition_journal_path(workspace_id)

    def _with_lease(
        self,
        workspace_id: str,
        fn: Callable[[WorkspaceMutationLease], T],
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
            return fn(lease)
        with WorkspaceMutationLease(self.settings, workspace_id) as owned:
            return fn(owned)

    def _with_corpus_lease(self, corpus_name: str, fn: Callable[[], T]) -> T:
        """Acquire corpus lease while workspace lease is already held.

        Lock order: workspace lease → corpus lease (never reverse).
        """
        with CorpusMutationLease(self.settings, corpus_name):
            return fn()

    def begin(
        self,
        workspace_id: str,
        *,
        expected_revision: int,
        lease: WorkspaceMutationLease | None = None,
    ) -> EmptyTransitionJournal:
        def _body(held: WorkspaceMutationLease) -> EmptyTransitionJournal:
            _ = held
            record = self.store.get(workspace_id)
            if record.revision != expected_revision:
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="revision_conflict"
                    ),
                )
            if record.status is not WorkspaceStatus.ACTIVE:
                raise AppError(
                    ErrorCode.WORKSPACE_NOT_READY,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="workspace_not_active"
                    ),
                )
            if record.current_snapshot_id is None:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="missing_current_snapshot"
                    ),
                )
            active_sources = [s for s in record.sources if s.active]
            if len(active_sources) != 1:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id,
                        reason="empty_transition_requires_one_source",
                    ),
                )
            path = self.journal_path(workspace_id)
            if path.exists():
                raise AppError(
                    ErrorCode.WORKSPACE_CONFLICT,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="empty_transition_in_progress"
                    ),
                )
            now = utc_now()
            journal = EmptyTransitionJournal(
                journal_id=new_operation_id().replace("wop_", "jrn_", 1),
                workspace_id=workspace_id,
                backing_corpus_name=record.backing_corpus_name,
                phase=EmptyTransitionPhase.INTENT_RECORDED,
                prior_revision=record.revision,
                prior_snapshot_id=record.current_snapshot_id,
                prior_workspace_json=record.model_dump_json(),
                created_at=now,
                updated_at=now,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, journal.model_dump_json())
            return journal

        return self._with_lease(workspace_id, _body, lease=lease)

    def load_journal(self, workspace_id: str) -> EmptyTransitionJournal | None:
        path = self.journal_path(workspace_id)
        if not path.exists():
            return None
        try:
            return EmptyTransitionJournal.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_corrupt"
                ),
            ) from exc

    def _save_journal(self, journal: EmptyTransitionJournal) -> EmptyTransitionJournal:
        updated = journal.model_copy(update={"updated_at": datetime.now(tz=UTC)})
        atomic_write_text(
            self.journal_path(journal.workspace_id), updated.model_dump_json()
        )
        return updated

    def step_retire_publication(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> EmptyTransitionJournal:
        def _body(held: WorkspaceMutationLease) -> EmptyTransitionJournal:
            _ = held
            journal = self.load_journal(workspace_id)
            if journal is None:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="empty_journal_missing"
                    ),
                )
            if journal.phase is EmptyTransitionPhase.INTENT_RECORDED:
                def _retire() -> None:
                    retire_current_publication(
                        self.settings, journal.backing_corpus_name
                    )

                self._with_corpus_lease(journal.backing_corpus_name, _retire)
                return self._save_journal(
                    journal.model_copy(
                        update={"phase": EmptyTransitionPhase.PUBLICATION_RETIRED}
                    )
                )
            if journal.phase in {
                EmptyTransitionPhase.PUBLICATION_RETIRED,
                EmptyTransitionPhase.WORKSPACE_EMPTIED,
                EmptyTransitionPhase.COMMITTED,
            }:
                return journal
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_phase_invalid"
                ),
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def step_empty_workspace(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> EmptyTransitionJournal:
        def _body(held: WorkspaceMutationLease) -> EmptyTransitionJournal:
            journal = self.load_journal(workspace_id)
            if journal is None:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id, reason="empty_journal_missing"
                    ),
                )
            if journal.phase is EmptyTransitionPhase.INTENT_RECORDED:
                journal = self.step_retire_publication(workspace_id, lease=held)
            if journal.phase is EmptyTransitionPhase.PUBLICATION_RETIRED:
                prior = WorkspaceRecord.model_validate_json(journal.prior_workspace_json)
                emptied = prior.model_copy(
                    update={
                        "sources": [],
                        "current_snapshot_id": None,
                        "status": WorkspaceStatus.EMPTY,
                        "revision": advance_revision(prior.revision),
                        "updated_at": utc_now(),
                    }
                )
                self.store.save(
                    emptied, lease=held, allow_during_empty_transition=True
                )
                return self._save_journal(
                    journal.model_copy(
                        update={"phase": EmptyTransitionPhase.WORKSPACE_EMPTIED}
                    )
                )
            if journal.phase in {
                EmptyTransitionPhase.WORKSPACE_EMPTIED,
                EmptyTransitionPhase.COMMITTED,
            }:
                return journal
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_phase_invalid"
                ),
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def step_commit(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> EmptyTransitionJournal:
        def _body(held: WorkspaceMutationLease) -> EmptyTransitionJournal:
            journal = self.step_empty_workspace(workspace_id, lease=held)
            if journal.phase is EmptyTransitionPhase.WORKSPACE_EMPTIED:
                journal = self._save_journal(
                    journal.model_copy(update={"phase": EmptyTransitionPhase.COMMITTED})
                )
            path = self.journal_path(workspace_id)
            if path.exists():
                path.unlink()
            return journal

        return self._with_lease(workspace_id, _body, lease=lease)

    def recover(
        self,
        workspace_id: str,
        *,
        lease: WorkspaceMutationLease | None = None,
    ) -> str:
        """Idempotent recovery to legal A or B. Returns ``A``, ``B``, or ``clean``."""

        def _body(held: WorkspaceMutationLease) -> str:
            _ = held
            journal = self.load_journal(workspace_id)
            if journal is None:
                return "clean"

            corpus = journal.backing_corpus_name

            def _restore_pointer() -> None:
                restore_current_publication_pointer(
                    self.settings, corpus, journal.prior_snapshot_id
                )

            def _retire_if_current() -> None:
                live = current_pointer_path(self.settings.paths.corpora, corpus)
                if live.exists():
                    retire_current_publication(self.settings, corpus)
                else:
                    # No current pointer; still clear stale audit marker.
                    clear_retirement_marker(self.settings, corpus)

            def _ensure_a_publication() -> None:
                """Restore current if missing; always clear stale retired.json."""
                live = current_pointer_path(self.settings.paths.corpora, corpus)
                if not live.exists():
                    restore_current_publication_pointer(
                        self.settings, corpus, journal.prior_snapshot_id
                    )
                else:
                    clear_retirement_marker(self.settings, corpus)

            try:
                workspace = self.store.get(workspace_id, include_tombstoned=True)
            except AppError:
                prior = WorkspaceRecord.model_validate_json(journal.prior_workspace_json)
                self.store.workspace_path(workspace_id).parent.mkdir(
                    parents=True, exist_ok=True
                )
                atomic_write_text(
                    self.store.workspace_path(workspace_id), prior.model_dump_json()
                )
                self._with_corpus_lease(corpus, _restore_pointer)
                self.journal_path(workspace_id).unlink(missing_ok=True)
                return "A"

            if workspace.status is WorkspaceStatus.EMPTY:
                self._with_corpus_lease(corpus, _retire_if_current)
                self.journal_path(workspace_id).unlink(missing_ok=True)
                return "B"

            if journal.phase in {
                EmptyTransitionPhase.PUBLICATION_RETIRED,
                EmptyTransitionPhase.INTENT_RECORDED,
            }:
                self._with_corpus_lease(corpus, _ensure_a_publication)
                prior = WorkspaceRecord.model_validate_json(journal.prior_workspace_json)
                atomic_write_text(
                    self.store.workspace_path(workspace_id), prior.model_dump_json()
                )
                self.journal_path(workspace_id).unlink(missing_ok=True)
                return "A"

            if journal.phase is EmptyTransitionPhase.WORKSPACE_EMPTIED:
                self._with_corpus_lease(corpus, _retire_if_current)
                self.journal_path(workspace_id).unlink(missing_ok=True)
                return "B"

            if journal.phase is EmptyTransitionPhase.COMMITTED:
                self.journal_path(workspace_id).unlink(missing_ok=True)
                return "B" if workspace.status is WorkspaceStatus.EMPTY else "A"

            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_phase_invalid"
                ),
            )

        return self._with_lease(workspace_id, _body, lease=lease)

    def recover_all(self) -> list[tuple[str, str]]:
        root = self.settings.paths.workspaces
        if not root.exists():
            return []
        results: list[tuple[str, str]] = []
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not child.name.startswith("ws_"):
                continue
            if (child / "journal" / "empty_transition.json").exists():
                results.append((child.name, self.recover(child.name)))
        return results
