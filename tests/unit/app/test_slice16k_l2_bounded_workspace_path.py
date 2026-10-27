"""L2 bounded-memory workspace projection and path migration contracts."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import offline_rag.app.workspace.capacity as capacity_module
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest_upload import spool_local_files
from offline_rag.app.workspace.lifecycle import SourceUpload, WorkspaceLifecycleService
from offline_rag.app.workspace.models import SourceVersionRecord, new_empty_workspace
from offline_rag.app.workspace.projection import materialize_desired_sources
from offline_rag.app.workspace.upload_spool import spool_workspace_multipart
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


def _workspace_multipart(
    filename: str, payload: bytes, content_type: str | None
) -> tuple[bytes, bytes]:
    boundary = b"----l6-workspace"
    headers = [
        b'Content-Disposition: form-data; name="files"; filename="'
        + filename.encode()
        + b'"'
    ]
    if content_type is not None:
        headers.append(b"Content-Type: " + content_type.encode())
    body = (
        b"--"
        + boundary
        + b"\r\n"
        + b"\r\n".join(headers)
        + b"\r\n\r\n"
        + payload
        + b"\r\n--"
        + boundary
        + b"--\r\n"
    )
    return body, boundary


async def _chunks(payload: bytes):
    yield payload


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


def test_path_backed_source_replace_uses_put_path_without_load_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    vault = RawSourceVault(settings.paths.workspaces)
    workspace_id = "ws_" + "f" * 32
    record = new_empty_workspace(title="L2", workspace_id=workspace_id)
    source_id = "src_" + "1" * 32
    record = record.model_copy(
        update={
            "sources": [
                SourceVersionRecord(
                    source_id=source_id,
                    version=1,
                    display_name="old.txt",
                    content_type="text/plain",
                    byte_size=3,
                    content_hash="a" * 64,
                    document_id="doc_" + "a" * 64,
                    vault_object_id="obj_old",
                    created_at=datetime.now(tz=UTC),
                    active_from_revision=1,
                )
            ]
        }
    )
    replacement = tmp_path / "replacement.txt"
    replacement.write_bytes(b"replacement-path")
    upload = SourceUpload(
        display_name=replacement.name,
        spool_path=replacement,
        content_sha256=hashlib.sha256(replacement.read_bytes()).hexdigest(),
    )
    service = object.__new__(WorkspaceLifecycleService)
    service.vault = vault
    service.history = SimpleNamespace(next_version=lambda *_args: 2)
    plan = service._plan_replace(record, source_id, upload)
    assert plan.pending_vault_writes[0].upload.spool_path == replacement

    def fail_read_bytes(_path: Path) -> bytes:
        raise AssertionError("path-backed SOURCE_REPLACE must not load whole bytes")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    persisted = service._persist_pending_vault_writes(record, plan)
    assert persisted.desired[0].content_hash == upload.content_sha256


def test_workspace_spool_uses_extension_media_type_for_limits(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        max_bytes_per_document=8,
        max_pdf_bytes_per_document=16,
    )
    spoofed_body, boundary = _workspace_multipart(
        "notes.txt", b"123456789", "application/pdf"
    )
    with pytest.raises(AppError) as spoofed:
        asyncio.run(
            spool_workspace_multipart(
                settings=settings,
                boundary=boundary,
                body_chunks=_chunks(spoofed_body),
                allow_multiple=False,
            )
        )
    assert spoofed.value.details["reason"] == "source_file_too_large"

    pdf_body, boundary = _workspace_multipart("handbook.pdf", b"123456789", None)
    upload = asyncio.run(
        spool_workspace_multipart(
            settings=settings,
            boundary=boundary,
            body_chunks=_chunks(pdf_body),
            allow_multiple=False,
        )
    )
    try:
        assert upload.files[0].content_type == "application/pdf"
    finally:
        upload.cleanup()


def test_resource_rejection_happens_before_vault_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_active_source_bytes_per_workspace=4)
    record = new_empty_workspace(title="L6", workspace_id="ws_" + "9" * 32)
    source = tmp_path / "large.txt"
    source.write_bytes(b"12345")
    service = object.__new__(WorkspaceLifecycleService)
    service.settings = settings
    service.runtime = SimpleNamespace(resources=None)
    service.vault = MagicMock()
    plan = service._plan_add(
        record,
        [SourceUpload(display_name=source.name, spool_path=source)],
    )
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            record,
            operation_id="op_1",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "workspace_source_bytes_exceeded"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


def _pre_vault_service(
    tmp_path: Path,
    *,
    filename: str,
    payload: bytes,
    profile_id: str | None,
    **api_overrides: object,
) -> tuple[WorkspaceLifecycleService, object]:
    settings = _settings(tmp_path, **api_overrides)
    record = new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32)
    source = tmp_path / filename
    source.write_bytes(payload)
    service = object.__new__(WorkspaceLifecycleService)
    service.settings = settings
    service.runtime = SimpleNamespace(
        resources=SimpleNamespace(
            embedder=(SimpleNamespace(profile_id=profile_id) if profile_id else None)
        )
    )
    service.vault = MagicMock()
    plan = service._plan_add(
        record,
        [SourceUpload(display_name=filename, spool_path=source)],
    )
    return service, plan


def test_large_pdf_profile_rejection_precedes_vault_write(tmp_path: Path) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="handbook.pdf",
        payload=b"12345",
        profile_id="unsupported_profile",
        max_bytes_per_document=4,
        max_pdf_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_profile",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "large_pdf_profile_not_qualified"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


def test_cuda_large_pdf_host_memory_rejection_precedes_vault_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="handbook.pdf",
        payload=b"12345",
        profile_id="cuda_fp16_v1",
        max_bytes_per_document=4,
        max_pdf_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    monkeypatch.setattr(
        capacity_module, "_memory_telemetry", lambda: (32_000_000_000, 1)
    )
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_cuda_memory",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "large_pdf_host_memory_insufficient"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


def test_cuda_large_pdf_vram_rejection_precedes_vault_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="handbook.pdf",
        payload=b"12345",
        profile_id="cuda_fp16_v1",
        max_bytes_per_document=4,
        max_pdf_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    monkeypatch.setattr(
        capacity_module,
        "_memory_telemetry",
        lambda: (32_000_000_000, 20_000_000_000),
    )
    monkeypatch.setattr(capacity_module, "_cuda_memory_telemetry", lambda _device: None)
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_cuda_vram",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "memory_telemetry_unavailable"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


def test_cuda_large_pdf_admission_reaches_vault_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="handbook.pdf",
        payload=b"12345",
        profile_id="cuda_fp16_v1",
        max_bytes_per_document=4,
        max_pdf_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    monkeypatch.setattr(
        capacity_module,
        "_memory_telemetry",
        lambda: (32_000_000_000, 20_000_000_000),
    )
    monkeypatch.setattr(
        capacity_module,
        "_cuda_memory_telemetry",
        lambda _device: capacity_module.CudaMemoryTelemetry(
            total_bytes=capacity_module.CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
            free_bytes=capacity_module.CUDA_LARGE_PDF_MIN_EFFECTIVE_CAPACITY_BYTES,
            current_process_reserved_bytes=0,
        ),
    )
    monkeypatch.setattr(capacity_module, "enforce_reconstruction_disk_capacity", lambda *a, **k: None)
    reached = False

    def persist(*_args: object, **_kwargs: object) -> object:
        nonlocal reached
        reached = True
        raise RuntimeError("vault stage reached")

    monkeypatch.setattr(service, "_persist_pending_vault_writes", persist)
    with pytest.raises(RuntimeError, match="vault stage reached"):
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_cuda_success",
            plan=plan,
            lease=None,
            control=None,
        )
    assert reached is True


def test_large_pdf_memory_rejection_precedes_vault_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="handbook.pdf",
        payload=b"12345",
        profile_id="cpu_onnx_fp32_v1",
        max_bytes_per_document=4,
        max_pdf_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    monkeypatch.setattr(capacity_module, "_memory_telemetry", lambda: (32_000_000_000, 1))
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_memory",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "large_pdf_host_memory_insufficient"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


def test_disk_rejection_precedes_vault_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, plan = _pre_vault_service(
        tmp_path,
        filename="notes.txt",
        payload=b"12345",
        profile_id=None,
        max_bytes_per_document=16,
        max_active_source_bytes_per_workspace=100,
    )
    def reject_disk(*_args: object, **_kwargs: object) -> None:
        raise AppError(
            ErrorCode.SERVICE_OVERLOADED,
            details=SafeErrorDetails(reason="storage_insufficient"),
        )

    monkeypatch.setattr(
        capacity_module, "enforce_reconstruction_disk_capacity", reject_disk
    )
    with pytest.raises(AppError) as exc:
        service._execute_publication(
            new_empty_workspace(title="L6", workspace_id="ws_" + "8" * 32),
            operation_id="op_disk",
            plan=plan,
            lease=None,
            control=None,
        )
    assert exc.value.details["reason"] == "storage_insufficient"
    service.vault.put_path.assert_not_called()
    service.vault.put_bytes.assert_not_called()


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
    assert per_file.value.details["reason"] == "source_file_too_large"
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
    assert aggregate.value.details["reason"] == "request_too_large"
    assert not list(settings.paths.staging.iterdir())
