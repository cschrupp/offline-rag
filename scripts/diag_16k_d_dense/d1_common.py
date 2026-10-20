"""Shared constants and helpers for 16K-D D1 scientific harness (no src changes)."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

AUTH = "S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001"
MATRIX_PARENT = "0ecf2f74e4d283f59ab932abbdaee6ebb821a5ac"
TOOLING_SUBJECT = "433725952c15a2feed4b65986d03e254d08d1568"
MATRIX_DOC = "docs/slice16k_d_d1_scientific_matrix_freeze.md"

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

WORKLOAD_LABEL = "D0-INCIDENT-1296-CHILD-V1"
EXPECTED_CHILD_COUNT = 1296
EXPECTED_BATCH_SIZE = 32
EXPECTED_BATCH_COUNT = 41
EXPECTED_CHUNK_MANIFEST_SHA256 = (
    "de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3"
)
EXPECTED_CORPUS_MANIFEST_SHA256 = (
    "69cefa61214e0e5e0a5eb71df01e323ede6f1807226181ef4134faeceb91b353"
)
EXPECTED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
PROFILE_CONTRACT = "dense-cuda-profile-v2"

# Frozen D1-B membership (0-based batch_index from D0).
D1B_BATCH_INDICES = (1, 14, 17, 13, 4, 6)
D1B_CELL_BY_INDEX = {
    1: "F1",
    14: "S1",
    17: "F2",
    13: "S2",
    4: "D1",
    6: "D2",
}

# Counterbalanced pair blocks → 36 measured encodes.
D1B_ENCODE_ORDER: tuple[int, ...] = (
    # P1: 1↔14
    1,
    14,
    14,
    1,
    1,
    14,
    14,
    1,
    1,
    14,
    14,
    1,
    # P2: 17↔13
    17,
    13,
    13,
    17,
    17,
    13,
    13,
    17,
    17,
    13,
    13,
    17,
    # P3: 4↔6
    4,
    6,
    6,
    4,
    4,
    6,
    6,
    4,
    4,
    6,
    6,
    4,
)

EVIDENCE_DIR = ROOT / "docs/evidence/16k_d_dense_cuda/d1"
SOURCE_PATHS = (
    Path("scripts/diag_16k_d_dense/run_d1_scientific.py"),
    Path("scripts/diag_16k_d_dense/d1_common.py"),
    Path("src/offline_rag/dense/profiling.py"),
    Path("src/offline_rag/dense/pipeline.py"),
)


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def git_tracked_clean() -> tuple[bool, str]:
    """Fail closed if tracked files are dirty (untracked work dirs allowed)."""
    out = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    dirty = [
        line
        for line in out.splitlines()
        if line and not line.startswith("??") and not line.startswith("!!")
    ]
    if dirty:
        return False, "tracked_working_tree_dirty: " + "; ".join(dirty[:20])
    return True, "clean_tracked"


def source_digests() -> dict[str, str]:
    return {str(p): sha256_file(ROOT / p) for p in SOURCE_PATHS}


def symlink_or_copy(src: Path, dest: Path) -> None:
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
    """Isolated OFFLINE_RAG_DATA_DIR with empty embeddings/qdrant (cold)."""
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    for name in ("manifests", "chunks", "chunk-manifests", "processed"):
        symlink_or_copy(ROOT / "data" / name, work_root / name)

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
    return work_root


def workload_identity() -> dict[str, Any]:
    chunk_manifest = ROOT / "data/chunk-manifests" / f"{CHUNK_SET_ID}.json"
    corpus_manifest = ROOT / "data/manifests" / f"{CORPUS_ID}.json"
    child_count = json.loads(chunk_manifest.read_text(encoding="utf-8")).get(
        "total_child_count"
    )
    return {
        "label": WORKLOAD_LABEL,
        "corpus_id": CORPUS_ID,
        "chunk_set_id": CHUNK_SET_ID,
        "historical_dense_index_id": DENSE_INDEX_ID,
        "child_count": child_count,
        "chunk_manifest_sha256": sha256_file(chunk_manifest),
        "corpus_manifest_sha256": sha256_file(corpus_manifest),
        "cold_or_warm": "cold",
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


def enrich_batch_wall_minus_device(batch: dict[str, Any]) -> dict[str, Any]:
    """Attach wall_minus_device_ms when both timings are available."""
    out = dict(batch)
    wall = out.get("encode_ms")
    device = out.get("encode_cuda_device_ms")
    status = out.get("encode_cuda_device_status")
    if (
        isinstance(wall, (int, float))
        and isinstance(device, (int, float))
        and status == "observed"
    ):
        out["wall_minus_device_ms"] = float(wall) - float(device)
    else:
        out["wall_minus_device_ms"] = None
    return out


def d1b_schedule() -> list[dict[str, Any]]:
    """Expand frozen encode order into repetition metadata."""
    counts: dict[int, int] = {i: 0 for i in D1B_BATCH_INDICES}
    schedule: list[dict[str, Any]] = []
    for call_index, batch_index in enumerate(D1B_ENCODE_ORDER):
        counts[batch_index] += 1
        schedule.append(
            {
                "call_index": call_index,
                "batch_index": batch_index,
                "cell": D1B_CELL_BY_INDEX[batch_index],
                "repetition": counts[batch_index],
                "block": (
                    "P1"
                    if call_index < 12
                    else ("P2" if call_index < 24 else "P3")
                ),
            }
        )
    return schedule


__all__ = [
    "ABANDONED_ROOT",
    "AUTH",
    "CHUNK_SET_ID",
    "CORPUS_ID",
    "CORPUS_NAME",
    "D1B_BATCH_INDICES",
    "D1B_CELL_BY_INDEX",
    "D1B_ENCODE_ORDER",
    "DENSE_INDEX_ID",
    "EVIDENCE_DIR",
    "EXPECTED_BATCH_COUNT",
    "EXPECTED_BATCH_SIZE",
    "EXPECTED_CHILD_COUNT",
    "EXPECTED_CHUNK_MANIFEST_SHA256",
    "EXPECTED_CORPUS_MANIFEST_SHA256",
    "EXPECTED_MODEL_ID",
    "EXPECTED_MODEL_REVISION",
    "MATRIX_DOC",
    "MATRIX_PARENT",
    "PROFILE_CONTRACT",
    "ROOT",
    "SOURCE_PATHS",
    "TOOLING_SUBJECT",
    "WORKLOAD_LABEL",
    "capture_runtime",
    "d1b_schedule",
    "enrich_batch_wall_minus_device",
    "git_sha",
    "git_tracked_clean",
    "prepare_isolated_tree",
    "sha256_file",
    "source_digests",
    "symlink_or_copy",
    "utc_now",
    "workload_identity",
]
