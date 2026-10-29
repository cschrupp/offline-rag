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
    from .evidence import reduce_authorized_cell_evidence
else:
    from contract import (
        classify_oom_diagnostics,
        enforce_cell_budget,
        evaluate_mechanism_pairs,
        evaluate_parity,
        evaluate_production_candidate,
    )
    from evidence import reduce_authorized_cell_evidence


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
    baseline = _reduce_group(args.baseline_evidence, args.baseline_specs, args)
    treatment = _reduce_group(args.treatment_evidence, args.treatment_specs, args)
    result = evaluate_mechanism_pairs(
        baseline_runs=baseline,
        treatment_runs=treatment,
        target_peak_key=args.target_peak_key,
    )
    result["source_evidence_sha256"] = [
        item["source_evidence_sha256"] for item in [*baseline, *treatment]
    ]
    result["source_cell_spec_sha256"] = [
        item["cell_spec_sha256"] for item in [*baseline, *treatment]
    ]
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
    baseline = _reduce_group(args.baseline_evidence, args.baseline_specs, args)
    treatment = _reduce_group(args.treatment_evidence, args.treatment_specs, args)
    reference = _reduce_one(args.reference_evidence, args.reference_spec, args)
    mechanism = evaluate_mechanism_pairs(
        baseline_runs=baseline,
        treatment_runs=treatment,
        target_peak_key=args.target_peak_key,
    )
    parity = [
        evaluate_parity(
            reference_documents=reference["vectors"]["documents"],
            candidate_documents=run["vectors"]["documents"],
            reference_queries=reference["vectors"]["queries"],
            candidate_queries=run["vectors"]["queries"],
        )
        for run in treatment
    ]
    result = evaluate_production_candidate(
        mechanism=mechanism,
        baseline_runs=baseline,
        treatment_runs=treatment,
        parity_results=parity,
        other_peak_keys=tuple(args.other_peak_key or []),
    )
    result["source_evidence_sha256"] = [
        item["source_evidence_sha256"] for item in [*baseline, *treatment]
    ] + [reference["source_evidence_sha256"]]
    result["source_cell_spec_sha256"] = [
        item["cell_spec_sha256"] for item in [*baseline, *treatment]
    ] + [reference["cell_spec_sha256"]]
    result["derived_parity"] = parity
    result["derived_mechanism"] = mechanism
    _write_json(args.out, result)
    return 0 if result.get("candidate") == "QUALIFIED" else 10


def _reduce_one(
    evidence_path: Path, spec_path: Path, args: argparse.Namespace
) -> dict[str, Any]:
    authority = _read_json(args.authority)
    workload = _read_json(args.workload)
    reduced = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    if not reduced["valid"]:
        raise ValueError("raw evidence failed deterministic validation")
    return reduced


def _reduce_group(
    evidence_paths: list[Path], spec_paths: list[Path], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if len(evidence_paths) != 3 or len(spec_paths) != 3:
        raise ValueError("comparative analysis requires exactly three raw cells")
    return [
        _reduce_one(evidence_path, spec_path, args)
        for evidence_path, spec_path in zip(evidence_paths, spec_paths, strict=True)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    parity = commands.add_parser("parity")
    parity.add_argument("--reference-vectors", required=True, type=Path)
    parity.add_argument("--candidate-vectors", required=True, type=Path)
    parity.add_argument("--out", type=Path)
    parity.set_defaults(func=_parity)
    pairs = commands.add_parser("pairs")
    pairs.add_argument("--authority", required=True, type=Path)
    pairs.add_argument("--workload", required=True, type=Path)
    pairs.add_argument("--baseline-evidence", required=True, type=Path, nargs=3)
    pairs.add_argument("--baseline-specs", required=True, type=Path, nargs=3)
    pairs.add_argument("--treatment-evidence", required=True, type=Path, nargs=3)
    pairs.add_argument("--treatment-specs", required=True, type=Path, nargs=3)
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
    candidate.add_argument("--authority", required=True, type=Path)
    candidate.add_argument("--workload", required=True, type=Path)
    candidate.add_argument("--baseline-evidence", required=True, type=Path, nargs=3)
    candidate.add_argument("--baseline-specs", required=True, type=Path, nargs=3)
    candidate.add_argument("--treatment-evidence", required=True, type=Path, nargs=3)
    candidate.add_argument("--treatment-specs", required=True, type=Path, nargs=3)
    candidate.add_argument("--reference-evidence", required=True, type=Path)
    candidate.add_argument("--reference-spec", required=True, type=Path)
    candidate.add_argument("--target-peak-key", required=True)
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
