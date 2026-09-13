"""offline-rag-retrieval-eval-result-v1 models and helpers."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt, Score
from offline_rag.evaluation.gold import (
    CANONICAL_CUTOFFS,
    DIAGNOSTIC_HIT_RATE_CUTOFF,
    RETRIEVAL_EVAL_RESULT_V1,
    RETRIEVAL_METRICS_V1,
)
from offline_rag.evaluation.metrics import RankingScore, macro_average

RetrievalMethod = Literal[
    "dense",
    "lexical",
    "hybrid",
    "hybrid-rerank",
    "hybrid-rerank-context",
]


class MetricValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    applicable_count: NonNegativeInt = 0


class MetricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_contract: NonEmptyStr = RETRIEVAL_METRICS_V1
    cutoffs: list[PositiveInt] = Field(default_factory=lambda: list(CANONICAL_CUTOFFS))
    diagnostic_hit_rate_cutoffs: list[PositiveInt] = Field(default_factory=list)
    binary_relevance_threshold: NonEmptyStr = "grade>=1"
    ndcg_gain_contract: NonEmptyStr = "2^rel-1"


class PopulationCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: NonNegativeInt
    executed_cases: NonNegativeInt
    quality_eligible_cases: NonNegativeInt


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recall_at_1: MetricValue
    recall_at_5: MetricValue
    recall_at_10: MetricValue
    precision_at_1: MetricValue
    precision_at_5: MetricValue
    precision_at_10: MetricValue
    hit_rate_at_1: MetricValue
    hit_rate_at_5: MetricValue
    hit_rate_at_10: MetricValue
    hit_rate_at_30: MetricValue
    mrr: MetricValue
    ndcg_at_1: MetricValue
    ndcg_at_5: MetricValue
    ndcg_at_10: MetricValue


class LatencySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_ms: Score = 0.0
    p50_ms: Score = 0.0
    p95_ms: Score = 0.0
    executed_cases: NonNegativeInt = 0


class CaseMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recall_at_1: float | None = None
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    precision_at_1: float | None = None
    precision_at_5: float | None = None
    precision_at_10: float | None = None
    hit_rate_at_1: float | None = None
    hit_rate_at_5: float | None = None
    hit_rate_at_10: float | None = None
    hit_rate_at_30: float | None = None
    mrr: float | None = None
    ndcg_at_1: float | None = None
    ndcg_at_5: float | None = None
    ndcg_at_10: float | None = None


class CaseEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    quality_eligible: bool
    positive_judgment_count: NonNegativeInt = 0
    grade_2_count: NonNegativeInt = 0
    grade_1_count: NonNegativeInt = 0
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    requested_depth: NonNegativeInt = 0
    returned_count: NonNegativeInt = 0
    first_relevant_rank: PositiveInt | None = None
    metrics: CaseMetrics = Field(default_factory=CaseMetrics)
    latency_ms: NonNegativeInt = 0
    error: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CategoryAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: NonEmptyStr
    total_cases: NonNegativeInt
    executed_cases: NonNegativeInt
    quality_eligible_cases: NonNegativeInt
    metrics: AggregateMetrics


class RetrievalEvaluationResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = RETRIEVAL_EVAL_RESULT_V1
    run_id: NonEmptyStr
    method: RetrievalMethod
    gold_schema_version: NonEmptyStr
    gold_dataset_id: NonEmptyStr
    gold_source_schema: NonEmptyStr
    gold_compatibility_mode: str | None = None
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr | None = None
    corpus_name: str | None = None
    semantic_provenance: dict[str, Any] = Field(default_factory=dict)
    metric_config: MetricConfig
    population: PopulationCounts
    aggregates: AggregateMetrics
    category_aggregates: list[CategoryAggregate] = Field(default_factory=list)
    latency: LatencySummary
    cases: list[CaseEvaluationResult] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def case_metrics_from_score(score: RankingScore) -> CaseMetrics:
    return CaseMetrics(
        recall_at_1=score.recall.get(1),
        recall_at_5=score.recall.get(5),
        recall_at_10=score.recall.get(10),
        precision_at_1=score.precision.get(1),
        precision_at_5=score.precision.get(5),
        precision_at_10=score.precision.get(10),
        hit_rate_at_1=score.hit_rate.get(1),
        hit_rate_at_5=score.hit_rate.get(5),
        hit_rate_at_10=score.hit_rate.get(10),
        hit_rate_at_30=score.hit_rate_30,
        mrr=score.mrr,
        ndcg_at_1=score.ndcg.get(1),
        ndcg_at_5=score.ndcg.get(5),
        ndcg_at_10=score.ndcg.get(10),
    )


def build_aggregate_metrics(cases: list[CaseEvaluationResult]) -> AggregateMetrics:
    def _collect(attr: str) -> list[float | None]:
        values: list[float | None] = []
        for case in cases:
            if case.error is not None:
                continue
            values.append(getattr(case.metrics, attr))
        return values

    def _metric(attr: str) -> MetricValue:
        mean, count = macro_average(_collect(attr))
        return MetricValue(value=mean, applicable_count=count)

    return AggregateMetrics(
        recall_at_1=_metric("recall_at_1"),
        recall_at_5=_metric("recall_at_5"),
        recall_at_10=_metric("recall_at_10"),
        precision_at_1=_metric("precision_at_1"),
        precision_at_5=_metric("precision_at_5"),
        precision_at_10=_metric("precision_at_10"),
        hit_rate_at_1=_metric("hit_rate_at_1"),
        hit_rate_at_5=_metric("hit_rate_at_5"),
        hit_rate_at_10=_metric("hit_rate_at_10"),
        hit_rate_at_30=_metric("hit_rate_at_30"),
        mrr=_metric("mrr"),
        ndcg_at_1=_metric("ndcg_at_1"),
        ndcg_at_5=_metric("ndcg_at_5"),
        ndcg_at_10=_metric("ndcg_at_10"),
    )


def build_category_aggregates(
    cases: list[CaseEvaluationResult],
) -> list[CategoryAggregate]:
    buckets: dict[str, list[CaseEvaluationResult]] = {}
    for case in cases:
        key = case.category if case.category is not None else "uncategorized"
        buckets.setdefault(key, []).append(case)
    aggregates: list[CategoryAggregate] = []
    for key in sorted(buckets):
        group = buckets[key]
        executed = [c for c in group if c.error is None]
        eligible = [c for c in group if c.quality_eligible]
        aggregates.append(
            CategoryAggregate(
                category=key,
                total_cases=len(group),
                executed_cases=len(executed),
                quality_eligible_cases=len(eligible),
                metrics=build_aggregate_metrics(group),
            )
        )
    return aggregates


def build_latency_summary(cases: list[CaseEvaluationResult]) -> LatencySummary:
    executed = [c for c in cases if c.error is None]
    values = [float(c.latency_ms) for c in executed]
    n = len(values)
    if n == 0:
        return LatencySummary(mean_ms=0.0, p50_ms=0.0, p95_ms=0.0, executed_cases=0)
    return LatencySummary(
        mean_ms=sum(values) / n,
        p50_ms=_percentile(values, 0.50),
        p95_ms=_percentile(values, 0.95),
        executed_cases=n,
    )


def metric_config_for_depth(requested_depth: int) -> MetricConfig:
    diagnostic: list[int] = []
    if requested_depth >= DIAGNOSTIC_HIT_RATE_CUTOFF:
        diagnostic.append(DIAGNOSTIC_HIT_RATE_CUTOFF)
    return MetricConfig(
        cutoffs=list(CANONICAL_CUTOFFS),
        diagnostic_hit_rate_cutoffs=diagnostic,
    )
