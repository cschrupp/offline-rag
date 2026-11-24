import json

import pytest
from native_parity import NativeParityError, validate


def _observation(strategy, workload, ordinal):
    count = 30 if workload == "Recipes" else 10
    sizes = (
        [16, 14]
        if workload == "Recipes" and strategy == "consecutive"
        else [8, 8, 8, 6]
        if workload == "Recipes"
        else [10]
        if strategy == "consecutive"
        else [8, 2]
    )
    seq = 128
    associations = [
        {
            "candidate_id_sha256": f"candidate-{index}",
            "pair_input_sha256": f"pair-{index}",
            "raw_logit": float(index) / 10,
        }
        for index in range(count)
    ]
    scores = {
        "event": "native_scores",
        "candidate_order_sha256": f"order-{workload}",
        "score_associations": associations,
    }
    context = {
        "event": "native_context",
        "anchor_order": [f"anchor-{index}" for index in range(10)],
        "evidence_unit_ids_sha256": f"evidence-{workload}",
        "context_sha256": f"context-{workload}",
        "reranker_execution": {"batching_strategy": strategy},
    }
    ranking = {
        "event": "native_ranked_candidates",
        "candidate_count": count,
        "ranked_candidate_ids_sha256": f"ranked-{workload}",
        "ranked_candidate_order": [f"ranked-{index}" for index in range(count)],
        "tie_break": "chunk-id-asc-v1",
    }
    citations = {
        "event": "native_citations",
        "citation_chunk_ids_sha256": f"citations-{workload}",
        "citation_evidence_unit_ids_sha256": f"citation-units-{workload}",
        "citation_chunk_count": 1,
        "citation_evidence_unit_count": 1,
    }
    generator = {"event": "synthetic_generator_returned", "elapsed_ms": 1.0}
    server_events = [scores, ranking, context, citations, generator]
    server_events.extend(
        {"event": "forward_started", "shape": [size, seq]} for size in sizes
    )
    return {
        "send": {
            "event": "send_attempt",
            "ordinal": ordinal,
            "strategy": strategy,
            "workload": workload,
            "case": "load",
        },
        "settled": {
            "event": "settled",
            "ordinal": ordinal,
            "settled": True,
            "admission": "accepted",
            "terminal": "completed",
            "http_status": 200,
            "server_events": server_events,
        },
    }


def _capacity_rejection(strategy, workload, ordinal, admission):
    reason = (
        "query_preflight_capacity_exhausted"
        if admission == "preflight_rejected"
        else "query_capacity_exhausted"
    )
    settled = {
        "event": "settled",
        "ordinal": ordinal,
        "settled": True,
        "admission": admission,
        "terminal": None if admission == "preflight_rejected" else "failed",
        "operation": None if admission == "preflight_rejected" else "capacity-rejected",
        "worker_returned": admission == "query_rejected",
        "http_status": 503,
        "reason": reason,
        "scientific_trace_ids": [],
    }
    return {
        "send": {
            "event": "send_attempt",
            "ordinal": ordinal,
            "strategy": strategy,
            "workload": workload,
            "case": "load",
        },
        "settled": settled,
    }


def _write_journal(path, observations):
    rows = []
    for item in observations:
        rows.extend((item["send"], item["settled"]))
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_native_parity_accepts_fixed_depth_matching_observations(tmp_path):
    rows = []
    ordinal = 1
    for strategy in ("consecutive", "length_sorted_8"):
        for workload in ("Recipes", "Rich"):
            for _ in range(7):
                rows.append(_observation(strategy, workload, ordinal))
                ordinal += 1
    journal = tmp_path / "events.jsonl"
    _write_journal(journal, rows)
    result = validate(journal)
    assert result["classification"] == "NATIVE_FIXED_DEPTH_PARITY_PASS"
    assert result["workloads"]["Recipes"]["candidate_count"] == 30
    assert result["workloads"]["Rich"]["candidate_count"] == 10
    assert result["workloads"]["Recipes"]["consecutive_completed"] == 7
    assert result["workloads"]["Rich"]["length_sorted_8_completed"] == 7


def test_native_parity_accepts_capacity_one_rejections_with_cell_coverage(tmp_path):
    rows = []
    ordinal = 1
    for strategy in ("consecutive", "length_sorted_8"):
        for workload in ("Recipes", "Rich"):
            rows.append(_observation(strategy, workload, ordinal))
            ordinal += 1
            for attempt in range(6):
                admission = (
                    "preflight_rejected" if attempt % 2 == 0 else "query_rejected"
                )
                rows.append(_capacity_rejection(strategy, workload, ordinal, admission))
                ordinal += 1
    journal = tmp_path / "events.jsonl"
    _write_journal(journal, rows)

    result = validate(journal)

    assert result["workloads"]["Recipes"]["consecutive_completed"] == 1
    assert result["workloads"]["Recipes"]["capacity_rejections"]["consecutive"] == {
        "query_preflight_capacity_exhausted": 3,
        "query_capacity_exhausted": 3,
    }


def test_native_parity_requires_completed_coverage_for_each_workload_and_arm(
    tmp_path,
):
    rows = []
    ordinal = 1
    for strategy in ("consecutive", "length_sorted_8"):
        for workload in ("Recipes", "Rich"):
            has_success = not (strategy == "length_sorted_8" and workload == "Rich")
            for attempt in range(7):
                if has_success and attempt == 0:
                    rows.append(_observation(strategy, workload, ordinal))
                else:
                    rows.append(
                        _capacity_rejection(
                            strategy,
                            workload,
                            ordinal,
                            "query_rejected",
                        )
                    )
                ordinal += 1
    journal = tmp_path / "events.jsonl"
    _write_journal(journal, rows)

    with pytest.raises(NativeParityError, match="completed request per arm"):
        validate(journal)


@pytest.mark.parametrize(
    "change", ["logit", "ranking", "anchor", "context", "association"]
)
def test_native_parity_rejects_scientific_output_difference(tmp_path, change):
    rows = []
    ordinal = 1
    target_candidate = None
    for strategy in ("consecutive", "length_sorted_8"):
        for workload in ("Recipes", "Rich"):
            for repetition in range(7):
                observation = _observation(strategy, workload, ordinal)
                rows.append(observation)
                if (
                    strategy == "length_sorted_8"
                    and workload == "Recipes"
                    and repetition == 0
                ):
                    target_candidate = observation
                ordinal += 1
    candidate_events = target_candidate["settled"]["server_events"]
    if change == "logit":
        candidate_events[0]["score_associations"][0]["raw_logit"] += 1
    elif change == "ranking":
        candidate_events[1]["ranked_candidate_order"][0] = "different"
    elif change == "anchor":
        candidate_events[2]["anchor_order"][0] = "different"
    elif change == "context":
        candidate_events[2]["context_sha256"] = "different"
    else:
        candidate_events[0]["score_associations"][0]["candidate_id_sha256"] = "other"
    journal = tmp_path / "events.jsonl"
    _write_journal(journal, rows)
    with pytest.raises(NativeParityError):
        validate(journal)
