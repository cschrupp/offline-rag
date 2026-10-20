#!/usr/bin/env python3
"""16K-D D1 stall-attribution scientific execution harness.

Authority: S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001
Matrix: docs/slice16k_d_d1_scientific_matrix_freeze.md

Phases: preflight → a1 → a2 → b → analyze
No src/** changes. Private text never written to evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from d1_common import (  # noqa: E402
    AUTH,
    CHUNK_SET_ID,
    CORPUS_NAME,
    D1B_BATCH_INDICES,
    D1B_CELL_BY_INDEX,
    D1B_ENCODE_ORDER,
    EVIDENCE_DIR,
    EXPECTED_BATCH_COUNT,
    EXPECTED_BATCH_SIZE,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CORPUS_MANIFEST_SHA256,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    MATRIX_DOC,
    MATRIX_PARENT,
    PROFILE_CONTRACT,
    TOOLING_SUBJECT,
    capture_runtime,
    d1b_schedule,
    enrich_batch_wall_minus_device,
    git_sha,
    git_tracked_clean,
    prepare_isolated_tree,
    source_digests,
    utc_now,
    workload_identity,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {path}")


def _common_provenance() -> dict[str, Any]:
    return {
        "authority": AUTH,
        "matrix_parent": MATRIX_PARENT,
        "matrix_document": MATRIX_DOC,
        "accepted_tooling_subject": TOOLING_SUBJECT,
        "execution_head": git_sha(),
        "source_sha256": source_digests(),
        "recorded_at": utc_now(),
        "runtime": capture_runtime(),
        "attribution_only_not_section_9_4_gate": True,
    }


def _fail(path: Path, reason: str, detail: dict[str, Any] | None = None) -> int:
    payload = {
        **_common_provenance(),
        "status": "INVALID_ATTEMPT",
        "invalid_reason": reason,
        "detail": detail or {},
    }
    _write_json(path, payload)
    print(f"FAIL-CLOSED: {reason}", file=sys.stderr)
    return 10


def reconstruct_cold_batch_plan(settings: Any) -> dict[str, Any]:
    """Mirror production cold pending-batch partitioning (chunk_id sort, batch 32)."""
    from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
    from offline_rag.dense.pipeline import child_jobs_from_chunk_set
    from offline_rag.dense.profiling import batch_identity_digest
    from offline_rag.dense.searchable_units import filter_dense_searchable_children

    chunk_path = chunk_state_path(settings.paths.corpora, CORPUS_NAME)
    chunk_state = load_chunk_state(chunk_path)
    jobs, _documents_total = child_jobs_from_chunk_set(
        settings=settings,
        chunk_set_id=chunk_state.current_chunk_set_id,
        chunk_manifest_name=chunk_state.current_chunk_manifest,
    )
    eligible, excluded = filter_dense_searchable_children(jobs, settings)
    jobs = eligible
    batch_size = int(settings.indexing.embedding.batch_size)
    batches: list[dict[str, Any]] = []
    for batch_index, start in enumerate(range(0, len(jobs), batch_size)):
        chunk_ids = [item[0].chunk_id for item in jobs[start : start + batch_size]]
        chunk_digest = batch_identity_digest(chunk_ids)
        identity = __import__("hashlib").sha256(
            f"{batch_index}:{len(chunk_ids)}:{chunk_digest}".encode()
        ).hexdigest()
        batches.append(
            {
                "batch_index": batch_index,
                "item_count": len(chunk_ids),
                "chunk_ids_digest": chunk_digest,
                "batch_identity_digest": identity,
                # chunk_ids retained in-memory only; never written to evidence.
                "_chunk_ids": chunk_ids,
                "_jobs": jobs[start : start + batch_size],
            }
        )
    return {
        "eligible_child_count": len(jobs),
        "excluded_count": len(excluded),
        "batch_size": batch_size,
        "batch_count": len(batches),
        "batches": batches,
        "chunk_set_id": chunk_state.current_chunk_set_id,
    }


def phase_preflight(work_root: Path) -> int:
    clean, clean_msg = git_tracked_clean()
    if not clean:
        return _fail(
            EVIDENCE_DIR / "d1_preflight_INVALID.json",
            "tracked_working_tree_dirty",
            {"detail": clean_msg},
        )

    os.environ["OFFLINE_RAG_DATA_DIR"] = str(work_root.resolve())
    os.environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
    os.environ["OFFLINE_RAG_DIAG_DENSE_PROFILE"] = "1"

    prepare_isolated_tree(work_root)
    workload = workload_identity()
    errors: list[str] = []
    if workload["child_count"] != EXPECTED_CHILD_COUNT:
        errors.append(f"child_count={workload['child_count']}")
    if workload["chunk_manifest_sha256"] != EXPECTED_CHUNK_MANIFEST_SHA256:
        errors.append("chunk_manifest_sha256_mismatch")
    if workload["corpus_manifest_sha256"] != EXPECTED_CORPUS_MANIFEST_SHA256:
        errors.append("corpus_manifest_sha256_mismatch")
    if workload["corpus_id"] != workload_identity()["corpus_id"]:
        errors.append("corpus_id_mismatch")
    if workload["chunk_set_id"] != CHUNK_SET_ID:
        errors.append("chunk_set_id_mismatch")

    from offline_rag.config import load_settings

    settings = load_settings()
    if settings.indexing.embedding.batch_size != EXPECTED_BATCH_SIZE:
        errors.append(f"batch_size={settings.indexing.embedding.batch_size}")
    if settings.indexing.embedding.model_id != EXPECTED_MODEL_ID:
        errors.append(f"model_id={settings.indexing.embedding.model_id}")
    if settings.indexing.embedding.revision != EXPECTED_MODEL_REVISION:
        errors.append(f"revision={settings.indexing.embedding.revision}")

    plan = reconstruct_cold_batch_plan(settings)
    if plan["eligible_child_count"] != EXPECTED_CHILD_COUNT:
        errors.append(f"eligible_child_count={plan['eligible_child_count']}")
    if plan["batch_count"] != EXPECTED_BATCH_COUNT:
        errors.append(f"batch_count={plan['batch_count']}")
    if plan["batch_size"] != EXPECTED_BATCH_SIZE:
        errors.append(f"plan_batch_size={plan['batch_size']}")

    selected: list[dict[str, Any]] = []
    for idx in D1B_BATCH_INDICES:
        if idx >= len(plan["batches"]):
            errors.append(f"missing_batch_index_{idx}")
            continue
        b = plan["batches"][idx]
        selected.append(
            {
                "cell": D1B_CELL_BY_INDEX[idx],
                "batch_index": idx,
                "item_count": b["item_count"],
                "chunk_ids_digest": b["chunk_ids_digest"],
                "batch_identity_digest": b["batch_identity_digest"],
            }
        )

    schedule = d1b_schedule()
    if len(D1B_ENCODE_ORDER) != 36:
        errors.append(f"encode_order_len={len(D1B_ENCODE_ORDER)}")
    for idx in D1B_BATCH_INDICES:
        if D1B_ENCODE_ORDER.count(idx) != 6:
            errors.append(f"repetition_count_{idx}={D1B_ENCODE_ORDER.count(idx)}")

    # CUDA / dtype / attention require model load — record as preflight_model checks
    # without counting as a measured scientific encode.
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts
    import torch

    if not torch.cuda.is_available():
        errors.append("cuda_not_available")

    embedder = make_embedder(settings)
    embedder._load()  # type: ignore[attr-defined]
    facts = observe_embedder_execution_facts(embedder)
    dtype = str(facts.get("dtype") or "").removeprefix("torch.")
    attention = str(facts.get("attention_backend") or "").lower()
    if dtype not in {"bfloat16", "bf16"}:
        errors.append(f"dtype={dtype}")
    if attention != "sdpa":
        errors.append(f"attention_backend={facts.get('attention_backend')}")

    if errors:
        return _fail(
            EVIDENCE_DIR / "d1_preflight_INVALID.json",
            "identity_preflight_failed",
            {"errors": errors, "workload": workload, "execution_facts": facts},
        )

    payload = {
        **_common_provenance(),
        "status": "PREFLIGHT_OK",
        "phase": "preflight",
        "git_tracked": clean_msg,
        "workload": workload,
        "execution_facts": {
            "device": "cuda",
            "dtype": dtype,
            "attention_backend": attention,
            "batch_size": EXPECTED_BATCH_SIZE,
            "profile_contract_expected": PROFILE_CONTRACT,
            "model_id": EXPECTED_MODEL_ID,
            "revision": EXPECTED_MODEL_REVISION,
        },
        "reconstruction": {
            "eligible_child_count": plan["eligible_child_count"],
            "excluded_count": plan["excluded_count"],
            "batch_count": plan["batch_count"],
            "batch_size": plan["batch_size"],
            "chunk_set_id": plan["chunk_set_id"],
            "sorting_contract": "chunk_id_ascending",
        },
        "d1b_selected_identities": selected,
        "d1b_encode_schedule": schedule,
        "note": (
            "D1-B identities frozen before A1. Model load in preflight is not a "
            "measured scientific encode of selected batches."
        ),
    }
    _write_json(EVIDENCE_DIR / "d1_preflight.json", payload)
    return 0


def _run_full_cold_indexing(cell: str, work_root: Path) -> int:
    clean, clean_msg = git_tracked_clean()
    if not clean:
        return _fail(
            EVIDENCE_DIR / f"d1_{cell.lower()}_INVALID.json",
            "tracked_working_tree_dirty",
            {"detail": clean_msg},
        )

    os.environ["OFFLINE_RAG_DATA_DIR"] = str(work_root.resolve())
    os.environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
    os.environ["OFFLINE_RAG_DIAG_DENSE_PROFILE"] = "1"

    prepare_isolated_tree(work_root)
    workload = workload_identity()

    from offline_rag.config import load_settings
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.domain.indexing import IndexingStatus

    settings = load_settings()
    embedder = make_embedder(settings)
    embedder._load()  # type: ignore[attr-defined]
    facts = observe_embedder_execution_facts(embedder)

    started = time.perf_counter()
    report = run_indexing(settings=settings, corpus_name=CORPUS_NAME, embedder=embedder)
    wall_s = time.perf_counter() - started

    if report.status is not IndexingStatus.SUCCESS:
        return _fail(
            EVIDENCE_DIR / f"d1_{cell.lower()}_INVALID.json",
            "indexing_status_not_success",
            {
                "status": str(report.status),
                "errors": report.errors,
                "counts": {
                    "generated": report.embeddings_generated,
                    "reused": report.embeddings_reused,
                },
            },
        )

    if report.embeddings_generated != EXPECTED_CHILD_COUNT or report.embeddings_reused != 0:
        return _fail(
            EVIDENCE_DIR / f"d1_{cell.lower()}_INVALID.json",
            "cold_count_contract_failed",
            {
                "generated": report.embeddings_generated,
                "reused": report.embeddings_reused,
                "children_total": report.children_total,
            },
        )

    profile = report.metadata.get("dense_profile") or {}
    if profile.get("contract") != PROFILE_CONTRACT:
        return _fail(
            EVIDENCE_DIR / f"d1_{cell.lower()}_INVALID.json",
            "profile_contract_mismatch",
            {"contract": profile.get("contract")},
        )
    if profile.get("batch_count") != EXPECTED_BATCH_COUNT:
        return _fail(
            EVIDENCE_DIR / f"d1_{cell.lower()}_INVALID.json",
            "batch_count_mismatch",
            {"batch_count": profile.get("batch_count")},
        )

    batches = [
        enrich_batch_wall_minus_device(b) for b in (profile.get("batches") or [])
    ]
    execution = report.metadata.get("dense_execution") or {}
    payload = {
        **_common_provenance(),
        "status": "CELL_VALID",
        "phase": cell,
        "git_tracked": clean_msg,
        "workload": workload,
        "execution_facts": facts,
        "dense_execution": execution,
        "counts": {
            "children_total": report.children_total,
            "embeddings_generated": report.embeddings_generated,
            "embeddings_reused": report.embeddings_reused,
            "embeddings_failed": report.embeddings_failed,
            "vectors_materialized": report.vectors_materialized,
        },
        "timing": {
            "wall_clock_s": wall_s,
            "dense_generation_ms": report.metadata.get("dense_generation_ms"),
            "dense_materialization_ms": report.metadata.get("dense_materialization_ms"),
            "report_duration_ms": report.duration_ms,
            "profile_timing_ms": profile.get("timing_ms"),
            "note": "attribution_only_not_section_9_4_confirmation",
        },
        "dense_profile_contract": profile.get("contract"),
        "batch_count": profile.get("batch_count"),
        "batches": batches,
        "tokenizer_status": profile.get("tokenizer_status"),
        "peak_vram_bytes": profile.get("peak_vram_bytes"),
        "peak_vram_status": profile.get("peak_vram_status"),
        "index_id": report.index_id,
        "collection_name": report.collection_name,
    }
    _write_json(EVIDENCE_DIR / f"d1_{cell.lower()}.json", payload)
    print(
        json.dumps(
            {
                "phase": cell,
                "generated": report.embeddings_generated,
                "reused": report.embeddings_reused,
                "wall_s": wall_s,
                "batch_count": profile.get("batch_count"),
            },
            indent=2,
        )
    )
    return 0


def phase_a1() -> int:
    return _run_full_cold_indexing("A1", ROOT / "data" / "16k_d_d1_a1_work")


def phase_a2() -> int:
    return _run_full_cold_indexing("A2", ROOT / "data" / "16k_d_d1_a2_work")


def phase_b() -> int:
    clean, clean_msg = git_tracked_clean()
    if not clean:
        return _fail(
            EVIDENCE_DIR / "d1_b_INVALID.json",
            "tracked_working_tree_dirty",
            {"detail": clean_msg},
        )

    preflight_path = EVIDENCE_DIR / "d1_preflight.json"
    if not preflight_path.exists():
        return _fail(EVIDENCE_DIR / "d1_b_INVALID.json", "missing_preflight", {})
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PREFLIGHT_OK":
        return _fail(
            EVIDENCE_DIR / "d1_b_INVALID.json",
            "preflight_not_ok",
            {"status": preflight.get("status")},
        )

    work_root = ROOT / "data" / "16k_d_d1_b_work"
    os.environ["OFFLINE_RAG_DATA_DIR"] = str(work_root.resolve())
    os.environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
    os.environ["OFFLINE_RAG_DIAG_DENSE_PROFILE"] = "1"
    prepare_isolated_tree(work_root)

    from offline_rag.config import load_settings
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts
    from offline_rag.dense.pipeline import make_embedding_text_builder
    from offline_rag.dense.profiling import (
        DenseProfileCollector,
        observe_cuda_allocator_state,
        observe_model_input_token_counts,
        profiled_encode_timing,
        sample_external_gpu_state,
    )
    from offline_rag.ingestion.persistence import (
        corpus_state_path,
        load_corpus_manifest,
        load_corpus_state,
    )
    from offline_rag.retrieval.ranking_text import (
        ranking_inputs_for_chunk,
        resolve_document_titles_from_source_names,
    )

    settings = load_settings()
    plan = reconstruct_cold_batch_plan(settings)
    pref_ids = {
        item["batch_index"]: item
        for item in preflight.get("d1b_selected_identities") or []
    }
    for idx in D1B_BATCH_INDICES:
        b = plan["batches"][idx]
        expected = pref_ids[idx]
        if (
            b["chunk_ids_digest"] != expected["chunk_ids_digest"]
            or b["batch_identity_digest"] != expected["batch_identity_digest"]
        ):
            return _fail(
                EVIDENCE_DIR / "d1_b_INVALID.json",
                "d1b_identity_drift_vs_preflight",
                {
                    "batch_index": idx,
                    "expected": expected,
                    "observed_digests": {
                        "chunk_ids_digest": b["chunk_ids_digest"],
                        "batch_identity_digest": b["batch_identity_digest"],
                    },
                },
            )

    text_builder = make_embedding_text_builder(settings)
    corpus_state = load_corpus_state(corpus_state_path(settings.paths.corpora, CORPUS_NAME))
    manifest_path = settings.paths.manifests / Path(corpus_state.current_manifest).name
    corpus_manifest = load_corpus_manifest(manifest_path)
    source_names = {
        entry.document_id: entry.source_name for entry in corpus_manifest.documents
    }
    document_ids = {
        chunk.document_id
        for idx in D1B_BATCH_INDICES
        for chunk, _aid in plan["batches"][idx]["_jobs"]
    }
    from offline_rag.dense.pipeline import _requires_document_titles

    document_titles = resolve_document_titles_from_source_names(
        document_ids=document_ids,
        source_name_by_document_id=source_names,
        require=_requires_document_titles(text_builder),
    )

    batch_texts: dict[int, list[str]] = {}
    for idx in D1B_BATCH_INDICES:
        texts: list[str] = []
        for chunk, _chunk_artifact_id in plan["batches"][idx]["_jobs"]:
            inputs = ranking_inputs_for_chunk(
                chunk_text=chunk.text,
                section_path=list(chunk.section_path or []),
                document_title=document_titles.get(chunk.document_id),
            )
            texts.append(text_builder.build(inputs))
        batch_texts[idx] = texts

    embedder = make_embedder(settings)
    embedder._load()  # type: ignore[attr-defined]
    facts = observe_embedder_execution_facts(embedder)
    collector = DenseProfileCollector()
    encodes: list[dict[str, Any]] = []

    for slot in d1b_schedule():
        batch_index = int(slot["batch_index"])
        texts = batch_texts[batch_index]
        encode_payloads = texts
        doc_instruction = getattr(embedder, "document_instruction", None)
        if isinstance(doc_instruction, str) and doc_instruction:
            encode_payloads = [f"{doc_instruction}{t}" for t in texts]

        token_counts, max_seq = observe_model_input_token_counts(
            embedder, encode_payloads, collector
        )
        chunk_ids = plan["batches"][batch_index]["_chunk_ids"]
        gpu_before = sample_external_gpu_state()
        with profiled_encode_timing() as timing:
            vectors = embedder.embed_documents(texts)
        gpu_after = sample_external_gpu_state()
        allocator = observe_cuda_allocator_state()
        if len(vectors) != len(texts):
            return _fail(
                EVIDENCE_DIR / "d1_b_INVALID.json",
                "embedder_batch_size_mismatch",
                {
                    "batch_index": batch_index,
                    "got": len(vectors),
                    "expected": len(texts),
                },
            )
        collector.record_batch(
            batch_index=batch_index,
            item_count=len(texts),
            token_counts=token_counts,
            max_sequence_length=max_seq,
            encode_ms=float(timing["encode_ms"]),
            persistence_ms=0.0,
            peak_vram_bytes_after=None,
            chunk_ids=chunk_ids,
            encode_cuda_device_ms=timing["encode_cuda_device_ms"],
            encode_cuda_device_status=str(timing["encode_cuda_device_status"]),
            encode_cuda_device_error=timing["encode_cuda_device_error"],
            process_cpu_delta=timing["process_cpu_delta"],
            cuda_allocator_after=allocator,
            gpu_external_before=gpu_before,
            gpu_external_after=gpu_after,
        )
        batch_dict = enrich_batch_wall_minus_device(
            DenseProfileCollector._batch_dict(collector.batches[-1])
        )
        encodes.append(
            {
                **slot,
                "measurement": batch_dict,
                "vector_count": len(vectors),
            }
        )

    if len(encodes) != 36:
        return _fail(
            EVIDENCE_DIR / "d1_b_INVALID.json",
            "encode_count_not_36",
            {"count": len(encodes)},
        )

    payload = {
        **_common_provenance(),
        "status": "CELL_VALID",
        "phase": "B",
        "git_tracked": clean_msg,
        "workload": workload_identity(),
        "execution_facts": facts,
        "preflight_identities": preflight.get("d1b_selected_identities"),
        "encode_count": len(encodes),
        "encodes": encodes,
        "note": (
            "One process / one model load; 36 measured encodes; no warm-up on "
            "selected batches; persistence_ms intentionally 0 (encode-only replay)."
        ),
    }
    _write_json(EVIDENCE_DIR / "d1_b.json", payload)
    print(json.dumps({"phase": "B", "encode_count": 36, "status": "CELL_VALID"}, indent=2))
    return 0


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry, strict=True))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def phase_analyze() -> int:
    a1_path = EVIDENCE_DIR / "d1_a1.json"
    a2_path = EVIDENCE_DIR / "d1_a2.json"
    b_path = EVIDENCE_DIR / "d1_b.json"
    for p in (a1_path, a2_path, b_path):
        if not p.exists():
            return _fail(
                EVIDENCE_DIR / "d1_analysis_INVALID.json",
                "missing_cell_evidence",
                {"missing": str(p)},
            )
    a1 = json.loads(a1_path.read_text(encoding="utf-8"))
    a2 = json.loads(a2_path.read_text(encoding="utf-8"))
    b = json.loads(b_path.read_text(encoding="utf-8"))
    if a1.get("status") != "CELL_VALID" or a2.get("status") != "CELL_VALID":
        return _fail(
            EVIDENCE_DIR / "d1_analysis_INVALID.json",
            "a_cell_not_valid",
            {"a1": a1.get("status"), "a2": a2.get("status")},
        )
    if b.get("status") != "CELL_VALID" or b.get("encode_count") != 36:
        return _fail(
            EVIDENCE_DIR / "d1_analysis_INVALID.json",
            "b_cell_not_valid",
            {"status": b.get("status"), "encode_count": b.get("encode_count")},
        )

    d0_clean = json.loads(
        (ROOT / "docs/evidence/16k_d_dense_cuda/d0_baseline_32e52024df47.json").read_text(
            encoding="utf-8"
        )
    )
    d0_hist = json.loads(
        (ROOT / "docs/evidence/16k_d_dense_cuda/d0_baseline_33a031b6a1bb.json").read_text(
            encoding="utf-8"
        )
    )

    def walls(evidence: dict[str, Any]) -> list[float]:
        return [float(x["encode_ms"]) for x in evidence.get("batches") or []]

    a1w, a2w = walls(a1), walls(a2)
    d0c, d0h = walls(d0_clean), walls(d0_hist)

    def by_index(evidence: dict[str, Any]) -> dict[int, dict[str, Any]]:
        return {int(b["batch_index"]): b for b in evidence.get("batches") or []}

    a1b, a2b = by_index(a1), by_index(a2)

    wall_dev_pairs = []
    residuals = []
    for batch in a1.get("batches") or []:
        if batch.get("encode_cuda_device_status") == "observed" and batch.get(
            "encode_cuda_device_ms"
        ) is not None:
            wall_dev_pairs.append(
                (float(batch["encode_ms"]), float(batch["encode_cuda_device_ms"]))
            )
            if batch.get("wall_minus_device_ms") is not None:
                residuals.append(float(batch["wall_minus_device_ms"]))

    shape_rows = []
    for batch in a1.get("batches") or []:
        stats = batch.get("token_length_stats") or {}
        shape_rows.append(
            {
                "batch_index": batch.get("batch_index"),
                "encode_ms": batch.get("encode_ms"),
                "max_sequence_length": batch.get("max_sequence_length"),
                "aggregate_input_tokens": batch.get("aggregate_input_tokens"),
                "padded_token_workload": batch.get("padded_token_workload"),
                "padding_fraction": batch.get("padding_fraction"),
            }
        )

    def corr_with(field: str) -> float | None:
        xs = []
        ys = []
        for row in shape_rows:
            if row.get(field) is None or row.get("encode_ms") is None:
                continue
            xs.append(float(row["encode_ms"]))
            ys.append(float(row[field]))
        return _pearson(xs, ys)

    # Paired comparisons from D1-B
    from collections import defaultdict

    by_batch: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for enc in b.get("encodes") or []:
        by_batch[int(enc["batch_index"])].append(enc)

    def batch_stats(idx: int) -> dict[str, Any]:
        walls_ms = [float(e["measurement"]["encode_ms"]) for e in by_batch[idx]]
        devices = [
            float(e["measurement"]["encode_cuda_device_ms"])
            for e in by_batch[idx]
            if e["measurement"].get("encode_cuda_device_status") == "observed"
            and e["measurement"].get("encode_cuda_device_ms") is not None
        ]
        return {
            "cell": D1B_CELL_BY_INDEX[idx],
            "batch_index": idx,
            "n": len(walls_ms),
            "wall_ms_mean": statistics.fmean(walls_ms) if walls_ms else None,
            "wall_ms_stdev": statistics.pstdev(walls_ms) if len(walls_ms) > 1 else 0.0,
            "wall_ms_min": min(walls_ms) if walls_ms else None,
            "wall_ms_max": max(walls_ms) if walls_ms else None,
            "device_ms_mean": statistics.fmean(devices) if devices else None,
            "device_ms_stdev": statistics.pstdev(devices) if len(devices) > 1 else 0.0,
        }

    paired = {
        "pair_1_14": {
            "fast": batch_stats(1),
            "slow": batch_stats(14),
            "wall_mean_ratio_slow_over_fast": (
                (batch_stats(14)["wall_ms_mean"] / batch_stats(1)["wall_ms_mean"])
                if batch_stats(1)["wall_ms_mean"]
                else None
            ),
        },
        "pair_17_13": {
            "fast": batch_stats(17),
            "slow": batch_stats(13),
            "wall_mean_ratio_slow_over_fast": (
                (batch_stats(13)["wall_ms_mean"] / batch_stats(17)["wall_ms_mean"])
                if batch_stats(17)["wall_ms_mean"]
                else None
            ),
        },
        "discordant_4_6": {
            "batch_4": batch_stats(4),
            "batch_6": batch_stats(6),
            "a1_wall_ms": {
                4: (a1b.get(4) or {}).get("encode_ms"),
                6: (a1b.get(6) or {}).get("encode_ms"),
            },
            "a2_wall_ms": {
                4: (a2b.get(4) or {}).get("encode_ms"),
                6: (a2b.get(6) or {}).get("encode_ms"),
            },
        },
    }

    # System-state associations (descriptive only)
    assoc_rows = []
    for batch in a1.get("batches") or []:
        cpu = batch.get("process_cpu_delta") or {}
        gpu_after = (batch.get("gpu_external_after") or {}).get("sample") or {}
        assoc_rows.append(
            {
                "batch_index": batch.get("batch_index"),
                "encode_ms": batch.get("encode_ms"),
                "wall_minus_device_ms": batch.get("wall_minus_device_ms"),
                "cpu_time_s": cpu.get("cpu_time_s"),
                "voluntary_context_switches": cpu.get("voluntary_context_switches"),
                "involuntary_context_switches": cpu.get("involuntary_context_switches"),
                "temperature_c": gpu_after.get("temperature_c"),
                "power_draw_w": gpu_after.get("power_draw_w"),
                "clock_sm_mhz": gpu_after.get("clock_sm_mhz"),
                "pstate": gpu_after.get("pstate"),
                "throttle_sw_power_cap": gpu_after.get("throttle_sw_power_cap"),
                "throttle_hw_thermal_slowdown": gpu_after.get(
                    "throttle_hw_thermal_slowdown"
                ),
            }
        )

    analysis = {
        **_common_provenance(),
        "status": "ANALYSIS_COMPLETE",
        "phase": "analyze",
        "validity": {
            "a1": a1.get("status"),
            "a2": a2.get("status"),
            "b_encode_count": b.get("encode_count"),
            "b": b.get("status"),
        },
        "a1_a2_batch_rank_spearman": _spearman(a1w, a2w),
        "a1_vs_d0_clean_rank_spearman": _spearman(a1w, d0c),
        "a1_vs_d0_historical_rank_spearman": _spearman(a1w, d0h),
        "a2_vs_d0_clean_rank_spearman": _spearman(a2w, d0c),
        "wall_vs_device_pearson_a1": _pearson(
            [p[0] for p in wall_dev_pairs], [p[1] for p in wall_dev_pairs]
        ),
        "wall_minus_device_residual_a1": {
            "n": len(residuals),
            "mean_ms": statistics.fmean(residuals) if residuals else None,
            "stdev_ms": statistics.pstdev(residuals) if len(residuals) > 1 else None,
            "min_ms": min(residuals) if residuals else None,
            "max_ms": max(residuals) if residuals else None,
        },
        "latency_shape_pearson_a1": {
            "max_sequence_length": corr_with("max_sequence_length"),
            "aggregate_input_tokens": corr_with("aggregate_input_tokens"),
            "padded_token_workload": corr_with("padded_token_workload"),
            "padding_fraction": corr_with("padding_fraction"),
        },
        "d1b_within_batch_dispersion": {
            str(i): batch_stats(i) for i in D1B_BATCH_INDICES
        },
        "paired_comparisons": paired,
        "system_state_rows_a1": assoc_rows,
        "interpretation_limits": [
            "No causal claim solely from correlation.",
            "D1-A/B wall times are attribution-only; not §9.4 10/12-minute gates.",
            "D1 does not promote or modify production policy.",
        ],
        "decision_boundary_targets": [
            "deterministic batch/content/shape effect",
            "GPU/device execution",
            "host/scheduling/synchronization",
            "power/clock/thermal state",
            "allocator/runtime state",
            "unresolved mixture",
        ],
    }
    _write_json(EVIDENCE_DIR / "d1_analysis.json", analysis)
    print(
        json.dumps(
            {
                "a1_a2_spearman": analysis["a1_a2_batch_rank_spearman"],
                "wall_device_pearson_a1": analysis["wall_vs_device_pearson_a1"],
                "b_36": b.get("encode_count"),
            },
            indent=2,
        )
    )
    return 0


def phase_all() -> int:
    """preflight in-process; A1/A2/B as fresh subprocesses; then analyze."""
    preflight_work = ROOT / "data" / "16k_d_d1_preflight_work"
    rc = phase_preflight(preflight_work)
    if rc != 0:
        return rc
    script = Path(__file__).resolve()
    for phase in ("a1", "a2", "b"):
        print(f"=== launching fresh process phase={phase} ===")
        proc = subprocess.run(
            [sys.executable, str(script), "--phase", phase],
            cwd=str(ROOT),
            check=False,
        )
        if proc.returncode != 0:
            return proc.returncode
    return phase_analyze()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("preflight", "a1", "a2", "b", "analyze", "all"),
        required=True,
    )
    parser.add_argument(
        "--preflight-work-root",
        type=Path,
        default=ROOT / "data" / "16k_d_d1_preflight_work",
    )
    args = parser.parse_args()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if args.phase == "preflight":
        return phase_preflight(args.preflight_work_root.resolve())
    if args.phase == "a1":
        return phase_a1()
    if args.phase == "a2":
        return phase_a2()
    if args.phase == "b":
        return phase_b()
    if args.phase == "analyze":
        return phase_analyze()
    if args.phase == "all":
        return phase_all()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
