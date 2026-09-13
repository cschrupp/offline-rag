"""Deterministic comparison of two retrieval-eval-result-v1 artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt
from offline_rag.evaluation.gold import (
    RETRIEVAL_EVAL_COMPARISON_V1,
    RETRIEVAL_EVAL_RESULT_V1,
    RETRIEVAL_METRICS_V1,
)
from offline_rag.evaluation.result import RetrievalEvaluationResultV1

COMPARABLE_METRICS: tuple[str, ...] = (
    "recall_at_1",
    "recall_at_5",
    "recall_at_10",
    "precision_at_1",
    "precision_at_5",
    "precision_at_10",
    "hit_rate_at_1",
    "hit_rate_at_5",
    "hit_rate_at_10",
    "hit_rate_at_30",
    "mrr",
    "ndcg_at_1",
    "ndcg_at_5",
    "ndcg_at_10",
)

HEADLINE_METRICS: tuple[str, ...] = (
    "recall_at_10",
    "precision_at_10",
    "hit_rate_at_10",
    "mrr",
    "ndcg_at_10",
    "hit_rate_at_30",
)


class CompareError(ValueError):
    """Incompatible or invalid comparison inputs."""


Outcome = Literal["win", "loss", "tie"]


class MetricDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: NonEmptyStr
    a: float | None = None
    b: float | None = None
    delta: float | None = None
    comparable: bool = False


class OutcomeCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wins: NonNegativeInt = 0
    losses: NonNegativeInt = 0
    ties: NonNegativeInt = 0
    comparable_cases: NonNegativeInt = 0
    non_comparable_cases: NonNegativeInt = 0


class CaseMetricComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float | None = None
    b: float | None = None
    delta: float | None = None
    outcome: Outcome | None = None


class CaseComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    quality_eligible: bool
    returned_count_a: NonNegativeInt = 0
    returned_count_b: NonNegativeInt = 0
    latency_ms_a: NonNegativeInt = 0
    latency_ms_b: NonNegativeInt = 0
    metrics: dict[str, CaseMetricComparison] = Field(default_factory=dict)


class CategoryComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: NonEmptyStr
    total_cases: NonNegativeInt
    quality_eligible_cases: NonNegativeInt
    aggregates: list[MetricDelta] = Field(default_factory=list)
    outcomes: dict[str, OutcomeCounts] = Field(default_factory=dict)


class RetrievalEvalComparisonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = RETRIEVAL_EVAL_COMPARISON_V1
    method: NonEmptyStr
    gold_dataset_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    result_a_run_id: NonEmptyStr
    result_b_run_id: NonEmptyStr
    semantic_a: dict[str, Any] = Field(default_factory=dict)
    semantic_b: dict[str, Any] = Field(default_factory=dict)
    aggregates: list[MetricDelta] = Field(default_factory=list)
    outcomes: dict[str, OutcomeCounts] = Field(default_factory=dict)
    categories: list[CategoryComparison] = Field(default_factory=list)
    latency_mean_ms_a: float | None = None
    latency_mean_ms_b: float | None = None
    latency_mean_delta_ms: float | None = None
    latency_p50_ms_a: float | None = None
    latency_p50_ms_b: float | None = None
    latency_p50_delta_ms: float | None = None
    cases: list[CaseComparison] = Field(default_factory=list)


def load_retrieval_eval_result(path: Path) -> RetrievalEvaluationResultV1:
    try:
        result = RetrievalEvaluationResultV1.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )
    except Exception as exc:  # noqa: BLE001
        raise CompareError(f"invalid retrieval eval result: {path}: {exc}") from exc
    if result.schema_version != RETRIEVAL_EVAL_RESULT_V1:
        raise CompareError(
            f"unsupported result schema_version: {result.schema_version!r}"
        )
    return result


def _classify(a: float | None, b: float | None) -> CaseMetricComparison:
    if a is None or b is None:
        return CaseMetricComparison(a=a, b=b, delta=None, outcome=None)
    delta = b - a
    if b > a:
        outcome: Outcome = "win"
    elif b < a:
        outcome = "loss"
    else:
        outcome = "tie"
    return CaseMetricComparison(a=a, b=b, delta=delta, outcome=outcome)


def _outcome_counts(cases: list[CaseComparison], metric: str) -> OutcomeCounts:
    wins = losses = ties = comparable = non_comparable = 0
    for case in cases:
        item = case.metrics.get(metric)
        if item is None or item.outcome is None:
            non_comparable += 1
            continue
        comparable += 1
        if item.outcome == "win":
            wins += 1
        elif item.outcome == "loss":
            losses += 1
        else:
            ties += 1
    return OutcomeCounts(
        wins=wins,
        losses=losses,
        ties=ties,
        comparable_cases=comparable,
        non_comparable_cases=non_comparable,
    )


def _aggregate_delta(metric: str, a: RetrievalEvaluationResultV1, b: RetrievalEvaluationResultV1) -> MetricDelta:
    va = getattr(a.aggregates, metric).value
    vb = getattr(b.aggregates, metric).value
    if va is None or vb is None:
        return MetricDelta(metric=metric, a=va, b=vb, delta=None, comparable=False)
    return MetricDelta(metric=metric, a=va, b=vb, delta=vb - va, comparable=True)


def compare_retrieval_results(
    result_a: RetrievalEvaluationResultV1,
    result_b: RetrievalEvaluationResultV1,
) -> RetrievalEvalComparisonV1:
    if result_a.gold_dataset_id != result_b.gold_dataset_id:
        raise CompareError(
            "comparison incompatible: gold dataset mismatch "
            f"({result_a.gold_dataset_id} != {result_b.gold_dataset_id})"
        )
    if result_a.chunk_set_id != result_b.chunk_set_id:
        raise CompareError(
            "comparison incompatible: chunk_set_id mismatch "
            f"({result_a.chunk_set_id} != {result_b.chunk_set_id})"
        )
    if result_a.method != result_b.method:
        raise CompareError(
            "comparison incompatible: method mismatch "
            f"({result_a.method} != {result_b.method})"
        )
    if result_a.metric_config.metric_contract != result_b.metric_config.metric_contract:
        raise CompareError("comparison incompatible: metric contract mismatch")
    if result_a.metric_config.metric_contract != RETRIEVAL_METRICS_V1:
        raise CompareError(
            f"unsupported metric contract: {result_a.metric_config.metric_contract}"
        )
    if list(result_a.metric_config.cutoffs) != list(result_b.metric_config.cutoffs):
        raise CompareError("comparison incompatible: metric cutoffs mismatch")

    by_a = {case.case_id: case for case in result_a.cases}
    by_b = {case.case_id: case for case in result_b.cases}
    if set(by_a) != set(by_b):
        raise CompareError("comparison incompatible: case-set mismatch")

    case_comparisons: list[CaseComparison] = []
    for case_id in sorted(by_a):
        ca = by_a[case_id]
        cb = by_b[case_id]
        if ca.quality_eligible != cb.quality_eligible:
            raise CompareError(
                f"comparison incompatible: quality_eligible mismatch for case {case_id}"
            )
        metrics = {
            name: _classify(getattr(ca.metrics, name), getattr(cb.metrics, name))
            for name in COMPARABLE_METRICS
        }
        case_comparisons.append(
            CaseComparison(
                case_id=case_id,
                query=ca.query,
                category=ca.category,
                tags=list(ca.tags),
                quality_eligible=ca.quality_eligible,
                returned_count_a=ca.returned_count,
                returned_count_b=cb.returned_count,
                latency_ms_a=ca.latency_ms,
                latency_ms_b=cb.latency_ms,
                metrics=metrics,
            )
        )

    aggregates = [_aggregate_delta(name, result_a, result_b) for name in COMPARABLE_METRICS]
    outcomes = {name: _outcome_counts(case_comparisons, name) for name in COMPARABLE_METRICS}

    categories: list[CategoryComparison] = []
    cat_keys = sorted(
        {
            (c.category if c.category is not None else "uncategorized")
            for c in case_comparisons
        }
    )
    for key in cat_keys:
        group = [
            c
            for c in case_comparisons
            if (c.category if c.category is not None else "uncategorized") == key
        ]
        # Rebuild category aggregates from source results for A/B values.
        agg_a = next(
            (item for item in result_a.category_aggregates if item.category == key),
            None,
        )
        agg_b = next(
            (item for item in result_b.category_aggregates if item.category == key),
            None,
        )
        cat_deltas: list[MetricDelta] = []
        for name in COMPARABLE_METRICS:
            va = getattr(agg_a.metrics, name).value if agg_a is not None else None
            vb = getattr(agg_b.metrics, name).value if agg_b is not None else None
            if va is None or vb is None:
                cat_deltas.append(
                    MetricDelta(metric=name, a=va, b=vb, delta=None, comparable=False)
                )
            else:
                cat_deltas.append(
                    MetricDelta(metric=name, a=va, b=vb, delta=vb - va, comparable=True)
                )
        categories.append(
            CategoryComparison(
                category=key,
                total_cases=len(group),
                quality_eligible_cases=sum(1 for c in group if c.quality_eligible),
                aggregates=cat_deltas,
                outcomes={name: _outcome_counts(group, name) for name in COMPARABLE_METRICS},
            )
        )

    lat_a = result_a.latency
    lat_b = result_b.latency
    return RetrievalEvalComparisonV1(
        method=result_a.method,
        gold_dataset_id=result_a.gold_dataset_id,
        chunk_set_id=result_a.chunk_set_id,
        result_a_run_id=result_a.run_id,
        result_b_run_id=result_b.run_id,
        semantic_a=dict(result_a.semantic_provenance),
        semantic_b=dict(result_b.semantic_provenance),
        aggregates=aggregates,
        outcomes=outcomes,
        categories=categories,
        latency_mean_ms_a=float(lat_a.mean_ms),
        latency_mean_ms_b=float(lat_b.mean_ms),
        latency_mean_delta_ms=float(lat_b.mean_ms) - float(lat_a.mean_ms),
        latency_p50_ms_a=float(lat_a.p50_ms),
        latency_p50_ms_b=float(lat_b.p50_ms),
        latency_p50_delta_ms=float(lat_b.p50_ms) - float(lat_a.p50_ms),
        cases=case_comparisons,
    )


def format_comparison_human(comparison: RetrievalEvalComparisonV1) -> str:
    lines: list[str] = []
    lines.append("Retrieval Evaluation Comparison")
    lines.append("")
    lines.append(f"Method: {comparison.method}")
    lines.append(f"Gold:   {comparison.gold_dataset_id}")
    lines.append(f"A run:  {comparison.result_a_run_id}")
    lines.append(f"B run:  {comparison.result_b_run_id}")
    lines.append("")
    lines.append("Semantic provenance A:")
    for key, value in sorted(comparison.semantic_a.items()):
        lines.append(f"  {key}: {value}")
    lines.append("Semantic provenance B:")
    for key, value in sorted(comparison.semantic_b.items()):
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append(f"{'Metric':<16} {'A':>10} {'B':>10} {'Delta':>10}")
    for item in comparison.aggregates:
        if item.metric not in HEADLINE_METRICS and item.metric != "hit_rate_at_30":
            if item.metric not in {
                "recall_at_1",
                "recall_at_5",
                "precision_at_1",
                "precision_at_5",
                "hit_rate_at_1",
                "hit_rate_at_5",
                "ndcg_at_1",
                "ndcg_at_5",
            }:
                continue
        if not item.comparable:
            lines.append(f"{item.metric:<16} {'n/a':>10} {'n/a':>10} {'n/a':>10}")
            continue
        assert item.a is not None and item.b is not None and item.delta is not None
        lines.append(
            f"{item.metric:<16} {item.a:10.4f} {item.b:10.4f} {item.delta:+10.4f}"
        )
    lines.append("")
    for metric in ("ndcg_at_10", "recall_at_10", "mrr"):
        counts = comparison.outcomes.get(metric)
        if counts is None:
            continue
        lines.append(
            f"{metric} cases: wins={counts.wins} losses={counts.losses} "
            f"ties={counts.ties} (comparable={counts.comparable_cases})"
        )
    lines.append("")
    lines.append("Latency (delta = B - A; positive means B slower):")
    if comparison.latency_mean_ms_a is not None and comparison.latency_mean_ms_b is not None:
        lines.append(
            f"  mean_ms  A={comparison.latency_mean_ms_a:.2f} "
            f"B={comparison.latency_mean_ms_b:.2f} "
            f"delta={comparison.latency_mean_delta_ms:+.2f}"
        )
    if comparison.latency_p50_ms_a is not None and comparison.latency_p50_ms_b is not None:
        lines.append(
            f"  p50_ms   A={comparison.latency_p50_ms_a:.2f} "
            f"B={comparison.latency_p50_ms_b:.2f} "
            f"delta={comparison.latency_p50_delta_ms:+.2f}"
        )
    lines.append("")
    lines.append("By category:")
    for cat in comparison.categories:
        lines.append(
            f"  {cat.category}: total={cat.total_cases} "
            f"eligible={cat.quality_eligible_cases}"
        )
        ndcg = next((m for m in cat.aggregates if m.metric == "ndcg_at_10"), None)
        if ndcg and ndcg.comparable and ndcg.delta is not None:
            lines.append(f"    nDCG@10 delta={ndcg.delta:+.4f}")
    return "\n".join(lines)
