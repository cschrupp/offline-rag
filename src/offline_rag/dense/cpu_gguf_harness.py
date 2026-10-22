"""CPU-GGUF-01 llama.cpp Q8_0 feasibility harness (execution-locked).

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001

Implements Stage-0 artifact/runtime compat, 128-child screen, and
d2-retrieval-parity-v1 scaffolding behind ``EXECUTION_AUTHORIZED``. While False,
scientific entrypoints refuse without launching llama-server or touching the
sample workload. When True, entrypoints delegate to ``cpu_gguf_executor``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.dense.cpu_gguf_feasibility import (
    DESIGN_DOC,
    EXACT_PARENT,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_DIMENSION,
    EXPECTED_GGUF_FILENAME,
    EXPECTED_GGUF_REPO_ID,
    EXPECTED_GGUF_REVISION,
    EXPECTED_GGUF_SHA256,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    EXPERIMENT_ID,
    FROZEN_BACKEND,
    FROZEN_BATCH_SIZE,
    FROZEN_DEVICE,
    FROZEN_NORMALIZE,
    FROZEN_N_GPU_LAYERS,
    FROZEN_POOLING,
    FROZEN_QUANT,
    FROZEN_THREADS,
    FROZEN_THREADS_BATCH,
    IMPLEMENTATION_AUTH,
    PARITY_CONTRACT_ID,
    PARITY_DOC_COUNT,
    PARITY_QUERY_COUNT,
    PARITY_THRESHOLDS,
    SCREEN_CHILD_COUNT,
    WORKLOAD_LABEL,
    StageResult,
    assert_frozen_runtime_knobs,
    assert_transition_allowed,
    plan_next,
    plan_to_dict,
    project_full_minutes,
    refuse_hub_substitution,
)
from offline_rag.dense.cpu_gguf_server import (
    probe_llama_server_binary,
    verify_official_gguf,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_screen_chunk_ids(all_chunk_ids: list[str]) -> list[str]:
    """Deterministic 128-child screen population (same digest as CPU-OV/ONNX)."""
    if len(all_chunk_ids) != EXPECTED_CHILD_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CHILD_COUNT} chunk ids, got {len(all_chunk_ids)}"
        )
    ranked = sorted(all_chunk_ids, key=sha256_text)
    selected = ranked[:SCREEN_CHILD_COUNT]
    digest = sha256_text("\n".join(selected))
    if digest != EXPECTED_SCREEN_CHUNK_IDS_DIGEST:
        raise ValueError(
            f"screen digest mismatch: observed={digest} "
            f"expected={EXPECTED_SCREEN_CHUNK_IDS_DIGEST}"
        )
    return selected


def select_parity_populations(
    all_chunk_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Reuse d2-retrieval-parity-v1 selection: first 64 by sha256(chunk_id), first 16 queries."""
    if len(all_chunk_ids) != EXPECTED_CHILD_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CHILD_COUNT} chunk ids, got {len(all_chunk_ids)}"
        )
    ranked = sorted(all_chunk_ids, key=sha256_text)
    docs = ranked[:PARITY_DOC_COUNT]
    queries = docs[:PARITY_QUERY_COUNT]
    return docs, queries


def load_chunk_ids_from_manifest(
    *,
    repo_root: Path | None = None,
) -> list[str]:
    """Load 1296 child ids only after frozen manifest SHA256 matches."""
    root = repo_root or _repo_root()
    manifest_path = (
        root / "data" / "chunk-manifests" / f"{EXPECTED_CHUNK_SET_ID}.json"
    )
    if not manifest_path.is_file():
        raise FileNotFoundError(f"chunk manifest missing: {manifest_path}")
    observed_sha = sha256_file(manifest_path)
    if observed_sha != EXPECTED_CHUNK_MANIFEST_SHA256:
        raise ValueError(
            "chunk manifest SHA256 mismatch: "
            f"observed={observed_sha} expected={EXPECTED_CHUNK_MANIFEST_SHA256}"
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("total_child_count") != EXPECTED_CHILD_COUNT:
        raise ValueError("chunk manifest child count mismatch")
    children: list[str] = []
    for doc in payload["documents"]:
        rel = doc["chunk_artifact"]
        path = root / "data" / rel
        if not path.is_file():
            path = root / rel
        art = json.loads(path.read_text(encoding="utf-8"))
        for child in art["children"]:
            children.append(str(child["chunk_id"]))
    if len(children) != EXPECTED_CHILD_COUNT:
        raise ValueError(f"loaded {len(children)} children")
    if len(set(children)) != len(children):
        raise ValueError("duplicate chunk_ids")
    return children


def preflight_gguf_and_binary(
    *,
    gguf_path: Path | None,
    llama_server_path: Path | None,
) -> dict[str, Any]:
    """Non-mutating preflight for locked responses (no server launch)."""
    out: dict[str, Any] = {
        "gguf_path": str(gguf_path) if gguf_path else None,
        "llama_server_path": str(llama_server_path) if llama_server_path else None,
        "gguf_ok": False,
        "binary_ok": False,
        "gguf_identity": None,
        "binary_identity": None,
        "gguf_error": None,
        "binary_error": None,
    }
    if gguf_path is None:
        out["gguf_error"] = "gguf_path not supplied"
    else:
        try:
            refuse_hub_substitution(
                local_gguf_exists=Path(gguf_path).is_file(),
                allow_download=False,
            )
            identity = verify_official_gguf(Path(gguf_path))
            out["gguf_ok"] = True
            out["gguf_identity"] = {
                "path": identity.path,
                "sha256": identity.sha256,
                "size_bytes": identity.size_bytes,
                "repo": identity.repo,
                "revision": identity.revision,
                "filename": identity.filename,
            }
        except Exception as exc:  # noqa: BLE001
            out["gguf_error"] = f"{type(exc).__name__}: {exc}"

    if llama_server_path is None:
        out["binary_error"] = "llama_server_path not supplied"
    else:
        try:
            identity = probe_llama_server_binary(Path(llama_server_path))
            out["binary_ok"] = True
            out["binary_identity"] = {
                "absolute_path": identity.absolute_path,
                "binary_sha256": identity.binary_sha256,
                "version_output": identity.version_output[:500],
                "cpu_architecture": identity.cpu_architecture,
            }
        except Exception as exc:  # noqa: BLE001
            out["binary_error"] = f"{type(exc).__name__}: {exc}"
    return out


@dataclass(frozen=True)
class LockedRefusal:
    status: str
    payload: dict[str, Any]


def _locked_payload(
    *,
    requested_action: str,
    history: list[StageResult],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = plan_next(history)
    body: dict[str, Any] = {
        "authority": IMPLEMENTATION_AUTH,
        "exact_parent": EXACT_PARENT,
        "experiment_id": EXPERIMENT_ID,
        "design_doc": DESIGN_DOC,
        "status": "EXECUTION_NOT_AUTHORIZED",
        "execution_authorized": EXECUTION_AUTHORIZED,
        "requested_action": requested_action,
        "plan": plan_to_dict(plan),
        "frozen": {
            "gguf_repo": EXPECTED_GGUF_REPO_ID,
            "gguf_revision": EXPECTED_GGUF_REVISION,
            "gguf_filename": EXPECTED_GGUF_FILENAME,
            "gguf_sha256": EXPECTED_GGUF_SHA256,
            "quant": FROZEN_QUANT,
            "dimension": EXPECTED_DIMENSION,
            "batch_size": FROZEN_BATCH_SIZE,
            "normalize": FROZEN_NORMALIZE,
            "device": FROZEN_DEVICE,
            "backend": FROZEN_BACKEND,
            "pooling": FROZEN_POOLING,
            "n_gpu_layers": FROZEN_N_GPU_LAYERS,
            "threads": FROZEN_THREADS,
            "threads_batch": FROZEN_THREADS_BATCH,
            "workload": WORKLOAD_LABEL,
            "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
            "screen_children": SCREEN_CHILD_COUNT,
            "screen_chunk_ids_digest": EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
            "parity_contract": PARITY_CONTRACT_ID,
            "parity_thresholds": PARITY_THRESHOLDS,
        },
        "note": (
            "Harness + executor machinery is implemented but llama.cpp scientific "
            "execution remains locked. A later Stage-0 AUTH must set "
            "EXECUTION_AUTHORIZED before GGUF provisioning smoke or any "
            "screen/parity/full run. No Hub download during scientific execution."
        ),
        "executor_implemented": True,
        "recorded_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }
    if extra:
        body.update(extra)
    return body


def require_execution_unlocked() -> None:
    if not EXECUTION_AUTHORIZED:
        raise PermissionError(
            "CPU-GGUF feasibility scientific execution is not authorized "
            f"(EXECUTION_AUTHORIZED=False under {IMPLEMENTATION_AUTH})"
        )


def _default_evidence_dir(repo_root: Path | None) -> Path:
    root = repo_root or _repo_root()
    return root / "data" / "16k_d_cpu_gguf_work" / "evidence"


def _assert_frozen_knobs() -> None:
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=FROZEN_NORMALIZE,
        device=FROZEN_DEVICE,
        backend=FROZEN_BACKEND,
        pooling=FROZEN_POOLING,
        n_gpu_layers=FROZEN_N_GPU_LAYERS,
        threads=FROZEN_THREADS,
        threads_batch=FROZEN_THREADS_BATCH,
    )


def run_stage0_compat(
    *,
    history: list[StageResult],
    gguf_path: Path | None = None,
    llama_server_path: Path | None = None,
    allow_download: bool = False,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Stage-0 artifact/runtime compatibility. Locked while EXECUTION_AUTHORIZED is False."""
    assert_transition_allowed(history, "run_stage0_compat")
    _assert_frozen_knobs()
    if allow_download:
        refuse_hub_substitution(local_gguf_exists=True, allow_download=True)
    preflight = preflight_gguf_and_binary(
        gguf_path=gguf_path,
        llama_server_path=llama_server_path,
    )
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action="run_stage0_compat",
            history=history,
            extra={
                "preflight": preflight,
                "executor_ready": True,
                "stage0_checks": [
                    "exact_gguf_sha256",
                    "llama_server_identity",
                    "cpu_only_n_gpu_layers_0",
                    "pooling_last",
                    "server_ready",
                    "synthetic_document_embedding",
                    "synthetic_query_embedding",
                    "dim_1024_finite_normalized",
                    "clean_shutdown",
                ],
            },
        )
    require_execution_unlocked()
    if gguf_path is None or llama_server_path is None:
        raise ValueError(
            "gguf_path and llama_server_path are required when execution is unlocked"
        )
    from offline_rag.dense import cpu_gguf_executor as ex

    return ex.execute_stage0_compat(
        gguf_path=Path(gguf_path),
        llama_server_path=Path(llama_server_path),
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_screen(
    *,
    history: list[StageResult],
    gguf_path: Path | None = None,
    llama_server_path: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Exactly one 128-child Q8_0 speed screen."""
    assert_transition_allowed(history, "run_screen_q8_0")
    _assert_frozen_knobs()
    chunk_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    selected = select_screen_chunk_ids(chunk_ids)
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action="run_screen_q8_0",
            history=history,
            extra={
                "screen_chunk_ids_digest": sha256_text("\n".join(selected)),
                "screen_child_count": len(selected),
                "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
                "application_request_batch": FROZEN_BATCH_SIZE,
                "expected_request_count": SCREEN_CHILD_COUNT // FROZEN_BATCH_SIZE,
                "preflight": preflight_gguf_and_binary(
                    gguf_path=gguf_path,
                    llama_server_path=llama_server_path,
                ),
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    if gguf_path is None or llama_server_path is None:
        raise ValueError(
            "gguf_path and llama_server_path are required when execution is unlocked"
        )
    from offline_rag.dense import cpu_gguf_executor as ex

    return ex.execute_screen(
        gguf_path=Path(gguf_path),
        llama_server_path=Path(llama_server_path),
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_parity(
    *,
    history: list[StageResult],
    gguf_path: Path | None = None,
    llama_server_path: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """d2-retrieval-parity-v1 scaffolding (implemented; not executed while locked)."""
    assert_transition_allowed(history, "run_parity_q8_0")
    chunk_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    docs, queries = select_parity_populations(chunk_ids)
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action="run_parity_q8_0",
            history=history,
            extra={
                "parity_contract": PARITY_CONTRACT_ID,
                "parity_thresholds": PARITY_THRESHOLDS,
                "document_count": len(docs),
                "query_count": len(queries),
                "document_ids_digest": sha256_text("\n".join(docs)),
                "query_ids_digest": sha256_text("\n".join(queries)),
                "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
                "reference_lane": "cuda/fp16/batch32 (D2 G1 selected candidate)",
                "candidate_lane": "llama_cpp/cpu/q8_0/pooling_last/batch32",
                "preflight": preflight_gguf_and_binary(
                    gguf_path=gguf_path,
                    llama_server_path=llama_server_path,
                ),
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    if gguf_path is None or llama_server_path is None:
        raise ValueError(
            "gguf_path and llama_server_path are required when execution is unlocked"
        )
    from offline_rag.dense import cpu_gguf_executor as ex

    return ex.execute_parity(
        gguf_path=Path(gguf_path),
        llama_server_path=Path(llama_server_path),
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_full_confirm(
    *,
    history: list[StageResult],
    selected_candidate: str = "q8_0",
    gguf_path: Path | None = None,
    llama_server_path: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Full 1296 confirmation interface (scaffolded; not executed under AUTH-001)."""
    del gguf_path, llama_server_path, evidence_dir  # unused while locked/unimplemented
    plan = plan_next(history)
    if not plan.full_confirm_eligible:
        raise ValueError(
            f"full confirm not eligible: terminal={plan.terminal} reason={plan.reason}"
        )
    if plan.selected_candidate != selected_candidate:
        raise ValueError(
            f"selected_candidate {selected_candidate!r} != plan "
            f"{plan.selected_candidate!r}"
        )
    assert_transition_allowed(history, "run_full_confirm")
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action="run_full_confirm",
            history=history,
            extra={
                "selected_candidate": selected_candidate,
                "full_confirm_eligible": True,
                "note_projection": (
                    "Projected screen minutes are never confirmation evidence; "
                    "full run must record measured wall_minutes only."
                ),
                "required_counts": {
                    "generated": EXPECTED_CHILD_COUNT,
                    "reused": 0,
                    "failed": 0,
                    "vectors_materialized": EXPECTED_CHILD_COUNT,
                    "dimension": EXPECTED_DIMENSION,
                    "full_wall_minutes_max": 25.0,
                },
                "executor_ready": True,
                "full_confirm_executor": False,
                "note": (
                    "AUTH-001 implements stage0/screen/parity interfaces only; "
                    "full confirm remains unimplemented until a later AUTH."
                ),
                "repo_root": str(repo_root) if repo_root else None,
            },
        )
    require_execution_unlocked()
    raise NotImplementedError(
        "CPU-GGUF full confirm is not implemented under AUTH-001; "
        "parity interface only. A later AUTH must authorize full confirm."
    )


def build_screen_result(
    *,
    chunks_per_sec: float,
    ok: bool = True,
    notes: str | None = None,
) -> StageResult:
    projected = project_full_minutes(chunks_per_sec)
    return StageResult(
        stage_id="screen_q8_0",
        ok=ok,
        chunks_per_sec=chunks_per_sec,
        projected_full_minutes=projected,
        full_wall_minutes=None,
        notes=notes,
    )


def build_full_confirm_result(
    *,
    full_wall_minutes: float,
    embeddings_generated: int = EXPECTED_CHILD_COUNT,
    embeddings_reused: int = 0,
    embeddings_failed: int = 0,
    vectors_materialized: int = EXPECTED_CHILD_COUNT,
    dimension: int = EXPECTED_DIMENSION,
    ok: bool = True,
    notes: str | None = None,
) -> StageResult:
    return StageResult(
        stage_id="full_confirm",
        ok=ok,
        full_wall_minutes=full_wall_minutes,
        embeddings_generated=embeddings_generated,
        embeddings_reused=embeddings_reused,
        embeddings_failed=embeddings_failed,
        vectors_materialized=vectors_materialized,
        dimension=dimension,
        projected_full_minutes=None,
        notes=notes,
    )


def environment_fingerprint() -> dict[str, Any]:
    return {
        "python": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "httpx": _optional_version("httpx"),
        "backend": FROZEN_BACKEND,
        "quant": FROZEN_QUANT,
    }


def _optional_version(mod_name: str) -> str | None:
    try:
        mod = __import__(mod_name)
        return getattr(mod, "__version__", "present_unknown_version")
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "LockedRefusal",
    "build_full_confirm_result",
    "build_screen_result",
    "environment_fingerprint",
    "load_chunk_ids_from_manifest",
    "preflight_gguf_and_binary",
    "require_execution_unlocked",
    "run_full_confirm",
    "run_parity",
    "run_screen",
    "run_stage0_compat",
    "select_parity_populations",
    "select_screen_chunk_ids",
    "sha256_file",
    "sha256_text",
]
