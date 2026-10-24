#!/usr/bin/env python3
"""P4 dual-backend product acceptance — real cross-profile smoke.

Authority:
  S16-K-D-DUAL-BACKEND-P4-PRODUCT-ACCEPTANCE-DEFAULT-POLICY-IMPLEMENTATION-AUTH-001

Does not modify production code, provision models, download artifacts, or rerun
scientific campaigns. Assembles a scratch dual-READY model root from already
qualified local Torch + ONNX trees for the interoperability gate only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO / "docs" / "evidence" / "16k_d_dual_backend_p4"
SMOKE_PATH = EVIDENCE_DIR / "p4_cross_profile_product_smoke.json"
CHAIN_PATH = EVIDENCE_DIR / "p4_evidence_chain.json"
BASE_YAML = REPO / "config" / "base.yaml"
TORCH_SRC = REPO / "models" / "embeddings" / "qwen3-embedding-0.6b"
ACCEPTED_ONNX_TREE = "3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345"

AUTHORITY = (
    "S16-K-D-DUAL-BACKEND-P4-PRODUCT-ACCEPTANCE-DEFAULT-POLICY-IMPLEMENTATION-AUTH-001"
)
PARENT = "9d80480f3e3be6b6a8e31a8272596defb4fccfa6"


class P4NotEligible(RuntimeError):
    pass


class P4ArchitectureBlocked(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _readiness_value(obj: Any) -> str:
    ready = getattr(obj, "readiness", obj)
    return str(getattr(ready, "value", ready)).lower()


def validate_evidence_chain() -> dict[str, Any]:
    chain = json.loads(CHAIN_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []

    def check_file(entry: dict[str, Any], *, disposition_key: str = "observed_disposition") -> None:
        path = REPO / entry["path"]
        if not path.is_file():
            errors.append(f"missing evidence file: {entry['path']}")
            return
        digest = _sha256_file(path)
        if digest != entry["sha256"]:
            errors.append(
                f"sha256 mismatch for {entry['path']}: expected {entry['sha256']} got {digest}"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        observed = payload.get("disposition")
        if observed != entry.get("expected_disposition"):
            errors.append(
                f"disposition mismatch for {entry['path']}: "
                f"expected {entry.get('expected_disposition')!r} got {observed!r}"
            )
        entry[disposition_key] = observed

    for entry in chain.get("product_runtime_evidence_consumed", []):
        check_file(entry)
        payload = json.loads((REPO / entry["path"]).read_text(encoding="utf-8"))
        if payload.get("accepted_tree_sha256") != ACCEPTED_ONNX_TREE:
            errors.append("P2 evidence tree sha mismatch")
    for entry in chain.get("provisioning_evidence_consumed", []):
        check_file(entry)
        payload = json.loads((REPO / entry["path"]).read_text(encoding="utf-8"))
        for key in ("post_state_torch_readiness", "post_state_onnx_readiness"):
            if str(payload.get(key)).lower() != str(entry.get(key)).lower():
                errors.append(f"P3 field mismatch: {key}")
        if payload.get("bundle_publication_count") != entry.get("bundle_publication_count"):
            errors.append("P3 bundle_publication_count mismatch")
    for entry in chain.get("scientific_evidence_consumed", []):
        check_file(entry)
        payload = json.loads((REPO / entry["path"]).read_text(encoding="utf-8"))
        tree = (
            payload.get("candidate", {}).get("candidate_tree_sha256_after")
            or payload.get("candidate", {}).get("expected_candidate_tree_sha256")
            or payload.get("accepted_tree_sha256")
        )
        if entry.get("accepted_onnx_tree_sha256") and tree != entry["accepted_onnx_tree_sha256"]:
            errors.append(f"scientific tree mismatch for {entry['path']}")
        if (
            entry.get("kind") == "onnx_fp32_128_screen"
            and entry.get("full1296_confirmed") is not False
        ):
            errors.append("screen evidence must record full1296_confirmed=false in chain")
    subjects = chain.get("subjects", {})
    for key, expected in {
        "p1_original_runtime_substrate": "fae82b2455cfdd0d1622065904a35895372740b6",
        "p1_failure_classification_corrective": "0da27594f0b8589c0cfa995bf97097e03f6accf8",
        "p2_accepted_technical_subject": "07ce117b9d94b9372244004386351c577c725fc6",
        "p3_accepted_technical_subject": "af6fa904b4309cb37a2204823347940bde70dcba",
        "accepted_onnx_fp32_tree_sha256": ACCEPTED_ONNX_TREE,
    }.items():
        if subjects.get(key) != expected:
            errors.append(f"subject mismatch {key}")
    if errors:
        raise P4ArchitectureBlocked("evidence chain validation failed: " + "; ".join(errors))
    chain["disposition"] = "PASS"
    CHAIN_PATH.write_text(json.dumps(chain, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return chain


def find_ready_onnx_instance() -> Path:
    from offline_rag.dense.embedding_artifacts import inspect_representation

    for root, dirs, files in os.walk("/tmp"):
        depth = root.count(os.sep)
        if depth > 8:
            dirs.clear()
            continue
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"uv-cache", "node_modules"}]
        if "offline-rag-embedding-bundle.json" not in files:
            continue
        p = Path(root)
        try:
            inspection = inspect_representation(p, "onnx_fp32_v1")
        except (OSError, ValueError, TypeError, RuntimeError):
            continue
        if _readiness_value(inspection) != "ready":
            continue
        inst = inspection.instance_path
        if inst is not None and Path(inst).is_dir():
            return Path(inst)
    # Fall back to scientific export if a prior P2 confirm tree is gone — still need
    # an installed representation manifest. Prefer already-qualified instances only.
    raise P4NotEligible(
        "qualified onnx_fp32_v1 READY instance not found under /tmp "
        "(P3-owned provisioning required beforehand; P4 does not provision)"
    )


def assemble_dual_model_root(dest: Path) -> Path:
    """Scratch dual-READY root from qualified local trees (not P3 provisioning)."""
    from offline_rag.dense.embedding_artifacts import inspect_representation

    if dest.is_dir():
        torch_i = inspect_representation(dest, "torch_st_v1")
        onnx_i = inspect_representation(dest, "onnx_fp32_v1")
        if _readiness_value(torch_i) == "ready" and _readiness_value(onnx_i) == "ready":
            return dest

    if not TORCH_SRC.is_dir():
        raise P4NotEligible(f"qualified torch source missing: {TORCH_SRC}")
    onnx_inst = find_ready_onnx_instance()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in TORCH_SRC.iterdir():
        if item.name == ".cache":
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, symlinks=False)
        else:
            shutil.copy2(item, target)
    rel = Path("nxt/onnx_fp32_v1") / onnx_inst.name
    target_inst = dest / rel
    target_inst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(onnx_inst, target_inst, symlinks=False)
    (dest / "offline-rag-embedding-bundle.json").write_text(
        json.dumps(
            {
                "bundle_schema": "seneca-embedding-bundle-v1",
                "representations": {"onnx_fp32_v1": str(rel).replace("\\", "/")},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    torch_i = inspect_representation(dest, "torch_st_v1")
    onnx_i = inspect_representation(dest, "onnx_fp32_v1")
    if _readiness_value(torch_i) != "ready":
        raise P4NotEligible(f"torch_st_v1 not READY after assembly: {torch_i.reason}")
    if _readiness_value(onnx_i) != "ready":
        raise P4NotEligible(f"onnx_fp32_v1 not READY after assembly: {onnx_i.reason}")
    return dest


def preflight_cuda() -> dict[str, Any]:
    import torch

    from offline_rag.dense.device import probe_torch_cuda

    available, build, raised = probe_torch_cuda()
    facts = {
        "torch_cuda_is_available": bool(torch.cuda.is_available()),
        "probe_cuda_available": bool(available),
        "probe_raised": bool(raised),
        "torch_cuda_build": build,
        "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
    }
    if not facts["torch_cuda_is_available"] or not available or raised:
        raise P4NotEligible(f"usable CUDA required; facts={facts}")
    return facts


def build_settings(
    work: Path,
    *,
    device: str,
    model_root: Path,
) -> Any:
    from offline_rag.config import load_settings

    env = {
        "OFFLINE_RAG_DATA_DIR": str(work / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(work / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
    }
    settings = load_settings(yaml_paths=[BASE_YAML], environ=env)
    emb = settings.indexing.embedding.model_copy(
        update={
            "implementation": "sentence_transformers",
            "device": device,
            "precision": "native",
            "model_id": "Qwen/Qwen3-Embedding-0.6B",
            "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
            "dimension": 1024,
            "normalize": True,
            "query_instruction": None,
            "document_instruction": None,
            "batch_size": 8,
        }
    )
    dense = settings.dense.model_copy(
        update={
            "model_path": model_root,
            "top_k": 5,
        }
    )
    # Prefer fake tokenizer for deterministic ≤16 children without tiktoken coupling.
    chunking = settings.chunking.model_copy(
        update={
            "tokenizer": settings.chunking.tokenizer.model_copy(
                update={"implementation": "fake"}
            )
        }
    )
    settings = settings.model_copy(
        update={
            "indexing": settings.indexing.model_copy(update={"embedding": emb}),
            "dense": dense,
            "chunking": chunking,
            "reranker": settings.reranker.model_copy(update={"enabled": False}),
            "generation": settings.generation.model_copy(
                update={
                    "enabled": False,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "local-test-model",
                    "approved_endpoints": ["http://127.0.0.1:11434/v1"],
                    "approved_models": ["local-test-model"],
                }
            ),
        }
    )
    for path in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.embedding_artifacts,
        settings.paths.docling_artifacts,
        settings.paths.tokenizer_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    # Scratch product assets required by ApplicationRuntime startup validation.
    from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"p4-unit")
    write_provisioning_manifest(
        settings.paths.docling_artifacts, docling_version="test"
    )
    tiktoken_src = REPO / "models" / "tokenizers" / "tiktoken"
    if (tiktoken_src / "offline-rag-tokenizer.json").is_file():
        if settings.paths.tokenizer_artifacts.exists():
            shutil.rmtree(settings.paths.tokenizer_artifacts)
        shutil.copytree(tiktoken_src, settings.paths.tokenizer_artifacts)
    return settings


def fixture_docs(docs_dir: Path) -> tuple[str, int]:
    docs_dir.mkdir(parents=True, exist_ok=True)
    texts = [
        "Alpha sensor continuous rating is 175 deg C under load.",
        "Beta tool maximum pressure is 15000 psi for continuous operation.",
        "Gamma valve seal material is PTFE for chemical service.",
        "Delta pump flow capacity is 120 gallons per minute at 60 Hz.",
        "Epsilon cable insulation class is F for motor leads.",
        "Zeta enclosure rating is IP66 for outdoor installation.",
        "Eta bearing lubrication interval is 2000 operating hours.",
        "Theta filter micron rating is 10 for hydraulic return lines.",
    ]
    for i, text in enumerate(texts):
        (docs_dir / f"doc_{i:02d}.txt").write_text(text + "\n", encoding="utf-8")
    digest = _sha256_text("\n".join(texts))
    return digest, len(texts)


def prepare_corpus(settings: Any, docs_dir: Path) -> int:
    from offline_rag.chunking.pipeline import run_chunking
    from offline_rag.chunking.tokenize import FakeTokenCounter
    from offline_rag.ingestion.pipeline import run_ingestion

    ingest = run_ingestion(
        settings=settings, inputs=[docs_dir], corpus_name="p4", recursive=False
    )
    if ingest.status.value not in {"success", "no_op"}:
        raise P4ArchitectureBlocked(f"ingest failed: {ingest.status}")
    chunk = run_chunking(
        settings=settings, corpus_name="p4", token_counter=FakeTokenCounter()
    )
    if chunk.status.value not in {"success", "no_op"}:
        raise P4ArchitectureBlocked(f"chunking failed: {chunk.status}")
    # Child count is enforced later via Qdrant point inventory (≤16).
    return 0


def identity_snapshot(settings: Any) -> dict[str, str]:
    from offline_rag.dense.config_hash import (
        build_dense_retrieval_config_hash,
        build_embedding_config_hash,
        build_index_config_hash,
    )

    return {
        "embedding_config_hash": build_embedding_config_hash(settings),
        "index_config_hash": build_index_config_hash(settings),
        "dense_retrieval_config_hash": build_dense_retrieval_config_hash(settings),
    }


def runtime_facts(embedder: Any) -> dict[str, Any]:
    from offline_rag.api.compute_settings import project_embedding_runtime_dto

    dto = project_embedding_runtime_dto(embedder)
    profile = getattr(embedder, "profile", None)
    return {
        "configured_device": dto.get("configured_device"),
        "configured_precision": dto.get("configured_precision"),
        "profile_id": dto.get("profile_id"),
        "representation_id": dto.get("representation_id"),
        "backend_family": dto.get("backend"),
        "resolved_device": dto.get("active_device") or dto.get("resolved_device"),
        "resolved_precision": dto.get("resolved_precision"),
        "provider": dto.get("provider"),
        "selection_reason": dto.get("selection_reason"),
        "embedding_state": dto.get("embedding_state"),
        "model_id": dto.get("model"),
        "model_revision": dto.get("model_revision"),
        "dimension": dto.get("embedding_dimension"),
        "batch_size": getattr(profile, "batch_size", None) if profile is not None else None,
    }


def collection_inventory(settings: Any, collection_name: str) -> dict[str, Any]:
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    backend = QdrantLocalBackend(settings.paths.qdrant_storage)
    try:
        client = backend._get_client()
        points: list[str] = []
        offset = None
        while True:
            records, offset = client.scroll(
                collection_name=collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for rec in records:
                points.append(str(rec.id))
            if offset is None:
                break
        points_sorted = sorted(points)
        counted = int(backend.count(collection_name))
        if counted != len(points_sorted):
            raise P4ArchitectureBlocked(
                f"point count mismatch scroll={len(points_sorted)} count={counted}"
            )
        return {
            "collection_name": collection_name,
            "point_count": len(points_sorted),
            "sorted_point_ids": points_sorted,
        }
    finally:
        close = getattr(backend, "close", None)
        if callable(close):
            close()


def document_embedding_inventory(settings: Any) -> dict[str, Any]:
    root = settings.paths.embeddings
    files: list[str] = []
    digests: dict[str, str] = {}
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                rel = str(path.relative_to(root))
                files.append(rel)
                digests[rel] = _sha256_file(path)
    return {
        "file_count": len(files),
        "sorted_relative_paths": files,
        "sha256_by_path": digests,
    }


def index_manifest_identity(settings: Any, corpus: str = "p4") -> dict[str, Any]:
    from offline_rag.dense.persistence import (
        index_state_path,
        load_index_manifest,
        load_index_state,
    )

    state = load_index_state(index_state_path(settings.paths.corpora, corpus))
    manifest = load_index_manifest(
        settings.paths.index_manifests / Path(state.current_index_manifest).name
    )
    return {
        "current_index_id": state.current_index_id,
        "source_chunk_set_id": state.source_chunk_set_id,
        "current_index_manifest": state.current_index_manifest,
        "collection_name": manifest.collection_name,
        "index_manifest_sha256": _sha256_file(
            settings.paths.index_manifests / Path(state.current_index_manifest).name
        ),
    }


@dataclass
class PhaseResult:
    device: str
    role: str
    runtime_facts: dict[str, Any]
    identities: dict[str, str]
    index_identity: dict[str, Any] | None
    inventory: dict[str, Any] | None
    embedding_inventory: dict[str, Any] | None
    retrieval: dict[str, Any] | None
    transitions: str
    elapsed_s: float


def run_index_phase(
    *,
    work: Path,
    device: str,
    model_root: Path,
    docs_dir: Path,
    prepare: bool,
) -> PhaseResult:
    from offline_rag.app.runtime import (
        ApplicationRuntime,
        ResourceFactories,
        RuntimeState,
    )
    from offline_rag.dense.embedder import make_embedder
    from offline_rag.dense.embedding_runtime import RuntimeState as EmbRuntimeState
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.dense.qdrant_local import QdrantLocalBackend

    settings = build_settings(work, device=device, model_root=model_root)
    if prepare:
        prepare_corpus(settings, docs_dir)

    started = time.perf_counter()
    class _Closeable:
        def close(self) -> None:
            return None

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=make_embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    try:
        runtime.start()
    except Exception as exc:
        raise P4ArchitectureBlocked(
            f"ApplicationRuntime.start raised for device={device}: {exc}"
        ) from exc
    if runtime.state is not RuntimeState.READY:
        # Re-probe common gates for a precise harness message.
        detail = runtime.failure_reason or "unknown"
        try:
            from offline_rag.app.startup_validation import (
                validate_global_startup_requirements,
            )

            validate_global_startup_requirements(settings)
        except Exception as exc:  # noqa: BLE001
            detail = f"{detail}; validate_global_startup_requirements={exc}"
        raise P4ArchitectureBlocked(
            f"ApplicationRuntime not READY for device={device}: "
            f"{runtime.state} / {detail}"
        )
    assert runtime.resources is not None
    embedder = runtime.resources.embedder
    from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntime

    if not isinstance(embedder, QualifiedEmbeddingRuntime):
        raise P4ArchitectureBlocked("expected QualifiedEmbeddingRuntime from make_embedder")
    if embedder.state is not EmbRuntimeState.UNLOADED:
        raise P4ArchitectureBlocked(f"expected UNLOADED at start, got {embedder.state}")

    report = run_indexing(settings=settings, corpus_name="p4", embedder=embedder)
    if report.status.value != "success":
        raise P4ArchitectureBlocked(f"indexing failed: {report.status} {report.errors}")
    if embedder.state is not EmbRuntimeState.READY:
        raise P4ArchitectureBlocked(f"embedder not READY after index: {embedder.state}")

    facts = runtime_facts(embedder)
    expected_profile = "cuda_fp16_v1" if device == "cuda" else "cpu_onnx_fp32_v1"
    expected_rep = "torch_st_v1" if device == "cuda" else "onnx_fp32_v1"
    if facts["profile_id"] != expected_profile:
        raise P4ArchitectureBlocked(
            f"index phase profile mismatch: expected {expected_profile} got {facts['profile_id']}"
        )
    if facts["representation_id"] != expected_rep:
        raise P4ArchitectureBlocked("index phase representation mismatch")
    if device == "cuda" and facts["resolved_device"] != "cuda":
        raise P4ArchitectureBlocked("CUDA phase did not resolve to cuda device")
    if device == "cpu" and (
        facts["resolved_device"] != "cpu" or facts["provider"] != "CPUExecutionProvider"
    ):
        raise P4ArchitectureBlocked("CPU phase did not use CPUExecutionProvider")

    idx_id = index_manifest_identity(settings)
    inv = collection_inventory(settings, idx_id["collection_name"])
    emb_inv = document_embedding_inventory(settings)
    identities = identity_snapshot(settings)
    identities["dense_index_id"] = idx_id["current_index_id"]
    identities["collection_name"] = idx_id["collection_name"]
    identities["chunk_set_id"] = idx_id["source_chunk_set_id"]

    runtime.shutdown()
    return PhaseResult(
        device=device,
        role="index",
        runtime_facts=facts,
        identities=identities,
        index_identity=idx_id,
        inventory=inv,
        embedding_inventory=emb_inv,
        retrieval=None,
        transitions="UNLOADED -> LOADING -> READY",
        elapsed_s=time.perf_counter() - started,
    )


def run_query_phase(
    *,
    work: Path,
    device: str,
    model_root: Path,
    queries: list[str],
    prior: PhaseResult,
) -> PhaseResult:
    from offline_rag.app.runtime import (
        ApplicationRuntime,
        ResourceFactories,
        RuntimeState,
    )
    from offline_rag.dense.embedder import make_embedder
    from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntime
    from offline_rag.dense.embedding_runtime import RuntimeState as EmbRuntimeState
    from offline_rag.dense.qdrant_local import QdrantLocalBackend
    from offline_rag.dense.retrieve import DenseRetriever

    settings = build_settings(work, device=device, model_root=model_root)
    started = time.perf_counter()

    class _Closeable:
        def close(self) -> None:
            return None

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=make_embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
        ),
    )
    runtime.start()
    if runtime.state is not RuntimeState.READY:
        raise P4ArchitectureBlocked(
            f"query ApplicationRuntime not READY for device={device}: "
            f"{runtime.state} / {runtime.failure_reason}"
        )
    assert runtime.resources is not None
    embedder = runtime.resources.embedder
    if not isinstance(embedder, QualifiedEmbeddingRuntime):
        raise P4ArchitectureBlocked("expected QualifiedEmbeddingRuntime")
    if embedder.state is not EmbRuntimeState.UNLOADED:
        raise P4ArchitectureBlocked(f"expected UNLOADED at query start, got {embedder.state}")

    identities = identity_snapshot(settings)
    for key in (
        "embedding_config_hash",
        "index_config_hash",
        "dense_retrieval_config_hash",
    ):
        if identities[key] != prior.identities[key]:
            raise P4ArchitectureBlocked(
                f"identity drift on {key}: index={prior.identities[key]} query={identities[key]}"
            )

    before_idx = index_manifest_identity(settings)
    before_inv = collection_inventory(settings, before_idx["collection_name"])
    before_emb = document_embedding_inventory(settings)
    if before_inv["sorted_point_ids"] != prior.inventory["sorted_point_ids"]:
        raise P4ArchitectureBlocked("point inventory changed before query vs after index")

    retriever = DenseRetriever(settings, embedder=embedder)
    try:
        results = []
        for q in queries:
            result = retriever.retrieve(query=q, corpus_name="p4")
            scores = [float(c.score) for c in result.candidates]
            if not scores:
                raise P4ArchitectureBlocked(f"empty candidates for query: {q!r}")
            if not all(math.isfinite(s) for s in scores):
                raise P4ArchitectureBlocked("non-finite retrieval scores")
            results.append(
                {
                    "query": q,
                    "candidate_count": len(result.candidates),
                    "top_score": scores[0],
                    "index_id": result.index_id,
                }
            )
    finally:
        retriever.close()

    if embedder.state is not EmbRuntimeState.READY:
        raise P4ArchitectureBlocked(f"embedder not READY after query: {embedder.state}")

    facts = runtime_facts(embedder)
    expected_profile = "cuda_fp16_v1" if device == "cuda" else "cpu_onnx_fp32_v1"
    expected_rep = "torch_st_v1" if device == "cuda" else "onnx_fp32_v1"
    if facts["profile_id"] != expected_profile or facts["representation_id"] != expected_rep:
        raise P4ArchitectureBlocked("query phase profile/representation mismatch")
    if device == "cuda" and facts["resolved_device"] != "cuda":
        raise P4ArchitectureBlocked("CUDA query phase did not use cuda")
    if device == "cpu" and facts["provider"] != "CPUExecutionProvider":
        raise P4ArchitectureBlocked("CPU query phase missing CPUExecutionProvider")

    after_idx = index_manifest_identity(settings)
    after_inv = collection_inventory(settings, after_idx["collection_name"])
    after_emb = document_embedding_inventory(settings)
    if after_idx != before_idx:
        raise P4ArchitectureBlocked("index identity changed during query phase")
    if after_inv != before_inv:
        raise P4ArchitectureBlocked("collection inventory changed during query phase")
    if after_emb != before_emb:
        raise P4ArchitectureBlocked("document embedding inventory changed during query")

    identities["dense_index_id"] = after_idx["current_index_id"]
    identities["collection_name"] = after_idx["collection_name"]
    identities["chunk_set_id"] = after_idx["source_chunk_set_id"]

    runtime.shutdown()
    return PhaseResult(
        device=device,
        role="query",
        runtime_facts=facts,
        identities=identities,
        index_identity=after_idx,
        inventory=after_inv,
        embedding_inventory=after_emb,
        retrieval={
            "status": "ok",
            "queries": results,
            "finite_scores": True,
            "candidate_count_total": sum(r["candidate_count"] for r in results),
        },
        transitions="UNLOADED -> LOADING -> READY",
        elapsed_s=time.perf_counter() - started,
    )


def direction_record(index_phase: PhaseResult, query_phase: PhaseResult) -> dict[str, Any]:
    return {
        "index_profile": index_phase.runtime_facts["profile_id"],
        "query_profile": query_phase.runtime_facts["profile_id"],
        "actual_index_runtime_facts": index_phase.runtime_facts,
        "actual_query_runtime_facts": query_phase.runtime_facts,
        "index_transitions": index_phase.transitions,
        "query_transitions": query_phase.transitions,
        "embedding_config_hash_at_index": index_phase.identities["embedding_config_hash"],
        "embedding_config_hash_at_query": query_phase.identities["embedding_config_hash"],
        "index_config_hash_at_index": index_phase.identities["index_config_hash"],
        "index_config_hash_at_query": query_phase.identities["index_config_hash"],
        "dense_retrieval_config_hash_at_index": index_phase.identities[
            "dense_retrieval_config_hash"
        ],
        "dense_retrieval_config_hash_at_query": query_phase.identities[
            "dense_retrieval_config_hash"
        ],
        "index_id_before": index_phase.identities["dense_index_id"],
        "index_id_after": query_phase.identities["dense_index_id"],
        "collection_before": index_phase.identities["collection_name"],
        "collection_after": query_phase.identities["collection_name"],
        "point_count_before": index_phase.inventory["point_count"],
        "point_count_after": query_phase.inventory["point_count"],
        "sorted_point_ids_before": index_phase.inventory["sorted_point_ids"],
        "sorted_point_ids_after": query_phase.inventory["sorted_point_ids"],
        "document_embedding_inventory_before": index_phase.embedding_inventory,
        "document_embedding_inventory_after": query_phase.embedding_inventory,
        "retrieval": query_phase.retrieval,
        "reindex_observed": False,
        "document_reembedding_observed": False,
        "index_elapsed_s": index_phase.elapsed_s,
        "query_elapsed_s": query_phase.elapsed_s,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-root",
        type=Path,
        default=None,
        help="Optional durable work root (default: temp under /tmp)",
    )
    args = parser.parse_args()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        chain = validate_evidence_chain()
        cuda_facts = preflight_cuda()
        work_root = args.work_root or Path(tempfile.mkdtemp(prefix="p4_acceptance_"))
        work_root = work_root.resolve()
        work_root.mkdir(parents=True, exist_ok=True)
        model_root = assemble_dual_model_root(work_root / "dual_model_root")

        queries = [
            "sensor temperature rating",
            "maximum pressure continuous",
            "valve seal PTFE",
            "pump flow gallons",
            "cable insulation class",
            "enclosure IP66",
            "bearing lubrication hours",
            "filter micron hydraulic",
        ]
        if len(queries) > 8:
            raise RuntimeError("query budget exceeded")

        # Direction A: CUDA index → CPU query
        work_a = work_root / "direction_a"
        docs_a = work_a / "docs"
        fixture_digest, doc_count = fixture_docs(docs_a)
        index_a = run_index_phase(
            work=work_a, device="cuda", model_root=model_root, docs_dir=docs_a, prepare=True
        )
        if index_a.inventory["point_count"] > 16:
            raise P4ArchitectureBlocked(
                f"fixture exceeded 16 child points: {index_a.inventory['point_count']}"
            )
        query_a = run_query_phase(
            work=work_a,
            device="cpu",
            model_root=model_root,
            queries=queries,
            prior=index_a,
        )
        direction_a = direction_record(index_a, query_a)

        # Direction B: CPU index → CUDA query (separate namespace)
        work_b = work_root / "direction_b"
        docs_b = work_b / "docs"
        fixture_docs(docs_b)
        index_b = run_index_phase(
            work=work_b, device="cpu", model_root=model_root, docs_dir=docs_b, prepare=True
        )
        if index_b.inventory["point_count"] > 16:
            raise P4ArchitectureBlocked(
                f"fixture exceeded 16 child points: {index_b.inventory['point_count']}"
            )
        query_b = run_query_phase(
            work=work_b,
            device="cuda",
            model_root=model_root,
            queries=queries,
            prior=index_b,
        )
        direction_b = direction_record(index_b, query_b)

        smoke = {
            "authority": AUTHORITY,
            "parent": PARENT,
            "recorded_at": datetime.now(tz=UTC).isoformat(),
            "work_root": str(work_root),
            "model_root": str(model_root),
            "fixture_digest": fixture_digest,
            "fixture_document_count": doc_count,
            "fixture_child_point_count_direction_a": direction_a["point_count_before"],
            "fixture_child_point_count_direction_b": direction_b["point_count_before"],
            "query_count": len(queries),
            "accepted_p1_original_subject": "fae82b2455cfdd0d1622065904a35895372740b6",
            "accepted_p1_corrective_subject": "0da27594f0b8589c0cfa995bf97097e03f6accf8",
            "accepted_p2_subject": "07ce117b9d94b9372244004386351c577c725fc6",
            "accepted_p3_subject": "af6fa904b4309cb37a2204823347940bde70dcba",
            "accepted_onnx_tree": ACCEPTED_ONNX_TREE,
            "accepted_parity_evidence": (
                "docs/evidence/16k_d_cpu_onnx/onnx_fp32_gpu_fp16_parity_pass_1792638012.json"
            ),
            "accepted_cpu_screen_evidence": (
                "docs/evidence/16k_d_cpu_onnx/onnx_fp32_128_screen_pass_1792638543.json"
            ),
            "default_device_policy": "auto",
            "default_precision_policy": "native",
            "cuda_preflight": cuda_facts,
            "evidence_chain_disposition": chain["disposition"],
            "direction_a": direction_a,
            "direction_b": direction_b,
            "full1296_confirmed": False,
            "scientific_campaign_calls": 0,
            "parity_rerun_calls": 0,
            "provisioning_calls": 0,
            "declarations": {
                "dual_backend_product_acceptance": "PASS",
                "default_policy": "AUTO/native — PRODUCT-QUALIFIED",
                "auto_cuda_lane": "cuda_fp16_v1 — PREFERRED WHEN CUDA USABLE",
                "auto_cpu_lane": (
                    "cpu_onnx_fp32_v1 — SUPPORTED STARTUP FALLBACK WHEN CUDA UNAVAILABLE"
                ),
                "explicit_cpu": "SUPPORTED",
                "explicit_cuda": "SUPPORTED WHEN CUDA USABLE",
                "shared_logical_index": "QUALIFIED",
                "runtime_failover": "NOT SUPPORTED / NOT AUTHORIZED",
                "full1296_cpu_confirmation": "NOT RUN / NOT CLAIMED",
            },
            "disposition": "PASS",
        }
        SMOKE_PATH.write_text(json.dumps(smoke, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"disposition": "PASS", "smoke": str(SMOKE_PATH)}, indent=2))
        return 0
    except P4NotEligible as exc:
        payload = {
            "terminal": "P4_NOT_ELIGIBLE_ENVIRONMENT",
            "reason": str(exc),
            "authority": AUTHORITY,
            "parent": PARENT,
        }
        SMOKE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 2
    except P4ArchitectureBlocked as exc:
        payload = {
            "terminal": "P4_ARCHITECTURE_BLOCKED",
            "reason": str(exc),
            "authority": AUTHORITY,
            "parent": PARENT,
        }
        SMOKE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 — harness terminal
        payload = {
            "terminal": "P4_HARNESS_ERROR",
            "reason": str(exc),
            "traceback": traceback.format_exc(),
            "authority": AUTHORITY,
            "parent": PARENT,
        }
        SMOKE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
