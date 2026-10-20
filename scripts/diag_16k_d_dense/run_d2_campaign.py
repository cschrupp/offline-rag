#!/usr/bin/env python3
"""16K-D D2 practical execution optimization harness.

Authority: S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-REWORK-AUTH-001
Accepted design subject: 8f96657d73b2213fb9b43557b001bc4c5a42188b

Scientific / benchmark cell execution is NOT AUTHORIZED while
EXECUTION_AUTHORIZED=False. The full cell executor is implemented and gated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from offline_rag.dense.d2_campaign import (  # noqa: E402
    ACCEPTED_DESIGN_SUBJECT,
    ALLOWED_CELLS,
    CELL_SPECS,
    EXECUTION_AUTHORIZED,
    IMPLEMENTATION_AUTH,
    IMPLEMENTATION_REWORK_AUTH,
    MAX_VALID_FULL_RUNS,
    CellResult,
    assert_transition_allowed,
    cell_spec,
    grades_against_gpu_gate,
    plan_next,
    reject_vram_only_g2_open,
)
from offline_rag.dense.d2_execution import (  # noqa: E402
    execute_d2_cell,
    run_d2_preflight,
)
from offline_rag.dense.precision import (  # noqa: E402
    classify_treatment_failure,
    is_cuda_resource_exhaustion,
)

EVIDENCE_DIR = ROOT / "docs/evidence/16k_d_dense_cuda/d2"


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
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
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
        "executor_ready": True,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    history = _parse_history(args.history)
    plan = plan_next(history)
    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "rework_authority": IMPLEMENTATION_REWORK_AUTH,
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
    result = run_d2_preflight(
        cell_id=args.cell,
        work_root=Path(args.work_root).resolve() if args.work_root else None,
        require_design_subject=bool(args.require_design_subject),
        repo_root=ROOT,
        prepare_tree=bool(args.prepare_tree),
    )
    if args.out:
        _write_json(Path(args.out), result.payload)
    else:
        print(json.dumps(result.payload, indent=2, sort_keys=True))
    return 0 if result.ok else 10


def cmd_classify(args: argparse.Namespace) -> int:
    if args.vram_open_g2:
        try:
            reject_vram_only_g2_open()
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 10
    exc: BaseException = RuntimeError(args.exception_text)
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
    """Gated execute entry — refuses while EXECUTION_AUTHORIZED is False."""
    work_root = Path(args.work_root).resolve()
    history = Path(args.history).resolve() if args.history else None
    evidence = Path(args.evidence_dir).resolve() if args.evidence_dir else EVIDENCE_DIR
    payload = execute_d2_cell(
        cell_id=args.cell,
        work_root=work_root,
        history_path=history,
        evidence_dir=evidence,
        repo_root=ROOT,
    )
    if args.out:
        _write_json(Path(args.out), payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if payload.get("status") == "EXECUTION_NOT_AUTHORIZED":
        print("FAIL-CLOSED: D2 scientific execution not authorized", file=sys.stderr)
        return 20
    if payload.get("status") == "PREFLIGHT_FAILED":
        return 10
    return 0


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

    p_pre = sub.add_parser("preflight", help="Fail-closed observed preflight")
    p_pre.add_argument("--cell", choices=ALLOWED_CELLS)
    p_pre.add_argument(
        "--work-root",
        required=True,
        help="Isolated data dir (prepared or to prepare)",
    )
    p_pre.add_argument(
        "--prepare-tree",
        action="store_true",
        help="Create/reset isolated empty embeddings/qdrant tree before checks",
    )
    p_pre.add_argument("--out")
    p_pre.add_argument(
        "--require-design-subject",
        action="store_true",
        help="Fail closed unless HEAD equals accepted design subject 8f96657…",
    )
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

    p_ex = sub.add_parser(
        "execute-cell",
        help="Run frozen cell (locked while EXECUTION_AUTHORIZED=False)",
    )
    p_ex.add_argument("--cell", required=True, choices=ALLOWED_CELLS)
    p_ex.add_argument("--work-root", required=True)
    p_ex.add_argument("--history", help="Campaign history JSON path")
    p_ex.add_argument("--evidence-dir", help="Evidence output directory")
    p_ex.add_argument("--out")
    p_ex.set_defaults(func=cmd_execute)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
