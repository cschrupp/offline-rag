"""16K-D P2 — dual-backend product/API/UI integration acceptance (D15 A–G)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.compute_product_settings import (
    SenecaComputeBody,
    SenecaComputeSettingsFile,
    compute_product_settings_path,
    write_product_compute_settings,
)
from offline_rag.app.observability_publish import dense_execution_from_runtime
from offline_rag.app.runtime import (
    ApplicationRuntime,
    RepresentationAvailabilityFact,
    ResourceFactories,
    RuntimeState,
    build_embedding_availability_snapshot,
)
from offline_rag.app.workspace.models import ManagedOperationDenseExecution
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.embedding_artifacts import (
    RepresentationInspection,
    RepresentationReadiness,
    RepresentationReasonCode,
)
from offline_rag.dense.embedding_runtime import (
    QualifiedEmbeddingRuntime,
    RuntimeFailureKind,
)
from offline_rag.dense.embedding_runtime import RuntimeState as EmbRuntimeState
from offline_rag.dense.execution_profile import (
    CPU_ONNX_FP32_V1,
    EmbeddingProfileResolution,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO = Path(__file__).resolve().parents[3]


class _Closeable:
    def close(self) -> None:
        return None


def _provision_assets(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    tiktoken_src = REPO / "models" / "tokenizers" / "tiktoken"
    if not (tiktoken_src / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    import shutil

    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(tiktoken_src, settings.paths.tokenizer_artifacts)


def _api_settings(tmp_path: Path, *, device: str = "auto") -> AppSettings:
    env = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
    }
    settings = load_settings(yaml_paths=[REPO / "config" / "base.yaml"], environ=env)
    emb = settings.indexing.embedding.model_copy(
        update={"implementation": "fake", "device": device, "dimension": 8}
    )
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "local-test-model",
            "approved_endpoints": ["http://127.0.0.1:11434/v1"],
            "approved_models": ["local-test-model"],
        }
    )
    settings = settings.model_copy(
        update={
            "indexing": settings.indexing.model_copy(update={"embedding": emb}),
            "generation": generation,
            "reranker": settings.reranker.model_copy(update={"enabled": False}),
        }
    )
    _provision_assets(settings)
    settings.paths.product_settings.mkdir(parents=True, exist_ok=True)
    return settings


def _ready_inspection(
    tmp_path: Path, representation_id: str
) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id=representation_id,  # type: ignore[arg-type]
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=tmp_path,
        instance_path=tmp_path,
        graph_file_name="onnx/model.onnx" if representation_id == "onnx_fp32_v1" else None,
    )


def _absent_inspection(
    tmp_path: Path, representation_id: str
) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id=representation_id,  # type: ignore[arg-type]
        readiness=RepresentationReadiness.ABSENT,
        reason_code=RepresentationReasonCode.INSTANCE_ABSENT,
        reason="missing",
        root=tmp_path,
        instance_path=None,
    )


def _qualified_runtime(
    tmp_path: Path,
    *,
    profile=CPU_ONNX_FP32_V1,
    cuda_available: bool = False,
    torch_cuda_build: str | None = None,
    selection_reason: str = "explicit_cpu_onnx_fp32",
    configured_device: str = "cpu",
    backend_factory=None,
) -> QualifiedEmbeddingRuntime:
    resolution = EmbeddingProfileResolution(
        configured_device=configured_device,  # type: ignore[arg-type]
        configured_precision="native",
        profile=profile,
        selection_reason=selection_reason,  # type: ignore[arg-type]
        cuda_available=cuda_available,
        torch_cuda_build=torch_cuda_build,
        selected_representation_status="READY",
    )
    return QualifiedEmbeddingRuntime(
        profile_resolution=resolution,
        representation=_ready_inspection(tmp_path, profile.representation_id),
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="test-rev",
        dimension=8,
        normalize=True,
        query_text_contract="raw-query-v1",
        backend_factory=backend_factory,
    )


def _runtime_with_embedder(
    settings: AppSettings, embedder_factory
) -> ApplicationRuntime:
    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=embedder_factory,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )


def test_layer_a_one_qualified_runtime_unloaded_on_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    calls = {"n": 0}

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        calls["n"] += 1
        return _qualified_runtime(tmp_path)

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    assert runtime.state is RuntimeState.READY
    assert calls["n"] == 1
    assert runtime.resources is not None
    emb = runtime.resources.embedder
    assert isinstance(emb, QualifiedEmbeddingRuntime)
    assert emb.state is EmbRuntimeState.UNLOADED
    assert runtime.embedding_availability is not None
    assert runtime.embedding_availability.qualified is True
    assert runtime.embedding_availability.onnx_fp32_v1.readiness == "READY"
    assert runtime.embedding_availability.torch_st_v1.readiness == "ABSENT"


def test_layer_a_static_selected_failure_not_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def boom(_s: AppSettings) -> None:
        raise RuntimeError("selected representation not READY")

    runtime = _runtime_with_embedder(settings, boom)
    runtime.start()
    assert runtime.state is RuntimeState.NOT_READY
    assert runtime.failure_reason == "startup_failed"
    assert runtime.resources is None
    assert runtime.embedding_availability is None


def test_layer_a_dynamic_init_failure_keeps_app_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        def bad_backend() -> None:
            raise RuntimeError("backend construct failed")

        return _qualified_runtime(tmp_path, backend_factory=bad_backend)

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    assert runtime.state is RuntimeState.READY
    emb = runtime.resources.embedder  # type: ignore[union-attr]
    with pytest.raises(Exception):
        emb.embed_query("hello")
    assert emb.state is EmbRuntimeState.FAILED
    assert emb.failure_kind is RuntimeFailureKind.INITIALIZATION
    assert runtime.state is RuntimeState.READY


def test_layer_a_dynamic_execution_failure_keeps_app_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    class BoomBackend:
        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            raise RuntimeError("exec boom")

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            raise RuntimeError("exec boom")

        def release(self) -> None:
            return None

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        return _qualified_runtime(tmp_path, backend_factory=lambda: BoomBackend())

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    emb = runtime.resources.embedder  # type: ignore[union-attr]
    with pytest.raises(Exception):
        emb.embed_query("hello")
    assert emb.state is EmbRuntimeState.FAILED
    assert emb.failure_kind is RuntimeFailureKind.EXECUTION
    assert runtime.state is RuntimeState.READY


def test_layer_a_borrow_same_embedder_object(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    runtime = _runtime_with_embedder(
        settings,
        lambda s: FakeEmbedder(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        ),
    )
    runtime.start()
    assert runtime.resources is not None
    owned = runtime.resources.embedder
    # Query cache borrows via resources_provider — identity must match.
    resources = runtime.query_runtimes.resources_provider()
    assert resources is not None
    assert resources.embedder is owned
    runtime.query_runtimes.close()
    assert runtime.resources.embedder is owned


def test_layer_a_shutdown_closes_embedder_after_drain(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    closed = {"n": 0}

    class Tracking(FakeEmbedder):
        def close(self) -> None:  # type: ignore[override]
            closed["n"] += 1

    runtime = _runtime_with_embedder(
        settings,
        lambda s: Tracking(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        ),
    )
    runtime.start()
    runtime.shutdown()
    assert runtime.state is RuntimeState.STOPPED
    assert closed["n"] == 1
    assert runtime.embedding_availability is None


def test_layer_b_get_reports_active_and_snapshot_availability(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="auto")

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        return _qualified_runtime(
            tmp_path,
            profile=CPU_ONNX_FP32_V1,
            configured_device="auto",
            cuda_available=False,
            torch_cuda_build=None,
            selection_reason="auto_cpu_onnx_fp32_cuda_unavailable",
        )

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        resp = client.get("/v1/settings/compute")
        assert resp.status_code == 200
        body = resp.json()
        assert body["active"]["embedding_device"] == "auto"
        assert body["runtime"]["profile_id"] == "cpu_onnx_fp32_v1"
        assert body["runtime"]["embedding_state"] == "UNLOADED"
        assert body["runtime"]["failure_reason"] is None
        assert body["availability"]["cpu"]["available"] is True
        assert body["availability"]["auto"]["available"] is True
        assert body["availability"]["cuda"]["available"] is False
        assert runtime.resources.embedder.state is EmbRuntimeState.UNLOADED  # type: ignore[union-attr]


def test_layer_b_cuda_absent_rep_rejects_without_write(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    product_path = compute_product_settings_path(settings.paths.product_settings)
    write_product_compute_settings(
        settings.paths.product_settings,
        SenecaComputeSettingsFile(compute=SenecaComputeBody(embedding_device="cpu")),
    )
    before = product_path.read_bytes()

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        return _qualified_runtime(
            tmp_path,
            profile=CPU_ONNX_FP32_V1,
            cuda_available=True,
            torch_cuda_build="12.8",
            selection_reason="explicit_cpu_onnx_fp32",
        )

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    assert runtime.embedding_availability is not None
    snap = runtime.embedding_availability
    runtime.embedding_availability = type(snap)(
        cuda_available=True,
        torch_cuda_build="12.8",
        cuda_probe_failed=False,
        selected_profile_id=snap.selected_profile_id,
        selected_representation_id=snap.selected_representation_id,
        torch_st_v1=RepresentationAvailabilityFact(
            readiness="ABSENT", bounded_reason="representation_absent"
        ),
        onnx_fp32_v1=snap.onnx_fp32_v1,
        qualified=True,
    )
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        put = client.put("/v1/settings/compute", json={"embedding_device": "cuda"})
        assert put.status_code == 422
        assert put.json()["error"]["code"] == "settings_invalid"
        assert put.json()["details"]["reason"] == "representation_absent"
        assert product_path.read_bytes() == before
        put_auto = client.put("/v1/settings/compute", json={"embedding_device": "auto"})
        assert put_auto.status_code == 422
        assert put_auto.json()["details"]["reason"] == "auto_selected_profile_unavailable"


def test_layer_b_pending_restart_and_same_as_active(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="auto")
    runtime = _runtime_with_embedder(
        settings,
        lambda s: FakeEmbedder(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        ),
    )
    runtime.start()
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        same = client.put("/v1/settings/compute", json={"embedding_device": "auto"})
        assert same.status_code == 200
        assert same.json()["pending"] is None
        assert same.json()["restart_required"] is False
        changed = client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        assert changed.status_code == 200
        assert changed.json()["pending"]["embedding_device"] == "cpu"
        assert changed.json()["restart_required"] is True


def test_layer_b_failed_runtime_still_allows_get_put(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        def bad() -> None:
            raise RuntimeError("init fail")

        return _qualified_runtime(tmp_path, backend_factory=bad)

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    emb = runtime.resources.embedder  # type: ignore[union-attr]
    with pytest.raises(Exception):
        emb.embed_query("x")
    assert emb.failure_kind is RuntimeFailureKind.INITIALIZATION
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        get = client.get("/v1/settings/compute")
        assert get.status_code == 200
        assert get.json()["runtime"]["embedding_state"] == "FAILED"
        assert (
            get.json()["runtime"]["failure_reason"] == "runtime_initialization_failed"
        )
        put = client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        assert put.status_code == 200
        assert put.json()["runtime"]["embedding_state"] == "FAILED"
        assert emb.state is EmbRuntimeState.FAILED


def test_layer_c_additive_embedding_projection(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        return _qualified_runtime(tmp_path)

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        caps = client.get("/v1/capabilities")
        assert caps.status_code == 200
        emb = caps.json()["embedding"]
        assert emb["configured_device"] == "cpu"
        assert emb["batch_size"] == settings.indexing.embedding.batch_size
        assert emb["profile_id"] == "cpu_onnx_fp32_v1"
        assert emb["embedding_state"] == "UNLOADED"
        assert emb["failure_reason"] is None
        assert "pending" not in emb
        assert runtime.resources.embedder.state is EmbRuntimeState.UNLOADED  # type: ignore[union-attr]


def test_layer_d_doctor_dual_representation_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Doctor must project dual-rep readiness + CUDA with bounded labels."""
    from offline_rag.cli import cmd_doctor
    import argparse

    settings = _api_settings(tmp_path, device="cpu")
    for p in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.traces,
        settings.paths.staging,
        settings.paths.locks,
        settings.paths.retrieval_models,
    ):
        Path(p).mkdir(parents=True, exist_ok=True)

    def _inspect(model_root, representation_id, **_kwargs):  # type: ignore[no-untyped-def]
        if representation_id == "torch_st_v1":
            return _ready_inspection(tmp_path, "torch_st_v1")
        return _absent_inspection(tmp_path, "onnx_fp32_v1")

    with (
        patch("offline_rag.cli._load_settings", return_value=settings),
        patch(
            "offline_rag.cli.validate_embedding_artifacts",
            return_value=type(
                "S",
                (),
                {
                    "path": tmp_path,
                    "readiness": type("R", (), {"value": "READY"})(),
                    "reason": "ok",
                    "manifest": None,
                },
            )(),
        ),
        patch(
            "offline_rag.dense.embedding_artifacts.inspect_representation",
            side_effect=_inspect,
        ),
        patch(
            "offline_rag.dense.device.probe_torch_cuda",
            return_value=(False, None, False),
        ),
        patch(
            "offline_rag.cli.validate_docling_artifacts",
            return_value=type(
                "D", (), {"path": tmp_path, "ready": True, "reason": None}
            )(),
        ),
        patch("offline_rag.cli.validate_tiktoken_artifacts", return_value=(True, None)),
        patch("offline_rag.cli.validate_corpus_name", return_value="default"),
        patch(
            "offline_rag.cli.corpus_state_path",
            return_value=tmp_path / "missing.state",
        ),
        patch("offline_rag.cli.chunking_status_for_corpus", return_value="n/a"),
        patch(
            "offline_rag.cli.chunk_state_path", return_value=tmp_path / "cmissing"
        ),
        patch("offline_rag.cli.configure_logging"),
        patch("offline_rag.cli.log_event"),
        patch("offline_rag.cli.os.access", return_value=True),
    ):
        args = argparse.Namespace(corpus="default")
        try:
            cmd_doctor(args)
        except Exception:
            pass
    out = capsys.readouterr().out
    assert "Representation torch_st_v1" in out
    assert "Representation onnx_fp32_v1" in out
    assert "torch-only" in out
    assert "pytorch_cpu_only" in out


def test_layer_e_historical_dense_execution_still_valid() -> None:
    legacy = {
        "device": "cpu",
        "dtype": None,
        "batch_size": 32,
        "attention_backend": None,
        "embedding_dimension": 1024,
    }
    parsed = ManagedOperationDenseExecution.model_validate(legacy)
    assert parsed.profile_id is None
    assert parsed.representation_id is None


def test_layer_e_new_fields_round_trip_and_no_load(tmp_path: Path) -> None:
    emb = _qualified_runtime(tmp_path)
    assert emb.state is EmbRuntimeState.UNLOADED
    facts = dense_execution_from_runtime(embedder=emb, batch_size=32)
    assert facts.profile_id == "cpu_onnx_fp32_v1"
    assert facts.representation_id == "onnx_fp32_v1"
    assert facts.backend == "sentence_transformers_onnx"
    assert facts.provider == "CPUExecutionProvider"
    assert facts.resolved_precision == "fp32"
    assert emb.state is EmbRuntimeState.UNLOADED
    again = ManagedOperationDenseExecution.model_validate(facts.model_dump())
    assert again.profile_id == "cpu_onnx_fp32_v1"


def test_layer_f_settings_do_not_mutate_models_dir(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="auto")
    models = Path(settings.paths.embedding_artifacts)
    models.mkdir(parents=True, exist_ok=True)
    sentinel = models / "sentinel.txt"
    sentinel.write_text("x", encoding="utf-8")
    before = sentinel.read_bytes()
    runtime = _runtime_with_embedder(
        settings,
        lambda s: FakeEmbedder(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        ),
    )
    runtime.start()
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        client.get("/v1/settings/compute")
        client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        client.get("/v1/capabilities")
    assert sentinel.read_bytes() == before


def test_layer_g_compute_request_body_unchanged(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    runtime = _runtime_with_embedder(
        settings,
        lambda s: FakeEmbedder(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        ),
    )
    runtime.start()
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        ok = client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        assert ok.status_code == 200
        bad = client.put(
            "/v1/settings/compute",
            json={"embedding_device": "cpu", "profile_id": "cpu_onnx_fp32_v1"},
        )
        assert bad.status_code == 422


def test_snapshot_builder_fake_preserves_legacy_availability(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="auto")
    emb = FakeEmbedder(dimension=8, configured_device="auto")
    snap = build_embedding_availability_snapshot(settings, emb)
    assert snap.qualified is False
    assert snap.onnx_fp32_v1.readiness == "READY"
    assert snap.torch_st_v1.readiness == "READY"
