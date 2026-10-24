"""16K-D P4 — dual-backend product acceptance & default-policy qualification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.api.compute_settings import project_embedding_runtime_dto
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ResourceFactories,
    RuntimeState,
)
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
    dense_collection_name,
    dense_index_id,
    embedding_id_from_parts,
)
from offline_rag.dense.config_hash import (
    build_dense_retrieval_config_hash,
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import EmbedderError
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
    CUDA_FP16_V1,
    PROFILES,
    EmbeddingProfileResolution,
    resolve_qualified_embedding_profile,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO = Path(__file__).resolve().parents[3]
BASE_YAML = REPO / "config" / "base.yaml"
EVIDENCE_CHAIN = (
    REPO / "docs" / "evidence" / "16k_d_dual_backend_p4" / "p4_evidence_chain.json"
)
SCREEN_EVIDENCE = (
    REPO
    / "docs"
    / "evidence"
    / "16k_d_cpu_onnx"
    / "onnx_fp32_128_screen_pass_1792638543.json"
)
PARITY_EVIDENCE = (
    REPO
    / "docs"
    / "evidence"
    / "16k_d_cpu_onnx"
    / "onnx_fp32_gpu_fp16_parity_pass_1792638012.json"
)


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
    settings = load_settings(yaml_paths=[BASE_YAML], environ=env)
    emb = settings.indexing.embedding.model_copy(
        update={
            "implementation": "fake",
            "device": device,
            "precision": "native",
            "dimension": 8,
        }
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


def _ready_inspection(tmp_path: Path, representation_id: str) -> RepresentationInspection:
    return RepresentationInspection(
        representation_id=representation_id,  # type: ignore[arg-type]
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=tmp_path,
        instance_path=tmp_path,
        graph_file_name="onnx/model.onnx" if representation_id == "onnx_fp32_v1" else None,
    )


def _absent_inspection(tmp_path: Path, representation_id: str) -> RepresentationInspection:
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
    profile: Any = CPU_ONNX_FP32_V1,
    cuda_available: bool = False,
    torch_cuda_build: str | None = None,
    selection_reason: str = "explicit_cpu_onnx_fp32",
    configured_device: str = "cpu",
    backend_factory: Any = None,
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
        model_id=QWEN3_EMBEDDING_MODEL_ID,
        model_revision=QWEN3_EMBEDDING_PINNED_REVISION,
        dimension=8,
        normalize=True,
        query_text_contract="raw-query-v1",
        backend_factory=backend_factory,
    )


def _runtime_with_embedder(
    settings: AppSettings, embedder_factory: Any
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


def _identity_settings(*, device: str, precision: str) -> AppSettings:
    base = AppSettings()
    emb = base.indexing.embedding.model_copy(
        update={
            "implementation": "sentence_transformers",
            "device": device,
            "precision": precision,
            "model_id": QWEN3_EMBEDDING_MODEL_ID,
            "revision": QWEN3_EMBEDDING_PINNED_REVISION,
            "dimension": 1024,
            "normalize": True,
            "query_instruction": None,
            "document_instruction": None,
        }
    )
    return base.model_copy(
        update={"indexing": base.indexing.model_copy(update={"embedding": emb})}
    )


def _p4_identity_tuple(settings: AppSettings) -> dict[str, str]:
    emb_cfg = build_embedding_config_hash(settings)
    idx_cfg = build_index_config_hash(settings)
    dense_cfg = build_dense_retrieval_config_hash(settings)
    emb_id = embedding_id_from_parts(
        "p4_chunk_fixture",
        embedding_text_digest="embtxt_p4_fixture",
        emb_cfg_hash=emb_cfg,
    )
    didx = dense_index_id("p4_chunkset_fixture", idx_cfg)
    coll = dense_collection_name(didx)
    return {
        "embedding_config_hash": emb_cfg,
        "index_config_hash": idx_cfg,
        "dense_retrieval_config_hash": dense_cfg,
        "embedding_logical_id": emb_id,
        "dense_index_id": didx,
        "collection_name": coll,
    }


# ---------------------------------------------------------------------------
# A. Closed production profile vocabulary
# ---------------------------------------------------------------------------


def test_a_closed_production_profile_vocabulary() -> None:
    assert set(PROFILES.keys()) == {"cuda_fp16_v1", "cpu_onnx_fp32_v1"}
    assert PROFILES["cuda_fp16_v1"] is CUDA_FP16_V1
    assert PROFILES["cpu_onnx_fp32_v1"] is CPU_ONNX_FP32_V1
    assert len(PROFILES) == 2


# ---------------------------------------------------------------------------
# B. Product default from real repository configuration
# ---------------------------------------------------------------------------


def test_b_product_default_auto_native_from_base_yaml() -> None:
    payload = yaml.safe_load(BASE_YAML.read_text(encoding="utf-8"))
    emb = payload["indexing"]["embedding"]
    assert emb["device"] == "auto"
    assert emb["precision"] == "native"
    # Also via settings load (not test constants alone).
    settings = load_settings(yaml_paths=[BASE_YAML], environ={})
    assert settings.indexing.embedding.device == "auto"
    assert settings.indexing.embedding.precision == "native"


# ---------------------------------------------------------------------------
# C. Resolver matrix (production resolver)
# ---------------------------------------------------------------------------


def test_c_resolver_matrix() -> None:
    cuda_ok = lambda: (True, "12.8", False)
    cuda_no = lambda: (False, "12.8", False)
    cuda_probe_fail = lambda: (False, "12.8", True)

    r = resolve_qualified_embedding_profile("auto", "native", probe=cuda_ok)
    assert r.profile.profile_id == "cuda_fp16_v1"
    assert r.profile.representation_id == "torch_st_v1"
    assert r.profile.device == "cuda"
    assert r.profile.precision == "fp16"
    assert r.selection_reason == "auto_cuda_fp16"

    r = resolve_qualified_embedding_profile("auto", "native", probe=cuda_no)
    assert r.profile.profile_id == "cpu_onnx_fp32_v1"
    assert r.profile.representation_id == "onnx_fp32_v1"
    assert r.profile.device == "cpu"
    assert r.profile.precision == "fp32"
    assert r.profile.provider == "CPUExecutionProvider"
    assert r.selection_reason == "auto_cpu_onnx_fp32_cuda_unavailable"

    r = resolve_qualified_embedding_profile("auto", "native", probe=cuda_probe_fail)
    assert r.profile.profile_id == "cpu_onnx_fp32_v1"
    assert r.selection_reason == "auto_cpu_onnx_fp32_cuda_probe_failed"

    r = resolve_qualified_embedding_profile("cpu", "native", probe=cuda_ok)
    assert r.profile.profile_id == "cpu_onnx_fp32_v1"
    assert r.selection_reason == "explicit_cpu_onnx_fp32"

    r = resolve_qualified_embedding_profile("cpu", "native", probe=cuda_no)
    assert r.profile.profile_id == "cpu_onnx_fp32_v1"

    r = resolve_qualified_embedding_profile("cuda", "native", probe=cuda_ok)
    assert r.profile.profile_id == "cuda_fp16_v1"
    assert r.selection_reason == "explicit_cuda_fp16"

    r = resolve_qualified_embedding_profile("cuda", "fp16", probe=cuda_ok)
    assert r.profile.profile_id == "cuda_fp16_v1"

    with pytest.raises(EmbedderError):
        resolve_qualified_embedding_profile("cpu", "fp16", probe=cuda_ok)


# ---------------------------------------------------------------------------
# D. Fail-closed selected representation
# ---------------------------------------------------------------------------


def test_d_auto_cuda_selected_torch_absent_not_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="auto")

    def boom(_s: AppSettings) -> None:
        raise EmbedderError(
            "selected embedding representation is not READY for profile "
            "cuda_fp16_v1 (torch_st_v1)"
        )

    runtime = _runtime_with_embedder(settings, boom)
    with patch(
        "offline_rag.dense.execution_profile.probe_torch_cuda",
        return_value=(True, "12.8", False),
    ):
        runtime.start()
    assert runtime.state is RuntimeState.NOT_READY
    assert runtime.failure_reason == "startup_failed"
    assert runtime.resources is None


def test_d_cpu_selected_onnx_absent_not_ready(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def boom(_s: AppSettings) -> None:
        raise EmbedderError(
            "selected embedding representation is not READY for profile "
            "cpu_onnx_fp32_v1 (onnx_fp32_v1)"
        )

    runtime = _runtime_with_embedder(settings, boom)
    runtime.start()
    assert runtime.state is RuntimeState.NOT_READY
    assert runtime.failure_reason == "startup_failed"
    assert runtime.resources is None


# ---------------------------------------------------------------------------
# E. Identity invariance (P4-owned evidence)
# ---------------------------------------------------------------------------


def test_e_identity_invariance_p4_owned_evidence() -> None:
    variants = [
        ("cpu", "native", lambda: (True, "12.8", False)),
        ("cuda", "native", lambda: (True, "12.8", False)),
        ("cuda", "fp16", lambda: (True, "12.8", False)),
        ("auto", "native", lambda: (True, "12.8", False)),
        ("auto", "native", lambda: (False, "12.8", False)),
        ("auto", "fp16", lambda: (True, "12.8", False)),
    ]
    evidence: list[dict[str, str]] = []
    for device, precision, probe in variants:
        settings = _identity_settings(device=device, precision=precision)
        resolve_qualified_embedding_profile(device, precision, probe=probe)
        evidence.append(_p4_identity_tuple(settings))
    assert len({tuple(sorted(e.items())) for e in evidence}) == 1
    # Explicit field equality across CPU and CUDA configs.
    cpu = _p4_identity_tuple(_identity_settings(device="cpu", precision="native"))
    cuda = _p4_identity_tuple(_identity_settings(device="cuda", precision="native"))
    for key in cpu:
        assert cpu[key] == cuda[key]


# ---------------------------------------------------------------------------
# F. Product preference semantics
# ---------------------------------------------------------------------------


def test_f_preference_semantics() -> None:
    cuda_host = lambda: (True, "12.8", False)
    cpu_host = lambda: (False, None, False)

    assert (
        resolve_qualified_embedding_profile("cpu", "native", probe=cuda_host).profile.profile_id
        == "cpu_onnx_fp32_v1"
    )
    assert (
        resolve_qualified_embedding_profile("cuda", "native", probe=cuda_host).profile.profile_id
        == "cuda_fp16_v1"
    )
    assert (
        resolve_qualified_embedding_profile("auto", "native", probe=cuda_host).profile.profile_id
        == "cuda_fp16_v1"
    )
    assert (
        resolve_qualified_embedding_profile("auto", "native", probe=cpu_host).profile.profile_id
        == "cpu_onnx_fp32_v1"
    )


# ---------------------------------------------------------------------------
# G. No runtime failover
# ---------------------------------------------------------------------------


def test_g_no_runtime_failover_on_terminal_failed(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")
    constructions = {"n": 0}

    class BoomBackend:
        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            raise RuntimeError("exec boom")

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            raise RuntimeError("exec boom")

        def release(self) -> None:
            return None

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        constructions["n"] += 1

        def backend_factory() -> BoomBackend:
            return BoomBackend()

        return _qualified_runtime(
            tmp_path,
            profile=CPU_ONNX_FP32_V1,
            backend_factory=backend_factory,
        )

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    assert constructions["n"] == 1
    emb = runtime.resources.embedder  # type: ignore[union-attr]
    with pytest.raises(RuntimeError):
        emb.embed_query("hello")
    assert emb.state is EmbRuntimeState.FAILED
    assert emb.failure_kind is RuntimeFailureKind.EXECUTION
    # Still a single process-owned runtime; no alternate backend resolution.
    assert constructions["n"] == 1
    assert emb.profile_id == "cpu_onnx_fp32_v1"
    assert runtime.state is RuntimeState.READY


# ---------------------------------------------------------------------------
# H. Observability projection
# ---------------------------------------------------------------------------


def test_h_observability_projection_cpu_and_cuda(tmp_path: Path) -> None:
    cpu_rt = _qualified_runtime(
        tmp_path,
        profile=CPU_ONNX_FP32_V1,
        configured_device="cpu",
        selection_reason="explicit_cpu_onnx_fp32",
        cuda_available=True,
        torch_cuda_build="12.8",
    )
    cpu_dto = project_embedding_runtime_dto(cpu_rt)
    assert cpu_dto["profile_id"] == "cpu_onnx_fp32_v1"
    assert cpu_dto["representation_id"] == "onnx_fp32_v1"
    assert cpu_dto["active_device"] == "cpu"
    assert cpu_dto["resolved_precision"] == "fp32"
    assert cpu_dto["backend"] == "sentence_transformers_onnx"
    assert cpu_dto["provider"] == "CPUExecutionProvider"
    assert cpu_dto["selection_reason"] == "explicit_cpu_onnx_fp32"
    assert str(cpu_dto["embedding_state"]).upper() == "UNLOADED"

    cuda_rt = _qualified_runtime(
        tmp_path,
        profile=CUDA_FP16_V1,
        configured_device="cuda",
        selection_reason="explicit_cuda_fp16",
        cuda_available=True,
        torch_cuda_build="12.8",
    )
    cuda_dto = project_embedding_runtime_dto(cuda_rt)
    assert cuda_dto["profile_id"] == "cuda_fp16_v1"
    assert cuda_dto["representation_id"] == "torch_st_v1"
    assert cuda_dto["active_device"] == "cuda"
    assert cuda_dto["resolved_precision"] == "fp16"
    assert cuda_dto["backend"] == "sentence_transformers_torch"
    assert cuda_dto["provider"] is None
    assert cuda_dto["selection_reason"] == "explicit_cuda_fp16"
    assert str(cuda_dto["embedding_state"]).upper() == "UNLOADED"


def test_h_capabilities_reports_process_owned_values(tmp_path: Path) -> None:
    settings = _api_settings(tmp_path, device="cpu")

    def factory(_s: AppSettings) -> QualifiedEmbeddingRuntime:
        return _qualified_runtime(
            tmp_path,
            profile=CPU_ONNX_FP32_V1,
            configured_device="cpu",
            selection_reason="explicit_cpu_onnx_fp32",
            cuda_available=True,
            torch_cuda_build="12.8",
        )

    runtime = _runtime_with_embedder(settings, factory)
    with patch(
        "offline_rag.dense.embedding_artifacts.inspect_representation",
        return_value=_absent_inspection(tmp_path, "torch_st_v1"),
    ):
        runtime.start()
    app = create_app(runtime=runtime)
    client = TestClient(app)
    resp = client.get("/v1/capabilities")
    assert resp.status_code == 200
    emb = resp.json()["embedding"]
    assert emb["profile_id"] == "cpu_onnx_fp32_v1"
    assert emb["representation_id"] == "onnx_fp32_v1"
    assert emb["active_device"] == "cpu"
    assert emb["resolved_precision"] == "fp32"
    assert emb["selection_reason"] == "explicit_cpu_onnx_fp32"
    assert str(emb["embedding_state"]).upper() == "UNLOADED"


# ---------------------------------------------------------------------------
# Evidence-chain / CPU claim boundary (deterministic)
# ---------------------------------------------------------------------------


def test_evidence_chain_binds_embedded_identities() -> None:
    chain = json.loads(EVIDENCE_CHAIN.read_text(encoding="utf-8"))
    assert chain["disposition"] == "PASS"
    assert (
        chain["subjects"]["p3_accepted_technical_subject"]
        == "af6fa904b4309cb37a2204823347940bde70dcba"
    )
    assert (
        chain["subjects"]["accepted_onnx_fp32_tree_sha256"]
        == "3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345"
    )
    prov = chain["provisioning_evidence_consumed"][0]
    assert prov["post_state_torch_readiness"] == "ready"
    assert prov["post_state_onnx_readiness"] == "ready"
    assert prov["bundle_publication_count"] == 1
    sci = {e["kind"]: e for e in chain["scientific_evidence_consumed"]}
    assert sci["onnx_fp32_gpu_fp16_parity"]["observed_disposition"] == "PASS"
    assert sci["onnx_fp32_128_screen"]["observed_disposition"] == "PRODUCT-PRACTICAL"
    assert sci["onnx_fp32_128_screen"]["full1296_confirmed"] is False


def test_cpu_claim_boundary_preserved() -> None:
    screen = json.loads(SCREEN_EVIDENCE.read_text(encoding="utf-8"))
    parity = json.loads(PARITY_EVIDENCE.read_text(encoding="utf-8"))
    assert screen["disposition"] == "PRODUCT-PRACTICAL"
    assert screen["metrics"]["projected_full_minutes"] == pytest.approx(48.68127353649343)
    assert parity["disposition"] == "PASS"
    assert (
        parity["candidate"]["candidate_tree_sha256_after"]
        == "3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345"
    )
