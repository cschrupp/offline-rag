"""Layer-1 deterministic generation/citation diagnostics (Slice 10B)."""

from __future__ import annotations

from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_ABSTENTION_DETERMINISTIC_V1,
    GENERATION_SEMANTIC_DETERMINISTIC_V1,
    CohortKey,
    GenerationAbstentionAggregatesV1,
    GenerationAbstentionCohortAggregateV1,
    GenerationCohortAggregateV1,
    GenerationDeterministicAggregatesV1,
    GenerationDeterministicCaseMetricsV1,
    GenerationEvidenceCaseV1,
    GenerationLatencySummaryV1,
    GenerationMetricValueV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticPopulationV1,
    LabelCohort,
)

__all__ = [
    "GENERATION_ABSTENTION_DETERMINISTIC_V1",
    "GENERATION_SEMANTIC_DETERMINISTIC_V1",
    "build_abstention_aggregates",
    "build_deterministic_aggregates",
    "build_population",
    "compute_case_deterministic_metrics",
    "percentile",
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = low if low == len(ordered) - 1 else low + 1
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def compute_case_deterministic_metrics(
    case: GenerationEvidenceCaseV1,
    result: GroundedAnswerResult,
) -> GenerationDeterministicCaseMetricsV1:
    grade_by_chunk = {j.chunk_id: int(j.relevance) for j in case.gold_judgments}
    gold_ids = set(grade_by_chunk)
    gold_grade2 = {cid for cid, grade in grade_by_chunk.items() if grade == 2}
    gold_grade1 = {cid for cid, grade in grade_by_chunk.items() if grade == 1}

    cited_source_ids = _cited_source_chunk_ids(result.citations)
    cited_gold = sorted(cid for cid in cited_source_ids if cid in gold_ids)
    cited_g2 = sum(1 for cid in cited_gold if cid in gold_grade2)
    cited_g1 = sum(1 for cid in cited_gold if cid in gold_grade1)

    # Hard-negative fixture: positive gold was intentionally NOT supplied as
    # evidence. Citation-quality diagnostics vs gold positives are non-applicable.
    recall: float | None = None
    grade2_hit: bool | None = None
    if case.expected_behavior != "abstain" and result.status == "answered":
        if gold_ids:
            recall = len(set(cited_gold)) / float(len(gold_ids))
        else:
            recall = 0.0
        if gold_grade2:
            grade2_hit = any(cid in gold_grade2 for cid in cited_gold)

    return GenerationDeterministicCaseMetricsV1(
        gold_positive_count=len(gold_ids),
        gold_grade2_count=len(gold_grade2),
        gold_grade1_count=len(gold_grade1),
        cited_evidence_count=len(result.citations),
        cited_gold_chunk_ids=cited_gold,
        cited_gold_grade2_count=cited_g2,
        cited_gold_grade1_count=cited_g1,
        gold_citation_recall=recall,
        grade2_citation_hit=grade2_hit,
    )


def _cited_source_chunk_ids(citations: list[ResolvedCitation]) -> list[str]:
    return [citation.source_chunk_id for citation in citations]


def build_population(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationSemanticPopulationV1:
    population = GenerationSemanticPopulationV1(
        total_cases=len(cases),
        executed_cases=len(cases),
        human_reviewed_cases=sum(
            1 for case in cases if case.label_cohort == "human_reviewed"
        ),
        assistant_only_cases=sum(
            1 for case in cases if case.label_cohort == "assistant_only"
        ),
    )
    for case in cases:
        if case.status == "answered":
            population.answered += 1
        elif case.status == "insufficient_evidence":
            if case.abstention_reason == "empty_context":
                population.empty_context += 1
            else:
                population.model_abstain += 1
        elif case.status == "generation_failed":
            population.generation_failed += 1
        elif case.status == "citation_invalid":
            population.citation_invalid += 1
    return population


def build_deterministic_aggregates(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationDeterministicAggregatesV1:
    full = _cohort_aggregate("full", cases)
    human = _cohort_aggregate(
        "human_reviewed",
        [c for c in cases if c.label_cohort == "human_reviewed"],
    )
    assistant = _cohort_aggregate(
        "assistant_only",
        [c for c in cases if c.label_cohort == "assistant_only"],
    )
    return GenerationDeterministicAggregatesV1(
        metric_contract=GENERATION_SEMANTIC_DETERMINISTIC_V1,
        answer_rate=full.answer_rate,
        false_abstention_rate=full.false_abstention_rate,
        generation_failed_rate=full.generation_failed_rate,
        citation_invalid_rate=full.citation_invalid_rate,
        empty_context_rate=full.empty_context_rate,
        mean_gold_citation_recall=full.mean_gold_citation_recall,
        grade2_citation_hit_rate=full.grade2_citation_hit_rate,
        citation_count_mean=_answered_citation_stat(cases, "mean"),
        citation_count_p50=_answered_citation_stat(cases, "p50"),
        citation_count_p95=_answered_citation_stat(cases, "p95"),
        latency=full.latency,
        cohorts={
            "full": full,
            "human_reviewed": human,
            "assistant_only": assistant,
        },
    )


def _cohort_aggregate(
    key: CohortKey,
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationCohortAggregateV1:
    n = len(cases)
    if n == 0:
        return GenerationCohortAggregateV1(cohort=key, case_count=0)

    answered = sum(1 for c in cases if c.status == "answered")
    false_abstain = sum(
        1
        for c in cases
        if c.status == "insufficient_evidence"
        and c.abstention_reason == "model_abstain"
    )
    gen_failed = sum(1 for c in cases if c.status == "generation_failed")
    citation_invalid = sum(1 for c in cases if c.status == "citation_invalid")
    empty_context = sum(
        1
        for c in cases
        if c.status == "insufficient_evidence"
        and c.abstention_reason == "empty_context"
    )

    recall_values = [
        float(c.deterministic_metrics.gold_citation_recall)
        for c in cases
        if c.status == "answered"
        and c.deterministic_metrics.gold_citation_recall is not None
    ]
    grade2_hits = [
        c.deterministic_metrics.grade2_citation_hit
        for c in cases
        if c.status == "answered"
        and c.deterministic_metrics.grade2_citation_hit is not None
    ]

    return GenerationCohortAggregateV1(
        cohort=key,
        case_count=n,
        answer_rate=answered / n,
        false_abstention_rate=false_abstain / n,
        generation_failed_rate=gen_failed / n,
        citation_invalid_rate=citation_invalid / n,
        empty_context_rate=empty_context / n,
        mean_gold_citation_recall=GenerationMetricValueV1(
            value=(sum(recall_values) / len(recall_values)) if recall_values else None,
            applicable_count=len(recall_values),
        ),
        grade2_citation_hit_rate=GenerationMetricValueV1(
            value=(
                (sum(1 for hit in grade2_hits if hit) / len(grade2_hits))
                if grade2_hits
                else None
            ),
            applicable_count=len(grade2_hits),
        ),
        latency=_latency_summary(cases),
    )


def _answered_citation_stat(
    cases: list[GenerationSemanticEvalCaseResultV1],
    which: str,
) -> float | None:
    counts = [
        float(c.deterministic_metrics.cited_evidence_count)
        for c in cases
        if c.status == "answered"
    ]
    if not counts:
        return None
    if which == "mean":
        return sum(counts) / len(counts)
    if which == "p50":
        return percentile(counts, 0.50)
    if which == "p95":
        return percentile(counts, 0.95)
    raise ValueError(f"unknown citation stat: {which}")


def _latency_summary(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationLatencySummaryV1:
    totals = [float(c.latency_ms) for c in cases if c.latency_ms is not None]
    gens = [
        float(c.generation_latency_ms)
        for c in cases
        if c.generation_latency_ms is not None
    ]
    if not totals:
        return GenerationLatencySummaryV1()
    return GenerationLatencySummaryV1(
        mean_ms=sum(totals) / len(totals),
        p50_ms=percentile(totals, 0.50),
        p95_ms=percentile(totals, 0.95),
        executed_count=len(totals),
        generation_mean_ms=(sum(gens) / len(gens)) if gens else 0.0,
    )


def cohort_mapping_from_cases(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> dict[str, LabelCohort]:
    return {
        case.case_id: case.label_cohort
        for case in cases
        if case.label_cohort is not None
    }


def build_abstention_aggregates(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationAbstentionAggregatesV1:
    """Layer-1 abstention aggregates for label-defined hard-negative fixtures.

    Denominator for top-level rates is ``total_cases`` (all cases in the
    negative fixture). Cohort rates use that cohort's ``case_count`` when
    non-zero; empty cohorts keep rates as null (do not invent zeros).
    """
    full = _abstention_cohort("full", cases)
    human = _abstention_cohort(
        "human_reviewed",
        [c for c in cases if c.label_cohort == "human_reviewed"],
    )
    assistant = _abstention_cohort(
        "assistant_only",
        [c for c in cases if c.label_cohort == "assistant_only"],
    )
    return GenerationAbstentionAggregatesV1(
        metric_contract=GENERATION_ABSTENTION_DETERMINISTIC_V1,
        total_cases=len(cases),
        correct_abstention_rate=full.correct_abstention_rate,
        false_answer_rate=full.false_answer_rate,
        generation_failed_rate=full.generation_failed_rate,
        citation_invalid_rate=full.citation_invalid_rate,
        empty_context_rate=full.empty_context_rate,
        latency=full.latency,
        cohorts={
            "full": full,
            "human_reviewed": human,
            "assistant_only": assistant,
        },
    )


def _abstention_cohort(
    key: CohortKey,
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationAbstentionCohortAggregateV1:
    n = len(cases)
    if n == 0:
        return GenerationAbstentionCohortAggregateV1(cohort=key, case_count=0)

    correct_abstain = sum(
        1
        for c in cases
        if c.status == "insufficient_evidence"
        and c.abstention_reason == "model_abstain"
    )
    false_answer = sum(1 for c in cases if c.status == "answered")
    gen_failed = sum(1 for c in cases if c.status == "generation_failed")
    citation_invalid = sum(1 for c in cases if c.status == "citation_invalid")
    empty_context = sum(
        1
        for c in cases
        if c.status == "insufficient_evidence"
        and c.abstention_reason == "empty_context"
    )
    return GenerationAbstentionCohortAggregateV1(
        cohort=key,
        case_count=n,
        correct_abstention_rate=correct_abstain / n,
        false_answer_rate=false_answer / n,
        generation_failed_rate=gen_failed / n,
        citation_invalid_rate=citation_invalid / n,
        empty_context_rate=empty_context / n,
        latency=_latency_summary(cases),
    )
