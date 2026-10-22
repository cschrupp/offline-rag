"""Slice 16L — embedding device auto-selection + Compute settings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from offline_rag.app.compute_product_settings import (
    SenecaComputeBody,
    SenecaComputeSettingsFile,
    compute_field_locks,
    compute_overlay_from_product_settings,
    read_product_compute_settings,
    write_product_compute_settings,
)
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import load_settings
from offline_rag.config.loader import ConfigError
from offline_rag.config.models import AppSettings, EmbeddingModelSettings
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.device import resolve_embedding_device
from offline_rag.dense.embedder import (
    EmbedderError,
    FakeEmbedder,
    SentenceTransformersEmbedder,
    make_embedder,
)

REPO = Path(__file__).resolve().parents[3]


def _settings(tmp_path: Path, **emb_updates) -> AppSettings:
    settings = AppSettings()
    emb = settings.indexing.embedding.model_copy(update=emb_updates)
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "product_settings": tmp_path / "settings",
                    "embedding_artifacts": tmp_path / "models" / "embeddings",
                }
            ),
            "indexing": settings.indexing.model_copy(update={"embedding": emb}),
        }
    )


def test_base_yaml_default_is_auto() -> None:
    settings = load_settings(yaml_paths=[REPO / "config" / "base.yaml"], environ={})
    assert settings.indexing.embedding.device == "auto"


def test_device_validation_accepts_and_rejects() -> None:
    for value in ("auto", "cpu", "cuda"):
        assert EmbeddingModelSettings(device=value).device == value
    for bad in ("gpu", "cuda:0", "metal", ""):
        with pytest.raises(ValidationError):
            EmbeddingModelSettings(device=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("configured", "available", "build", "raised", "resolved", "reason"),
    [
        ("auto", False, None, False, "cpu", "cuda_unavailable"),
        ("auto", False, "12.8", False, "cpu", "cuda_unavailable"),
        ("auto", True, "12.8", False, "cuda", "cuda_available"),
        ("auto", False, "12.8", True, "cpu", "cuda_probe_failed"),
        ("cpu", True, "12.8", False, "cpu", "explicit_cpu"),
        ("cpu", False, None, False, "cpu", "explicit_cpu"),
        ("cuda", True, "12.8", False, "cuda", "explicit_cuda"),
    ],
)
def test_resolver_matrix(
    configured: str,
    available: bool,
    build: str | None,
    raised: bool,
    resolved: str,
    reason: str,
) -> None:
    result = resolve_embedding_device(
        configured,
        probe=lambda: (available, build, raised),
    )
    assert result.resolved_device == resolved
    assert result.selection_reason == reason
    assert result.configured_device == configured


def test_explicit_cuda_unavailable_fails_closed() -> None:
    with pytest.raises(EmbedderError, match="CUDA is unavailable"):
        resolve_embedding_device("cuda", probe=lambda: (False, None, False))
    with pytest.raises(EmbedderError, match="CUDA is unavailable"):
        resolve_embedding_device("cuda", probe=lambda: (False, "12.8", True))


def test_sentence_transformer_never_receives_auto(tmp_path: Path) -> None:
    """P1: make_embedder returns QualifiedEmbeddingRuntime; profile device is cuda/cpu."""
    from offline_rag.dense.embedding_artifacts import (
        RepresentationInspection,
        RepresentationReadiness,
        RepresentationReasonCode,
    )
    from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntime
    from offline_rag.dense.execution_profile import (
        CUDA_FP16_V1,
        EmbeddingProfileResolution,
    )

    settings = _settings(tmp_path, implementation="sentence_transformers", device="auto")
    captured: dict[str, str] = {}

    class CapturingST(SentenceTransformersEmbedder):
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            captured["device"] = kwargs["device"]
            self.device = kwargs["device"]
            self.resolved_device = kwargs["device"]
            self.configured_device = kwargs["configured_device"]
            self.cuda_available = kwargs["cuda_available"]
            self.torch_cuda_build = kwargs["torch_cuda_build"]
            self.device_selection_reason = kwargs["device_selection_reason"]
            self.model_id = kwargs["model_id"]
            self.model_revision = kwargs["model_revision"]
            self.dimension = kwargs["dimension"]
            self.normalize = kwargs["normalize"]
            self.adapter_contract = "sentence-transformers-v1"
            self.query_text_contract = "raw-query-v1"
            self.batch_size = kwargs["batch_size"]
            self._model = object()

        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            return [[0.0] * self.dimension for _ in texts]

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            return [0.0] * self.dimension

    ready = RepresentationInspection(
        representation_id="torch_st_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=tmp_path,
        instance_path=tmp_path,
    )
    with (
        patch(
            "offline_rag.dense.execution_profile.resolve_qualified_embedding_profile",
            return_value=EmbeddingProfileResolution(
                configured_device="auto",
                configured_precision="native",
                profile=CUDA_FP16_V1,
                selection_reason="auto_cuda_fp16",
                cuda_available=True,
                torch_cuda_build="12.8",
            ),
        ),
        patch(
            "offline_rag.dense.embedder.resolve_embedding_model_dir",
            return_value=tmp_path,
        ),
        patch(
            "offline_rag.dense.embedding_artifacts.inspect_representation",
            return_value=ready,
        ),
        patch(
            "offline_rag.dense.embedder.SentenceTransformersEmbedder",
            CapturingST,
        ),
    ):
        emb = make_embedder(settings)
        assert isinstance(emb, QualifiedEmbeddingRuntime)
        assert emb.device == "cuda"
        assert emb.state.value == "UNLOADED"
        # Heavy load constructs backend with concrete device, never "auto".
        _ = emb.embed_query("q")
    assert captured["device"] == "cuda"


def test_no_mid_run_cpu_fallback() -> None:
    """CUDA encode failures must not retry on CPU (existing raise path)."""
    emb = SentenceTransformersEmbedder.__new__(SentenceTransformersEmbedder)
    emb.device = "cuda"
    emb.resolved_device = "cuda"
    emb.dimension = 8
    emb.normalize = False
    emb.batch_size = 2
    emb.document_instruction = None
    emb.query_instruction = None
    emb.query_text_contract = "raw-query-v1"
    emb._model = MagicMock()
    emb._model.encode.side_effect = RuntimeError("CUDA OOM")
    with pytest.raises(RuntimeError, match="CUDA OOM"):
        emb.embed_documents(["a", "b"])
    assert emb._model.encode.call_count == 1


def test_hash_invariance_across_devices() -> None:
    base = AppSettings()
    hashes_emb = []
    hashes_idx = []
    for device in ("auto", "cpu", "cuda"):
        emb = base.indexing.embedding.model_copy(update={"device": device})
        settings = base.model_copy(
            update={"indexing": base.indexing.model_copy(update={"embedding": emb})}
        )
        hashes_emb.append(build_embedding_config_hash(settings))
        hashes_idx.append(build_index_config_hash(settings))
    assert hashes_emb[0] == hashes_emb[1] == hashes_emb[2]
    assert hashes_idx[0] == hashes_idx[1] == hashes_idx[2]


def test_product_compute_store_only_embedding_device(tmp_path: Path) -> None:
    root = tmp_path / "settings"
    write_product_compute_settings(
        root,
        SenecaComputeSettingsFile(
            compute=SenecaComputeBody(embedding_device="cpu")
        ),
    )
    loaded = read_product_compute_settings(root)
    assert loaded is not None
    assert loaded.compute.embedding_device == "cpu"
    overlay = compute_overlay_from_product_settings(root)
    assert overlay == {"indexing": {"embedding": {"device": "cpu"}}}
    bad = root / "seneca-compute.json"
    bad.write_text(
        '{"schema_version":"seneca-compute-settings-v1",'
        '"compute":{"embedding_device":"auto","batch_size":8}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_product_compute_settings(root)


def test_precedence_yaml_then_product_then_env(tmp_path: Path) -> None:
    product = tmp_path / "settings"
    product.mkdir(parents=True, exist_ok=True)
    write_product_compute_settings(
        product,
        SenecaComputeSettingsFile(
            compute=SenecaComputeBody(embedding_device="auto")
        ),
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        "indexing:\n  embedding:\n    device: cpu\n"
        f"paths:\n  product_settings: {product}\n",
        encoding="utf-8",
    )
    yaml_only = load_settings(yaml_paths=[yaml_path], environ={})
    # Product overlays YAML cpu → auto
    assert yaml_only.indexing.embedding.device == "auto"

    env_wins = load_settings(
        yaml_paths=[yaml_path],
        environ={"OFFLINE_RAG_EMBEDDING_DEVICE": "cuda"},
    )
    assert env_wins.indexing.embedding.device == "cuda"


def test_env_lock_presence() -> None:
    assert compute_field_locks({})["embedding_device"] is False
    assert compute_field_locks({"OFFLINE_RAG_EMBEDDING_DEVICE": "cpu"})[
        "embedding_device"
    ]
    assert compute_field_locks({"OFFLINE_RAG_EMBEDDING_DEVICE": ""})[
        "embedding_device"
    ]


class _Closeable:
    def close(self) -> None:
        return None


def _provision_assets(settings: AppSettings) -> None:
    from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

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


def _api_runtime(settings: AppSettings) -> ApplicationRuntime:
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda s: FakeEmbedder(
                dimension=8, configured_device=str(s.indexing.embedding.device)
            ),
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )


def test_compute_api_pending_restart_and_runtime_authority(tmp_path: Path) -> None:
    from offline_rag.api.app import create_app

    settings = _api_settings(tmp_path, device="auto")
    runtime = _api_runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        get = client.get("/v1/settings/compute")
        assert get.status_code == 200
        body = get.json()
        assert body["active"]["embedding_device"] == "auto"
        assert body["pending"] is None
        assert body["runtime"]["active_device"] == "test"
        assert body["availability"]["auto"]["available"] is True
        assert body["availability"]["cpu"]["available"] is True
        assert body["availability"]["cuda"]["available"] is False

        put = client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        assert put.status_code == 200
        saved = put.json()
        assert saved["saved"] is True
        assert saved["restart_required"] is True
        assert saved["active"]["embedding_device"] == "auto"
        assert saved["pending"]["embedding_device"] == "cpu"
        # Active process resource unchanged before restart.
        assert saved["runtime"]["active_device"] == "test"

        caps = client.get("/v1/capabilities")
        assert caps.status_code == 200
        emb = caps.json()["embedding"]
        assert emb["configured_device"] == "auto"
        assert emb["active_device"] == "test"
        assert emb["batch_size"] == settings.indexing.embedding.batch_size


def test_compute_api_env_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from offline_rag.api.app import create_app

    monkeypatch.setenv("OFFLINE_RAG_EMBEDDING_DEVICE", "cpu")
    settings = _api_settings(tmp_path, device="cpu")
    runtime = _api_runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        get = client.get("/v1/settings/compute")
        assert get.status_code == 200
        assert get.json()["locks"]["embedding_device"] is True
        put = client.put("/v1/settings/compute", json={"embedding_device": "auto"})
        assert put.status_code == 409


def test_fake_embedder_make_embedder(tmp_path: Path) -> None:
    settings = _settings(tmp_path, implementation="fake", device="auto")
    emb = make_embedder(settings)
    assert isinstance(emb, FakeEmbedder)
    assert emb.resolved_device == "test"
    assert emb.cuda_available is None


def test_invalid_env_device_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(
            yaml_paths=[],
            environ={"OFFLINE_RAG_EMBEDDING_DEVICE": "gpu"},
        )


def test_compute_api_rejects_unavailable_cuda_without_write(tmp_path: Path) -> None:
    from offline_rag.api.app import create_app
    from offline_rag.app.compute_product_settings import compute_product_settings_path

    settings = _api_settings(tmp_path, device="auto")
    product_path = compute_product_settings_path(settings.paths.product_settings)
    write_product_compute_settings(
        settings.paths.product_settings,
        SenecaComputeSettingsFile(
            compute=SenecaComputeBody(embedding_device="auto")
        ),
    )
    before = product_path.read_bytes()
    runtime = _api_runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        # FakeEmbedder reports cuda_available=None → unavailable.
        put = client.put("/v1/settings/compute", json={"embedding_device": "cuda"})
        assert put.status_code == 422
        body = put.json()
        assert body["error"]["code"] == "settings_invalid"
        reason = (body.get("details") or {}).get("reason")
        assert reason in {
            "pytorch_cpu_only",
            "cuda_device_unavailable",
            "cuda_probe_failed",
            "cuda_unavailable",
        }
        assert product_path.read_bytes() == before
        # auto/cpu remain saveable.
        ok_cpu = client.put("/v1/settings/compute", json={"embedding_device": "cpu"})
        assert ok_cpu.status_code == 200
        assert ok_cpu.json()["pending"]["embedding_device"] == "cpu"
        ok_auto = client.put("/v1/settings/compute", json={"embedding_device": "auto"})
        assert ok_auto.status_code == 200


def test_compute_api_accepts_cuda_when_runtime_reports_available(tmp_path: Path) -> None:
    from offline_rag.api.app import create_app
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    settings = _api_settings(tmp_path, device="auto")

    def _cuda_ready_embedder(s: AppSettings) -> FakeEmbedder:
        emb = FakeEmbedder(
            dimension=8, configured_device=str(s.indexing.embedding.device)
        )
        emb.cuda_available = True
        emb.torch_cuda_build = "12.8"
        emb.device_selection_reason = "cuda_available"
        emb.resolved_device = "cuda"
        emb.device = "cuda"
        return emb

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=_cuda_ready_embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        put = client.put("/v1/settings/compute", json={"embedding_device": "cuda"})
        assert put.status_code == 200
        saved = put.json()
        assert saved["saved"] is True
        assert saved["restart_required"] is True
        assert saved["active"]["embedding_device"] == "auto"
        assert saved["pending"]["embedding_device"] == "cuda"
        loaded = read_product_compute_settings(settings.paths.product_settings)
        assert loaded is not None
        assert loaded.compute.embedding_device == "cuda"


def test_runtime_explicit_cuda_unavailable_fails_closed(tmp_path: Path) -> None:
    from offline_rag.app.runtime import RuntimeState
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    settings = _api_settings(tmp_path, device="cuda")
    emb = settings.indexing.embedding.model_copy(
        update={"implementation": "sentence_transformers", "device": "cuda"}
    )
    settings = settings.model_copy(
        update={"indexing": settings.indexing.model_copy(update={"embedding": emb})}
    )
    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=make_embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    with patch(
        "offline_rag.dense.device.probe_torch_cuda",
        return_value=(False, None, False),
    ):
        runtime.start()
    assert runtime.state is RuntimeState.NOT_READY
    assert runtime.is_ready is False
    assert runtime.resources is None
    assert runtime.failure_reason == "startup_failed"


def test_runtime_auto_unavailable_cuda_starts_ready(tmp_path: Path) -> None:
    from offline_rag.app.runtime import RuntimeState
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    settings = _api_settings(tmp_path, device="auto")
    emb = settings.indexing.embedding.model_copy(
        update={"implementation": "sentence_transformers", "device": "auto"}
    )
    settings = settings.model_copy(
        update={"indexing": settings.indexing.model_copy(update={"embedding": emb})}
    )

    from offline_rag.dense.embedding_artifacts import (
        RepresentationInspection,
        RepresentationReadiness,
        RepresentationReasonCode,
    )

    ready_onnx = RepresentationInspection(
        representation_id="onnx_fp32_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=tmp_path,
        instance_path=tmp_path,
        graph_file_name="onnx/model.onnx",
    )

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=make_embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    with (
        patch(
            "offline_rag.dense.execution_profile.probe_torch_cuda",
            return_value=(False, "12.8", False),
        ),
        patch(
            "offline_rag.dense.embedder.resolve_embedding_model_dir",
            return_value=tmp_path,
        ),
        patch(
            "offline_rag.dense.embedding_artifacts.inspect_representation",
            return_value=ready_onnx,
        ),
    ):
        runtime.start()
    assert runtime.state is RuntimeState.READY
    assert runtime.is_ready is True
    assert runtime.resources is not None
    # P1: AUTO without CUDA selects cpu_onnx_fp32_v1 (UNLOADED until first encode).
    assert runtime.resources.embedder.device == "cpu"  # type: ignore[union-attr]
    assert getattr(runtime.resources.embedder, "profile_id", None) == "cpu_onnx_fp32_v1"
