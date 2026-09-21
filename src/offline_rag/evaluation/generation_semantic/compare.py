"""Artifact-only generation-semantic result comparison (Slice 10E).

Loads two existing ``offline-rag-generation-semantic-eval-result-v1`` artifacts,
validates controlled prompt A/B compatibility, and produces a typed
``offline-rag-generation-semantic-eval-comparison-v1`` without invoking
generation, judge, or retrieval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.core.ids import (
    PROMPT_GROUNDED_PROVENANCE_V2,
    PROMPT_GROUNDED_V1,
    generation_comparison_id_from_payload,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_SEMANTIC_EVAL_COMPARISON_V1,
    GENERATION_SEMANTIC_EVAL_RESULT_V1,
    GOLD_EVIDENCE_V1,
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    CountDeltaV1,
    DimensionTransitionCountsV1,
    GenerationCompareCaseV1,
    GenerationCompareCompatibilityV1,
    GenerationNegativeCompareAggregatesV1,
    GenerationPositiveCohortCompareV1,
    GenerationPositiveCompareAggregatesV1,
    GenerationSemanticEvalComparisonV1,
    GenerationSemanticEvalResultV1,
    GenerationSemanticTransitionSummaryV1,
    MetricDeltaV1,
    NegativeLayer1Outcome,
    SemanticTransitionKind,
)
from offline_rag.ingestion.io import atomic_write_text

CONTROLLED_PROMPT_A = PROMPT_GROUNDED_V1
CONTROLLED_PROMPT_B = PROMPT_GROUNDED_PROVENANCE_V2

ANSWER_CORRECTNESS_ORDER = ("incorrect", "partially_correct", "fully_correct")
FAITHFULNESS_ORDER = ("unsupported", "partially_supported", "fully_supported")
COMPLETENESS_ORDER = ("incomplete", "partial", "complete")
CITATION_COVERAGE_ORDER = ("unsupported", "partial", "complete")
CITATION_USEFULNESS_ORDER = (
    "mostly_irrelevant",
    "some_irrelevant",
    "all_useful",
)

_GENERATION_SEMANTIC_COMPARE_KEYS = (
    "provider",
    "adapter_contract",
    "model",
    "temperature",
    "max_output_tokens",
    "output_contract",
    "recovery_contract",
    "reasoning_contract",
)


class GenerationCompareError(ValueError):
    """Fail-closed generation-semantic comparison error."""


def load_generation_semantic_eval_result(
    path: Path | str,
) -> GenerationSemanticEvalResultV1:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise GenerationCompareError(f"failed to read result artifact: {exc}") from exc
    try:
        result = GenerationSemanticEvalResultV1.model_validate_json(raw)
    except ValidationError as exc:
        raise GenerationCompareError(
            f"invalid generation result artifact: {exc}"
        ) from exc
    if result.schema_version != GENERATION_SEMANTIC_EVAL_RESULT_V1:
        raise GenerationCompareError(
            f"unsupported result schema_version: {result.schema_version}"
        )
    return result


def compare_generation_semantic_results(
    result_a: GenerationSemanticEvalResultV1,
    result_b: GenerationSemanticEvalResultV1,
    *,
    require_controlled_prompt_pair: bool = True,
) -> GenerationSemanticEvalComparisonV1:
    """Compare two measure-once generation-semantic results (artifact-only)."""
    compatibility = _validate_compatibility(
        result_a,
        result_b,
        require_controlled_prompt_pair=require_controlled_prompt_pair,
    )

    case_rows = _build_case_comparisons(result_a, result_b)
    positive_aggregates: GenerationPositiveCompareAggregatesV1 | None = None
    negative_aggregates: GenerationNegativeCompareAggregatesV1 | None = None
    semantic_transitions: GenerationSemanticTransitionSummaryV1 | None = None

    if result_a.expected_behavior == "answer":
        positive_aggregates = _positive_aggregates(result_a, result_b)
        semantic_transitions = _semantic_transition_summary(case_rows)
    else:
        negative_aggregates = _negative_aggregates(result_a, result_b, case_rows)

    comparison = GenerationSemanticEvalComparisonV1(
        comparison_id="pending",
        gold_dataset_id=result_a.gold_dataset_id,
        evidence_set_id=result_a.evidence_set_id,
        evidence_contract=result_a.evidence_contract,
        expected_behavior=result_a.expected_behavior,
        semantic_metric_contract=result_a.semantic_metric_contract,
        corpus_id=result_a.corpus_id,
        chunk_set_id=result_a.chunk_set_id,
        a_run_id=result_a.run_id,
        b_run_id=result_b.run_id,
        a_generation_config_hash=result_a.generation_config_hash,
        b_generation_config_hash=result_b.generation_config_hash,
        a_prompt_contract=str(
            result_a.generation_semantic_provenance.get("prompt_contract")
        ),
        b_prompt_contract=str(
            result_b.generation_semantic_provenance.get("prompt_contract")
        ),
        a_judge_config_hash=(
            result_a.judge_provenance.judge_config_hash
            if result_a.judge_provenance is not None
            else None
        ),
        b_judge_config_hash=(
            result_b.judge_provenance.judge_config_hash
            if result_b.judge_provenance is not None
            else None
        ),
        compatibility=compatibility,
        positive_aggregates=positive_aggregates,
        negative_aggregates=negative_aggregates,
        semantic_transitions=semantic_transitions,
        cases=case_rows,
        metadata={},
    )
    comparison_id = compute_generation_comparison_id(comparison)
    return comparison.model_copy(update={"comparison_id": comparison_id})


def compute_generation_comparison_id(
    comparison: GenerationSemanticEvalComparisonV1,
) -> str:
    return generation_comparison_id_from_payload(
        generation_comparison_semantic_payload(comparison)
    )


def generation_comparison_semantic_payload(
    comparison: GenerationSemanticEvalComparisonV1,
) -> dict[str, Any]:
    """Canonical identity payload (no timestamps / filesystem paths)."""
    payload = comparison.model_dump(mode="json")
    payload.pop("comparison_id", None)
    metadata = dict(payload.get("metadata") or {})
    for key in ("created_at", "a_path", "b_path", "output_path", "result_path"):
        metadata.pop(key, None)
    payload["metadata"] = metadata
    return payload


def persist_generation_comparison(
    comparison: GenerationSemanticEvalComparisonV1,
    *,
    path: Path,
) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    expected_id = compute_generation_comparison_id(comparison)
    if comparison.comparison_id != expected_id:
        raise GenerationCompareError(
            "comparison_id does not match semantic payload: "
            f"artifact={comparison.comparison_id} expected={expected_id}"
        )
    serialized = comparison.model_dump_json()
    if out.exists():
        existing = out.read_text(encoding="utf-8")
        try:
            prior = GenerationSemanticEvalComparisonV1.model_validate_json(existing)
        except ValidationError as exc:
            raise GenerationCompareError(
                f"existing comparison artifact is invalid: {out}: {exc}"
            ) from exc
        if prior.model_dump(mode="json") != comparison.model_dump(mode="json"):
            raise GenerationCompareError(
                f"comparison artifact already exists with different payload: {out}"
            )
        return out
    atomic_write_text(out, serialized)
    return out


def default_comparison_artifact_path(
    eval_results_root: Path, comparison_id: str
) -> Path:
    return (
        Path(eval_results_root)
        / "generation_semantic"
        / "comparisons"
        / f"{comparison_id}.json"
    )


def format_generation_comparison_human(
    comparison: GenerationSemanticEvalComparisonV1,
) -> str:
    lines = [
        "Generation semantic comparison completed",
        "",
        f"Comparison:    {comparison.comparison_id}",
        f"Evidence:      {comparison.evidence_set_id}",
        f"Contract:      {comparison.evidence_contract}",
        f"Expected:      {comparison.expected_behavior}",
        f"A run:         {comparison.a_run_id} ({comparison.a_prompt_contract})",
        f"B run:         {comparison.b_run_id} ({comparison.b_prompt_contract})",
        f"Cases:         {len(comparison.cases)}",
    ]
    if comparison.positive_aggregates is not None:
        full = comparison.positive_aggregates.cohorts.get("full")
        if full is not None:
            lines.extend(
                [
                    "",
                    "Positive (full)",
                    f"  answer_rate:           {_fmt_delta(full.answer_rate)}",
                    f"  false_abstention_rate: {_fmt_delta(full.false_abstention_rate)}",
                    f"  fully_correct_rate:    {_fmt_delta(full.fully_correct_rate)}",
                    f"  fully_supported_rate:  {_fmt_delta(full.fully_supported_rate)}",
                ]
            )
    if comparison.negative_aggregates is not None:
        neg = comparison.negative_aggregates
        lines.extend(
            [
                "",
                "Negative abstention",
                f"  correct_abstention: {_fmt_delta(neg.correct_abstention_rate)}",
                f"  false_answer:       {_fmt_delta(neg.false_answer_rate)}",
            ]
        )
    if comparison.semantic_transitions is not None:
        lines.append("")
        lines.append("Semantic transitions (paired judge-succeeded)")
        for name in (
            "answer_correctness",
            "faithfulness",
            "completeness",
            "citation_coverage",
            "citation_usefulness",
        ):
            counts = getattr(comparison.semantic_transitions, name)
            lines.append(
                f"  {name}: improved={counts.improved} unchanged={counts.unchanged} "
                f"regressed={counts.regressed} not_comparable={counts.not_comparable}"
            )
    return "\n".join(lines)


def _fmt_delta(metric: MetricDeltaV1) -> str:
    if metric.a is None and metric.b is None:
        return "n/a"
    a = "n/a" if metric.a is None else f"{metric.a:.4f}"
    b = "n/a" if metric.b is None else f"{metric.b:.4f}"
    d = "n/a" if metric.delta is None else f"{metric.delta:+.4f}"
    return f"A={a} B={b} delta={d}"


def classify_semantic_transition(
    value_a: str | None,
    value_b: str | None,
    order: Sequence[str],
) -> SemanticTransitionKind:
    if value_a is None or value_b is None:
        return "not_comparable"
    if value_a not in order or value_b not in order:
        return "not_comparable"
    ia = order.index(value_a)
    ib = order.index(value_b)
    if ib > ia:
        return "improved"
    if ib < ia:
        return "regressed"
    return "unchanged"


def classify_negative_layer1_outcome(
    *,
    status: str | None,
    abstention_reason: str | None,
) -> NegativeLayer1Outcome:
    if status == "answered":
        return "false_answer"
    if status == "insufficient_evidence":
        if abstention_reason == "model_abstain":
            return "correct_abstention"
        if abstention_reason == "empty_context":
            return "empty_context"
        return "other"
    if status == "generation_failed":
        return "generation_failed"
    if status == "citation_invalid":
        return "citation_invalid"
    return "other"


def _validate_compatibility(
    result_a: GenerationSemanticEvalResultV1,
    result_b: GenerationSemanticEvalResultV1,
    *,
    require_controlled_prompt_pair: bool,
) -> GenerationCompareCompatibilityV1:
    if result_a.gold_dataset_id != result_b.gold_dataset_id:
        raise GenerationCompareError("gold_dataset_id mismatch")
    if result_a.evidence_set_id != result_b.evidence_set_id:
        raise GenerationCompareError("evidence_set_id mismatch")
    if result_a.evidence_contract != result_b.evidence_contract:
        raise GenerationCompareError("evidence_contract mismatch")
    if result_a.expected_behavior != result_b.expected_behavior:
        raise GenerationCompareError("expected_behavior mismatch")
    if result_a.corpus_id != result_b.corpus_id:
        raise GenerationCompareError("corpus_id mismatch")
    if result_a.chunk_set_id != result_b.chunk_set_id:
        raise GenerationCompareError("chunk_set_id mismatch")
    if result_a.semantic_metric_contract != result_b.semantic_metric_contract:
        raise GenerationCompareError("semantic_metric_contract mismatch")

    cases_a = {c.case_id: c for c in result_a.cases}
    cases_b = {c.case_id: c for c in result_b.cases}
    if set(cases_a) != set(cases_b):
        raise GenerationCompareError("case ID sets differ")
    for case_id in sorted(cases_a):
        ca = cases_a[case_id]
        cb = cases_b[case_id]
        if ca.query != cb.query:
            raise GenerationCompareError(f"query mismatch for case {case_id}")
        if ca.label_cohort != cb.label_cohort:
            raise GenerationCompareError(f"cohort mismatch for case {case_id}")

    prompt_a = str(result_a.generation_semantic_provenance.get("prompt_contract") or "")
    prompt_b = str(result_b.generation_semantic_provenance.get("prompt_contract") or "")
    if not prompt_a or not prompt_b:
        raise GenerationCompareError(
            "prompt_contract missing from generation provenance"
        )

    _assert_generation_semantics_equal_except_prompt(
        result_a.generation_semantic_provenance,
        result_b.generation_semantic_provenance,
    )

    prompt_pair_accepted = (
        prompt_a == CONTROLLED_PROMPT_A and prompt_b == CONTROLLED_PROMPT_B
    )
    if require_controlled_prompt_pair and not prompt_pair_accepted:
        raise GenerationCompareError(
            "controlled prompt pair required: "
            f"A={CONTROLLED_PROMPT_A!r} B={CONTROLLED_PROMPT_B!r}; "
            f"got A={prompt_a!r} B={prompt_b!r}"
        )

    if not result_a.judge_enabled or not result_b.judge_enabled:
        raise GenerationCompareError("both results must have judge_enabled=true")
    if result_a.judge_provenance is None or result_b.judge_provenance is None:
        raise GenerationCompareError("both results require judge_provenance")
    _assert_judge_contract_equal(result_a.judge_provenance, result_b.judge_provenance)

    return GenerationCompareCompatibilityV1(
        same_gold_dataset_id=True,
        same_evidence_set_id=True,
        same_evidence_contract=True,
        same_expected_behavior=True,
        same_corpus_id=True,
        same_chunk_set_id=True,
        same_case_set=True,
        same_queries=True,
        same_cohort_labels=True,
        same_semantic_metric_contract=True,
        same_generation_semantics_except_prompt=True,
        same_judge_contract=True,
        prompt_pair_accepted=prompt_pair_accepted,
        a_prompt_contract=prompt_a,
        b_prompt_contract=prompt_b,
    )


def _assert_generation_semantics_equal_except_prompt(
    semantics_a: Mapping[str, Any],
    semantics_b: Mapping[str, Any],
) -> None:
    for key in _GENERATION_SEMANTIC_COMPARE_KEYS:
        if semantics_a.get(key) != semantics_b.get(key):
            raise GenerationCompareError(
                f"generation semantic field differs (not prompt): {key} "
                f"A={semantics_a.get(key)!r} B={semantics_b.get(key)!r}"
            )
    if float(semantics_a.get("temperature", 0.0)) != 0.0:
        raise GenerationCompareError("controlled comparison requires temperature==0.0")
    if float(semantics_b.get("temperature", 0.0)) != 0.0:
        raise GenerationCompareError("controlled comparison requires temperature==0.0")


def _assert_judge_contract_equal(prov_a: Any, prov_b: Any) -> None:
    fields = (
        "judge_config_hash",
        "provider",
        "normalized_endpoint",
        "model",
        "prompt_contract",
        "output_contract",
        "network_policy",
        "same_model_self_judge",
    )
    for field in fields:
        if getattr(prov_a, field) != getattr(prov_b, field):
            raise GenerationCompareError(
                f"judge contract mismatch on {field}: "
                f"A={getattr(prov_a, field)!r} B={getattr(prov_b, field)!r}"
            )


def _build_case_comparisons(
    result_a: GenerationSemanticEvalResultV1,
    result_b: GenerationSemanticEvalResultV1,
) -> list[GenerationCompareCaseV1]:
    cases_b = {c.case_id: c for c in result_b.cases}
    rows: list[GenerationCompareCaseV1] = []
    for case_a in sorted(result_a.cases, key=lambda item: item.case_id):
        case_b = cases_b[case_a.case_id]
        judge_a = case_a.judge_result
        judge_b = case_b.judge_result
        a_correct = judge_a.answer_correctness if judge_a else None
        b_correct = judge_b.answer_correctness if judge_b else None
        a_faith = judge_a.faithfulness if judge_a else None
        b_faith = judge_b.faithfulness if judge_b else None
        a_comp = judge_a.completeness if judge_a else None
        b_comp = judge_b.completeness if judge_b else None
        a_cov = judge_a.citation_coverage if judge_a else None
        b_cov = judge_b.citation_coverage if judge_b else None
        a_use = judge_a.citation_usefulness if judge_a else None
        b_use = judge_b.citation_usefulness if judge_b else None

        # Only compare semantic dimensions when both judges succeeded.
        both_succeeded = (
            judge_a is not None
            and judge_b is not None
            and judge_a.judge_status == "succeeded"
            and judge_b.judge_status == "succeeded"
        )
        if both_succeeded:
            correct_t = classify_semantic_transition(
                a_correct, b_correct, ANSWER_CORRECTNESS_ORDER
            )
            faith_t = classify_semantic_transition(a_faith, b_faith, FAITHFULNESS_ORDER)
            comp_t = classify_semantic_transition(a_comp, b_comp, COMPLETENESS_ORDER)
            cov_t = classify_semantic_transition(a_cov, b_cov, CITATION_COVERAGE_ORDER)
            use_t = classify_semantic_transition(
                a_use, b_use, CITATION_USEFULNESS_ORDER
            )
        else:
            correct_t = faith_t = comp_t = cov_t = use_t = "not_comparable"

        recall_a = case_a.deterministic_metrics.gold_citation_recall
        recall_b = case_b.deterministic_metrics.gold_citation_recall
        recall_delta = (
            float(recall_b) - float(recall_a)
            if recall_a is not None and recall_b is not None
            else None
        )
        latency_delta = (
            int(case_b.latency_ms) - int(case_a.latency_ms)
            if case_a.latency_ms is not None and case_b.latency_ms is not None
            else None
        )

        a_outcome = b_outcome = transition = None
        review_signal = False
        if result_a.expected_behavior == "abstain":
            a_outcome = classify_negative_layer1_outcome(
                status=case_a.status, abstention_reason=case_a.abstention_reason
            )
            b_outcome = classify_negative_layer1_outcome(
                status=case_b.status, abstention_reason=case_b.abstention_reason
            )
            transition = f"{a_outcome}->{b_outcome}"
            review_signal = _fixture_review_signal(case_a) or _fixture_review_signal(
                case_b
            )

        rows.append(
            GenerationCompareCaseV1(
                case_id=case_a.case_id,
                label_cohort=case_a.label_cohort,
                query=case_a.query,
                a_status=case_a.status,
                b_status=case_b.status,
                status_transition=f"{case_a.status}->{case_b.status}",
                a_layer1_outcome=a_outcome,
                b_layer1_outcome=b_outcome,
                layer1_outcome_transition=transition,
                a_citation_ids=list(case_a.citation_ids),
                b_citation_ids=list(case_b.citation_ids),
                a_citation_count=case_a.deterministic_metrics.cited_evidence_count,
                b_citation_count=case_b.deterministic_metrics.cited_evidence_count,
                a_gold_citation_recall=recall_a,
                b_gold_citation_recall=recall_b,
                gold_citation_recall_delta=recall_delta,
                a_grade2_citation_hit=case_a.deterministic_metrics.grade2_citation_hit,
                b_grade2_citation_hit=case_b.deterministic_metrics.grade2_citation_hit,
                a_judge_status=judge_a.judge_status if judge_a else None,
                b_judge_status=judge_b.judge_status if judge_b else None,
                a_answer_correctness=a_correct,
                b_answer_correctness=b_correct,
                answer_correctness_transition=correct_t,
                a_faithfulness=a_faith,
                b_faithfulness=b_faith,
                faithfulness_transition=faith_t,
                a_completeness=a_comp,
                b_completeness=b_comp,
                completeness_transition=comp_t,
                a_citation_coverage=a_cov,
                b_citation_coverage=b_cov,
                citation_coverage_transition=cov_t,
                a_citation_usefulness=a_use,
                b_citation_usefulness=b_use,
                citation_usefulness_transition=use_t,
                a_latency_ms=case_a.latency_ms,
                b_latency_ms=case_b.latency_ms,
                latency_delta_ms=latency_delta,
                negative_fixture_review_signal=review_signal,
            )
        )
    return rows


def _fixture_review_signal(case: Any) -> bool:
    if case.status != "answered":
        return False
    judge = case.judge_result
    if judge is None or judge.judge_status != "succeeded":
        return False
    return judge.answer_correctness == "fully_correct" or (
        judge.faithfulness == "fully_supported"
    )


def _rate_delta(a: float | None, b: float | None) -> MetricDeltaV1:
    if a is None and b is None:
        return MetricDeltaV1()
    delta = None if a is None or b is None else float(b) - float(a)
    return MetricDeltaV1(a=a, b=b, delta=delta)


def _metric_value_delta(a: Any, b: Any) -> MetricDeltaV1:
    a_val = None if a is None else a.value
    b_val = None if b is None else b.value
    a_n = 0 if a is None else int(a.applicable_count)
    b_n = 0 if b is None else int(b.applicable_count)
    delta = None if a_val is None or b_val is None else float(b_val) - float(a_val)
    return MetricDeltaV1(
        a=a_val,
        b=b_val,
        delta=delta,
        a_applicable_count=a_n,
        b_applicable_count=b_n,
    )


def _count_delta(a: int | None, b: int | None) -> CountDeltaV1:
    if a is None and b is None:
        return CountDeltaV1()
    delta = None if a is None or b is None else int(b) - int(a)
    return CountDeltaV1(a=a, b=b, delta=delta)


def _positive_aggregates(
    result_a: GenerationSemanticEvalResultV1,
    result_b: GenerationSemanticEvalResultV1,
) -> GenerationPositiveCompareAggregatesV1:
    cohorts: dict[str, GenerationPositiveCohortCompareV1] = {}
    for key in ("full", "human_reviewed", "assistant_only"):
        ca = result_a.deterministic_aggregates.cohorts.get(key)
        cb = result_b.deterministic_aggregates.cohorts.get(key)
        sa = (
            None
            if result_a.semantic_aggregates is None
            else result_a.semantic_aggregates.cohorts.get(key)
        )
        sb = (
            None
            if result_b.semantic_aggregates is None
            else result_b.semantic_aggregates.cohorts.get(key)
        )
        case_count = 0 if ca is None else ca.case_count
        cohorts[key] = GenerationPositiveCohortCompareV1(
            cohort=key,  # type: ignore[arg-type]
            case_count=case_count,
            answer_rate=_rate_delta(
                None if ca is None else ca.answer_rate,
                None if cb is None else cb.answer_rate,
            ),
            false_abstention_rate=_rate_delta(
                None if ca is None else ca.false_abstention_rate,
                None if cb is None else cb.false_abstention_rate,
            ),
            generation_failed_rate=_rate_delta(
                None if ca is None else ca.generation_failed_rate,
                None if cb is None else cb.generation_failed_rate,
            ),
            citation_invalid_rate=_rate_delta(
                None if ca is None else ca.citation_invalid_rate,
                None if cb is None else cb.citation_invalid_rate,
            ),
            mean_gold_citation_recall=_metric_value_delta(
                None if ca is None else ca.mean_gold_citation_recall,
                None if cb is None else cb.mean_gold_citation_recall,
            ),
            grade2_citation_hit_rate=_metric_value_delta(
                None if ca is None else ca.grade2_citation_hit_rate,
                None if cb is None else cb.grade2_citation_hit_rate,
            ),
            fully_correct_rate=_metric_value_delta(
                None if sa is None else sa.fully_correct_rate,
                None if sb is None else sb.fully_correct_rate,
            ),
            fully_supported_rate=_metric_value_delta(
                None if sa is None else sa.fully_supported_rate,
                None if sb is None else sb.fully_supported_rate,
            ),
            complete_answer_rate=_metric_value_delta(
                None if sa is None else sa.complete_answer_rate,
                None if sb is None else sb.complete_answer_rate,
            ),
            complete_citation_coverage_rate=_metric_value_delta(
                None if sa is None else sa.complete_citation_coverage_rate,
                None if sb is None else sb.complete_citation_coverage_rate,
            ),
            all_citations_useful_rate=_metric_value_delta(
                None if sa is None else sa.all_citations_useful_rate,
                None if sb is None else sb.all_citations_useful_rate,
            ),
            latency_mean_ms=_rate_delta(
                None if ca is None else float(ca.latency.mean_ms),
                None if cb is None else float(cb.latency.mean_ms),
            ),
            eligible_answered_cases=_count_delta(
                None if sa is None else sa.eligible_answered_cases,
                None if sb is None else sb.eligible_answered_cases,
            ),
            judge_succeeded=_count_delta(
                None if sa is None else sa.judge_succeeded,
                None if sb is None else sb.judge_succeeded,
            ),
            judge_failed=_count_delta(
                None if sa is None else sa.judge_failed,
                None if sb is None else sb.judge_failed,
            ),
            judge_unavailable=_count_delta(
                None if sa is None else sa.judge_unavailable,
                None if sb is None else sb.judge_unavailable,
            ),
        )
    return GenerationPositiveCompareAggregatesV1(cohorts=cohorts)


def _semantic_transition_summary(
    cases: list[GenerationCompareCaseV1],
) -> GenerationSemanticTransitionSummaryV1:
    summary = GenerationSemanticTransitionSummaryV1()
    mapping = (
        ("answer_correctness", "answer_correctness_transition"),
        ("faithfulness", "faithfulness_transition"),
        ("completeness", "completeness_transition"),
        ("citation_coverage", "citation_coverage_transition"),
        ("citation_usefulness", "citation_usefulness_transition"),
    )
    for dim_name, field_name in mapping:
        counts = DimensionTransitionCountsV1()
        for case in cases:
            kind = getattr(case, field_name)
            if kind is None:
                counts.not_comparable += 1
            else:
                setattr(counts, kind, getattr(counts, kind) + 1)
        setattr(summary, dim_name, counts)
    return summary


def _negative_aggregates(
    result_a: GenerationSemanticEvalResultV1,
    result_b: GenerationSemanticEvalResultV1,
    cases: list[GenerationCompareCaseV1],
) -> GenerationNegativeCompareAggregatesV1:
    if result_a.evidence_contract != HUMAN_GRADE0_HARD_NEGATIVE_V1:
        raise GenerationCompareError(
            f"negative aggregates require {HUMAN_GRADE0_HARD_NEGATIVE_V1}"
        )
    aa = result_a.abstention_aggregates
    ab = result_b.abstention_aggregates
    if aa is None or ab is None:
        raise GenerationCompareError(
            "negative comparison requires abstention_aggregates"
        )

    transitions: dict[str, int] = {}
    for case in cases:
        key = case.layer1_outcome_transition or "unknown"
        transitions[key] = transitions.get(key, 0) + 1

    false_judged_a = false_supported_a = false_correct_a = 0
    false_judged_b = false_supported_b = false_correct_b = 0
    cases_b = {c.case_id: c for c in result_b.cases}
    for case_a in result_a.cases:
        case_b = cases_b[case_a.case_id]
        ja, jb = case_a.judge_result, case_b.judge_result
        if (
            case_a.status == "answered"
            and ja is not None
            and ja.judge_status == "succeeded"
        ):
            false_judged_a += 1
            if ja.faithfulness == "fully_supported":
                false_supported_a += 1
            if ja.answer_correctness == "fully_correct":
                false_correct_a += 1
        if (
            case_b.status == "answered"
            and jb is not None
            and jb.judge_status == "succeeded"
        ):
            false_judged_b += 1
            if jb.faithfulness == "fully_supported":
                false_supported_b += 1
            if jb.answer_correctness == "fully_correct":
                false_correct_b += 1

    return GenerationNegativeCompareAggregatesV1(
        total_cases=aa.total_cases,
        correct_abstention_rate=_rate_delta(
            aa.correct_abstention_rate, ab.correct_abstention_rate
        ),
        false_answer_rate=_rate_delta(aa.false_answer_rate, ab.false_answer_rate),
        generation_failed_rate=_rate_delta(
            aa.generation_failed_rate, ab.generation_failed_rate
        ),
        citation_invalid_rate=_rate_delta(
            aa.citation_invalid_rate, ab.citation_invalid_rate
        ),
        empty_context_rate=_rate_delta(aa.empty_context_rate, ab.empty_context_rate),
        latency_mean_ms=_rate_delta(
            float(aa.latency.mean_ms), float(ab.latency.mean_ms)
        ),
        false_answers_judged=_count_delta(false_judged_a, false_judged_b),
        false_answers_fully_supported=_count_delta(
            false_supported_a, false_supported_b
        ),
        false_answers_fully_correct=_count_delta(false_correct_a, false_correct_b),
        abstention_outcome_transitions=dict(sorted(transitions.items())),
    )


__all__ = [
    "CONTROLLED_PROMPT_A",
    "CONTROLLED_PROMPT_B",
    "GENERATION_SEMANTIC_EVAL_COMPARISON_V1",
    "GOLD_EVIDENCE_V1",
    "GenerationCompareError",
    "classify_negative_layer1_outcome",
    "classify_semantic_transition",
    "compare_generation_semantic_results",
    "compute_generation_comparison_id",
    "default_comparison_artifact_path",
    "format_generation_comparison_human",
    "generation_comparison_semantic_payload",
    "load_generation_semantic_eval_result",
    "persist_generation_comparison",
]
