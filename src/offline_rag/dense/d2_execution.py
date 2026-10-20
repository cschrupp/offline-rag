"""D2 fail-closed preflight and locked cell executor (16K-D).

Scientific execution remains gated by ``EXECUTION_AUTHORIZED`` in
``d2_campaign``. This module implements the real machinery so a later
execution AUTH can unlock without redesigning the runner.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.dense.d2_campaign import (
    ACCEPTED_DESIGN_SUBJECT,
    ALLOWED_CELLS,
    CELL_SPECS,
    CORPUS_NAME,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_CORPUS_ID,
    EXPECTED_CORPUS_MANIFEST_SHA256,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    EXPECTED_SEARCHABLE_UNITS_CONTRACT,
    EXPECTED_SEARCHABLE_UNITS_STRATEGY,
    ABANDONED_CORPUS_ROOT_REL,
    IMPLEMENTATION_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    WORKLOAD_LABEL,
    CellId,
    CellResult,
    CellSpec,
    assert_transition_allowed,
    cell_spec,
)
from offline_rag.dense.d2_observability import (
    capture_cpu_baseline_facts,
    capture_gpu_memory_facts,
    parity_probe_surface_status,
)
from offline_rag.dense.precision import classify_treatment_failure


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha(*, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=cwd or _repo_root(), text=True
    ).strip()


def git_tracked_clean(*, cwd: Path | None = None) -> tuple[bool, str]:
    out = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=cwd or _repo_root(), text=True
    )
    dirty = [
        line
        for line in out.splitlines()
        if line and not line.startswith("??") and not line.startswith("!!")
    ]
    if dirty:
        return False, "tracked_working_tree_dirty: " + "; ".join(dirty[:20])
    return True, "clean_tracked"


def _dir_is_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    return False


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


def prepare_isolated_tree(work_root: Path, *, repo_root: Path | None = None) -> Path:
    """Build isolated OFFLINE_RAG_DATA_DIR with empty embeddings/qdrant."""
    root = repo_root or _repo_root()
    abandoned = root / ABANDONED_CORPUS_ROOT_REL
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    for name in ("manifests", "chunks", "chunk-manifests", "processed"):
        _symlink_or_copy(root / "data" / name, work_root / name)

    (work_root / "embeddings").mkdir()
    (work_root / "qdrant").mkdir()
    (work_root / "index-manifests").mkdir()
    (work_root / "locks").mkdir()
    (work_root / "staging").mkdir()
    (work_root / "traces").mkdir()

    corpus_dir = work_root / "corpora" / CORPUS_NAME
    (corpus_dir / "chunking").mkdir(parents=True)

    corpus_state = json.loads((abandoned / "state.json").read_text(encoding="utf-8"))
    corpus_state["corpus_name"] = CORPUS_NAME
    (corpus_dir / "state.json").write_text(
        json.dumps(corpus_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    chunk_state = json.loads(
        (abandoned / "chunking" / "state.json").read_text(encoding="utf-8")
    )
    chunk_state["corpus_name"] = CORPUS_NAME
    (corpus_dir / "chunking" / "state.json").write_text(
        json.dumps(chunk_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return work_root


def observe_workload_identity(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Hash and read actual frozen manifests from the repository data tree."""
    root = repo_root or _repo_root()
    chunk_manifest = root / "data/chunk-manifests" / f"{EXPECTED_CHUNK_SET_ID}.json"
    corpus_manifest = root / "data/manifests" / f"{EXPECTED_CORPUS_ID}.json"
    observed: dict[str, Any] = {
        "label": WORKLOAD_LABEL,
        "chunk_manifest_path": str(chunk_manifest),
        "corpus_manifest_path": str(corpus_manifest),
        "chunk_manifest_exists": chunk_manifest.is_file(),
        "corpus_manifest_exists": corpus_manifest.is_file(),
        "chunk_set_id": EXPECTED_CHUNK_SET_ID,
        "corpus_id": EXPECTED_CORPUS_ID,
        "child_count": None,
        "chunk_manifest_sha256": None,
        "corpus_manifest_sha256": None,
        "chunk_manifest_declared_chunk_set_id": None,
        "chunk_manifest_declared_corpus_id": None,
        "corpus_manifest_declared_corpus_id": None,
    }
    if chunk_manifest.is_file():
        payload = json.loads(chunk_manifest.read_text(encoding="utf-8"))
        observed["child_count"] = payload.get("total_child_count")
        observed["chunk_manifest_declared_chunk_set_id"] = payload.get("chunk_set_id")
        observed["chunk_manifest_declared_corpus_id"] = payload.get("corpus_id")
        observed["chunk_manifest_sha256"] = sha256_file(chunk_manifest)
    if corpus_manifest.is_file():
        payload = json.loads(corpus_manifest.read_text(encoding="utf-8"))
        observed["corpus_manifest_declared_corpus_id"] = payload.get("corpus_id")
        observed["corpus_manifest_sha256"] = sha256_file(corpus_manifest)
    return observed


def cell_environ(spec: CellSpec) -> dict[str, str]:
    """Env overrides that pin a frozen cell without changing production defaults."""
    return {
        "OFFLINE_RAG_EMBEDDING_DEVICE": spec.device,
        "OFFLINE_RAG_EMBEDDING_PRECISION": spec.precision,
        "OFFLINE_RAG_EMBEDDING_BATCH_SIZE": str(spec.batch_size),
    }


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    issues: tuple[str, ...]
    payload: dict[str, Any]


def run_d2_preflight(
    *,
    cell_id: str | None = None,
    work_root: Path | None = None,
    require_design_subject: bool = False,
    repo_root: Path | None = None,
    prepare_tree: bool = False,
) -> PreflightResult:
    """Fail-closed verification of workload, settings, and isolation facts."""
    root = repo_root or _repo_root()
    issues: list[str] = []
    clean, clean_detail = git_tracked_clean(cwd=root)
    head = git_sha(cwd=root)
    if not clean:
        issues.append(clean_detail)
    if require_design_subject and head != ACCEPTED_DESIGN_SUBJECT:
        issues.append(
            f"execution_head_mismatch: head={head} "
            f"expected_design_subject={ACCEPTED_DESIGN_SUBJECT}"
        )

    workload = observe_workload_identity(repo_root=root)
    if not workload["chunk_manifest_exists"]:
        issues.append("chunk_manifest_missing")
    if not workload["corpus_manifest_exists"]:
        issues.append("corpus_manifest_missing")
    if workload["chunk_manifest_sha256"] != EXPECTED_CHUNK_MANIFEST_SHA256:
        issues.append(
            f"chunk_manifest_sha256_mismatch:"
            f"observed={workload['chunk_manifest_sha256']}"
        )
    if workload["corpus_manifest_sha256"] != EXPECTED_CORPUS_MANIFEST_SHA256:
        issues.append(
            f"corpus_manifest_sha256_mismatch:"
            f"observed={workload['corpus_manifest_sha256']}"
        )
    if workload["child_count"] != EXPECTED_CHILD_COUNT:
        issues.append(f"child_count_mismatch:observed={workload['child_count']}")
    declared_chunk = workload.get("chunk_manifest_declared_chunk_set_id")
    if declared_chunk != EXPECTED_CHUNK_SET_ID:
        issues.append(f"chunk_set_id_mismatch:observed={declared_chunk}")
    declared_corpus = workload.get("corpus_manifest_declared_corpus_id")
    if declared_corpus != EXPECTED_CORPUS_ID:
        issues.append(f"corpus_id_mismatch:observed={declared_corpus}")
    chunk_corpus = workload.get("chunk_manifest_declared_corpus_id")
    if chunk_corpus != EXPECTED_CORPUS_ID:
        issues.append(f"chunk_manifest_corpus_id_mismatch:observed={chunk_corpus}")

    prepared_root: Path | None = None
    if work_root is not None and prepare_tree:
        prepared_root = prepare_isolated_tree(work_root, repo_root=root)

    isolation_root = prepared_root or work_root
    isolation: dict[str, Any] = {
        "work_root": str(isolation_root) if isolation_root else None,
        "embeddings_empty": None,
        "qdrant_empty": None,
    }
    if isolation_root is not None:
        emb = isolation_root / "embeddings"
        qdr = isolation_root / "qdrant"
        emb_empty = _dir_is_empty(emb)
        qdr_empty = _dir_is_empty(qdr)
        isolation["embeddings_empty"] = emb_empty
        isolation["qdrant_empty"] = qdr_empty
        if not emb_empty:
            issues.append("isolated_embeddings_not_empty")
        if not qdr_empty:
            issues.append("isolated_qdrant_not_empty")
    else:
        issues.append("work_root_required_for_isolation_check")

    # Effective settings for the cell (or defaults when no cell).
    from offline_rag.config import load_settings

    environ = dict(os.environ)
    spec: CellSpec | None = None
    if cell_id is not None:
        if cell_id not in ALLOWED_CELLS:
            issues.append(f"unauthorized_cell:{cell_id}")
        else:
            spec = cell_spec(cell_id)
            environ.update(cell_environ(spec))
    if isolation_root is not None:
        environ["OFFLINE_RAG_DATA_DIR"] = str(isolation_root.resolve())

    settings = load_settings(environ=environ)
    emb = settings.indexing.embedding
    units = settings.indexing.searchable_units
    effective = {
        "strict_offline": bool(settings.project.strict_offline),
        "model_id": emb.model_id,
        "model_revision": emb.revision,
        "configured_device": emb.device,
        "configured_precision": emb.precision,
        "batch_size": int(emb.batch_size),
        "searchable_units_strategy": units.strategy,
        "searchable_units_contract": units.contract_version,
    }
    if not effective["strict_offline"]:
        issues.append("strict_offline_false")
    if effective["model_id"] != EXPECTED_MODEL_ID:
        issues.append(f"model_id_mismatch:observed={effective['model_id']}")
    if effective["model_revision"] != EXPECTED_MODEL_REVISION:
        issues.append(f"model_revision_mismatch:observed={effective['model_revision']}")
    if (
        effective["searchable_units_strategy"] != EXPECTED_SEARCHABLE_UNITS_STRATEGY
        or effective["searchable_units_contract"]
        != EXPECTED_SEARCHABLE_UNITS_CONTRACT
    ):
        issues.append(
            "searchable_units_mismatch:"
            f"{effective['searchable_units_strategy']}/"
            f"{effective['searchable_units_contract']}"
        )
    if spec is not None:
        if effective["configured_device"] != spec.device:
            # auto is not a frozen D2 cell device; cells pin cpu/cuda.
            issues.append(
                f"device_mismatch:observed={effective['configured_device']}"
                f":expected={spec.device}"
            )
        if effective["configured_precision"] != spec.precision:
            issues.append(
                f"precision_mismatch:observed={effective['configured_precision']}"
                f":expected={spec.precision}"
            )
        if effective["batch_size"] != spec.batch_size:
            issues.append(
                f"batch_size_mismatch:observed={effective['batch_size']}"
                f":expected={spec.batch_size}"
            )

    # Device resolution facts (no model encode).
    from offline_rag.dense.device import resolve_embedding_device
    from offline_rag.dense.precision import resolve_embedding_precision

    runtime_facts: dict[str, Any] = {
        "resolved_device": None,
        "resolved_precision": None,
        "cuda_available": None,
        "device_selection_reason": None,
        "precision_selection_reason": None,
    }
    try:
        device_res = resolve_embedding_device(effective["configured_device"])
        runtime_facts["resolved_device"] = device_res.resolved_device
        runtime_facts["cuda_available"] = device_res.cuda_available
        runtime_facts["device_selection_reason"] = device_res.selection_reason
        prec_res = resolve_embedding_precision(
            effective["configured_precision"],
            resolved_device=device_res.resolved_device,
        )
        runtime_facts["resolved_precision"] = prec_res.resolved_precision
        runtime_facts["precision_selection_reason"] = prec_res.selection_reason
        if spec is not None and device_res.resolved_device != spec.device:
            issues.append(
                f"resolved_device_mismatch:observed={device_res.resolved_device}"
                f":expected={spec.device}"
            )
        if spec is not None and prec_res.resolved_precision != spec.precision:
            issues.append(
                f"resolved_precision_mismatch:observed={prec_res.resolved_precision}"
                f":expected={spec.precision}"
            )
    except Exception as exc:  # noqa: BLE001
        issues.append(f"device_precision_resolve_failed:{type(exc).__name__}:{exc}")

    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "execution_head": head,
        "require_design_subject": require_design_subject,
        "tracked_tree": clean_detail,
        "tracked_clean": clean,
        "workload_expected": {
            "label": WORKLOAD_LABEL,
            "searchable_children": EXPECTED_CHILD_COUNT,
            "chunk_set_id": EXPECTED_CHUNK_SET_ID,
            "corpus_id": EXPECTED_CORPUS_ID,
            "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
            "corpus_manifest_sha256": EXPECTED_CORPUS_MANIFEST_SHA256,
            "model_id": EXPECTED_MODEL_ID,
            "model_revision": EXPECTED_MODEL_REVISION,
            "searchable_units_strategy": EXPECTED_SEARCHABLE_UNITS_STRATEGY,
            "searchable_units_contract": EXPECTED_SEARCHABLE_UNITS_CONTRACT,
        },
        "workload_observed": workload,
        "effective_settings": effective,
        "runtime_facts": runtime_facts,
        "isolation": isolation,
        "parity_probe": parity_probe_surface_status(),
        "execution_authorized": EXECUTION_AUTHORIZED,
        "cell": cell_id,
        "cell_spec": (
            {
                "device": spec.device,
                "precision": spec.precision,
                "batch_size": spec.batch_size,
            }
            if spec is not None
            else None
        ),
        "issues": issues,
        "status": "PREFLIGHT_OK" if not issues else "PREFLIGHT_FAILED",
        "recorded_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
    }
    return PreflightResult(ok=not issues, issues=tuple(issues), payload=payload)


def _append_history(path: Path, result: CellResult) -> None:
    items: list[dict[str, Any]] = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else list(data.get("history", []))
    items.append(asdict(result))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def execute_d2_cell_unlocked(
    *,
    cell_id: CellId | str,
    work_root: Path,
    history_path: Path | None = None,
    evidence_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Real cold-cell executor (preflight → index → evidence → history).

    Callers must only invoke this when scientific execution is authorized.
    ``execute_d2_cell`` is the authority-gated public entrypoint.
    """
    root = repo_root or _repo_root()
    if cell_id not in ALLOWED_CELLS:
        raise ValueError(f"unauthorized D2 cell: {cell_id!r}")
    spec = cell_spec(str(cell_id))

    if history_path is not None and history_path.exists():
        raw = json.loads(history_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("history", [])
        history = [
            CellResult(
                cell_id=i["cell_id"],
                validity=i["validity"],
                wall_minutes=i.get("wall_minutes"),
                parity_ok=i.get("parity_ok"),
                correctness_ok=i.get("correctness_ok"),
            )
            for i in items
        ]
        assert_transition_allowed(history, str(cell_id))

    preflight = run_d2_preflight(
        cell_id=str(cell_id),
        work_root=work_root,
        require_design_subject=False,
        repo_root=root,
        prepare_tree=True,
    )
    if not preflight.ok:
        return {
            "status": "PREFLIGHT_FAILED",
            "cell": cell_id,
            "preflight": preflight.payload,
            "executor_ready": True,
        }

    environ = dict(os.environ)
    environ.update(cell_environ(spec))
    environ["OFFLINE_RAG_DATA_DIR"] = str(work_root.resolve())
    # D2 uses production-representative timing — no D1 CUDA-event sync profile.
    environ.pop("OFFLINE_RAG_DIAG_DENSE_PROFILE", None)

    from offline_rag.config import load_settings
    from offline_rag.dense.embedder import make_embedder, observe_embedder_execution_facts
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.domain.indexing import IndexingStatus

    settings = load_settings(environ=environ)
    identity_correct = True
    wall_s: float | None = None
    validity = "invalid"
    report_payload: dict[str, Any] = {}
    cpu_facts: dict[str, Any] = {}
    gpu_facts: dict[str, Any] = {}
    try:
        embedder = make_embedder(settings)
        load = getattr(embedder, "_load", None)
        if callable(load):
            load()
        observed = observe_embedder_execution_facts(embedder)
        if spec.precision == "fp16":
            dtype = str(observed.get("dtype") or "").removeprefix("torch.")
            if dtype not in {"float16", "torch.float16"}:
                raise RuntimeError(
                    f"pre-encode dtype not float16 after FP16 policy: {dtype!r}"
                )
        if spec.device == "cpu":
            cpu_facts = capture_cpu_baseline_facts(
                embedder=embedder, batch_size=spec.batch_size
            )
        started = time.perf_counter()
        report = run_indexing(
            settings=settings,
            corpus_name=CORPUS_NAME,
            embedder=embedder,
        )
        wall_s = time.perf_counter() - started
        gpu_facts = capture_gpu_memory_facts()
        meta = report.metadata or {}
        execution = meta.get("dense_execution") or {}
        report_payload = {
            "indexing_status": str(report.status),
            "errors": list(report.errors or []),
            "embeddings_generated": report.embeddings_generated,
            "embeddings_reused": report.embeddings_reused,
            "embeddings_failed": report.embeddings_failed,
            "vectors_materialized": report.vectors_materialized,
            "children_total": report.children_total,
            "dense_generation_ms": meta.get("dense_generation_ms"),
            "dense_materialization_ms": meta.get("dense_materialization_ms"),
            "duration_ms": report.duration_ms,
            "dense_execution": execution,
            "observed_dtype": observed.get("dtype"),
            "observed_attention": observed.get("attention_backend"),
        }
        if report.status is not IndexingStatus.SUCCESS:
            validity = "invalid"
        elif (
            report.embeddings_generated != EXPECTED_CHILD_COUNT
            or report.embeddings_reused != 0
        ):
            validity = "invalid"
            report_payload["count_mismatch"] = True
        else:
            validity = "valid"
    except Exception as exc:  # noqa: BLE001
        validity = classify_treatment_failure(exc, identity_correct=identity_correct)
        report_payload = {
            "exception_type": type(exc).__name__,
            "exception": str(exc),
            "validity": validity,
        }

    wall_minutes = (wall_s / 60.0) if wall_s is not None else None
    # Parity/correctness unfrozen here; leave None so selection fails closed
    # until execution AUTH freezes the probe and assesses both.
    cell_result = CellResult(
        cell_id=str(cell_id),  # type: ignore[arg-type]
        validity=validity,  # type: ignore[arg-type]
        wall_minutes=wall_minutes,
        parity_ok=None,
        correctness_ok=None,
    )
    if history_path is not None:
        _append_history(history_path, cell_result)

    evidence = {
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "status": "CELL_EXECUTED",
        "cell": cell_id,
        "cell_spec": {
            "device": spec.device,
            "precision": spec.precision,
            "batch_size": spec.batch_size,
        },
        "validity": validity,
        "wall_clock_s": wall_s,
        "wall_minutes": wall_minutes,
        "result": asdict(cell_result),
        "report": report_payload,
        "cpu_facts": cpu_facts,
        "gpu_facts": gpu_facts,
        "preflight": preflight.payload,
        "parity_probe": parity_probe_surface_status(),
        "execution_head": git_sha(cwd=root),
        "recorded_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "executor_ready": True,
    }
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out = (
            evidence_dir
            / f"d2_{str(cell_id).replace('-', '_').lower()}_{int(time.time())}.json"
        )
        out.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        evidence["evidence_path"] = str(out)
    return evidence


def execute_d2_cell(
    *,
    cell_id: CellId | str,
    work_root: Path,
    history_path: Path | None = None,
    evidence_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Authority-gated cell entrypoint.

    Implements the full executor behind ``EXECUTION_AUTHORIZED``. While false,
    refuses without invoking encode/indexing.
    """
    if not EXECUTION_AUTHORIZED:
        return {
            "authority": IMPLEMENTATION_AUTH,
            "rework_authority": IMPLEMENTATION_REWORK_AUTH,
            "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
            "status": "EXECUTION_NOT_AUTHORIZED",
            "requested_cell": cell_id,
            "execution_authorized": False,
            "note": (
                "Cell executor machinery is implemented "
                "(execute_d2_cell_unlocked) but locked. A later execution AUTH "
                "must set EXECUTION_AUTHORIZED before the first G1 treatment."
            ),
            "executor_ready": True,
            "unlocked_entrypoint": (
                "offline_rag.dense.d2_execution.execute_d2_cell_unlocked"
            ),
            "work_root": str(work_root),
            "history_path": str(history_path) if history_path else None,
            "evidence_dir": str(evidence_dir) if evidence_dir else None,
        }
    return execute_d2_cell_unlocked(
        cell_id=cell_id,
        work_root=work_root,
        history_path=history_path,
        evidence_dir=evidence_dir,
        repo_root=repo_root,
    )


__all__ = [
    "PreflightResult",
    "cell_environ",
    "execute_d2_cell",
    "execute_d2_cell_unlocked",
    "git_sha",
    "git_tracked_clean",
    "observe_workload_identity",
    "prepare_isolated_tree",
    "run_d2_preflight",
    "sha256_file",
]
