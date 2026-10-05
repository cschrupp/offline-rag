"""Cross-registry EMPTY-transition journal and recovery (Slice 16A).

Supports the future one-source → EMPTY workflow without implementing full
source-removal orchestration. Guarantees recovery lands in legal state A or B:

A: prior non-empty workspace + prior publication current
B: EMPTY workspace + no active current publication

Historical immutable snapshot manifests are never deleted by recovery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.workspace.models import (
    WorkspaceRecord,
    WorkspaceStatus,
    advance_revision,
    new_operation_id,
    utc_now,
)
from offline_rag.app.workspace.retirement import (
    restore_current_publication_pointer,
    retire_current_publication,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

JOURNAL_SCHEMA_VERSION = "offline-rag-empty-transition-journal-v1"


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
        return self.store.workspace_dir(workspace_id) / "journal" / "empty_transition.json"

    def begin(
        self, workspace_id: str, *, expected_revision: int
    ) -> EmptyTransitionJournal:
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
                    workspace_id=workspace_id, reason="empty_transition_requires_one_source"
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

    def step_retire_publication(self, workspace_id: str) -> EmptyTransitionJournal:
        journal = self.load_journal(workspace_id)
        if journal is None:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_missing"
                ),
            )
        if journal.phase is EmptyTransitionPhase.INTENT_RECORDED:
            retire_current_publication(self.settings, journal.backing_corpus_name)
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

    def step_empty_workspace(self, workspace_id: str) -> EmptyTransitionJournal:
        journal = self.load_journal(workspace_id)
        if journal is None:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="empty_journal_missing"
                ),
            )
        if journal.phase is EmptyTransitionPhase.INTENT_RECORDED:
            # Require retirement first so we never empty while publication still current
            # without an intent that retirement will follow under recovery.
            journal = self.step_retire_publication(workspace_id)
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
            self.store.save(emptied)
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

    def step_commit(self, workspace_id: str) -> EmptyTransitionJournal:
        journal = self.step_empty_workspace(workspace_id)
        if journal.phase is EmptyTransitionPhase.WORKSPACE_EMPTIED:
            journal = self._save_journal(
                journal.model_copy(update={"phase": EmptyTransitionPhase.COMMITTED})
            )
        # Clear journal after commit (terminal).
        path = self.journal_path(workspace_id)
        if path.exists():
            path.unlink()
        return journal

    def recover(self, workspace_id: str) -> str:
        """Idempotent recovery to legal A or B. Returns ``A``, ``B``, or ``clean``."""
        journal = self.load_journal(workspace_id)
        if journal is None:
            return "clean"

        pointer = current_pointer_path(
            self.settings.paths.corpora, journal.backing_corpus_name
        )
        try:
            workspace = self.store.get(workspace_id, include_tombstoned=True)
        except AppError:
            # Workspace unreadable — restore prior JSON if possible then A.
            prior = WorkspaceRecord.model_validate_json(journal.prior_workspace_json)
            self.store.workspace_path(workspace_id).parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                self.store.workspace_path(workspace_id), prior.model_dump_json()
            )
            restore_current_publication_pointer(
                self.settings, journal.backing_corpus_name, journal.prior_snapshot_id
            )
            self.journal_path(workspace_id).unlink(missing_ok=True)
            return "A"

        if workspace.status is WorkspaceStatus.EMPTY:
            # Prefer B: ensure publication not current.
            if pointer.exists():
                retire_current_publication(self.settings, journal.backing_corpus_name)
            self.journal_path(workspace_id).unlink(missing_ok=True)
            return "B"

        # Workspace still non-empty → restore A.
        if journal.phase in {
            EmptyTransitionPhase.PUBLICATION_RETIRED,
            EmptyTransitionPhase.INTENT_RECORDED,
        }:
            if not pointer.exists():
                restore_current_publication_pointer(
                    self.settings,
                    journal.backing_corpus_name,
                    journal.prior_snapshot_id,
                )
            # Ensure workspace matches prior recorded state.
            prior = WorkspaceRecord.model_validate_json(journal.prior_workspace_json)
            atomic_write_text(
                self.store.workspace_path(workspace_id), prior.model_dump_json()
            )
            self.journal_path(workspace_id).unlink(missing_ok=True)
            return "A"

        if journal.phase is EmptyTransitionPhase.WORKSPACE_EMPTIED:
            # Should already be empty; treat as B.
            if pointer.exists():
                retire_current_publication(self.settings, journal.backing_corpus_name)
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
