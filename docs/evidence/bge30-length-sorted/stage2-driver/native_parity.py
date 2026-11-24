"""Validate native Stage 2 batching parity from sanitized event journals."""

from __future__ import annotations

import json
import math
from pathlib import Path


class NativeParityError(RuntimeError):
    """Observed native request outputs violate the frozen parity contract."""


def _events_for(row: dict, event_name: str) -> list[dict]:
    return [
        item for item in row.get("server_events", []) if item.get("event") == event_name
    ]


def _load_observations(path: Path) -> tuple[dict[str, list[dict]], dict]:
    attempts = {}
    settled = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("event") == "send_attempt":
            if row.get("ordinal") in attempts:
                raise NativeParityError("duplicate submission attempt ordinal")
            attempts[row["ordinal"]] = row
        elif row.get("event") == "settled":
            if row.get("ordinal") in settled:
                raise NativeParityError("duplicate submission settlement ordinal")
            settled[row["ordinal"]] = row
    output = {"Recipes": [], "Rich": []}
    capacity_rejections = {
        workload: {
            strategy: {
                "query_preflight_capacity_exhausted": 0,
                "query_capacity_exhausted": 0,
            }
            for strategy in ("consecutive", "length_sorted_8")
        }
        for workload in ("Recipes", "Rich")
    }
    load_attempts = {
        ordinal: case
        for ordinal, case in attempts.items()
        if case.get("case") == "load"
    }
    if len(load_attempts) != 28:
        raise NativeParityError("native journal must contain all 28 load attempts")
    attempted_by_cell = {
        (workload, strategy): 0
        for workload in output
        for strategy in ("consecutive", "length_sorted_8")
    }
    for ordinal, case in load_attempts.items():
        result = settled.get(ordinal)
        if result is None:
            raise NativeParityError("load attempt is missing its persisted settlement")
        workload = case.get("workload")
        strategy = case.get("strategy")
        if workload not in output or strategy not in {
            "consecutive",
            "length_sorted_8",
        }:
            raise NativeParityError("unknown workload or strategy in request ledger")
        attempted_by_cell[(workload, strategy)] += 1
        if result.get("ordinal") != ordinal or result.get("settled") is not True:
            raise NativeParityError("load settlement is not correlated or terminal")
        admission = result.get("admission")
        if admission in {"preflight_rejected", "query_rejected"}:
            expected_reason = (
                "query_preflight_capacity_exhausted"
                if admission == "preflight_rejected"
                else "query_capacity_exhausted"
            )
            if (
                result.get("http_status") != 503
                or result.get("reason") != expected_reason
            ):
                raise NativeParityError("invalid capacity-rejection settlement")
            if admission == "preflight_rejected" and (
                result.get("terminal") is not None
                or result.get("operation") is not None
                or result.get("worker_returned") is not False
                or result.get("scientific_trace_ids") != []
            ):
                raise NativeParityError("invalid preflight-capacity rejection")
            if admission == "query_rejected" and (
                result.get("terminal") != "failed"
                or result.get("worker_returned") is not True
                or result.get("scientific_trace_ids") != []
            ):
                raise NativeParityError("invalid query-capacity rejection")
            capacity_rejections[workload][strategy][expected_reason] += 1
            continue
        if admission != "accepted" or result.get("terminal") != "completed":
            raise NativeParityError("load request did not complete successfully")
        if result.get("http_status") != 200:
            raise NativeParityError("completed load did not return HTTP 200")
        scores = _events_for(result, "native_scores")
        rankings = _events_for(result, "native_ranked_candidates")
        contexts = _events_for(result, "native_context")
        citations = _events_for(result, "native_citations")
        generator = _events_for(result, "synthetic_generator_returned")
        if (
            len(scores) != 1
            or len(rankings) != 1
            or len(contexts) != 1
            or len(citations) != 1
            or len(generator) != 1
        ):
            raise NativeParityError("completed load is missing native parity evidence")
        if case["workload"] not in output:
            raise NativeParityError("unknown workload in request ledger")
        if strategy not in {"consecutive", "length_sorted_8"}:
            raise NativeParityError("unknown execution strategy in request ledger")
        output[workload].append(
            {
                "ordinal": ordinal,
                "strategy": strategy,
                "scores": scores[0],
                "ranking": rankings[0],
                "context": contexts[0],
                "citations": citations[0],
                "forward_shapes": [
                    item.get("shape") for item in _events_for(result, "forward_started")
                ],
            }
        )
    if any(count != 7 for count in attempted_by_cell.values()):
        raise NativeParityError(
            "each workload and strategy cell requires seven attempts"
        )
    return output, capacity_rejections


def _assert_shapes(item: dict, workload: str) -> None:
    if workload == "Recipes":
        expected_count = 30
        expected_shapes = (
            [[16, None], [14, None]]
            if item["strategy"] == "consecutive"
            else [[8, None], [8, None], [8, None], [6, None]]
        )
    else:
        expected_count = 10
        expected_shapes = (
            [[10, None]]
            if item["strategy"] == "consecutive"
            else [[8, None], [2, None]]
        )
    associations = item["scores"].get("score_associations", [])
    if len(associations) != expected_count:
        raise NativeParityError(f"{workload} scorer input count differs")
    ranking = item["ranking"]
    if (
        ranking.get("candidate_count") != expected_count
        or ranking.get("tie_break") != "chunk-id-asc-v1"
        or len(ranking.get("ranked_candidate_order", [])) != expected_count
    ):
        raise NativeParityError(f"{workload} complete ranked candidate set differs")
    shapes = item["forward_shapes"]
    if len(shapes) != len(expected_shapes) or any(
        not isinstance(shape, list)
        or len(shape) != 2
        or shape[0] != expected[0]
        or not 0 < shape[1] <= 1024
        for shape, expected in zip(shapes, expected_shapes, strict=True)
    ):
        raise NativeParityError(f"{workload} strategy batch shapes differ")
    if (
        item["context"].get("reranker_execution", {}).get("batching_strategy")
        != item["strategy"]
    ):
        raise NativeParityError("request's effective strategy differs")


def _compare(left: dict, right: dict, *, workload: str) -> None:
    _assert_shapes(left, workload)
    _assert_shapes(right, workload)
    left_scores = left["scores"]["score_associations"]
    right_scores = right["scores"]["score_associations"]
    if left["scores"].get("candidate_order_sha256") != right["scores"].get(
        "candidate_order_sha256"
    ):
        raise NativeParityError(f"{workload} original candidate order differs")
    for baseline, candidate in zip(left_scores, right_scores, strict=True):
        identity_keys = ("candidate_id_sha256", "pair_input_sha256")
        if any(baseline.get(key) != candidate.get(key) for key in identity_keys):
            raise NativeParityError(
                f"{workload} score-to-candidate association differs"
            )
        baseline_logit = baseline.get("raw_logit")
        candidate_logit = candidate.get("raw_logit")
        if not isinstance(baseline_logit, (int, float)) or not isinstance(
            candidate_logit, (int, float)
        ):
            raise NativeParityError("raw score is not numeric")
        if not math.isfinite(baseline_logit) or not math.isfinite(candidate_logit):
            raise NativeParityError("raw score is not finite")
        if abs(candidate_logit - baseline_logit) > 1e-4 + 1e-5 * abs(baseline_logit):
            raise NativeParityError(f"{workload} raw-logit tolerance failed")
    for key in ("ranked_candidate_ids_sha256", "ranked_candidate_order"):
        if left["ranking"].get(key) != right["ranking"].get(key):
            raise NativeParityError(f"{workload} full ranking differs at {key}")
    for key in ("anchor_order", "evidence_unit_ids_sha256", "context_sha256"):
        if left["context"].get(key) != right["context"].get(key):
            raise NativeParityError(f"{workload} context output differs at {key}")
    for key in ("citation_chunk_ids_sha256", "citation_evidence_unit_ids_sha256"):
        if left["citations"].get(key) != right["citations"].get(key):
            raise NativeParityError(f"{workload} citations differ at {key}")
    for key in ("citation_chunk_count", "citation_evidence_unit_count"):
        if left["citations"].get(key) != right["citations"].get(key):
            raise NativeParityError(f"{workload} citations differ at {key}")
    if not left["citations"].get("citation_chunk_count") or not left["citations"].get(
        "citation_evidence_unit_count"
    ):
        raise NativeParityError(f"{workload} completed answer has no citations")


def validate(path: Path) -> dict:
    observations, capacity_rejections = _load_observations(path)
    summary = {}
    for workload, rows in observations.items():
        by_strategy = {
            strategy: [row for row in rows if row["strategy"] == strategy]
            for strategy in ("consecutive", "length_sorted_8")
        }
        if any(not by_strategy[strategy] for strategy in by_strategy):
            raise NativeParityError(
                f"{workload} requires at least one completed request per arm"
            )
        reference = by_strategy["consecutive"][0]
        for candidate in rows:
            _compare(reference, candidate, workload=workload)
        summary[workload] = {
            "consecutive_completed": len(by_strategy["consecutive"]),
            "length_sorted_8_completed": len(by_strategy["length_sorted_8"]),
            "capacity_rejections": capacity_rejections[workload],
            "candidate_count": len(reference["scores"]["score_associations"]),
            "parity": "PASS",
        }
    return {"classification": "NATIVE_FIXED_DEPTH_PARITY_PASS", "workloads": summary}
