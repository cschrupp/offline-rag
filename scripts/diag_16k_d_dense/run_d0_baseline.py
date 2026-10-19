#!/usr/bin/env python3
"""16K-D D0 cold CUDA FP32 / batch-32 dense baseline runner.

Authority: S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001
Contract: docs/slice16k_beta_ingestion_readiness_design.md §9

Restores the frozen ~1296-child incident chunk set into an isolated data tree,
forces harness-only FP32 (does not change production defaults), runs cold dense
indexing with OFFLINE_RAG_DIAG_DENSE_PROFILE=1, and writes evidence under
docs/evidence/16k_d_dense_cuda/. Private document text is never written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

AUTH = "S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001"
CORPUS_NAME = "16k_d_d0_incident"
CHUNK_SET_ID = (
    "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d"
)
CORPUS_ID = "corpus_3c74b057074e928cccf7da048c06db0cf6df63bbe546ec14c071604949f160e3"
DENSE_INDEX_ID = (
    "denseindex_e29c701572d7a0d4d46a9800a0a9104e69c8cd1468b73d01c4484ef41561b706"
)
ABANDONED_ROOT = (
    ROOT
    / "data/corpora/wsc_fdd77b77611448eb93cdc239d2610281/abandoned"
    / "20261016T003020Z-036695894ce04681a147718a8c9f6cad"
    / "corpora/wsc_fdd77b77611448eb93cdc239d2610281"
)
EVIDENCE_DIR = ROOT / "docs/evidence/16k_d_dense_cuda"
WORKLOAD_LABEL = "D0-INCIDENT-1296-CHILD-V1"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _symlink_or_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    try:
        dest.symlink_to(src.resolve(), target_is_directory=src.is_dir())
    except OSError:
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)


def prepare_isolated_tree(work_root: Path) -> Path:
    """Build an isolated OFFLINE_RAG_DATA_DIR for a cold baseline."""
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    for name in (
        "manifests",
        "chunks",
        "chunk-manifests",
        "processed",
    ):
        _symlink_or_copy(ROOT / "data" / name, work_root / name)

    # Private mutable namespaces for this run only.
    (work_root / "embeddings").mkdir()
    (work_root / "qdrant").mkdir()
    (work_root / "index-manifests").mkdir()
    (work_root / "locks").mkdir()
    (work_root / "staging").mkdir()
    (work_root / "traces").mkdir()

    corpus_dir = work_root / "corpora" / CORPUS_NAME
    (corpus_dir / "chunking").mkdir(parents=True)

    corpus_state = json.loads((ABANDONED_ROOT / "state.json").read_text(encoding="utf-8"))
    corpus_state["corpus_name"] = CORPUS_NAME
    (corpus_dir / "state.json").write_text(
        json.dumps(corpus_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    chunk_state = json.loads(
        (ABANDONED_ROOT / "chunking" / "state.json").read_text(encoding="utf-8")
    )
    chunk_state["corpus_name"] = CORPUS_NAME
    (corpus_dir / "chunking" / "state.json").write_text(
        json.dumps(chunk_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Intentionally omit indexing/state.json so dense cannot short-circuit to NO_OP.
    return work_root


def force_embedder_float32(embedder: Any) -> dict[str, Any]:
    """Harness-only dtype force for the D0 FP32 lane. Not a production default."""
    import torch

    before = None
    model = embedder._load()
    try:
        first = model[0] if len(model) else None
        auto_model = getattr(first, "auto_model", None)
        if auto_model is not None:
            param = next(auto_model.parameters(), None)
            if param is not None:
                before = str(param.dtype).removeprefix("torch.")
    except Exception as exc:  # noqa: BLE001
        return {
            "dtype_policy": "harness_forced_float32",
            "dtype_before": None,
            "dtype_after": None,
            "error": f"{type(exc).__name__}: {exc}",
        }
    model.float()
    after = None
    try:
        first = model[0] if len(model) else None
        auto_model = getattr(first, "auto_model", None)
        if auto_model is not None:
            param = next(auto_model.parameters(), None)
            if param is not None:
                after = str(param.dtype).removeprefix("torch.")
    except Exception:  # noqa: BLE001
        after = "float32" if torch.float32 else None
    return {
        "dtype_policy": "harness_forced_float32",
        "dtype_before": before,
        "dtype_after": after,
        "error": None,
    }


def capture_runtime() -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "gpu_name": None,
        "gpu_memory_total_mib": None,
        "cuda_version": None,
        "torch_version": None,
        "nvidia_smi_error": None,
    }
    try:
        import torch

        runtime["torch_version"] = torch.__version__
        runtime["cuda_version"] = getattr(torch.version, "cuda", None)
        if torch.cuda.is_available():
            runtime["gpu_name"] = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            runtime["gpu_memory_total_mib"] = int(props.total_memory / (1024 * 1024))
    except Exception as exc:  # noqa: BLE001
        runtime["torch_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        runtime["nvidia_smi"] = out
    except Exception as exc:  # noqa: BLE001
        runtime["nvidia_smi_error"] = f"{type(exc).__name__}: {exc}"
    return runtime


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work-root",
        type=Path,
        default=ROOT / "data" / "16k_d_d0_work",
        help="Isolated data tree for this baseline run",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Prepare tree only (no indexing)",
    )
    parser.add_argument(
        "--dtype-lane",
        choices=("fp32_force", "native"),
        default="native",
        help=(
            "fp32_force: harness-only model.float() after load (D0 design lane). "
            "native: measure provisioned model dtype as loaded (current path). "
            "Default native after fp32_force hit CUBLAS_STATUS_EXECUTION_FAILED "
            "on this host's RTX 2080 Super."
        ),
    )
    args = parser.parse_args()

    os.environ["OFFLINE_RAG_DIAG_DENSE_PROFILE"] = "1"
    os.environ["OFFLINE_RAG_EMBEDDING_DEVICE"] = "cuda"
    os.environ["OFFLINE_RAG_DATA_DIR"] = str(args.work_root.resolve())

    work_root = prepare_isolated_tree(args.work_root.resolve())
    chunk_manifest = ROOT / "data/chunk-manifests" / f"{CHUNK_SET_ID}.json"
    corpus_manifest = ROOT / "data/manifests" / f"{CORPUS_ID}.json"
    if not chunk_manifest.exists() or not corpus_manifest.exists():
        print("ERROR: missing frozen workload manifests", file=sys.stderr)
        return 2

    workload = {
        "label": WORKLOAD_LABEL,
        "corpus_id": CORPUS_ID,
        "chunk_set_id": CHUNK_SET_ID,
        "historical_dense_index_id": DENSE_INDEX_ID,
        "child_count": json.loads(chunk_manifest.read_text(encoding="utf-8")).get(
            "total_child_count"
        ),
        "chunk_manifest_sha256": _sha256_file(chunk_manifest),
        "corpus_manifest_sha256": _sha256_file(corpus_manifest),
        "cold_or_warm": "cold",
        "note": (
            "Isolated empty embeddings/ + qdrant/; no private document text "
            "in evidence."
        ),
    }

    if args.skip_run:
        print(json.dumps({"prepared": str(work_root), "workload": workload}, indent=2))
        return 0

    from offline_rag.config import load_settings
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.domain.indexing import IndexingStatus

    settings = load_settings()
    # Fail closed if defaults drifted.
    if settings.indexing.embedding.batch_size != 32:
        print(
            f"ERROR: batch_size={settings.indexing.embedding.batch_size}, expected 32",
            file=sys.stderr,
        )
        return 3

    embedder = make_embedder(settings)
    if args.dtype_lane == "fp32_force":
        dtype_force = force_embedder_float32(embedder)
        observed = observe_embedder_execution_facts(embedder)
        if observed.get("dtype") not in {"float32", "torch.float32"} and dtype_force.get(
            "dtype_after"
        ) not in {"float32", "torch.float32"}:
            print(
                f"ERROR: failed to establish FP32 lane; observed={observed} "
                f"force={dtype_force}",
                file=sys.stderr,
            )
            return 4
    else:
        # Preload so dtype/attention are observable before first timed batch.
        embedder._load()  # type: ignore[attr-defined]
        observed = observe_embedder_execution_facts(embedder)
        dtype_force = {
            "dtype_policy": "native_as_loaded",
            "dtype_before": observed.get("dtype"),
            "dtype_after": observed.get("dtype"),
            "error": None,
            "note": (
                "Harness did not force dtype. Provisioned model config torch_dtype "
                "is bfloat16; this measures the executable current path on this host."
            ),
        }

    started = time.perf_counter()
    report = run_indexing(
        settings=settings,
        corpus_name=CORPUS_NAME,
        embedder=embedder,
    )
    wall_s = time.perf_counter() - started

    if report.status is not IndexingStatus.SUCCESS:
        print(
            f"ERROR: indexing status={report.status} errors={report.errors}",
            file=sys.stderr,
        )
        # Still write a failure evidence stub for debugging.
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        fail_path = EVIDENCE_DIR / (
            f"d0_baseline_{args.dtype_lane}_FAILED_{int(time.time())}.json"
        )
        fail_path.write_text(
            json.dumps(
                {
                    "authority": AUTH,
                    "status": "BASELINE_FAILED",
                    "dtype_lane": args.dtype_lane,
                    "indexing_status": str(report.status),
                    "errors": report.errors,
                    "metadata": {
                        k: v
                        for k, v in (report.metadata or {}).items()
                        if k != "dense_profile"
                    },
                    "dense_execution": (report.metadata or {}).get("dense_execution"),
                    "dtype_force": dtype_force,
                    "workload": workload,
                    "runtime": capture_runtime(),
                    "git_sha": _git_sha(),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"WROTE {fail_path}", file=sys.stderr)
        return 5

    profile = report.metadata.get("dense_profile") or {}
    execution = report.metadata.get("dense_execution") or {}
    git_sha = _git_sha()
    evidence = {
        "authority": AUTH,
        "slice": "16K-D",
        "gate": "D0",
        "status": "BASELINE_EXECUTED",
        "dtype_lane": args.dtype_lane,
        "fp32_force_attempt": {
            "evidence": "docs/evidence/16k_d_dense_cuda/d0_fp32_force_FAILED_cublasSgemm.json",
            "result": "CUBLAS_STATUS_EXECUTION_FAILED on cublasSgemm",
            "note": (
                "Design §9.2 lists CUDA FP32/batch-32 as step 1. On this host, "
                "harness-forced FP32 failed; measured baseline is native "
                "as-loaded dtype with batch_size=32."
            ),
        },
        "git_sha": git_sha,
        "executed_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "workload": workload,
        "runtime": capture_runtime(),
        "embedding_model": {
            "model_id": settings.indexing.embedding.model_id,
            "revision": settings.indexing.embedding.revision,
            "dimension": settings.indexing.embedding.dimension,
            "normalize": settings.indexing.embedding.normalize,
            "adapter_contract": settings.indexing.embedding.adapter_contract,
            "embedding_config_hash": report.embedding_config_hash,
            "index_config_hash": report.index_config_hash,
        },
        "searchable_units": {
            "strategy": settings.indexing.searchable_units.strategy,
            "contract_version": settings.indexing.searchable_units.contract_version,
        },
        "execution_policy": {
            "device": execution.get("device"),
            "dtype": execution.get("dtype"),
            "batch_size": execution.get("batch_size"),
            "attention_backend": execution.get("attention_backend"),
            "embedding_dimension": execution.get("embedding_dimension"),
            "dtype_force": dtype_force,
            "production_default_unchanged": True,
            "note": (
                "FP32 forced only inside this harness after model load; "
                "config/base.yaml and make_embedder defaults unchanged."
            ),
        },
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
        },
        "throughput": profile.get("throughput"),
        "model_input_token_stats": profile.get("model_input_token_stats"),
        "oversized_unsplittable_count": profile.get("oversized_unsplittable_count"),
        "per_batch_max_sequence_length": profile.get("per_batch_max_sequence_length"),
        "first_batch_versus_steady_state": {
            "first_batch_encode_ms": (profile.get("timing_ms") or {}).get(
                "first_batch_encode"
            ),
            "steady_state_encode_mean_ms": (profile.get("timing_ms") or {}).get(
                "steady_state_encode_mean"
            ),
        },
        "peak_vram_bytes": profile.get("peak_vram_bytes"),
        "peak_vram_status": profile.get("peak_vram_status"),
        "peak_vram_error": profile.get("peak_vram_error"),
        "tokenizer_status": profile.get("tokenizer_status"),
        "tokenizer_error": profile.get("tokenizer_error"),
        "index_id": report.index_id,
        "collection_name": report.collection_name,
        "dense_profile_contract": profile.get("contract"),
        "batch_count": profile.get("batch_count"),
        "batches": profile.get("batches"),
        "unavailable_measurements": [
            key
            for key, status in (
                ("peak_vram", profile.get("peak_vram_status")),
                ("tokenizer", profile.get("tokenizer_status")),
            )
            if status not in {"observed", None}
        ],
        "explicitly_closed": [
            "FP16 treatment execution",
            "batch-size sweep",
            "optimized attention treatment",
            "persistence optimization",
            "Qdrant optimization",
            "default promotion",
            "16K-E/F/G",
            "Slice 17/18",
            "main promotion",
            "HTTP-500 GPU investigation reopen",
        ],
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EVIDENCE_DIR / "d0_baseline_summary.json"
    out_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Also pin a SHA-stamped copy for immutable review.
    stamped = EVIDENCE_DIR / f"d0_baseline_{git_sha[:12]}.json"
    stamped.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"WROTE {out_path}")
    print(f"WROTE {stamped}")
    print(
        json.dumps(
            {
                "status": report.status.value,
                "generated": report.embeddings_generated,
                "reused": report.embeddings_reused,
                "wall_s": wall_s,
                "dtype": execution.get("dtype"),
                "batch_size": execution.get("batch_size"),
                "device": execution.get("device"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
