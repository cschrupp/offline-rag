"""OpenVINO CPU feasibility harness (execution-locked).

Authority: S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001

Implements Stage-0..4 machinery behind ``EXECUTION_AUTHORIZED``. While False,
scientific entrypoints refuse without invoking OpenVINO or the sample workload.
When True, entrypoints delegate to ``cpu_ov_executor`` (real ST/OpenVINO path).
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.dense.cpu_ov_feasibility import (
    DESIGN_DOC,
    EXACT_PARENT,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_DIMENSION,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    EXPERIMENT_ID,
    FROZEN_BACKEND,
    FROZEN_BATCH_SIZE,
    FROZEN_DEVICE,
    FROZEN_NORMALIZE,
    IMPLEMENTATION_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    PARITY_CONTRACT_ID,
    PARITY_DOC_COUNT,
    PARITY_QUERY_COUNT,
    PARITY_THRESHOLDS,
    REWORK_PARENT,
    SCREEN_CHILD_COUNT,
    WORKLOAD_LABEL,
    FeasibilityPlan,
    StageResult,
    WeightFormat,
    assert_frozen_runtime_knobs,
    assert_transition_allowed,
    parity_thresholds_pass,
    plan_next,
    plan_to_dict,
    project_full_minutes,
    refuse_hub_substitution,
)
from offline_rag.dense.provision import (
    EmbeddingArtifactsUnavailableError,
    require_embedding_artifacts,
    validate_embedding_artifacts,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_export_tree(export_dir: Path) -> dict[str, Any]:
    """Hash OpenVINO export artifacts (.xml/.bin and siblings). Large blobs stay
    outside Git; digests are recorded in evidence.
    """
    if not export_dir.is_dir():
        raise FileNotFoundError(f"export_dir missing: {export_dir}")
    files: list[dict[str, Any]] = []
    for path in sorted(export_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(export_dir))
        files.append(
            {
                "relative_path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    digest_material = json.dumps(files, sort_keys=True, separators=(",", ":"))
    return {
        "export_dir": str(export_dir),
        "file_count": len(files),
        "files": files,
        "tree_sha256": hashlib.sha256(digest_material.encode("utf-8")).hexdigest(),
    }


def select_screen_chunk_ids(all_chunk_ids: list[str]) -> list[str]:
    """Deterministic 128-child screen population."""
    if len(all_chunk_ids) != EXPECTED_CHILD_COUNT:
        raise ValueError(
            f"expected {EXPECTED_CHILD_COUNT} chunk ids, got {len(all_chunk_ids)}"
        )
    ranked = sorted(all_chunk_ids, key=sha256_text)
    return ranked[:SCREEN_CHILD_COUNT]


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
    """Load 1296 child ids only after frozen manifest SHA256 matches (F002)."""
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


def resolve_local_pinned_model_dir(
    *,
    settings: Any | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve Seneca's locally provisioned pinned checkpoint (no Hub)."""
    root = repo_root or _repo_root()
    if settings is None:
        from offline_rag.config import load_settings

        settings = load_settings()
    from offline_rag.dense.provision import resolve_embedding_model_dir

    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    path = Path(model_dir)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def verify_local_model_identity(model_dir: Path) -> dict[str, Any]:
    """Fail closed via Seneca provisioning identity (F002).

    Directory + config.json alone is insufficient. Requires
    ``require_embedding_artifacts`` / digest-validated manifest matching the
    frozen Qwen revision ``97b0c614…``.
    """
    refuse_hub_substitution(
        local_model_dir_exists=model_dir.is_dir(),
        allow_download=False,
    )
    try:
        require_embedding_artifacts(
            model_dir,
            expected_model_id=EXPECTED_MODEL_ID,
            expected_revision=EXPECTED_MODEL_REVISION,
            expected_dimension=EXPECTED_DIMENSION,
        )
    except EmbeddingArtifactsUnavailableError as exc:
        raise ValueError(
            f"local embedding artifacts failed identity gate: {exc}"
        ) from exc

    status = validate_embedding_artifacts(
        model_dir,
        expected_model_id=EXPECTED_MODEL_ID,
        expected_revision=EXPECTED_MODEL_REVISION,
        expected_dimension=EXPECTED_DIMENSION,
    )
    if status.manifest is None:
        raise ValueError("embedding manifest missing after require_embedding_artifacts")
    resolved = status.manifest.resolved_revision
    if resolved != EXPECTED_MODEL_REVISION:
        raise ValueError(
            f"resolved_revision {resolved!r} != frozen {EXPECTED_MODEL_REVISION!r}"
        )
    return {
        "model_dir": str(model_dir),
        "model_id": EXPECTED_MODEL_ID,
        "expected_revision": EXPECTED_MODEL_REVISION,
        "resolved_revision": resolved,
        "artifact_id": status.manifest.artifact_id,
        "readiness": status.readiness.value,
        "config_exists": (model_dir / "config.json").is_file(),
    }


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
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "exact_parent": EXACT_PARENT,
        "rework_parent": REWORK_PARENT,
        "experiment_id": EXPERIMENT_ID,
        "design_doc": DESIGN_DOC,
        "status": "EXECUTION_NOT_AUTHORIZED",
        "execution_authorized": EXECUTION_AUTHORIZED,
        "requested_action": requested_action,
        "plan": plan_to_dict(plan),
        "frozen": {
            "model_id": EXPECTED_MODEL_ID,
            "model_revision": EXPECTED_MODEL_REVISION,
            "dimension": EXPECTED_DIMENSION,
            "batch_size": FROZEN_BATCH_SIZE,
            "normalize": FROZEN_NORMALIZE,
            "device": FROZEN_DEVICE,
            "backend": FROZEN_BACKEND,
            "workload": WORKLOAD_LABEL,
            "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
            "screen_children": SCREEN_CHILD_COUNT,
            "parity_contract": PARITY_CONTRACT_ID,
            "parity_thresholds": PARITY_THRESHOLDS,
        },
        "note": (
            "Harness + executor machinery is implemented but OpenVINO scientific "
            "execution remains locked. A later execution AUTH must set "
            "EXECUTION_AUTHORIZED before Stage-0 export or any screen/parity/full run."
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
            "CPU-OV feasibility scientific execution is not authorized "
            f"(EXECUTION_AUTHORIZED=False under {IMPLEMENTATION_REWORK_AUTH})"
        )


def _default_evidence_dir(repo_root: Path | None) -> Path:
    root = repo_root or _repo_root()
    return root / "data" / "16k_d_cpu_ov_work" / "evidence"


def run_export_compat(
    *,
    history: list[StageResult],
    export_dir: Path,
    weight_format: WeightFormat = "fp16",
    allow_download: bool = False,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    """Stage-0 FP16-only export/compat. Locked while EXECUTION_AUTHORIZED is False."""
    # F004: Stage 0 cannot perform INT8 preparation.
    if weight_format != "fp16":
        raise ValueError(
            "Stage-0 export_compat is FP16-only; INT8 preparation requires "
            "run_export_int8 after the planner opens INT8 eligibility"
        )
    assert_transition_allowed(history, "run_export_compat")
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=FROZEN_NORMALIZE,
        device=FROZEN_DEVICE,
        backend=FROZEN_BACKEND,
    )
    if allow_download:
        refuse_hub_substitution(local_model_dir_exists=True, allow_download=True)
    if not EXECUTION_AUTHORIZED:
        try:
            model_dir = resolve_local_pinned_model_dir(repo_root=repo_root)
            identity = verify_local_model_identity(model_dir)
            local_ok = True
            local_error = None
        except Exception as exc:  # noqa: BLE001
            identity = None
            local_ok = False
            local_error = f"{type(exc).__name__}: {exc}"
        return _locked_payload(
            requested_action="run_export_compat",
            history=history,
            extra={
                "weight_format": "fp16",
                "export_dir": str(export_dir),
                "local_model_preflight_ok": local_ok,
                "local_model_identity": identity,
                "local_model_preflight_error": local_error,
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    from offline_rag.dense import cpu_ov_executor as ex

    model_dir = resolve_local_pinned_model_dir(repo_root=repo_root)
    return ex.execute_export_compat(
        export_dir=export_dir,
        model_dir=model_dir,
        weight_format="fp16",
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_export_int8(
    *,
    history: list[StageResult],
    export_dir: Path,
    allow_download: bool = False,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
    calibration_texts: list[str] | None = None,
) -> dict[str, Any]:
    """Conditional INT8 preparation — only after planner opens INT8 (F004)."""
    assert_transition_allowed(history, "run_export_int8")
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=FROZEN_NORMALIZE,
        device=FROZEN_DEVICE,
        backend=FROZEN_BACKEND,
    )
    if allow_download:
        refuse_hub_substitution(local_model_dir_exists=True, allow_download=True)
    if not EXECUTION_AUTHORIZED:
        try:
            model_dir = resolve_local_pinned_model_dir(repo_root=repo_root)
            identity = verify_local_model_identity(model_dir)
            local_ok = True
            local_error = None
        except Exception as exc:  # noqa: BLE001
            identity = None
            local_ok = False
            local_error = f"{type(exc).__name__}: {exc}"
        return _locked_payload(
            requested_action="run_export_int8",
            history=history,
            extra={
                "weight_format": "int8",
                "export_dir": str(export_dir),
                "local_model_preflight_ok": local_ok,
                "local_model_identity": identity,
                "local_model_preflight_error": local_error,
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    from offline_rag.dense import cpu_ov_executor as ex

    model_dir = resolve_local_pinned_model_dir(repo_root=repo_root)
    return ex.execute_export_int8(
        export_dir=export_dir,
        model_dir=model_dir,
        calibration_texts=calibration_texts,
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_screen(
    *,
    history: list[StageResult],
    weight_format: WeightFormat,
    export_dir: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    action = "run_screen_fp16" if weight_format == "fp16" else "run_screen_int8"
    assert_transition_allowed(history, action)  # type: ignore[arg-type]
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=FROZEN_NORMALIZE,
        device=FROZEN_DEVICE,
        backend=FROZEN_BACKEND,
    )
    chunk_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    selected = select_screen_chunk_ids(chunk_ids)
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action=action,
            history=history,
            extra={
                "weight_format": weight_format,
                "screen_chunk_ids_digest": sha256_text("\n".join(selected)),
                "screen_child_count": len(selected),
                "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    if export_dir is None:
        raise ValueError("export_dir is required when execution is unlocked")
    from offline_rag.dense import cpu_ov_executor as ex

    return ex.execute_screen(
        export_dir=export_dir,
        weight_format=weight_format,
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_parity(
    *,
    history: list[StageResult],
    weight_format: WeightFormat,
    export_dir: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    action = "run_parity_fp16" if weight_format == "fp16" else "run_parity_int8"
    assert_transition_allowed(history, action)  # type: ignore[arg-type]
    chunk_ids = load_chunk_ids_from_manifest(repo_root=repo_root)
    docs, queries = select_parity_populations(chunk_ids)
    if not EXECUTION_AUTHORIZED:
        return _locked_payload(
            requested_action=action,
            history=history,
            extra={
                "weight_format": weight_format,
                "parity_contract": PARITY_CONTRACT_ID,
                "parity_thresholds": PARITY_THRESHOLDS,
                "document_count": len(docs),
                "query_count": len(queries),
                "document_ids_digest": sha256_text("\n".join(docs)),
                "query_ids_digest": sha256_text("\n".join(queries)),
                "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
                "reference_lane": "cuda/fp16/batch32 (D2 G1 selected candidate)",
                "candidate_lane": f"openvino/cpu/{weight_format}/batch32",
                "executor_ready": True,
            },
        )
    require_execution_unlocked()
    if export_dir is None:
        raise ValueError("export_dir is required when execution is unlocked")
    from offline_rag.dense import cpu_ov_executor as ex

    return ex.execute_parity(
        export_dir=export_dir,
        weight_format=weight_format,
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def run_full_confirm(
    *,
    history: list[StageResult],
    selected_candidate: WeightFormat,
    export_dir: Path | None = None,
    repo_root: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
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
            },
        )
    require_execution_unlocked()
    if export_dir is None:
        raise ValueError("export_dir is required when execution is unlocked")
    from offline_rag.dense import cpu_ov_executor as ex

    return ex.execute_full_confirm(
        export_dir=export_dir,
        weight_format=selected_candidate,
        repo_root=repo_root or _repo_root(),
        evidence_dir=evidence_dir or _default_evidence_dir(repo_root),
    )


def build_screen_result(
    *,
    stage_id: str,
    chunks_per_sec: float,
    ok: bool = True,
    notes: str | None = None,
) -> StageResult:
    """Helper for later execution AUTH — keeps projection out of full_wall."""
    projected = project_full_minutes(chunks_per_sec)
    return StageResult(
        stage_id=stage_id,  # type: ignore[arg-type]
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
    """Record versions when available; never invent."""
    versions: dict[str, Any] = {
        "python": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "sentence_transformers": None,
        "openvino": None,
        "optimum": None,
        "optimum_intel": None,
    }
    for mod_name, key in (
        ("sentence_transformers", "sentence_transformers"),
        ("openvino", "openvino"),
        ("optimum", "optimum"),
        ("optimum_intel", "optimum_intel"),
    ):
        try:
            mod = __import__(mod_name)
            versions[key] = getattr(mod, "__version__", "present_unknown_version")
        except Exception:  # noqa: BLE001
            versions[key] = None
    return versions


__all__ = [
    "LockedRefusal",
    "build_full_confirm_result",
    "build_screen_result",
    "environment_fingerprint",
    "hash_export_tree",
    "load_chunk_ids_from_manifest",
    "parity_thresholds_pass",
    "plan_next",
    "require_execution_unlocked",
    "resolve_local_pinned_model_dir",
    "run_export_compat",
    "run_export_int8",
    "run_full_confirm",
    "run_parity",
    "run_screen",
    "select_parity_populations",
    "select_screen_chunk_ids",
    "sha256_file",
    "sha256_text",
    "verify_local_model_identity",
]
