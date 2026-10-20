#!/usr/bin/env python3
"""16K-D D2 practical execution optimization harness.

Authority: S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001
Accepted design subject: 8f96657d73b2213fb9b43557b001bc4c5a42188b

Scientific / benchmark cell execution is NOT AUTHORIZED under this AUTH.
This harness encodes the frozen state machine, preflight, cell specs, and
validity classification so a later execution AUTH can open G1-1 safely.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from offline_rag.dense.d2_campaign import (  # noqa: E402
    ACCEPTED_DESIGN_SUBJECT,
    ALLOWED_CELLS,
    CELL_SPECS,
    DESIGN_DOC,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHUNK_SET_ID,
    EXPECTED_CORPUS_ID,
    EXPECTED_CORPUS_MANIFEST_SHA256,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    IMPLEMENTATION_AUTH,
    MAX_VALID_FULL_RUNS,
    WORKLOAD_LABEL,
    CellResult,
    assert_transition_allowed,
    cell_spec,
    grades_against_gpu_gate,
    plan_next,
    reject_vram_only_g2_open,
)
from offline_rag.dense.d2_observability import (  # noqa: E402
    parity_probe_surface_status,
)
from offline_rag.dense.precision import (  # noqa: E402
    classify_treatment_failure,
    is_cuda_resource_exhaustion,
)

EVIDENCE_DIR = ROOT / "docs/evidence/16k_d_dense_cuda/d2"
SOURCE_PATHS = (
    Path("scripts/diag_16k_d_dense/run_d2_campaign.py"),
    Path("src/offline_rag/dense/d2_campaign.py"),
    Path("src/offline_rag/dense/d2_observability.py"),
    Path("src/offline_rag/dense/precision.py"),
    Path("src/offline_rag/dense/embedder.py"),
    Path("src/offline_rag/config/models.py"),
)


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def git_tracked_clean() -> tuple[bool, str]:
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
    return {str(p): _sha256_file(ROOT / p) for p in SOURCE_PATHS}


def capture_runtime() -> dict[str, Any]:
    runtime: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "gpu_name": None,
        "cuda_available": None,
        "torch_version": None,
        "torch_cuda_build": None,
    }
    try:
        import torch

        runtime["torch_version"] = str(torch.__version__)
        build = getattr(getattr(torch, "version", None), "cuda", None)
        runtime["torch_cuda_build"] = str(build) if build else None
        runtime["cuda_available"] = bool(torch.cuda.is_available())
        if runtime["cuda_available"]:
            runtime["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:  # noqa: BLE001
        runtime["torch_error"] = f"{type(exc).__name__}: {exc}"
    return runtime


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {path}")


def _parse_history(raw: str | None) -> list[CellResult]:
    if not raw:
        return []
    path = Path(raw)
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("history", [])
    out: list[CellResult] = []
    for item in items:
        out.append(
            CellResult(
                cell_id=item["cell_id"],
                validity=item["validity"],
                wall_minutes=item.get("wall_minutes"),
                parity_ok=item.get("parity_ok"),
                correctness_ok=item.get("correctness_ok"),
            )
        )
    return out


def cmd_list_cells(_: argparse.Namespace) -> int:
    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "cells": {
            cid: {
                "device": spec.device,
                "precision": spec.precision,
                "batch_size": spec.batch_size,
                "grades_against_gpu_gate": spec.grades_against_gpu_gate,
            }
            for cid, spec in CELL_SPECS.items()
        },
        "max_valid_full_runs": MAX_VALID_FULL_RUNS,
        "execution_authorized": EXECUTION_AUTHORIZED,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    history = _parse_history(args.history)
    plan = plan_next(history)
    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "execution_authorized": EXECUTION_AUTHORIZED,
        "history_len": len(history),
        "valid_full_run_count": plan.valid_full_run_count,
        "terminal": plan.terminal,
        "next_cell": plan.next_cell,
        "reason": plan.reason,
        "g2_eligible": plan.g2_eligible,
        "selected_lane": plan.selected_lane,
    }
    if args.out:
        _write_json(Path(args.out), payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_validate_transition(args: argparse.Namespace) -> int:
    history = _parse_history(args.history)
    try:
        assert_transition_allowed(history, args.cell)
    except ValueError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 10
    spec = cell_spec(args.cell)
    print(
        json.dumps(
            {
                "ok": True,
                "cell": args.cell,
                "device": spec.device,
                "precision": spec.precision,
                "batch_size": spec.batch_size,
                "grades_against_gpu_gate": grades_against_gpu_gate(args.cell),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    clean, clean_detail = git_tracked_clean()
    head = git_sha()
    issues: list[str] = []
    if not clean:
        issues.append(clean_detail)
    if args.require_design_subject and head != ACCEPTED_DESIGN_SUBJECT:
        # Implementation tranche tip will differ from design subject; record both.
        pass
    cell = args.cell
    if cell is not None:
        if cell not in ALLOWED_CELLS:
            issues.append(f"unauthorized_cell:{cell}")
        else:
            spec = cell_spec(cell)
            if spec.device == "cuda" and args.force_cpu_check:
                issues.append("cell_requires_cuda")

    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "design_document": DESIGN_DOC,
        "execution_head": head,
        "tracked_tree": clean_detail,
        "tracked_clean": clean,
        "source_sha256": source_digests(),
        "runtime": capture_runtime(),
        "workload": {
            "label": WORKLOAD_LABEL,
            "searchable_children": EXPECTED_CHILD_COUNT,
            "chunk_set_id": EXPECTED_CHUNK_SET_ID,
            "corpus_id": EXPECTED_CORPUS_ID,
            "chunk_manifest_sha256": EXPECTED_CHUNK_MANIFEST_SHA256,
            "corpus_manifest_sha256": EXPECTED_CORPUS_MANIFEST_SHA256,
            "model_id": EXPECTED_MODEL_ID,
            "model_revision": EXPECTED_MODEL_REVISION,
        },
        "parity_probe": parity_probe_surface_status(),
        "execution_authorized": EXECUTION_AUTHORIZED,
        "cell": cell,
        "cell_spec": (
            {
                "device": cell_spec(cell).device,
                "precision": cell_spec(cell).precision,
                "batch_size": cell_spec(cell).batch_size,
            }
            if cell in ALLOWED_CELLS
            else None
        ),
        "strict_offline_required": True,
        "isolated_empty_embedding_qdrant_required": True,
        "issues": issues,
        "status": "PREFLIGHT_OK" if not issues else "PREFLIGHT_FAILED",
        "recorded_at": _utc_now(),
    }
    if args.out:
        _write_json(Path(args.out), payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not issues else 10


def cmd_classify(args: argparse.Namespace) -> int:
    if args.vram_open_g2:
        try:
            reject_vram_only_g2_open()
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 10
    exc: BaseException
    if args.exception_text:
        exc = RuntimeError(args.exception_text)
    else:
        exc = RuntimeError("unspecified")
    validity = classify_treatment_failure(
        exc, identity_correct=not args.identity_incorrect
    )
    print(
        json.dumps(
            {
                "validity": validity,
                "is_cuda_resource_exhaustion": is_cuda_resource_exhaustion(exc),
                "identity_correct": not args.identity_incorrect,
                "retryable": False if validity == "valid_negative_resource" else None,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    """Refuse scientific execution under implementation AUTH."""
    if not EXECUTION_AUTHORIZED:
        payload = {
            "authority": IMPLEMENTATION_AUTH,
            "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
            "status": "EXECUTION_NOT_AUTHORIZED",
            "requested_cell": args.cell,
            "note": (
                "D2 cell execution (FP16/CPU/parity) is closed under "
                "IMPLEMENTATION_AUTH. Freeze parity + open execution AUTH before "
                "the first G1 call."
            ),
            "execution_authorized": False,
            "env_precision": os.environ.get("OFFLINE_RAG_EMBEDDING_PRECISION"),
            "env_batch_size": os.environ.get("OFFLINE_RAG_EMBEDDING_BATCH_SIZE"),
            "env_device": os.environ.get("OFFLINE_RAG_EMBEDDING_DEVICE"),
        }
        if args.out:
            _write_json(Path(args.out), payload)
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        print("FAIL-CLOSED: D2 scientific execution not authorized", file=sys.stderr)
        return 20
    print("unreachable: EXECUTION_AUTHORIZED unexpectedly true", file=sys.stderr)
    return 99


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-cells", help="Show frozen D2 cells")
    p_list.set_defaults(func=cmd_list_cells)

    p_plan = sub.add_parser("plan", help="Plan next cell from history JSON")
    p_plan.add_argument("--history", help="Path to history JSON list/object")
    p_plan.add_argument("--out", help="Write plan JSON")
    p_plan.set_defaults(func=cmd_plan)

    p_val = sub.add_parser("validate-transition", help="Fail closed on bad transition")
    p_val.add_argument("--history", help="Path to history JSON")
    p_val.add_argument("--cell", required=True, choices=ALLOWED_CELLS)
    p_val.set_defaults(func=cmd_validate_transition)

    p_pre = sub.add_parser("preflight", help="Fail-closed preflight surface")
    p_pre.add_argument("--cell", choices=ALLOWED_CELLS)
    p_pre.add_argument("--out")
    p_pre.add_argument(
        "--require-design-subject",
        action="store_true",
        help="Reserved; implementation tip may differ from design subject",
    )
    p_pre.add_argument("--force-cpu-check", action="store_true")
    p_pre.set_defaults(func=cmd_preflight)

    p_cls = sub.add_parser("classify-failure", help="Classify treatment failure")
    p_cls.add_argument("--exception-text", default="CUDA out of memory")
    p_cls.add_argument("--identity-incorrect", action="store_true")
    p_cls.add_argument(
        "--vram-open-g2",
        action="store_true",
        help="Demonstrate VRAM-only G2 open is rejected",
    )
    p_cls.set_defaults(func=cmd_classify)

    p_ex = sub.add_parser("execute-cell", help="Blocked under implementation AUTH")
    p_ex.add_argument("--cell", required=True, choices=ALLOWED_CELLS)
    p_ex.add_argument("--out")
    p_ex.set_defaults(func=cmd_execute)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
