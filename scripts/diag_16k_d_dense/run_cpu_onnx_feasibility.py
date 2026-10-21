#!/usr/bin/env python3
"""16K-D CPU-ONNX-01 feasibility harness CLI (execution-locked).

Authority: S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from offline_rag.dense.cpu_onnx_feasibility import (  # noqa: E402
    EXECUTION_AUTHORIZED,
    EXPERIMENT_ID,
    IMPLEMENTATION_AUTH,
    StageResult,
    plan_next,
    plan_to_dict,
    stage_result_to_dict,
)
from offline_rag.dense.cpu_onnx_harness import (  # noqa: E402
    environment_fingerprint,
    run_export_fp32,
    run_export_qint8_avx2,
    run_full_confirm,
    run_parity,
    run_screen,
)


def _load_history(path: str | None) -> list[StageResult]:
    if not path:
        return []
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("history", [])
    out: list[StageResult] = []
    for item in items:
        out.append(
            StageResult(
                stage_id=item["stage_id"],
                ok=bool(item["ok"]),
                chunks_per_sec=item.get("chunks_per_sec"),
                projected_full_minutes=item.get("projected_full_minutes"),
                parity_ok=item.get("parity_ok"),
                full_wall_minutes=item.get("full_wall_minutes"),
                embeddings_generated=item.get("embeddings_generated"),
                embeddings_reused=item.get("embeddings_reused"),
                embeddings_failed=item.get("embeddings_failed"),
                vectors_materialized=item.get("vectors_materialized"),
                dimension=item.get("dimension"),
                notes=item.get("notes"),
            )
        )
    return out


def _print(payload: dict[str, Any], out: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n", encoding="utf-8")
        print(f"WROTE {out}")
    else:
        print(text)


def cmd_plan(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    plan = plan_next(history)
    payload = {
        "authority": IMPLEMENTATION_AUTH,
        "experiment_id": EXPERIMENT_ID,
        "execution_authorized": EXECUTION_AUTHORIZED,
        "history": [stage_result_to_dict(h) for h in history],
        "plan": plan_to_dict(plan),
        "environment": environment_fingerprint(),
    }
    _print(payload, args.out)
    return 0


def cmd_export_fp32(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_export_fp32(
        history=history,
        export_dir=Path(args.export_dir),
        allow_download=False,
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_export_qint8(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_export_qint8_avx2(
        history=history,
        export_dir=Path(args.export_dir),
        source_export_dir=Path(args.source_export_dir)
        if getattr(args, "source_export_dir", None)
        else None,
        expected_source_tree_sha256=getattr(args, "expected_source_tree_sha256", None),
        allow_download=False,
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_screen(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_screen(
        history=history,
        export_dir=Path(args.export_dir),
        expected_candidate_tree_sha256=getattr(
            args, "expected_candidate_tree_sha256", None
        ),
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_parity(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_parity(
        history=history,
        export_dir=Path(args.export_dir),
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_full(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    try:
        payload = run_full_confirm(
            history=history,
            selected_candidate="qint8_avx2",
            export_dir=Path(args.export_dir),
            repo_root=ROOT,
        )
    except ValueError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 10
    except NotImplementedError as exc:
        print(f"FAIL-CLOSED: {exc}", file=sys.stderr)
        return 10
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="Plan next frozen stage from history JSON")
    p_plan.add_argument("--history", help="Path to StageResult JSON list")
    p_plan.add_argument("--out")
    p_plan.set_defaults(func=cmd_plan)

    p_ex = sub.add_parser("export-fp32", help="FP32 ONNX source export (locked)")
    p_ex.add_argument("--history")
    p_ex.add_argument("--export-dir", required=True)
    p_ex.add_argument("--out")
    p_ex.set_defaults(func=cmd_export_fp32)

    p_ex8 = sub.add_parser(
        "export-qint8-avx2",
        help="QINT8 AVX2 derivative from accepted FP32 ONNX export (locked)",
    )
    p_ex8.add_argument("--history", required=True)
    p_ex8.add_argument("--export-dir", required=True)
    p_ex8.add_argument(
        "--source-export-dir",
        help="Immutable ST/ONNX FP32 export used as QINT8 AVX2 source",
    )
    p_ex8.add_argument(
        "--expected-source-tree-sha256",
        help=(
            "Required when unlocked: exact SHA256 of the accepted FP32 Stage-0 "
            "export tree (F001)"
        ),
    )
    p_ex8.add_argument("--out")
    p_ex8.set_defaults(func=cmd_export_qint8)

    p_sc = sub.add_parser("screen", help="128-child QINT8 AVX2 screen (locked)")
    p_sc.add_argument("--history", required=True)
    p_sc.add_argument(
        "--export-dir",
        required=True,
        help="Local ONNX QINT8 export directory (required when execution unlocks)",
    )
    p_sc.add_argument(
        "--expected-candidate-tree-sha256",
        help=(
            "Required when unlocked: exact SHA256 of the accepted QINT8 candidate "
            "tree; verified before and after encode (F003)"
        ),
    )
    p_sc.add_argument("--out")
    p_sc.set_defaults(func=cmd_screen)

    p_pa = sub.add_parser("parity", help="d2-retrieval-parity-v1 reuse (locked)")
    p_pa.add_argument("--history", required=True)
    p_pa.add_argument(
        "--export-dir",
        required=True,
        help="Local ONNX QINT8 export directory (required when execution unlocks)",
    )
    p_pa.add_argument("--out")
    p_pa.set_defaults(func=cmd_parity)

    p_fu = sub.add_parser("full-confirm", help="1296 confirmation (locked + eligibility)")
    p_fu.add_argument("--history", required=True)
    p_fu.add_argument(
        "--export-dir",
        required=True,
        help="Local ONNX QINT8 export directory (required when execution unlocks)",
    )
    p_fu.add_argument("--out")
    p_fu.set_defaults(func=cmd_full)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
