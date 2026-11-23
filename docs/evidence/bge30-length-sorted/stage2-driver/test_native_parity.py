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
    server_events = [scores, ranking, context, citations]
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
            "admission": "accepted",
            "terminal": "completed",
            "http_status": 200,
            "server_events": server_events,
        },
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
