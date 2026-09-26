"""Recompute derived 12C scientific fields from primary IDs/judgments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from offline_rag.evaluation.gold import ChunkJudgment, GoldCase
from offline_rag.evaluation.metrics import score_ranking
from offline_rag.evaluation.recovery_12c.contracts import (
    AttemptObservationV1,
    GoldJudgmentRefV1,
    ranking_score_to_dict,
)


def require_unique_ids(ids: Sequence[str], *, field_name: str) -> list[str]:
    values = list(ids)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must contain unique IDs")
    return values


def expected_gold_overlap_ids(
    *,
    gold_positive_chunk_ids: Sequence[str],
    evidence_surface_chunk_ids: Sequence[str],
) -> list[str]:
    """Exact sorted intersection used by OD-12C-4 / 11B evidence-surface rule."""
    positives = require_unique_ids(
        gold_positive_chunk_ids, field_name="gold_positive_chunk_ids"
    )
    surface = require_unique_ids(
        evidence_surface_chunk_ids, field_name="evidence_surface_chunk_ids"
    )
    return sorted(set(positives) & set(surface))


def validate_observation_gold_overlap(
    observation: AttemptObservationV1,
    *,
    gold_positive_chunk_ids: Sequence[str],
) -> None:
    """Fail closed unless stored overlap equals recomputed intersection."""
    require_unique_ids(
        observation.evidence_surface_chunk_ids,
        field_name="evidence_surface_chunk_ids",
    )
    require_unique_ids(
        observation.gold_positive_overlap_chunk_ids,
        field_name="gold_positive_overlap_chunk_ids",
    )
    expected = expected_gold_overlap_ids(
        gold_positive_chunk_ids=gold_positive_chunk_ids,
        evidence_surface_chunk_ids=observation.evidence_surface_chunk_ids,
    )
    actual = list(observation.gold_positive_overlap_chunk_ids)
    if actual != expected:
        raise ValueError(
            "gold_positive_overlap_chunk_ids must equal "
            "sorted(gold_positive_chunk_ids ∩ evidence_surface_chunk_ids); "
            f"expected={expected!r} actual={actual!r}"
        )
    if bool(actual) != bool(observation.gold_positive_overlap):
        raise ValueError(
            "gold_positive_overlap must equal bool(gold_positive_overlap_chunk_ids)"
        )
    positives = set(gold_positive_chunk_ids)
    surface = set(observation.evidence_surface_chunk_ids)
    for chunk_id in actual:
        if chunk_id not in positives:
            raise ValueError(
                f"overlap chunk_id {chunk_id!r} is not in gold_positive_chunk_ids"
            )
        if chunk_id not in surface:
            raise ValueError(
                f"overlap chunk_id {chunk_id!r} is not in evidence_surface_chunk_ids"
            )


def gold_judgments_from_case(case: GoldCase) -> list[GoldJudgmentRefV1]:
    return [
        GoldJudgmentRefV1(chunk_id=j.chunk_id, relevance=int(j.relevance))  # type: ignore[arg-type]
        for j in sorted(case.judgments, key=lambda item: item.chunk_id)
    ]


def gold_case_from_judgments(
    *,
    case_id: str,
    query: str,
    judgments: Sequence[GoldJudgmentRefV1],
) -> GoldCase:
    return GoldCase(
        id=case_id,
        query=query,
        judgments=tuple(
            ChunkJudgment(chunk_id=j.chunk_id, relevance=j.relevance)  # type: ignore[arg-type]
            for j in judgments
        ),
    )


def recompute_ranking_metrics(
    *,
    case_id: str,
    query: str,
    judgments: Sequence[GoldJudgmentRefV1],
    ranked_chunk_ids: Sequence[str],
) -> dict[str, float | None] | None:
    """Recompute Slice-9 metrics; None when the case is quality-ineligible."""
    case = gold_case_from_judgments(case_id=case_id, query=query, judgments=judgments)
    if not case.quality_eligible:
        return None
    score = score_ranking(
        case,
        list(ranked_chunk_ids),
        requested_depth=max(len(ranked_chunk_ids), 10),
        hit_rate_30_applicable=False,
    )
    return ranking_score_to_dict(score)


def ranking_dicts_equal(
    left: Mapping[str, float | None] | None,
    right: Mapping[str, float | None] | None,
) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    if set(left) != set(right):
        return False
    for key in left:
        a = left[key]
        b = right[key]
        if a is None and b is None:
            continue
        if a is None or b is None:
            return False
        if float(a) != float(b):
            return False
    return True


def assert_ranking_matches_recompute(
    stored: Mapping[str, float | None] | None,
    *,
    case_id: str,
    query: str,
    judgments: Sequence[GoldJudgmentRefV1],
    ranked_chunk_ids: Sequence[str],
    field_name: str,
) -> None:
    expected = recompute_ranking_metrics(
        case_id=case_id,
        query=query,
        judgments=judgments,
        ranked_chunk_ids=ranked_chunk_ids,
    )
    if not ranking_dicts_equal(stored, expected):
        raise ValueError(
            f"{field_name} does not match recomputed Slice-9 metrics from "
            f"frozen Gold judgments + ranked chunk IDs"
        )


def prepared_case_set_identity_payload(
    *,
    gold_dataset_id: str,
    cases: Sequence[tuple[str, str, str, Sequence[GoldJudgmentRefV1]]],
) -> dict[str, Any]:
    """Semantic prepared population identity (no contexts/latency/secrets)."""
    ordered = sorted(cases, key=lambda item: item[0])
    return {
        "gold_dataset_id": gold_dataset_id,
        "cases": [
            {
                "case_id": case_id,
                "original_query": query,
                "adjudication_cohort": cohort,
                "gold_judgments": [
                    {"chunk_id": j.chunk_id, "relevance": int(j.relevance)}
                    for j in judgments
                ],
            }
            for case_id, query, cohort, judgments in ordered
        ],
    }
