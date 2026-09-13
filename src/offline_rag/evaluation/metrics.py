"""Deterministic retrieval metrics for GoldDataset v1 (Slice 9)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from offline_rag.evaluation.gold import (
    CANONICAL_CUTOFFS,
    DIAGNOSTIC_HIT_RATE_CUTOFF,
    GoldCase,
)


@dataclass(frozen=True, slots=True)
class RankingScore:
    """Per-query metric scores; None means N/A / non-applicable."""

    quality_eligible: bool
    recall: dict[int, float | None]
    precision: dict[int, float | None]
    hit_rate: dict[int, float | None]
    hit_rate_30: float | None
    mrr: float | None
    ndcg: dict[int, float | None]
    first_relevant_rank: int | None
    returned_count: int
    requested_depth: int


def binary_relevant_ids(case: GoldCase) -> set[str]:
    return case.positive_chunk_ids()


def relevance_grades(case: GoldCase) -> dict[str, int]:
    return case.relevance_map()


def recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not relevant:
        raise ValueError("recall_at_k requires a non-empty relevant set")
    top = set(retrieved[:k])
    return len(relevant & top) / len(relevant)


def precision_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    """Decision 9: denominator is min(k, |L|); empty successful list → 0.0."""
    if k < 1:
        raise ValueError("k must be >= 1")
    if not retrieved:
        return 0.0
    m = min(k, len(retrieved))
    if m <= 0:
        return 0.0
    top = retrieved[:m]
    hits = sum(1 for chunk_id in top if chunk_id in relevant)
    return hits / float(m)


def hit_rate_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not relevant:
        raise ValueError("hit_rate_at_k requires a non-empty relevant set")
    top = retrieved[:k]
    return 1.0 if any(chunk_id in relevant for chunk_id in top) else 0.0


def mean_reciprocal_rank(relevant: set[str], retrieved: list[str]) -> float:
    if not relevant:
        raise ValueError("mean_reciprocal_rank requires a non-empty relevant set")
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return 1.0 / float(rank)
    return 0.0


def first_relevant_rank(relevant: set[str], retrieved: list[str]) -> int | None:
    for rank, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant:
            return rank
    return None


def _gain(rel: int) -> float:
    return float((2**rel) - 1)


def dcg_at_k(grades_by_rank: list[int], k: int) -> float:
    total = 0.0
    for rank, rel in enumerate(grades_by_rank[:k], start=1):
        if rel <= 0:
            continue
        total += _gain(rel) / math.log2(rank + 1)
    return total


def ndcg_at_k(grades: dict[str, int], retrieved: list[str], k: int) -> float | None:
    """Return nDCG@k or None when IDCG is zero (no positive judgments)."""
    if k < 1:
        raise ValueError("k must be >= 1")
    positives = sorted((rel for rel in grades.values() if rel >= 1), reverse=True)
    if not positives:
        return None
    ideal = dcg_at_k(positives, k)
    if ideal <= 0.0:
        return None
    observed_grades = [int(grades.get(chunk_id, 0)) for chunk_id in retrieved[:k]]
    return dcg_at_k(observed_grades, k) / ideal


def score_ranking(
    case: GoldCase,
    retrieved: list[str],
    *,
    requested_depth: int,
    hit_rate_30_applicable: bool,
) -> RankingScore:
    """Score one successful ranking against a GoldCase."""
    cutoffs = CANONICAL_CUTOFFS
    if not case.quality_eligible:
        return RankingScore(
            quality_eligible=False,
            recall={k: None for k in cutoffs},
            precision={k: None for k in cutoffs},
            hit_rate={k: None for k in cutoffs},
            hit_rate_30=None,
            mrr=None,
            ndcg={k: None for k in cutoffs},
            first_relevant_rank=None,
            returned_count=len(retrieved),
            requested_depth=requested_depth,
        )

    relevant = binary_relevant_ids(case)
    grades = relevance_grades(case)
    recall = {k: recall_at_k(relevant, retrieved, k) for k in cutoffs}
    precision = {k: precision_at_k(relevant, retrieved, k) for k in cutoffs}
    hit_rate = {k: hit_rate_at_k(relevant, retrieved, k) for k in cutoffs}
    hit30: float | None
    if hit_rate_30_applicable:
        hit30 = hit_rate_at_k(relevant, retrieved, DIAGNOSTIC_HIT_RATE_CUTOFF)
    else:
        hit30 = None
    return RankingScore(
        quality_eligible=True,
        recall=recall,
        precision=precision,
        hit_rate=hit_rate,
        hit_rate_30=hit30,
        mrr=mean_reciprocal_rank(relevant, retrieved),
        ndcg={k: ndcg_at_k(grades, retrieved, k) for k in cutoffs},
        first_relevant_rank=first_relevant_rank(relevant, retrieved),
        returned_count=len(retrieved),
        requested_depth=requested_depth,
    )


def macro_average(values: list[float | None]) -> tuple[float | None, int]:
    """Average numeric values; ignore None. Returns (mean, eligible_count)."""
    numeric = [float(v) for v in values if v is not None]
    if not numeric:
        return None, 0
    return sum(numeric) / len(numeric), len(numeric)
