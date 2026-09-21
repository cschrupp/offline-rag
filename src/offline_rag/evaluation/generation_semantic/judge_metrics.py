"""Layer-2 semantic judge aggregate metrics (Slice 10C)."""

from __future__ import annotations

from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_SEMANTIC_METRICS_V1,
    CohortKey,
    GenerationMetricValueV1,
    GenerationSemanticAggregatesV1,
    GenerationSemanticCohortAggregateV1,
    GenerationSemanticDimensionCountsV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticJudgeCaseResultV1,
)


def not_applicable_judge_result() -> GenerationSemanticJudgeCaseResultV1:
    return GenerationSemanticJudgeCaseResultV1(judge_status="not_applicable")


def unavailable_judge_result() -> GenerationSemanticJudgeCaseResultV1:
    return GenerationSemanticJudgeCaseResultV1(judge_status="judge_unavailable")


def failed_judge_result(
    reason: str,
) -> GenerationSemanticJudgeCaseResultV1:
    allowed = {
        "timeout",
        "transport_error",
        "http_error",
        "empty_response",
        "invalid_json",
        "schema_invalid",
        "redirect_not_allowed",
        "authentication_error",
        "prompt_build_error",
        "provider_error",
    }
    typed = reason if reason in allowed else "provider_error"
    return GenerationSemanticJudgeCaseResultV1(
        judge_status="judge_failed",
        judge_failure_reason=typed,  # type: ignore[arg-type]
    )


def build_semantic_aggregates(
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationSemanticAggregatesV1:
    full = _semantic_cohort("full", cases)
    human = _semantic_cohort(
        "human_reviewed",
        [c for c in cases if c.label_cohort == "human_reviewed"],
    )
    assistant = _semantic_cohort(
        "assistant_only",
        [c for c in cases if c.label_cohort == "assistant_only"],
    )
    return GenerationSemanticAggregatesV1(
        metric_contract=GENERATION_SEMANTIC_METRICS_V1,
        eligible_answered_cases=full.eligible_answered_cases,
        judge_succeeded=full.judge_succeeded,
        judge_failed=full.judge_failed,
        judge_unavailable=full.judge_unavailable,
        answer_correctness=full.answer_correctness,
        faithfulness=full.faithfulness,
        completeness=full.completeness,
        citation_coverage=full.citation_coverage,
        citation_usefulness=full.citation_usefulness,
        fully_correct_rate=full.fully_correct_rate,
        fully_supported_rate=full.fully_supported_rate,
        complete_answer_rate=full.complete_answer_rate,
        complete_citation_coverage_rate=full.complete_citation_coverage_rate,
        all_citations_useful_rate=full.all_citations_useful_rate,
        cohorts={
            "full": full,
            "human_reviewed": human,
            "assistant_only": assistant,
        },
    )


def _semantic_cohort(
    key: CohortKey,
    cases: list[GenerationSemanticEvalCaseResultV1],
) -> GenerationSemanticCohortAggregateV1:
    n = len(cases)
    if n == 0:
        return GenerationSemanticCohortAggregateV1(cohort=key, case_count=0)

    answered = [c for c in cases if c.status == "answered"]
    eligible = answered
    succeeded = [
        c
        for c in eligible
        if c.judge_result is not None and c.judge_result.judge_status == "succeeded"
    ]
    failed = sum(
        1
        for c in eligible
        if c.judge_result is not None and c.judge_result.judge_status == "judge_failed"
    )
    unavailable = sum(
        1
        for c in eligible
        if c.judge_result is not None
        and c.judge_result.judge_status == "judge_unavailable"
    )

    return GenerationSemanticCohortAggregateV1(
        cohort=key,
        case_count=n,
        answered_count=len(answered),
        eligible_answered_cases=len(eligible),
        judge_succeeded=len(succeeded),
        judge_failed=failed,
        judge_unavailable=unavailable,
        answer_correctness=_dimension_counts(
            succeeded,
            "answer_correctness",
            ("fully_correct", "partially_correct", "incorrect"),
        ),
        faithfulness=_dimension_counts(
            succeeded,
            "faithfulness",
            ("fully_supported", "partially_supported", "unsupported"),
        ),
        completeness=_dimension_counts(
            succeeded, "completeness", ("complete", "partial", "incomplete")
        ),
        citation_coverage=_dimension_counts(
            succeeded,
            "citation_coverage",
            ("complete", "partial", "unsupported"),
        ),
        citation_usefulness=_dimension_counts(
            succeeded,
            "citation_usefulness",
            ("all_useful", "some_irrelevant", "mostly_irrelevant"),
        ),
        fully_correct_rate=_rate(succeeded, "answer_correctness", "fully_correct"),
        fully_supported_rate=_rate(succeeded, "faithfulness", "fully_supported"),
        complete_answer_rate=_rate(succeeded, "completeness", "complete"),
        complete_citation_coverage_rate=_rate(
            succeeded, "citation_coverage", "complete"
        ),
        all_citations_useful_rate=_rate(succeeded, "citation_usefulness", "all_useful"),
    )


def _dimension_counts(
    succeeded: list[GenerationSemanticEvalCaseResultV1],
    field: str,
    labels: tuple[str, ...],
) -> GenerationSemanticDimensionCountsV1:
    counts = {label: 0 for label in labels}
    for case in succeeded:
        assert case.judge_result is not None
        value = getattr(case.judge_result, field)
        if value in counts:
            counts[value] += 1
    return GenerationSemanticDimensionCountsV1(counts=counts)


def _rate(
    succeeded: list[GenerationSemanticEvalCaseResultV1],
    field: str,
    target: str,
) -> GenerationMetricValueV1:
    applicable = len(succeeded)
    if applicable == 0:
        return GenerationMetricValueV1(value=None, applicable_count=0)
    hits = 0
    for case in succeeded:
        assert case.judge_result is not None
        if getattr(case.judge_result, field) == target:
            hits += 1
    return GenerationMetricValueV1(
        value=hits / applicable,
        applicable_count=applicable,
    )
