"""Slice 16B — non-empty publication transition recovery (S16-D11 / S16-D13).

Covers the crash-consistency contract for add/remove/replace that leaves at
least one active source: recovery must land in exactly one legal state.

A: prior workspace record + prior publication current
B: new workspace record + new publication current

Immutable snapshot manifests are never deleted; only ``current.json`` moves.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.publication import (
    current_pointer_path,
    snapshot_manifest_path,
)
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.models import (
    SourceVersionRecord,
    WorkspaceRecord,
    WorkspaceStatus,
    backing_corpus_name_for,
    new_source_id,
    new_workspace_id,
    utc_now,
)
from offline_rag.app.workspace.publication_journal import (
    LineageDelta,
    NonEmptyPublicationCoordinator,
    NonEmptyPublicationPhase,
    PublicationMutationKind,
    SourceVersionRef,
)
from offline_rag.app.workspace.retirement import retirement_marker_path
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

SNAP_V05 = "snap_" + "a" * 64
SNAP_V06 = "snap_" + "b" * 64


def _settings(tmp_path: Path) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    ensure_data_directories(settings)
    return settings


def _write_snapshot_manifest(
    settings: AppSettings, corpus: str, snapshot_id: str
) -> Path:
    """Durable immutable manifest stand-in.

    Recovery only requires the manifest to exist (pointer restore refuses to
    point at a snapshot that is gone); it never parses it.
    """
    path = snapshot_manifest_path(settings.paths.corpora, corpus, snapshot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps({"snapshot_id": snapshot_id}))
    return path


def _set_current(settings: AppSettings, corpus: str, snapshot_id: str) -> None:
    path = current_pointer_path(settings.paths.corpora, corpus)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path, PublishedPointer(snapshot_id=snapshot_id).model_dump_json()
    )


def _current(settings: AppSettings, corpus: str) -> str | None:
    path = current_pointer_path(settings.paths.corpora, corpus)
    if not path.exists():
        return None
    return PublishedPointer.model_validate_json(
        path.read_text(encoding="utf-8")
    ).snapshot_id


def _source(
    source_id: str,
    *,
    version: int,
    display_name: str,
    document_id: str,
    active_from_revision: int,
    active_from_snapshot_id: str | None,
) -> SourceVersionRecord:
    return SourceVersionRecord(
        source_id=source_id,
        version=version,
        display_name=display_name,
        content_type="application/pdf",
        byte_size=1024,
        content_hash=f"ch_{document_id}",
        document_id=document_id,
        vault_object_id=f"vobj_{document_id[-4:] * 8}",
        active=True,
        created_at=utc_now(),
        active_from_revision=active_from_revision,
        active_from_snapshot_id=active_from_snapshot_id,
    )


def _active_workspace(settings: AppSettings) -> tuple[WorkspaceRecord, str]:
    """One-source ACTIVE workspace publishing SNAP_V05."""
    workspace_id = new_workspace_id()
    corpus = backing_corpus_name_for(workspace_id)
    source_id = new_source_id()
    now = utc_now()
    record = WorkspaceRecord(
        workspace_id=workspace_id,
        title="Manual B",
        description="",
        revision=2,
        backing_corpus_name=corpus,
        current_snapshot_id=SNAP_V05,
        status=WorkspaceStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        sources=[
            _source(
                source_id,
                version=1,
                display_name="manual_b_v05.pdf",
                document_id="doc_v05",
                active_from_revision=2,
                active_from_snapshot_id=SNAP_V05,
            )
        ],
    )
    WorkspaceStore(settings).create(record)
    _write_snapshot_manifest(settings, corpus, SNAP_V05)
    _set_current(settings, corpus, SNAP_V05)
    return record, source_id


def _empty_workspace(settings: AppSettings) -> WorkspaceRecord:
    workspace_id = new_workspace_id()
    now = utc_now()
    record = WorkspaceRecord(
        workspace_id=workspace_id,
        title="Fresh",
        description="",
        revision=1,
        backing_corpus_name=backing_corpus_name_for(workspace_id),
        current_snapshot_id=None,
        status=WorkspaceStatus.EMPTY,
        created_at=now,
        updated_at=now,
        sources=[],
    )
    WorkspaceStore(settings).create(record)
    return record


def _replacement(record: WorkspaceRecord, source_id: str) -> SourceVersionRecord:
    return _source(
        source_id,
        version=2,
        display_name="manual_b_v06.pdf",
        document_id="doc_v06",
        active_from_revision=record.revision + 1,
        active_from_snapshot_id=None,
    )


def _replace_delta(source_id: str) -> LineageDelta:
    return LineageDelta(
        appended=[SourceVersionRef(source_id=source_id, version=2)],
        superseded=[SourceVersionRef(source_id=source_id, version=1)],
    )


def _begin_replace(
    coordinator: NonEmptyPublicationCoordinator,
    record: WorkspaceRecord,
    source_id: str,
) -> SourceVersionRecord:
    replacement = _replacement(record, source_id)
    coordinator.begin(
        record.workspace_id,
        operation_id="wop_" + "1" * 32,
        mutation_kind=PublicationMutationKind.SOURCE_REPLACE,
        expected_revision=record.revision,
        desired_sources=[replacement],
        lineage_delta=_replace_delta(source_id),
    )
    return replacement


def _committed_record(
    record: WorkspaceRecord, replacement: SourceVersionRecord
) -> WorkspaceRecord:
    return record.model_copy(
        update={
            "revision": record.revision + 1,
            "current_snapshot_id": SNAP_V06,
            "sources": [
                replacement.model_copy(
                    update={"active_from_snapshot_id": SNAP_V06}
                )
            ],
            "updated_at": utc_now(),
        }
    )


def test_recovery_rolls_back_to_a_when_publication_landed_but_workspace_did_not(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    _begin_replace(coordinator, record, source_id)
    # Ingest published v06 and it became current, then the process died before
    # the workspace could claim it.
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V06)

    assert coordinator.recover(record.workspace_id) == "A"

    assert _current(settings, corpus) == SNAP_V05
    restored = store.get(record.workspace_id)
    assert restored.revision == 2
    assert restored.current_snapshot_id == SNAP_V05
    assert [item.version for item in restored.sources] == [1]
    assert not coordinator.journal_path(record.workspace_id).exists()
    # Immutable history is preserved even for the abandoned publication.
    assert snapshot_manifest_path(settings.paths.corpora, corpus, SNAP_V06).exists()
    # Recovery is idempotent.
    assert coordinator.recover(record.workspace_id) == "clean"


def test_recovery_rolls_back_to_a_when_journal_never_recorded_new_snapshot(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    _begin_replace(coordinator, record, source_id)
    # Pointer moved but the phase write was lost: the journal has no
    # new_snapshot_id, so the only legal landing is A.
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    journal = coordinator.load_journal(record.workspace_id)
    assert journal is not None
    assert journal.phase is NonEmptyPublicationPhase.INTENT_RECORDED
    assert journal.new_snapshot_id is None

    assert coordinator.recover(record.workspace_id) == "A"
    assert _current(settings, corpus) == SNAP_V05


def test_recovery_retires_publication_when_prior_workspace_was_empty(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record = _empty_workspace(settings)
    corpus = record.backing_corpus_name
    source_id = new_source_id()
    added = _source(
        source_id,
        version=1,
        display_name="first.pdf",
        document_id="doc_first",
        active_from_revision=2,
        active_from_snapshot_id=None,
    )

    coordinator.begin(
        record.workspace_id,
        operation_id="wop_" + "2" * 32,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
        expected_revision=1,
        desired_sources=[added],
        lineage_delta=LineageDelta(
            appended=[SourceVersionRef(source_id=source_id, version=1)]
        ),
    )
    _write_snapshot_manifest(settings, corpus, SNAP_V05)
    _set_current(settings, corpus, SNAP_V05)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V05)

    assert coordinator.recover(record.workspace_id) == "A"

    # There is no prior pointer to restore, so the abandoned publication must be
    # retired rather than left reachable by an EMPTY workspace.
    assert _current(settings, corpus) is None
    assert retirement_marker_path(settings.paths.corpora, corpus).exists()
    assert snapshot_manifest_path(settings.paths.corpora, corpus, SNAP_V05).exists()
    restored = store.get(record.workspace_id)
    assert restored.status is WorkspaceStatus.EMPTY
    assert restored.revision == 1
    assert restored.sources == []


def test_recovery_completes_b_when_workspace_committed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    history = SourceHistoryStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    replacement = _begin_replace(coordinator, record, source_id)
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V06)
    coordinator.commit_workspace(
        record.workspace_id, _committed_record(record, replacement)
    )
    # Crash before finalize.

    assert coordinator.recover(record.workspace_id) == "B"

    assert _current(settings, corpus) == SNAP_V06
    committed = store.get(record.workspace_id)
    assert committed.revision == 3
    assert committed.current_snapshot_id == SNAP_V06
    assert [item.version for item in committed.sources] == [2]
    assert not coordinator.journal_path(record.workspace_id).exists()

    # Recovery also finished the lineage leg.
    old = history.get(record.workspace_id, source_id, 1)
    assert old.active is False
    assert old.active_through_revision == 2
    assert old.active_through_snapshot_id == SNAP_V05
    new = history.get(record.workspace_id, source_id, 2)
    assert new.active is True
    assert new.active_from_snapshot_id == SNAP_V06
    assert new.document_id == "doc_v06"


def test_recovery_completes_b_on_durable_workspace_evidence_without_phase_write(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    replacement = _begin_replace(coordinator, record, source_id)
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V06)
    # Workspace write landed; the phase marker update did not.
    atomic_write_text(
        store.workspace_path(record.workspace_id),
        _committed_record(record, replacement).model_dump_json(),
    )
    journal = coordinator.load_journal(record.workspace_id)
    assert journal is not None
    assert journal.phase is NonEmptyPublicationPhase.PUBLICATION_OBSERVED

    assert coordinator.recover(record.workspace_id) == "B"
    assert _current(settings, corpus) == SNAP_V06
    assert store.get(record.workspace_id).current_snapshot_id == SNAP_V06


def test_recovery_restores_current_pointer_lost_after_workspace_commit(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    replacement = _begin_replace(coordinator, record, source_id)
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V06)
    coordinator.commit_workspace(
        record.workspace_id, _committed_record(record, replacement)
    )
    # Pointer lost (torn write) after the workspace already claimed v06.
    current_pointer_path(settings.paths.corpora, corpus).unlink()

    assert coordinator.recover(record.workspace_id) == "B"
    assert _current(settings, corpus) == SNAP_V06


def test_journal_fences_ordinary_workspace_mutations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = WorkspaceStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)

    _begin_replace(coordinator, record, source_id)

    with pytest.raises(AppError) as metadata_error:
        store.apply_metadata_patch(
            record.workspace_id, expected_revision=2, title="Renamed"
        )
    assert metadata_error.value.code is ErrorCode.WORKSPACE_CONFLICT
    assert (metadata_error.value.details or {})["reason"] == (
        "publication_transition_in_progress"
    )

    with pytest.raises(AppError) as tombstone_error:
        store.tombstone(record.workspace_id, expected_revision=2)
    assert tombstone_error.value.code is ErrorCode.WORKSPACE_CONFLICT

    # A second concurrent transition is also refused.
    with pytest.raises(AppError) as begin_error:
        _begin_replace(coordinator, record, source_id)
    assert begin_error.value.code is ErrorCode.WORKSPACE_CONFLICT


def test_begin_refuses_empty_desired_set(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)

    # Zero active sources is the EMPTY transition (S16-D13), which must never
    # reach the ingest-backed publication path.
    with pytest.raises(AppError) as error:
        coordinator.begin(
            record.workspace_id,
            operation_id="wop_" + "3" * 32,
            mutation_kind=PublicationMutationKind.SOURCE_REMOVE,
            expected_revision=record.revision,
            desired_sources=[],
            lineage_delta=LineageDelta(
                superseded=[SourceVersionRef(source_id=source_id, version=1)]
            ),
        )
    assert error.value.code is ErrorCode.REQUEST_INVALID
    assert (error.value.details or {})["reason"] == (
        "publication_requires_active_source"
    )


def test_begin_rejects_stale_expected_revision(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)

    with pytest.raises(AppError) as error:
        coordinator.begin(
            record.workspace_id,
            operation_id="wop_" + "4" * 32,
            mutation_kind=PublicationMutationKind.SOURCE_REPLACE,
            expected_revision=1,
            desired_sources=[_replacement(record, source_id)],
            lineage_delta=_replace_delta(source_id),
        )
    assert error.value.code is ErrorCode.WORKSPACE_CONFLICT
    assert (error.value.details or {})["reason"] == "revision_conflict"


def test_finalize_commits_lineage_and_drops_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    history = SourceHistoryStore(settings)
    coordinator = NonEmptyPublicationCoordinator(settings)
    record, source_id = _active_workspace(settings)
    corpus = record.backing_corpus_name

    replacement = _begin_replace(coordinator, record, source_id)
    _write_snapshot_manifest(settings, corpus, SNAP_V06)
    _set_current(settings, corpus, SNAP_V06)
    coordinator.mark_publication_observed(record.workspace_id, SNAP_V06)
    coordinator.commit_workspace(
        record.workspace_id, _committed_record(record, replacement)
    )
    coordinator.finalize(record.workspace_id)

    assert not coordinator.journal_path(record.workspace_id).exists()
    assert coordinator.recover(record.workspace_id) == "clean"
    versions = history.list_for_source(record.workspace_id, source_id)
    assert [item.version for item in versions] == [1, 2]
    # Public lineage projection must not leak vault addressing (S16-D10).
    assert "vault_object_id" not in history.public_projection(versions[0])


def test_recover_all_handles_every_open_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    coordinator = NonEmptyPublicationCoordinator(settings)
    first, first_source = _active_workspace(settings)
    second, second_source = _active_workspace(settings)

    _begin_replace(coordinator, first, first_source)
    _write_snapshot_manifest(settings, first.backing_corpus_name, SNAP_V06)
    _set_current(settings, first.backing_corpus_name, SNAP_V06)
    coordinator.mark_publication_observed(first.workspace_id, SNAP_V06)

    replacement = _begin_replace(coordinator, second, second_source)
    _write_snapshot_manifest(settings, second.backing_corpus_name, SNAP_V06)
    _set_current(settings, second.backing_corpus_name, SNAP_V06)
    coordinator.mark_publication_observed(second.workspace_id, SNAP_V06)
    coordinator.commit_workspace(
        second.workspace_id, _committed_record(second, replacement)
    )

    outcomes = dict(coordinator.recover_all())
    assert outcomes[first.workspace_id] == "A"
    assert outcomes[second.workspace_id] == "B"
    assert coordinator.recover_all() == []
