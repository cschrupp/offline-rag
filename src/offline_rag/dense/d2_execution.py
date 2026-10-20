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
    ABANDONED_CORPUS_ROOT_REL,
    ACCEPTED_DESIGN_SUBJECT,
    ALLOWED_CELLS,
    CONFIRMATION_CELLS,
    CORPUS_NAME,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_CORPUS_ID,
    EXPECTED_CORPUS_MANIFEST_SHA256,
    EXPECTED_EXECUTION_HEAD,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    EXPECTED_SEARCHABLE_UNITS_CONTRACT,
    EXPECTED_SEARCHABLE_UNITS_STRATEGY,
    IMPLEMENTATION_AUTH,
    IMPLEMENTATION_REWORK2_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    WORKLOAD_LABEL,
    CellId,
    CellResult,
    CellSpec,
    assert_transition_allowed,
    cell_spec,
    plan_next,
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


def verify_prepared_workload_state(work_root: Path) -> dict[str, Any]:
    """Verify the isolated corpus/chunk state that run_indexing will consume."""
    corpus_state_path = work_root / "corpora" / CORPUS_NAME / "state.json"
    chunk_state_path = (
        work_root / "corpora" / CORPUS_NAME / "chunking" / "state.json"
    )
    result: dict[str, Any] = {
        "corpus_state_exists": corpus_state_path.is_file(),
        "chunk_state_exists": chunk_state_path.is_file(),
        "current_corpus_id": None,
        "current_chunk_set_id": None,
        "current_manifest": None,
        "current_chunk_manifest": None,
        "issues": [],
    }
    issues: list[str] = []
    if not corpus_state_path.is_file():
        issues.append("prepared_corpus_state_missing")
    else:
        corpus_state = json.loads(corpus_state_path.read_text(encoding="utf-8"))
        result["current_corpus_id"] = corpus_state.get("current_corpus_id")
        result["current_manifest"] = corpus_state.get("current_manifest")
        if corpus_state.get("current_corpus_id") != EXPECTED_CORPUS_ID:
            issues.append(
                f"prepared_corpus_id_mismatch:"
                f"observed={corpus_state.get('current_corpus_id')}"
            )
        manifest_rel = corpus_state.get("current_manifest")
        if isinstance(manifest_rel, str):
            # Paths are relative to data root (work_root).
            manifest_path = work_root / manifest_rel
            if not manifest_path.is_file():
                # Also accept manifests/<id>.json layout.
                alt = work_root / "manifests" / f"{EXPECTED_CORPUS_ID}.json"
                if not alt.is_file():
                    issues.append("prepared_corpus_manifest_missing")
                elif sha256_file(alt) != EXPECTED_CORPUS_MANIFEST_SHA256:
                    issues.append("prepared_corpus_manifest_sha256_mismatch")
            elif sha256_file(manifest_path) != EXPECTED_CORPUS_MANIFEST_SHA256:
                issues.append("prepared_corpus_manifest_sha256_mismatch")
        else:
            issues.append("prepared_corpus_manifest_ref_missing")

    if not chunk_state_path.is_file():
        issues.append("prepared_chunk_state_missing")
    else:
        chunk_state = json.loads(chunk_state_path.read_text(encoding="utf-8"))
        result["current_chunk_set_id"] = chunk_state.get("current_chunk_set_id")
        result["current_chunk_manifest"] = chunk_state.get("current_chunk_manifest")
        if chunk_state.get("current_chunk_set_id") != EXPECTED_CHUNK_SET_ID:
            issues.append(
                f"prepared_chunk_set_id_mismatch:"
                f"observed={chunk_state.get('current_chunk_set_id')}"
            )
        if chunk_state.get("source_corpus_id") not in {None, EXPECTED_CORPUS_ID}:
            issues.append(
                f"prepared_chunk_source_corpus_mismatch:"
                f"observed={chunk_state.get('source_corpus_id')}"
            )
        chunk_rel = chunk_state.get("current_chunk_manifest")
        if isinstance(chunk_rel, str):
            chunk_path = work_root / chunk_rel
            alt = work_root / "chunk-manifests" / f"{EXPECTED_CHUNK_SET_ID}.json"
            target = chunk_path if chunk_path.is_file() else alt
            if not target.is_file():
                issues.append("prepared_chunk_manifest_missing")
            elif sha256_file(target) != EXPECTED_CHUNK_MANIFEST_SHA256:
                issues.append("prepared_chunk_manifest_sha256_mismatch")
        else:
            issues.append("prepared_chunk_manifest_ref_missing")

    result["issues"] = issues
    return result


def run_d2_preflight(
    *,
    cell_id: str | None = None,
    work_root: Path | None = None,
    require_design_subject: bool = False,
    expected_execution_head: str | None = None,
    require_execution_head: bool = False,
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
            f"design_subject_mismatch: head={head} "
            f"expected_design_subject={ACCEPTED_DESIGN_SUBJECT}"
        )

    expected_head = (
        expected_execution_head
        if expected_execution_head is not None
        else EXPECTED_EXECUTION_HEAD
    )
    if require_execution_head:
        if expected_head is None:
            issues.append("expected_execution_head_not_frozen")
        elif head != expected_head:
            issues.append(
                f"execution_head_mismatch: head={head} expected={expected_head}"
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
    prepared_state: dict[str, Any] | None = None
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
        prepared_state = verify_prepared_workload_state(isolation_root)
        issues.extend(str(i) for i in prepared_state.get("issues", []))
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
        "rework2_authority": IMPLEMENTATION_REWORK2_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "execution_head": head,
        "expected_execution_head": expected_head,
        "require_execution_head": require_execution_head,
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
        "prepared_state": prepared_state,
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


def load_campaign_history(path: Path) -> list[CellResult]:
    """Load history; missing file yields empty history (G1-1 only)."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else list(data.get("history", []))
    out: list[CellResult] = []
    for item in items:
        out.append(
            CellResult(
                cell_id=item["cell_id"],
                validity=item["validity"],
                wall_minutes=item.get("wall_minutes"),
                parity_ok=item.get("parity_ok"),
                correctness_ok=item.get("correctness_ok"),
                assessment_evidence_digest=item.get("assessment_evidence_digest"),
                assessment_evidence_path=item.get("assessment_evidence_path"),
                assessment_recorded_at=item.get("assessment_recorded_at"),
            )
        )
    return out


def write_campaign_history(path: Path, history: list[CellResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in history], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_history(path: Path, result: CellResult) -> None:
    history = load_campaign_history(path)
    history.append(result)
    write_campaign_history(path, history)


def record_confirmation_assessment(
    *,
    history_path: Path,
    cell_id: str,
    parity_ok: bool,
    correctness_ok: bool,
    evidence_digest: str,
    evidence_path: str | None = None,
) -> dict[str, Any]:
    """Attach parity/correctness to an already-executed confirmation cell (F009)."""
    if cell_id not in CONFIRMATION_CELLS:
        raise ValueError(
            f"assessment only allowed for confirmation cells {sorted(CONFIRMATION_CELLS)}; "
            f"got {cell_id!r}"
        )
    if not isinstance(parity_ok, bool) or not isinstance(correctness_ok, bool):
        raise ValueError("parity_ok and correctness_ok must be explicit booleans")
    digest = str(evidence_digest).strip()
    if not digest:
        raise ValueError("assessment_evidence_digest is required")

    history = load_campaign_history(history_path)
    # Find latest valid execution of this confirmation cell without assessment.
    target_index: int | None = None
    for i in range(len(history) - 1, -1, -1):
        item = history[i]
        if item.cell_id != cell_id:
            continue
        if item.validity == "invalid":
            continue
        target_index = i
        break
    if target_index is None:
        raise ValueError(f"no executed confirmation cell {cell_id!r} in history")

    prior = history[target_index]
    if prior.parity_ok is not None or prior.correctness_ok is not None:
        raise ValueError(
            f"confirmation cell {cell_id!r} already has assessment; refusing overwrite"
        )

    recorded_at = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    updated = CellResult(
        cell_id=prior.cell_id,
        validity=prior.validity,
        wall_minutes=prior.wall_minutes,
        parity_ok=parity_ok,
        correctness_ok=correctness_ok,
        assessment_evidence_digest=digest,
        assessment_evidence_path=evidence_path,
        assessment_recorded_at=recorded_at,
    )
    history[target_index] = updated
    write_campaign_history(history_path, history)
    plan = plan_next(history)
    return {
        "status": "ASSESSMENT_RECORDED",
        "cell_id": cell_id,
        "parity_ok": parity_ok,
        "correctness_ok": correctness_ok,
        "assessment_evidence_digest": digest,
        "assessment_evidence_path": evidence_path,
        "assessment_recorded_at": recorded_at,
        "plan": {
            "terminal": plan.terminal,
            "next_cell": plan.next_cell,
            "reason": plan.reason,
            "selected_lane": plan.selected_lane,
            "g2_eligible": plan.g2_eligible,
        },
    }


def execute_d2_cell_unlocked(
    *,
    cell_id: CellId | str,
    work_root: Path,
    history_path: Path,
    evidence_dir: Path | None = None,
    repo_root: Path | None = None,
    expected_execution_head: str | None = None,
) -> dict[str, Any]:
    """Real cold-cell executor (preflight → index → evidence → history).

    Callers must only invoke this when scientific execution is authorized.
    ``execute_d2_cell`` is the authority-gated public entrypoint.
    ``history_path`` is mandatory: missing file means empty history (G1-1 only).
    """
    root = repo_root or _repo_root()
    if cell_id not in ALLOWED_CELLS:
        raise ValueError(f"unauthorized D2 cell: {cell_id!r}")
    if history_path is None:
        raise ValueError("history_path is required for D2 cell execution")
    spec = cell_spec(str(cell_id))

    history = load_campaign_history(history_path)
    assert_transition_allowed(history, str(cell_id))

    preflight = run_d2_preflight(
        cell_id=str(cell_id),
        work_root=work_root,
        require_design_subject=False,
        expected_execution_head=expected_execution_head,
        require_execution_head=True,
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
    cpu_facts_before: dict[str, Any] = {}
    cpu_facts: dict[str, Any] = {}
    gpu_facts: dict[str, Any] = {}
    practical_timing: dict[str, Any] | None = None
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
            cpu_facts_before = capture_cpu_baseline_facts(
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
        if spec.device == "cpu":
            cpu_facts = capture_cpu_baseline_facts(
                embedder=embedder, batch_size=spec.batch_size
            )
            # Characterize completed C0 with post-run facts + CPU-time delta.
            before_cpu = cpu_facts_before.get("process_cpu_time_s")
            after_cpu = cpu_facts.get("process_cpu_time_s")
            if isinstance(before_cpu, (int, float)) and isinstance(
                after_cpu, (int, float)
            ):
                cpu_facts["process_cpu_time_delta_s"] = float(after_cpu) - float(
                    before_cpu
                )
            cpu_facts["sampled"] = "after_run_indexing"
            cpu_facts["before_snapshot"] = {
                "process_cpu_time_s": before_cpu,
                "peak_rss_bytes": cpu_facts_before.get("peak_rss_bytes"),
            }
        meta = report.metadata or {}
        execution = meta.get("dense_execution") or {}
        practical_timing = meta.get("practical_timing")
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
            "practical_timing": practical_timing,
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
    # until assessment recording (F009) after the later parity probe.
    cell_result = CellResult(
        cell_id=str(cell_id),  # type: ignore[arg-type]
        validity=validity,  # type: ignore[arg-type]
        wall_minutes=wall_minutes,
        parity_ok=None,
        correctness_ok=None,
    )
    _append_history(history_path, cell_result)

    evidence = {
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
        "rework2_authority": IMPLEMENTATION_REWORK2_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "expected_execution_head": (
            expected_execution_head
            if expected_execution_head is not None
            else EXPECTED_EXECUTION_HEAD
        ),
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
        "practical_timing": practical_timing,
        "cpu_facts": cpu_facts,
        "gpu_facts": gpu_facts,
        "preflight": preflight.payload,
        "parity_probe": parity_probe_surface_status(),
        "history_path": str(history_path),
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
    history_path: Path,
    evidence_dir: Path | None = None,
    repo_root: Path | None = None,
    expected_execution_head: str | None = None,
) -> dict[str, Any]:
    """Authority-gated cell entrypoint.

    Implements the full executor behind ``EXECUTION_AUTHORIZED``. While false,
    refuses without invoking encode/indexing.
    """
    if history_path is None:
        raise ValueError("history_path is required for D2 cell execution")
    if not EXECUTION_AUTHORIZED:
        return {
            "authority": IMPLEMENTATION_AUTH,
            "rework_authority": IMPLEMENTATION_REWORK_AUTH,
            "rework2_authority": IMPLEMENTATION_REWORK2_AUTH,
            "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
            "status": "EXECUTION_NOT_AUTHORIZED",
            "requested_cell": cell_id,
            "execution_authorized": False,
            "note": (
                "Cell executor machinery is implemented "
                "(execute_d2_cell_unlocked) but locked. A later execution AUTH "
                "must set EXECUTION_AUTHORIZED and freeze EXPECTED_EXECUTION_HEAD "
                "before the first G1 treatment."
            ),
            "executor_ready": True,
            "unlocked_entrypoint": (
                "offline_rag.dense.d2_execution.execute_d2_cell_unlocked"
            ),
            "work_root": str(work_root),
            "history_path": str(history_path),
            "evidence_dir": str(evidence_dir) if evidence_dir else None,
            "expected_execution_head": (
                expected_execution_head
                if expected_execution_head is not None
                else EXPECTED_EXECUTION_HEAD
            ),
        }
    return execute_d2_cell_unlocked(
        cell_id=cell_id,
        work_root=work_root,
        history_path=history_path,
        evidence_dir=evidence_dir,
        repo_root=repo_root,
        expected_execution_head=expected_execution_head,
    )


__all__ = [
    "PreflightResult",
    "cell_environ",
    "execute_d2_cell",
    "execute_d2_cell_unlocked",
    "git_sha",
    "git_tracked_clean",
    "load_campaign_history",
    "observe_workload_identity",
    "prepare_isolated_tree",
    "record_confirmation_assessment",
    "run_d2_preflight",
    "sha256_file",
    "verify_prepared_workload_state",
    "write_campaign_history",
]
