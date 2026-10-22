#!/usr/bin/env python3
"""16K-D CPU-GGUF-01 feasibility harness CLI (execution-locked).

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from offline_rag.dense.cpu_gguf_feasibility import (  # noqa: E402
    EXECUTION_AUTHORIZED,
    EXPERIMENT_ID,
    IMPLEMENTATION_AUTH,
    StageResult,
    plan_next,
    plan_to_dict,
    stage_result_to_dict,
)
from offline_rag.dense.cpu_gguf_harness import (  # noqa: E402
    environment_fingerprint,
    run_full_confirm,
    run_parity,
    run_screen,
    run_stage0_compat,
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


def cmd_stage0(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_stage0_compat(
        history=history,
        gguf_path=Path(args.gguf) if args.gguf else None,
        llama_server_path=Path(args.llama_server) if args.llama_server else None,
        allow_download=False,
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_screen(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_screen(
        history=history,
        gguf_path=Path(args.gguf) if args.gguf else None,
        llama_server_path=Path(args.llama_server) if args.llama_server else None,
        expected_llama_server_sha256=getattr(
            args, "expected_llama_server_sha256", None
        ),
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_parity(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    payload = run_parity(
        history=history,
        gguf_path=Path(args.gguf) if args.gguf else None,
        llama_server_path=Path(args.llama_server) if args.llama_server else None,
        expected_llama_server_sha256=getattr(
            args, "expected_llama_server_sha256", None
        ),
        repo_root=ROOT,
    )
    _print(payload, args.out)
    return 20 if payload.get("status") == "EXECUTION_NOT_AUTHORIZED" else 0


def cmd_full(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    try:
        payload = run_full_confirm(
            history=history,
            selected_candidate="q8_0",
            gguf_path=Path(args.gguf) if args.gguf else None,
            llama_server_path=Path(args.llama_server) if args.llama_server else None,
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

    p_s0 = sub.add_parser(
        "stage0",
        help="Stage-0 GGUF SHA + llama-server smoke (locked)",
    )
    p_s0.add_argument("--history")
    p_s0.add_argument("--gguf", help="Local pinned Q8_0 GGUF path")
    p_s0.add_argument("--llama-server", help="Local llama-server binary path")
    p_s0.add_argument("--out")
    p_s0.set_defaults(func=cmd_stage0)

    p_sc = sub.add_parser("screen", help="128-child Q8_0 screen (locked)")
    p_sc.add_argument("--history", required=True)
    p_sc.add_argument("--gguf", help="Local pinned Q8_0 GGUF path")
    p_sc.add_argument("--llama-server", help="Local llama-server binary path")
    p_sc.add_argument(
        "--expected-llama-server-sha256",
        help=(
            "Required when unlocked: accepted Stage-0 llama-server binary SHA256 "
            "(F001 runtime pin)"
        ),
    )
    p_sc.add_argument("--out")
    p_sc.set_defaults(func=cmd_screen)

    p_pa = sub.add_parser("parity", help="d2-retrieval-parity-v1 reuse (locked)")
    p_pa.add_argument("--history", required=True)
    p_pa.add_argument("--gguf", help="Local pinned Q8_0 GGUF path")
    p_pa.add_argument("--llama-server", help="Local llama-server binary path")
    p_pa.add_argument(
        "--expected-llama-server-sha256",
        help=(
            "Required when unlocked: accepted Stage-0 llama-server binary SHA256 "
            "(F001 runtime pin)"
        ),
    )
    p_pa.add_argument("--out")
    p_pa.set_defaults(func=cmd_parity)

    p_fu = sub.add_parser("full-confirm", help="1296 confirmation (locked + eligibility)")
    p_fu.add_argument("--history", required=True)
    p_fu.add_argument("--gguf", help="Local pinned Q8_0 GGUF path")
    p_fu.add_argument("--llama-server", help="Local llama-server binary path")
    p_fu.add_argument("--out")
    p_fu.set_defaults(func=cmd_full)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
