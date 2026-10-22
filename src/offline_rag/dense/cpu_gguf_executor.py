"""CPU-GGUF-01 llama.cpp scientific executor (callable only when unlocked).

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001

Implements Stage-0 llama-server smoke, 128-child screen timing, and
d2-retrieval-parity-v1 scaffolding against CUDA FP16 reference.

Must not be invoked while ``EXECUTION_AUTHORIZED`` is False.
Does not download GGUF or llama-server; requires pre-existing pinned locals.

F001: screen/parity require expected_llama_server_sha256 before launch.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from offline_rag.core.ids import (
    PLAIN_EMBEDDING_TEXT_CONTRACT,
    RAW_QUERY_V1,
    embedding_text_hash,
)
from offline_rag.dense.cpu_gguf_client import LlamaCppEmbeddingClient
from offline_rag.dense.cpu_gguf_feasibility import (
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_DIMENSION,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    EXPERIMENT_ID,
    FROZEN_BATCH_SIZE,
    FROZEN_N_GPU_LAYERS,
    FROZEN_NORMALIZE,
    FROZEN_POOLING,
    FROZEN_QUANT,
    FROZEN_THREADS,
    FROZEN_THREADS_BATCH,
    IMPLEMENTATION_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    PARITY_CONTRACT_ID,
    PARITY_THRESHOLDS,
    parity_thresholds_pass,
    project_full_minutes,
    refuse_hub_substitution,
)
from offline_rag.dense.cpu_gguf_harness import (
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
)
from offline_rag.dense.cpu_gguf_server import (
    LlamaServerProcess,
    require_llama_server_sha256,
)
from offline_rag.dense.text import PlainEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk
from offline_rag.retrieval.ranking_text import ranking_inputs_for_chunk


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _finite(vec: Sequence[float]) -> bool:
    return all(math.isfinite(float(x)) for x in vec)


def _l2(vec: Sequence[float]) -> float:
    return math.sqrt(sum(float(x) * float(x) for x in vec))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"dimension mismatch {len(a)} != {len(b)}")
    dot = sum(float(x) * float(y) for x, y in zip(a, b, strict=True))
    na = _l2(list(a))
    nb = _l2(list(b))
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return float(dot / (na * nb))


def _maybe_write_evidence(
    payload: dict[str, Any],
    *,
    evidence_dir: Path | None,
    stem: str,
) -> dict[str, Any]:
    if evidence_dir is None:
        return payload
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = evidence_dir / f"{stem}_{ts}.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    out = dict(payload)
    out["evidence_path"] = str(path)
    return out


def _environment_fingerprint() -> dict[str, Any]:
    from offline_rag.dense.cpu_gguf_harness import environment_fingerprint

    return environment_fingerprint()


def capture_cpu_host_runtime_facts() -> dict[str, Any]:
    facts: dict[str, Any] = {"captured_at": _utc_now()}
    try:
        import subprocess

        completed = subprocess.run(
            ["lscpu"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        for line in (completed.stdout or "").splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            if key in {"Model name", "Architecture", "CPU(s)", "Vendor ID"}:
                facts[key] = val.strip()
    except Exception as exc:  # noqa: BLE001
        facts["lscpu_error"] = f"{type(exc).__name__}: {exc}"
    return facts


def load_children_by_id(
    *,
    repo_root: Path,
    chunk_ids: Sequence[str] | None = None,
) -> dict[str, Chunk]:
    """Load child chunks keyed by id; verifies manifest identity via harness."""
    from offline_rag.dense.cpu_gguf_harness import load_chunk_ids_from_manifest

    all_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    wanted = set(chunk_ids) if chunk_ids is not None else set(all_ids)

    manifest_path = (
        repo_root / "data" / "chunk-manifests" / f"{EXPECTED_CHUNK_SET_ID}.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    out: dict[str, Chunk] = {}
    for doc in payload["documents"]:
        rel = doc["chunk_artifact"]
        path = repo_root / "data" / rel
        if not path.is_file():
            path = repo_root / rel
        art = json.loads(path.read_text(encoding="utf-8"))
        for child in art["children"]:
            cid = str(child["chunk_id"])
            if cid in wanted:
                out[cid] = Chunk.model_validate(child)
    missing = wanted - set(out)
    if missing:
        raise ValueError(f"missing {len(missing)} chunk ids from artifacts")
    return out


def document_embedding_texts(chunks: Sequence[Chunk]) -> list[tuple[str, str, str]]:
    """plain-v1: embedding text is exact chunk.text."""
    builder = PlainEmbeddingTextBuilder()
    rows: list[tuple[str, str, str]] = []
    for chunk in chunks:
        inputs = ranking_inputs_for_chunk(
            chunk_text=chunk.text,
            section_path=list(chunk.section_path or []),
            document_title=None,
        )
        text = builder.build(inputs)
        if text != chunk.text:
            raise RuntimeError("plain-v1 contract violation: text != chunk.text")
        if builder.contract_version != PLAIN_EMBEDDING_TEXT_CONTRACT:
            raise RuntimeError("unexpected embedding text contract")
        rows.append((chunk.chunk_id, embedding_text_hash(text), text))
    return rows


def resolve_gguf_query_contract() -> str:
    """CPU-GGUF-01 freezes raw-query-v1 (no ST prompt injection into llama.cpp)."""
    return RAW_QUERY_V1


def smoke_encode(
    client: LlamaCppEmbeddingClient,
    *,
    query_text_contract: str,
) -> dict[str, Any]:
    if query_text_contract != RAW_QUERY_V1:
        raise ValueError(
            f"CPU-GGUF-01 requires {RAW_QUERY_V1}; got {query_text_contract}"
        )
    doc_vecs = client.embed_documents(["cpu-gguf stage0 document smoke"])
    q_vec = client.embed_query("cpu-gguf stage0 query smoke")
    issues: list[str] = []
    if len(doc_vecs) != 1 or len(doc_vecs[0]) != EXPECTED_DIMENSION:
        issues.append("document_dim")
    if len(q_vec) != EXPECTED_DIMENSION:
        issues.append("query_dim")
    if not _finite(doc_vecs[0]):
        issues.append("document_non_finite")
    if not _finite(q_vec):
        issues.append("query_non_finite")
    if FROZEN_NORMALIZE:
        dn = _l2(doc_vecs[0])
        qn = _l2(q_vec)
        if not (0.99 <= dn <= 1.01):
            issues.append(f"document_norm={dn}")
        if not (0.99 <= qn <= 1.01):
            issues.append(f"query_norm={qn}")
    return {
        "ok": not issues,
        "issues": issues,
        "document_dim": len(doc_vecs[0]) if doc_vecs else None,
        "query_dim": len(q_vec),
        "query_text_contract": query_text_contract,
        "pooling": FROZEN_POOLING,
        "normalize": FROZEN_NORMALIZE,
    }


def execute_stage0_compat(
    *,
    gguf_path: Path,
    llama_server_path: Path,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    refuse_hub_substitution(local_gguf_exists=gguf_path.is_file(), allow_download=False)
    log_dir = None
    if evidence_dir is not None:
        log_dir = Path(evidence_dir) / "llama_server_logs" / "stage0_compat"
    server = LlamaServerProcess(
        binary_path=llama_server_path,
        gguf_path=gguf_path,
        threads=FROZEN_THREADS,
        threads_batch=FROZEN_THREADS_BATCH,
        log_dir=log_dir,
    )
    launch = None
    smoke: dict[str, Any] | None = None
    stop_code: int | None = None
    ok = False
    error: str | None = None
    accepted_sha: str | None = None
    try:
        launch = server.start()
        accepted_sha = launch.binary.binary_sha256
        if launch.n_gpu_layers != FROZEN_N_GPU_LAYERS:
            raise RuntimeError(
                f"n_gpu_layers {launch.n_gpu_layers} != {FROZEN_N_GPU_LAYERS}"
            )
        if launch.pooling != FROZEN_POOLING:
            raise RuntimeError(f"pooling {launch.pooling!r} != {FROZEN_POOLING!r}")
        query_contract = resolve_gguf_query_contract()
        with LlamaCppEmbeddingClient(base_url=server.base_url) as client:
            smoke = smoke_encode(client, query_text_contract=query_contract)
        ok = bool(smoke and smoke.get("ok"))
        if not ok:
            accepted_sha = None
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        ok = False
        accepted_sha = None
    finally:
        stop_code = server.stop()

    # On success, accepted_sha is the runtime pin for screen/parity authorities.
    if ok and launch is not None:
        accepted_sha = launch.binary.binary_sha256

    payload: dict[str, Any] = {
        "status": "ok" if ok else "failed",
        "stage_id": "stage0_compat",
        "ok": ok,
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "quant": FROZEN_QUANT,
        # F001: prominent Stage-0 runtime pin for subsequent authorities.
        "accepted_llama_server_sha256": accepted_sha,
        "accepted_llama_server_identity": (
            {
                "absolute_path": launch.binary.absolute_path,
                "binary_sha256": launch.binary.binary_sha256,
                "version_output": launch.binary.version_output,
                "version_exit_code": launch.binary.version_exit_code,
                "cpu_architecture": launch.binary.cpu_architecture,
            }
            if ok and launch is not None
            else None
        ),
        "launch": server.launch_record_dict(),
        "server_logs": server.log_diagnostics(),
        "smoke": smoke,
        "server_stop_code": stop_code,
        "error": error,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "repo_root": str(repo_root) if repo_root else None,
        "note": (
            "Stage-0 only: artifact SHA + llama-server identity + synthetic smoke. "
            "accepted_llama_server_sha256 is the runtime pin for screen/parity. "
            "No corpus screen."
        ),
    }
    return _maybe_write_evidence(payload, evidence_dir=evidence_dir, stem="stage0_compat")


def execute_screen(
    *,
    gguf_path: Path,
    llama_server_path: Path,
    expected_llama_server_sha256: str,
    repo_root: Path,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """128-child screen; model load is outside the timed encode region."""
    refuse_hub_substitution(local_gguf_exists=gguf_path.is_file(), allow_download=False)
    # F001: pin before any corpus load / server launch.
    require_llama_server_sha256(
        Path(llama_server_path),
        expected_llama_server_sha256=expected_llama_server_sha256,
    )
    children_by_id = load_children_by_id(repo_root=repo_root)
    selected_ids = select_screen_chunk_ids(sorted(children_by_id.keys()))
    digest = sha256_text("\n".join(selected_ids))
    if digest != EXPECTED_SCREEN_CHUNK_IDS_DIGEST:
        raise ValueError(
            f"screen digest mismatch: observed={digest} "
            f"expected={EXPECTED_SCREEN_CHUNK_IDS_DIGEST}"
        )
    chunks = [children_by_id[cid] for cid in selected_ids]
    rows = document_embedding_texts(chunks)
    texts = [t for _, _, t in rows]
    if len(texts) != 128:
        raise RuntimeError(f"expected 128 screen texts, got {len(texts)}")
    expected_requests = len(texts) // FROZEN_BATCH_SIZE
    if len(texts) % FROZEN_BATCH_SIZE != 0:
        raise RuntimeError("screen size must be divisible by frozen batch size")

    log_dir = None
    if evidence_dir is not None:
        log_dir = Path(evidence_dir) / "llama_server_logs" / "screen_q8_0"
    server = LlamaServerProcess(
        binary_path=llama_server_path,
        gguf_path=gguf_path,
        threads=FROZEN_THREADS,
        threads_batch=FROZEN_THREADS_BATCH,
        log_dir=log_dir,
        expected_llama_server_sha256=expected_llama_server_sha256,
    )
    encode_s: float | None = None
    vectors: list[list[float]] = []
    cpu_before: dict[str, Any] = {}
    cpu_after: dict[str, Any] = {}
    stop_code: int | None = None
    try:
        launch = server.start()
        if launch.n_gpu_layers != 0:
            raise RuntimeError("fail-closed: n_gpu_layers must be 0 for CPU screen")
        with LlamaCppEmbeddingClient(
            base_url=server.base_url,
            request_batch_size=FROZEN_BATCH_SIZE,
        ) as client:
            cpu_before = capture_cpu_host_runtime_facts()
            started = time.perf_counter()
            vectors = client.embed_documents(texts)
            encode_s = time.perf_counter() - started
            cpu_after = capture_cpu_host_runtime_facts()
    finally:
        stop_code = server.stop()

    if encode_s is None:
        raise RuntimeError("screen encode did not complete")
    if len(vectors) != len(texts):
        raise RuntimeError("screen encode length mismatch")
    for vec in vectors:
        if len(vec) != EXPECTED_DIMENSION or not _finite(vec):
            raise RuntimeError("screen vector validation failed")

    chunks_per_sec = float(len(texts)) / encode_s if encode_s > 0 else float("inf")
    projected = project_full_minutes(chunks_per_sec)
    payload = {
        "status": "ok",
        "stage_id": "screen_q8_0",
        "ok": True,
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "quant": FROZEN_QUANT,
        "pooling": FROZEN_POOLING,
        "n_gpu_layers": FROZEN_N_GPU_LAYERS,
        "threads": FROZEN_THREADS,
        "threads_batch": FROZEN_THREADS_BATCH,
        "batch_size": FROZEN_BATCH_SIZE,
        "application_request_count": expected_requests,
        "screen_child_count": len(texts),
        "screen_chunk_ids_digest": digest,
        "expected_llama_server_sha256": str(expected_llama_server_sha256).lower(),
        "encode_wall_s": encode_s,
        "chunks_per_sec": chunks_per_sec,
        "projected_full_minutes": projected,
        "full_wall_minutes": None,
        "dimension": EXPECTED_DIMENSION,
        "normalize": FROZEN_NORMALIZE,
        "query_text_contract": resolve_gguf_query_contract(),
        "launch": server.launch_record_dict(),
        "server_logs": server.log_diagnostics(),
        "server_stop_code": stop_code,
        "cpu_host_runtime_before": cpu_before,
        "cpu_host_runtime_after": cpu_after,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
        "note": "projected_full_minutes is screening only; not confirmation evidence",
    }
    return _maybe_write_evidence(payload, evidence_dir=evidence_dir, stem="screen_q8_0")


def execute_parity(
    *,
    gguf_path: Path,
    llama_server_path: Path,
    expected_llama_server_sha256: str,
    repo_root: Path,
    evidence_dir: Path | None = None,
    reference_embedder: Any | None = None,
    reference_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """d2-retrieval-parity-v1 scaffolding against CUDA FP16 reference."""
    refuse_hub_substitution(local_gguf_exists=gguf_path.is_file(), allow_download=False)
    require_llama_server_sha256(
        Path(llama_server_path),
        expected_llama_server_sha256=expected_llama_server_sha256,
    )
    children_by_id = load_children_by_id(repo_root=repo_root)
    all_ids = sorted(children_by_id.keys())
    doc_ids, query_ids = select_parity_populations(all_ids)
    docs = [children_by_id[cid] for cid in doc_ids]
    queries = [children_by_id[cid] for cid in query_ids]
    doc_rows = document_embedding_texts(docs)
    query_contract = resolve_gguf_query_contract()

    if reference_embedder is None:
        from offline_rag.config import load_settings
        from offline_rag.dense.embedder import (
            make_embedder,
            observe_embedder_execution_facts,
        )

        environ = dict(os.environ)
        environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
        environ["OFFLINE_RAG_EMBEDDING_PRECISION"] = "fp16"
        environ["OFFLINE_RAG_EMBEDDING_BATCH_SIZE"] = str(FROZEN_BATCH_SIZE)
        settings = load_settings(environ=environ)
        reference_embedder = make_embedder(settings)
        load = getattr(reference_embedder, "_load", None)
        if callable(load):
            load()
        reference_facts = observe_embedder_execution_facts(reference_embedder)
    elif reference_facts is None:
        reference_facts = {}

    ref_docs = {
        cid: list(vec)
        for (cid, _, _), vec in zip(
            doc_rows,
            reference_embedder.embed_documents([t for _, _, t in doc_rows]),
            strict=True,
        )
    }
    ref_queries = {
        chunk.chunk_id: list(reference_embedder.embed_query(chunk.text))
        for chunk in queries
    }

    log_dir = None
    if evidence_dir is not None:
        log_dir = Path(evidence_dir) / "llama_server_logs" / "parity_q8_0"
    server = LlamaServerProcess(
        binary_path=llama_server_path,
        gguf_path=gguf_path,
        threads=FROZEN_THREADS,
        threads_batch=FROZEN_THREADS_BATCH,
        log_dir=log_dir,
        expected_llama_server_sha256=expected_llama_server_sha256,
    )
    cand_docs: dict[str, list[float]] = {}
    cand_queries: dict[str, list[float]] = {}
    stop_code: int | None = None
    try:
        server.start()
        with LlamaCppEmbeddingClient(
            base_url=server.base_url,
            request_batch_size=FROZEN_BATCH_SIZE,
        ) as client:
            for (cid, _, text), vec in zip(
                doc_rows,
                client.embed_documents([t for _, _, t in doc_rows]),
                strict=True,
            ):
                cand_docs[cid] = vec
            for chunk in queries:
                if query_contract != RAW_QUERY_V1:
                    raise ValueError(f"unexpected query contract {query_contract}")
                cand_queries[chunk.chunk_id] = client.embed_query(chunk.text)
    finally:
        stop_code = server.stop()

    doc_cos = [
        _cosine(ref_docs[cid], cand_docs[cid]) for cid in doc_ids if cid in ref_docs
    ]
    query_cos = [
        _cosine(ref_queries[cid], cand_queries[cid])
        for cid in query_ids
        if cid in ref_queries
    ]

    def _topk(
        q: list[float], docs_map: dict[str, list[float]], order: list[str], k: int = 10
    ) -> list[str]:
        scored = [(_cosine(q, docs_map[cid]), cid) for cid in order]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [cid for _, cid in scored[:k]]

    top1 = 0
    overlaps: list[float] = []
    for qid in query_ids:
        ref_top = _topk(ref_queries[qid], ref_docs, doc_ids)
        cand_top = _topk(cand_queries[qid], cand_docs, doc_ids)
        if ref_top and cand_top and ref_top[0] == cand_top[0]:
            top1 += 1
        overlaps.append(len(set(ref_top) & set(cand_top)) / 10.0)

    metrics = {
        "median_document_vector_cosine": float(statistics.median(doc_cos))
        if doc_cos
        else 0.0,
        "min_document_vector_cosine": float(min(doc_cos)) if doc_cos else 0.0,
        "median_query_vector_cosine": float(statistics.median(query_cos))
        if query_cos
        else 0.0,
        "min_query_vector_cosine": float(min(query_cos)) if query_cos else 0.0,
        "top1_agreement": top1,
        "mean_top10_set_overlap": float(statistics.mean(overlaps)) if overlaps else 0.0,
        "min_top10_set_overlap": float(min(overlaps)) if overlaps else 0.0,
    }
    ok = parity_thresholds_pass(metrics)
    payload = {
        "status": "ok" if ok else "failed",
        "stage_id": "parity_q8_0",
        "ok": ok,
        "parity_ok": ok,
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "parity_contract": PARITY_CONTRACT_ID,
        "parity_thresholds": PARITY_THRESHOLDS,
        "metrics": metrics,
        "quant": FROZEN_QUANT,
        "pooling": FROZEN_POOLING,
        "expected_llama_server_sha256": str(expected_llama_server_sha256).lower(),
        "query_text_contract": query_contract,
        "reference_facts": reference_facts,
        "document_count": len(doc_ids),
        "query_count": len(query_ids),
        "launch": server.launch_record_dict(),
        "server_logs": server.log_diagnostics(),
        "server_stop_code": stop_code,
        "environment": _environment_fingerprint(),
        "recorded_at": _utc_now(),
    }
    return _maybe_write_evidence(payload, evidence_dir=evidence_dir, stem="parity_q8_0")


__all__ = [
    "capture_cpu_host_runtime_facts",
    "document_embedding_texts",
    "execute_parity",
    "execute_screen",
    "execute_stage0_compat",
    "load_children_by_id",
    "resolve_gguf_query_contract",
    "smoke_encode",
]
