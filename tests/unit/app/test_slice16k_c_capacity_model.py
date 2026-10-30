"""16K-C — transport vs workspace/search capacity model proofs."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import offline_rag.app.workspace.capacity as capacity_module
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest_upload import cleanup_staging, spool_local_files
from offline_rag.app.workspace.capacity import (
    CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
    CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES,
    CudaMemoryTelemetry,
    enforce_large_pdf_runtime,
    enforce_reconstruction_disk_capacity,
    enforce_searchable_workload_capacity,
    enforce_workspace_active_source_bytes,
    enforce_workspace_active_source_capacity,
    large_pdf_runtime_eligibility,
    validate_desired_set_integrity,
)
from offline_rag.app.workspace.models import SourceVersionRecord
from offline_rag.app.workspace.projection import enforce_desired_set_limits
from offline_rag.app.workspace.publication_journal import PublicationMutationKind
from offline_rag.config.models import ApiSettings, AppSettings, PathSettings


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    api = ApiSettings(**api_overrides)  # type: ignore[arg-type]
    paths = PathSettings(
        staging=tmp_path / "staging",
        workspaces=tmp_path / "workspaces",
        locks=tmp_path / "locks",
        qdrant_storage=tmp_path / "qdrant",
    )
    for p in (
        paths.staging,
        paths.workspaces,
        paths.locks,
        paths.qdrant_storage,
    ):
        p.mkdir(parents=True, exist_ok=True)
    return AppSettings(api=api, paths=paths)


def _source(
    source_id: str = "src_1",
    *,
    byte_size: int = 100,
) -> SourceVersionRecord:
    return SourceVersionRecord(
        source_id=source_id,
        version=1,
        display_name=f"{source_id}.txt",
        content_type="text/plain",
        byte_size=byte_size,
        content_hash="a" * 64,
        document_id="d" * 64,
        vault_object_id="obj_" + source_id,
        active=True,
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        active_from_revision=1,
        active_from_snapshot_id=None,
    )


def test_transport_defaults_unchanged() -> None:
    api = ApiSettings()
    assert api.max_files_per_ingest == 32
    assert api.max_bytes_per_document == 26_214_400
    assert api.max_pdf_bytes_per_document == 94_371_840
    assert api.max_total_upload_bytes == 104_857_600
    assert api.max_active_source_bytes_per_workspace is None
    assert api.max_active_sources_per_workspace is None
    assert api.max_searchable_child_chunks_per_workspace is None


def test_workspace_source_capacity_independent_of_transport(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_active_sources_per_workspace=2)
    desired = [_source("a"), _source("b"), _source("c")]
    with pytest.raises(AppError) as exc:
        enforce_workspace_active_source_capacity(
            settings,
            desired,
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
        )
    assert exc.value.code is ErrorCode.REQUEST_INVALID
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "workspace_source_capacity_exceeded"


def test_remove_not_blocked_by_source_capacity(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_active_sources_per_workspace=1)
    desired = [_source("a"), _source("b")]
    enforce_workspace_active_source_capacity(
        settings,
        desired,
        mutation_kind=PublicationMutationKind.SOURCE_REMOVE,
    )


def test_workspace_source_bytes_uses_complete_desired_set(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_active_source_bytes_per_workspace=100)
    enforce_workspace_active_source_bytes(
        settings,
        [_source("a", byte_size=60)],
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
    )
    with pytest.raises(AppError) as exc:
        enforce_workspace_active_source_bytes(
            settings,
            [_source("a", byte_size=60), _source("b", byte_size=41)],
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
        )
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "workspace_source_bytes_exceeded"


def test_default_workspace_source_bytes_are_unbounded_by_unqualified_aggregate(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    desired = [_source(f"text_{index}", byte_size=20 * 1024 * 1024) for index in range(10)]
    pdf = _source("pdf", byte_size=64 * 1024 * 1024)
    desired.append(
        pdf.model_copy(
            update={"display_name": "large.pdf", "content_type": "application/pdf"}
        )
    )
    enforce_workspace_active_source_bytes(
        settings,
        desired,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
    )


def test_reconstruction_disk_admission_retains_aggregate_storage_bound(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    active_bytes = 10 * 20 * 1024 * 1024 + 64 * 1024 * 1024
    desired = [_source("bulk", byte_size=active_bytes)]
    required = 5 * active_bytes + 1_073_741_824
    enforce_reconstruction_disk_capacity(
        settings,
        desired,
        disk_usage=lambda _path: type("Usage", (), {"free": required})(),
    )
    with pytest.raises(AppError) as exc:
        enforce_reconstruction_disk_capacity(
            settings,
            desired,
            disk_usage=lambda _path: type("Usage", (), {"free": required - 1})(),
        )
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "storage_insufficient"


def test_source_remove_can_reduce_oversized_legacy_workspace(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_active_source_bytes_per_workspace=100)
    enforce_workspace_active_source_bytes(
        settings,
        [_source("remaining", byte_size=130)],
        mutation_kind=PublicationMutationKind.SOURCE_REMOVE,
    )


def test_pdf_transport_uses_pdf_limit(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        max_bytes_per_document=8,
        max_pdf_bytes_per_document=16,
    )
    pdf = tmp_path / "manual.pdf"
    pdf.write_bytes(b"123456789")
    upload = spool_local_files(
        settings=settings,
        corpus_name="manuals",
        files=[(pdf, pdf.name)],
    )
    assert upload.files[0].size_bytes == 9
    cleanup_staging(upload.staging_root)


def test_large_pdf_runtime_requires_qualified_profile_and_memory() -> None:
    settings = AppSettings()
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="other_profile",
        memory=(64_000_000_000, 64_000_000_000),
    ) == (False, "profile_not_qualified")
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cpu_onnx_fp32_v1",
        memory=(32_000_000_000, 1),
    ) == (False, "host_memory_insufficient")


def test_cuda_large_pdf_runtime_uses_profile_specific_host_and_vram_gates() -> None:
    settings = AppSettings()
    exact_cuda = CudaMemoryTelemetry(
        total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
        free_bytes=1,
        current_process_reserved_bytes=123,
    )
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=exact_cuda,
    ) == (True, None)
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES - 1),
        cuda_memory=exact_cuda,
    ) == (False, "host_memory_insufficient")
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=CudaMemoryTelemetry(
            total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES - 1,
            free_bytes=1,
            current_process_reserved_bytes=0,
        ),
    ) == (False, "large_pdf_gpu_memory_insufficient")
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=CudaMemoryTelemetry(
            total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
            free_bytes=1,
            current_process_reserved_bytes=0,
        ),
    ) == (True, None)


def test_cuda_transient_free_capacity_does_not_preempt_qualified_runtime() -> None:
    telemetry = CudaMemoryTelemetry(
        total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
        free_bytes=1,
        current_process_reserved_bytes=0,
    )
    assert large_pdf_runtime_eligibility(
        AppSettings(),
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=telemetry,
    ) == (True, None)


def test_cuda_telemetry_unavailable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings()
    monkeypatch.setattr(capacity_module, "_cuda_memory_telemetry", lambda _device: None)
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=None,
    ) == (False, "memory_telemetry_unavailable")


def test_malformed_cuda_telemetry_fails_closed() -> None:
    settings = AppSettings()
    assert large_pdf_runtime_eligibility(
        settings,
        profile_id="cuda_fp16_v1",
        memory=(32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
        cuda_memory=CudaMemoryTelemetry(
            total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
            free_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES + 1,
            current_process_reserved_bytes=0,
        ),
    ) == (False, "memory_telemetry_unavailable")


def test_host_and_cuda_telemetry_failures_keep_internal_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings()
    monkeypatch.setattr(capacity_module, "_memory_telemetry", lambda: None)
    host = capacity_module._large_pdf_runtime_eligibility(
        settings, profile_id="cpu_onnx_fp32_v1"
    )
    assert host.diagnostic_reason == "HOST_MEMORY_TELEMETRY_UNAVAILABLE"

    monkeypatch.setattr(
        capacity_module,
        "_memory_telemetry",
        lambda: (32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
    )
    monkeypatch.setattr(capacity_module, "_cuda_memory_telemetry", lambda _device: None)
    cuda = capacity_module._large_pdf_runtime_eligibility(
        settings, profile_id="cuda_fp16_v1"
    )
    assert cuda.diagnostic_reason == "CUDA_MEMORY_TELEMETRY_UNAVAILABLE"


def test_large_pdf_admission_and_empty_disk_transition(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    pdf = _source("pdf", byte_size=26_214_401).model_copy(
        update={"content_type": "application/pdf"}
    )
    with pytest.raises(AppError) as exc:
        enforce_large_pdf_runtime(settings, [pdf], profile_id="unsupported_profile")
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "large_pdf_profile_not_qualified"
    enforce_reconstruction_disk_capacity(
        settings,
        [],
        disk_usage=lambda _path: type("Usage", (), {"free": 0})(),
    )


def test_searchable_workload_capacity_fail_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_searchable_child_chunks_per_workspace=10)
    with pytest.raises(AppError) as exc:
        enforce_searchable_workload_capacity(
            settings,
            searchable_child_count=11,
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
        )
    assert exc.value.details is not None
    assert exc.value.details["reason"] == "searchable_workload_capacity_exceeded"


def test_remove_not_blocked_by_searchable_capacity(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_searchable_child_chunks_per_workspace=1)
    enforce_searchable_workload_capacity(
        settings,
        searchable_child_count=99,
        mutation_kind=PublicationMutationKind.SOURCE_REMOVE,
    )


def test_f001_legacy_ingest_not_constrained_by_workspace_searchable_ceiling(
    tmp_path: Path,
) -> None:
    """F001: mutation_kind=None must not apply per-workspace searchable ceiling."""
    settings = _settings(tmp_path, max_searchable_child_chunks_per_workspace=1)
    enforce_searchable_workload_capacity(
        settings,
        searchable_child_count=99,
        mutation_kind=None,
    )


def test_searchable_workload_within_ceiling_allows_add(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_searchable_child_chunks_per_workspace=10)
    enforce_searchable_workload_capacity(
        settings,
        searchable_child_count=10,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
    )
    enforce_searchable_workload_capacity(
        settings,
        searchable_child_count=10,
        mutation_kind=PublicationMutationKind.SOURCE_REPLACE,
    )


def test_unset_workspace_ceilings_do_not_invent_support_claim(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    enforce_workspace_active_source_capacity(
        settings,
        [_source(f"s{i}") for i in range(40)],
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
    )
    enforce_searchable_workload_capacity(
        settings,
        searchable_child_count=12_000,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
    )


def test_reconstruction_skips_transport_on_desired_set(tmp_path: Path) -> None:
    """Proof 7: vaulted aggregate may exceed one HTTP upload request."""
    settings = _settings(
        tmp_path,
        max_files_per_ingest=2,
        max_total_upload_bytes=150,
        max_bytes_per_document=100,
    )
    desired = [
        _source("a", byte_size=80),
        _source("b", byte_size=80),
        _source("c", byte_size=80),
    ]
    enforce_desired_set_limits(settings, desired)
    validate_desired_set_integrity(desired)


def test_spool_local_reconstruction_bypasses_request_envelope(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        max_files_per_ingest=1,
        max_total_upload_bytes=50,
        max_bytes_per_document=40,
    )
    files_dir = tmp_path / "local"
    files_dir.mkdir()
    paths: list[tuple[Path, str]] = []
    for i in range(3):
        p = files_dir / f"f{i}.txt"
        # Distinct bytes so document identity does not collide.
        p.write_bytes((f"payload-{i}-").encode() + (b"x" * 60))
        paths.append((p, p.name))

    with pytest.raises(AppError) as transport_exc:
        spool_local_files(
            settings=settings,
            corpus_name="manuals",
            files=paths,
            apply_transport_limits=True,
        )
    assert transport_exc.value.details is not None
    assert transport_exc.value.details["reason"] == "too_many_files"

    upload = spool_local_files(
        settings=settings,
        corpus_name="manuals",
        files=paths,
        apply_transport_limits=False,
    )
    assert len(upload.files) == 3


def _drive_to_dense_gate(
    tmp_path: Path,
    *,
    child_chunks: int,
    ceiling: int,
    mutation_kind: object | None,
    authorize_workspace_id: str | None,
) -> tuple[AppError | None, MagicMock]:
    """Run ingest through chunk→capacity; dense raises a sentinel if reached."""
    from offline_rag.app.ingest import run_product_replace_ingest
    from offline_rag.domain.chunking import ChunkingReport, ChunkingStatus
    from offline_rag.domain.ingestion import IngestionReport, IngestionStatus

    settings = _settings(
        tmp_path, max_searchable_child_chunks_per_workspace=ceiling
    )
    runtime = MagicMock()
    runtime.require_ready = MagicMock()
    runtime.settings = settings
    runtime.resources = SimpleNamespace(embedder=object(), qdrant=object())

    upload = MagicMock()
    upload.corpus_name = "manuals"
    upload.files = [MagicMock(), MagicMock()]
    upload.source_name_by_storage_name = MagicMock(return_value={})

    now = datetime(2020, 1, 1, tzinfo=UTC)
    chunk_report = ChunkingReport(
        run_id="run_chunk",
        corpus_name="manuals",
        corpus_id="c" * 64,
        status=ChunkingStatus.SUCCESS,
        started_at=now,
        completed_at=now,
        duration_ms=1,
        child_chunks=child_chunks,
    )
    ingest_report = IngestionReport(
        run_id="run_ingest",
        corpus_name="manuals",
        status=IngestionStatus.SUCCESS,
        started_at=now,
        completed_at=now,
        duration_ms=1,
        corpus_id="c" * 64,
    )

    dense_mock = MagicMock(
        side_effect=AppError(
            ErrorCode.INGEST_FAILED,
            details=SafeErrorDetails(reason="dense_reached_after_capacity_gate"),
        )
    )
    ownership = (
        patch(
            "offline_rag.app.workspace.corpus_ownership.assert_legacy_ingest_allowed",
            return_value=None,
        )
        if authorize_workspace_id is None
        else patch(
            "offline_rag.app.workspace.corpus_ownership.assert_authorized_workspace_corpus",
            return_value=None,
        )
    )
    with (
        patch(
            "offline_rag.app.ingest._validate_document_identities",
            return_value=None,
        ),
        patch(
            "offline_rag.app.ingest._establish_candidate",
            return_value=SimpleNamespace(
                settings=settings,
                sources_root=tmp_path,
                stage_corpora_root=tmp_path,
                candidate_root=tmp_path,
            ),
        ),
        patch(
            "offline_rag.app.ingest._source_inputs",
            return_value=[object(), object()],
        ),
        patch("offline_rag.app.ingest.run_ingestion", return_value=ingest_report),
        patch(
            "offline_rag.app.ingest.load_corpus_state",
            return_value=SimpleNamespace(
                sources={
                    "a": SimpleNamespace(document_id="d1"),
                    "b": SimpleNamespace(document_id="d2"),
                }
            ),
        ),
        patch(
            "offline_rag.app.ingest.corpus_state_path",
            return_value=tmp_path / "cs",
        ),
        patch("offline_rag.app.ingest.run_chunking", return_value=chunk_report),
        patch("offline_rag.app.ingest.run_indexing", dense_mock),
        ownership,
    ):
        lease = MagicMock()
        lease.held = True
        lease.corpus_name = "manuals"
        kwargs: dict = {"corpus_lease": lease, "mutation_kind": mutation_kind}
        if authorize_workspace_id is not None:
            kwargs["authorize_workspace_id"] = authorize_workspace_id
        try:
            run_product_replace_ingest(runtime, upload, **kwargs)
        except AppError as exc:
            return exc, dense_mock
    return None, dense_mock


def test_pre_dense_capacity_gate_runs_before_indexing(tmp_path: Path) -> None:
    """F001: workspace Add above searchable ceiling fails before dense."""
    err, dense_mock = _drive_to_dense_gate(
        tmp_path,
        child_chunks=9,
        ceiling=5,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
        authorize_workspace_id="ws_test",
    )
    assert err is not None
    assert err.details is not None
    assert err.details["reason"] == "searchable_workload_capacity_exceeded"
    dense_mock.assert_not_called()


def test_f001_workspace_replace_over_cap_fails_before_dense(tmp_path: Path) -> None:
    err, dense_mock = _drive_to_dense_gate(
        tmp_path,
        child_chunks=9,
        ceiling=5,
        mutation_kind=PublicationMutationKind.SOURCE_REPLACE,
        authorize_workspace_id="ws_test",
    )
    assert err is not None
    assert err.details is not None
    assert err.details["reason"] == "searchable_workload_capacity_exceeded"
    dense_mock.assert_not_called()


def test_f001_workspace_add_within_ceiling_reaches_dense(tmp_path: Path) -> None:
    err, dense_mock = _drive_to_dense_gate(
        tmp_path,
        child_chunks=5,
        ceiling=5,
        mutation_kind=PublicationMutationKind.SOURCE_ADD,
        authorize_workspace_id="ws_test",
    )
    assert err is not None
    assert err.details is not None
    assert err.details["reason"] == "dense_reached_after_capacity_gate"
    dense_mock.assert_called_once()


def test_f001_legacy_v1_ingest_ignores_workspace_searchable_ceiling(
    tmp_path: Path,
) -> None:
    """F001: POST /v1/ingest path (mutation_kind=None) is not constrained."""
    err, dense_mock = _drive_to_dense_gate(
        tmp_path,
        child_chunks=99,
        ceiling=5,
        mutation_kind=None,
        authorize_workspace_id=None,
    )
    assert err is not None
    assert err.details is not None
    assert err.details["reason"] == "dense_reached_after_capacity_gate"
    dense_mock.assert_called_once()


def _capabilities_body(settings: AppSettings, embedder: object | None = None) -> dict:
    from offline_rag.api.capabilities import get_capabilities

    runtime = MagicMock()
    runtime.require_ready = MagicMock()
    runtime.settings = settings
    runtime.resources = (
        SimpleNamespace(embedder=embedder) if embedder is not None else None
    )
    request = MagicMock()
    request.app.state.runtime = runtime
    return get_capabilities(request)


def test_capabilities_separate_transport_and_workspace(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        max_active_sources_per_workspace=7,
        max_searchable_child_chunks_per_workspace=100,
    )
    body = _capabilities_body(settings)
    assert body["transport_limits"]["max_files_per_upload_request"] == 32
    assert body["transport_limits"]["max_bytes_per_uploaded_file"] == 26_214_400
    assert body["transport_limits"]["max_bytes_per_upload_request"] == 104_857_600
    assert body["workspace_capacity"]["max_active_sources"] == 7
    assert body["workspace_capacity"]["max_searchable_child_chunks"] == 100
    assert body["workspace_capacity"]["max_active_source_bytes"] is None
    assert body["large_pdf"]["effective_max_bytes"] == 26_214_400
    assert body["large_pdf"]["runtime_eligible"] is False
    assert body["large_pdf"]["qualified_profiles"] == [
        "cpu_onnx_fp32_v1",
        "cuda_fp16_v1",
    ]
    assert body["source_limits"]["max_active_sources"] == 7
    assert body["source_limits"]["max_bytes_per_source"] == 26_214_400
    assert body["source_limits"]["max_active_source_bytes"] == 104_857_600


def test_capabilities_null_workspace_when_unset(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    body = _capabilities_body(settings)
    assert body["workspace_capacity"]["max_active_sources"] is None
    assert body["workspace_capacity"]["max_searchable_child_chunks"] is None
    assert body["workspace_capacity"]["max_active_source_bytes"] is None
    assert body["source_limits"]["max_active_sources"] is None


def test_capabilities_reports_eligible_cuda_without_loading_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    embedder = SimpleNamespace(
        profile_id="cuda_fp16_v1",
        resolved_device="cuda",
        device="cuda",
        configured_device="auto",
        configured_precision="native",
        resolved_precision="fp16",
        cuda_available=True,
        torch_cuda_build="12.1",
        device_selection_reason="auto_cuda_fp16",
        representation_id="torch_st_v1",
        state="UNLOADED",
        backend_factory_calls=0,
    )
    monkeypatch.setattr(
        capacity_module,
        "_memory_telemetry",
        lambda: (32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
    )
    monkeypatch.setattr(
        capacity_module,
        "_cuda_memory_telemetry",
        lambda _device: CudaMemoryTelemetry(
            total_bytes=CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES,
            free_bytes=1,
            current_process_reserved_bytes=0,
        ),
    )
    body = _capabilities_body(settings, embedder)
    assert body["embedding"]["configured_device"] == "auto"
    assert body["embedding"]["active_device"] == "cuda"
    assert body["embedding"]["profile_id"] == "cuda_fp16_v1"
    assert body["large_pdf"]["runtime_eligible"] is True
    assert body["large_pdf"]["effective_max_bytes"] == 94_371_840
    assert body["large_pdf"]["unavailable_reason"] is None
    assert embedder.state == "UNLOADED"
    assert embedder.backend_factory_calls == 0


def test_capabilities_cuda_resource_failure_projects_25_mib(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    embedder = SimpleNamespace(
        profile_id="cuda_fp16_v1",
        resolved_device="cuda",
        device="cuda",
        configured_device="auto",
        configured_precision="native",
        resolved_precision="fp16",
        cuda_available=True,
        torch_cuda_build="12.1",
        device_selection_reason="auto_cuda_fp16",
        representation_id="torch_st_v1",
        state="UNLOADED",
    )
    monkeypatch.setattr(
        capacity_module,
        "_memory_telemetry",
        lambda: (32_000_000_000, CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES),
    )
    monkeypatch.setattr(capacity_module, "_cuda_memory_telemetry", lambda _device: None)
    body = _capabilities_body(settings, embedder)
    assert body["large_pdf"]["runtime_eligible"] is False
    assert body["large_pdf"]["effective_max_bytes"] == 26_214_400
    assert body["large_pdf"]["unavailable_reason"] == "memory_telemetry_unavailable"
