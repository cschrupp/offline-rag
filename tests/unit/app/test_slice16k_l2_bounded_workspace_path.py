"""L2 bounded-memory workspace projection and path migration contracts."""

from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.ingest_upload import spool_local_files
from offline_rag.app.workspace.lifecycle import SourceUpload, WorkspaceLifecycleService
from offline_rag.app.workspace.models import SourceVersionRecord, new_empty_workspace
from offline_rag.app.workspace.projection import materialize_desired_sources
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config.models import ApiSettings, AppSettings, PathSettings
from offline_rag.core.ids import document_id_from_bytes


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    paths = PathSettings(
        staging=tmp_path / "staging",
        workspaces=tmp_path / "workspaces",
        locks=tmp_path / "locks",
        qdrant_storage=tmp_path / "qdrant",
    )
    for path in (paths.staging, paths.workspaces, paths.locks, paths.qdrant_storage):
        path.mkdir(parents=True, exist_ok=True)
    return AppSettings(api=ApiSettings(**api_overrides), paths=paths)  # type: ignore[arg-type]


def test_projection_verifies_and_copies_without_byte_apis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    vault = RawSourceVault(settings.paths.workspaces)
    workspace_id = "ws_" + "a" * 32
    payload = b"projection-payload" * 32
    meta = vault.put_bytes(workspace_id, payload, display_name="source.txt")
    desired = [
        SourceVersionRecord(
            source_id="src_" + "b" * 32,
            version=1,
            display_name="source.txt",
            content_type="text/plain",
            byte_size=len(payload),
            content_hash=meta.content_hash,
            document_id=document_id_from_bytes(payload),
            vault_object_id=meta.object_id,
            created_at=datetime.now(tz=UTC),
            active_from_revision=1,
        )
    ]

    def fail(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("projection must use path-based vault primitives")

    monkeypatch.setattr(vault, "load_bytes", fail)
    monkeypatch.setattr(Path, "read_bytes", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    projected = materialize_desired_sources(
        settings, workspace_id=workspace_id, desired=desired, vault=vault
    )
    try:
        with projected.sources[0].path.open("rb") as handle:
            assert handle.read() == payload
        assert projected.sources[0].byte_size == len(payload)
    finally:
        projected.cleanup()


def test_projection_fails_closed_on_source_hash_mismatch_and_cleans_scratch(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    vault = RawSourceVault(settings.paths.workspaces)
    workspace_id = "ws_" + "c" * 32
    meta = vault.put_bytes(workspace_id, b"projection", display_name="source.txt")
    work_dir = settings.paths.staging / "projection-failure"
    desired = [
        SourceVersionRecord(
            source_id="src_" + "d" * 32,
            version=1,
            display_name="source.txt",
            content_type="text/plain",
            byte_size=10,
            content_hash="0" * 64,
            document_id="doc_" + "0" * 64,
            vault_object_id=meta.object_id,
            created_at=datetime.now(tz=UTC),
            active_from_revision=1,
        )
    ]
    with pytest.raises(AppError) as exc:
        materialize_desired_sources(
            settings,
            workspace_id=workspace_id,
            desired=desired,
            vault=vault,
            work_dir=work_dir,
        )
    assert exc.value.code is ErrorCode.WORKSPACE_STATE_UNAVAILABLE
    assert not work_dir.exists()


def test_projection_rejects_corrupt_vault_bytes_and_cleans_scratch(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    vault = RawSourceVault(settings.paths.workspaces)
    workspace_id = "ws_" + "f" * 32
    meta = vault.put_bytes(workspace_id, b"projection", display_name="source.txt")
    vault.object_path(workspace_id, meta.object_id).write_bytes(b"corrupt")
    desired = [
        SourceVersionRecord(
            source_id="src_" + "1" * 32,
            version=1,
            display_name="source.txt",
            byte_size=10,
            content_hash=meta.content_hash,
            document_id="doc_" + "1" * 64,
            vault_object_id=meta.object_id,
            created_at=datetime.now(tz=UTC),
            active_from_revision=1,
        )
    ]
    work_dir = settings.paths.staging / "corrupt-projection"
    with pytest.raises(AppError) as exc:
        materialize_desired_sources(
            settings,
            workspace_id=workspace_id,
            desired=desired,
            vault=vault,
            work_dir=work_dir,
        )
    assert exc.value.code is ErrorCode.WORKSPACE_STATE_UNAVAILABLE
    assert not work_dir.exists()


def test_spool_local_files_streams_and_preserves_document_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    source = tmp_path / "binary.txt"
    payload = bytes(range(256)) * 64
    source.write_bytes(payload)

    def fail_read_bytes(_path: Path) -> bytes:
        raise AssertionError("spool_local_files must stream source bytes")

    def fail_write_bytes(_path: Path, _data: bytes) -> None:
        raise AssertionError("spool_local_files must not write source bytes via Path")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    monkeypatch.setattr(Path, "write_bytes", fail_write_bytes)
    upload = spool_local_files(
        settings=settings, corpus_name="manuals", files=[(source, source.name)]
    )
    try:
        item = upload.files[0]
        with item.absolute_path.open("rb") as handle:
            assert handle.read() == payload
        assert item.document_id == document_id_from_bytes(payload)
        assert item.size_bytes == len(payload)
    finally:
        shutil.rmtree(upload.staging_root, ignore_errors=True)


def test_path_backed_source_add_uses_put_path_without_load_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    vault = RawSourceVault(settings.paths.workspaces)
    workspace_id = "ws_" + "e" * 32
    record = new_empty_workspace(title="L2", workspace_id=workspace_id)
    source = tmp_path / "add.txt"
    payload = b"source-add-path" * 32
    source.write_bytes(payload)
    upload = SourceUpload(display_name="add.txt", spool_path=source)

    def fail_load_bytes(_upload: SourceUpload) -> bytes:
        raise AssertionError("path-backed SOURCE_ADD must not load whole bytes")

    monkeypatch.setattr(SourceUpload, "load_bytes", fail_load_bytes)
    service = object.__new__(WorkspaceLifecycleService)
    service.vault = vault
    plan = service._plan_add(record, [upload])
    assert plan.desired[0].document_id == document_id_from_bytes(payload)
    assert plan.desired[0].content_hash == hashlib.sha256(payload).hexdigest()


def test_spool_duplicate_batch_cleans_entire_staging_root(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"duplicate")
    second.write_bytes(b"duplicate")
    with pytest.raises(AppError) as exc:
        spool_local_files(
            settings=settings,
            corpus_name="manuals",
            files=[(first, first.name), (second, second.name)],
        )
    assert exc.value.code is ErrorCode.DOCUMENT_INVALID
    assert exc.value.details["reason"] == "document_identity_conflict"
    assert not list(settings.paths.staging.iterdir())


def test_spool_local_files_enforces_streamed_transport_limits(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        max_bytes_per_document=8,
        max_total_upload_bytes=10,
    )
    large = tmp_path / "large.txt"
    large.write_bytes(b"123456789")
    with pytest.raises(AppError) as per_file:
        spool_local_files(settings=settings, corpus_name="manuals", files=[(large, large.name)])
    assert per_file.value.details["reason"] == "document_too_large"
    assert not list(settings.paths.staging.iterdir())

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"1234567")
    second.write_bytes(b"7654321")
    with pytest.raises(AppError) as aggregate:
        spool_local_files(
            settings=settings,
            corpus_name="manuals",
            files=[(first, first.name), (second, second.name)],
        )
    assert aggregate.value.details["reason"] == "upload_too_large"
    assert not list(settings.paths.staging.iterdir())
