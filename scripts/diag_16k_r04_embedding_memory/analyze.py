"""Offline R04 evidence analysis; this module never loads a model or CUDA."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .contract import (
        classify_oom_diagnostics,
        enforce_cell_budget,
        evaluate_mechanism_pairs,
        evaluate_parity,
        evaluate_production_candidate,
    )
else:
    from contract import (
        classify_oom_diagnostics,
        enforce_cell_budget,
        evaluate_mechanism_pairs,
        evaluate_parity,
        evaluate_production_candidate,
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path | None, payload: Any) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path is None:
        print(rendered, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _parity(args: argparse.Namespace) -> int:
    ref = _read_json(args.reference_vectors)
    candidate = _read_json(args.candidate_vectors)
    result = evaluate_parity(
        reference_documents=ref["documents"],
        candidate_documents=candidate["documents"],
        reference_queries=ref["queries"],
        candidate_queries=candidate["queries"],
    )
    _write_json(args.out, result)
    return 0 if result["passed"] else 10


def _pairs(args: argparse.Namespace) -> int:
    result = evaluate_mechanism_pairs(
        baseline_runs=_read_json(args.baseline),
        treatment_runs=_read_json(args.treatment),
        target_peak_key=args.target_peak_key,
    )
    _write_json(args.out, result)
    return 0 if result.get("mechanism") != "INCONCLUSIVE" else 10


def _budget(args: argparse.Namespace) -> int:
    result = enforce_cell_budget(_read_json(args.records))
    _write_json(args.out, result)
    return 0


def _oom(args: argparse.Namespace) -> int:
    result = classify_oom_diagnostics(_read_json(args.metrics))
    _write_json(args.out, result)
    return 0 if result["status"] == "CLASSIFIED" else 10


def _candidate(args: argparse.Namespace) -> int:
    result = evaluate_production_candidate(
        mechanism=_read_json(args.mechanism),
        baseline_runs=_read_json(args.baseline),
        treatment_runs=_read_json(args.treatment),
        parity_results=_read_json(args.parity),
        other_peak_keys=tuple(args.other_peak_key or []),
    )
    _write_json(args.out, result)
    return 0 if result.get("candidate") == "QUALIFIED" else 10


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    parity = commands.add_parser("parity")
    parity.add_argument("--reference-vectors", required=True, type=Path)
    parity.add_argument("--candidate-vectors", required=True, type=Path)
    parity.add_argument("--out", type=Path)
    parity.set_defaults(func=_parity)
    pairs = commands.add_parser("pairs")
    pairs.add_argument("--baseline", required=True, type=Path)
    pairs.add_argument("--treatment", required=True, type=Path)
    pairs.add_argument("--target-peak-key", required=True)
    pairs.add_argument("--out", type=Path)
    pairs.set_defaults(func=_pairs)
    budget = commands.add_parser("budget")
    budget.add_argument("--records", required=True, type=Path)
    budget.add_argument("--out", type=Path)
    budget.set_defaults(func=_budget)
    oom = commands.add_parser("oom")
    oom.add_argument("--metrics", required=True, type=Path)
    oom.add_argument("--out", type=Path)
    oom.set_defaults(func=_oom)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("--mechanism", required=True, type=Path)
    candidate.add_argument("--baseline", required=True, type=Path)
    candidate.add_argument("--treatment", required=True, type=Path)
    candidate.add_argument("--parity", required=True, type=Path)
    candidate.add_argument("--other-peak-key", action="append")
    candidate.add_argument("--out", type=Path)
    candidate.set_defaults(func=_candidate)
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ANALYSIS_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
