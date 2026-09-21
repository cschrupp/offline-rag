"""Slice 10E — artifact-only generation-semantic comparison."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.core.ids import PROMPT_GROUNDED_PROVENANCE_V2, PROMPT_GROUNDED_V1
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.evaluation.generation_semantic.compare import (
    CONTROLLED_PROMPT_A,
    CONTROLLED_PROMPT_B,
    GenerationCompareError,
    classify_semantic_transition,
    compare_generation_semantic_results,
    compute_generation_comparison_id,
    generation_comparison_semantic_payload,
    persist_generation_comparison,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_ABSTENTION_DETERMINISTIC_V1,
    GOLD_EVIDENCE_V1,
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    GenerationAbstentionAggregatesV1,
    GenerationCohortAggregateV1,
    GenerationDeterministicAggregatesV1,
    GenerationDeterministicCaseMetricsV1,
    GenerationMetricValueV1,
    GenerationSemanticAggregatesV1,
    GenerationSemanticCohortAggregateV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticEvalResultV1,
    GenerationSemanticJudgeCaseResultV1,
    GenerationSemanticJudgeProvenanceV1,
    GenerationSemanticPopulationV1,
)
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.lexical.retrieve import LexicalRetriever


def _judge_prov(
    *, judgecfg: str = "judgecfg_same"
) -> GenerationSemanticJudgeProvenanceV1:
    return GenerationSemanticJudgeProvenanceV1(
        judge_requested=True,
        judge_available=True,
        judge_config_hash=judgecfg,
        provider="openai_compatible",
        normalized_endpoint="http://127.0.0.1:11434/v1",
        model="test-model",
        adapter_contract="openai-compatible-generation-semantic-judge-v1",
        prompt_contract="generation-semantic-judge-v1",
        output_contract="generation-semantic-judge-output-v1",
        reasoning_contract="direct-output-v1",
        network_policy="localhost_only",
        same_model_self_judge=True,
        same_endpoint_as_generator=True,
        preflight_status="READY",
        preflight_kind="ready",
    )


def _semantics(*, prompt: str) -> dict[str, object]:
    return {
        "provider": "openai_compatible",
        "adapter_contract": "openai-compatible-generator-v1",
        "model": "test-model",
        "temperature": 0.0,
        "max_output_tokens": 1200,
        "prompt_contract": prompt,
        "output_contract": "grounded-answer-v1",
        "recovery_contract": "no-retry-v1",
        "reasoning_contract": "direct-output-v1",
    }


def _case(
    case_id: str,
    *,
    cohort: str = "human_reviewed",
    status: str = "answered",
    abstention_reason: str | None = None,
    judge_status: str = "succeeded",
    answer_correctness: str = "partially_correct",
    faithfulness: str = "partially_supported",
    completeness: str = "partial",
    citation_coverage: str = "partial",
    citation_usefulness: str = "some_irrelevant",
    recall: float | None = 1.0,
    latency_ms: int = 10,
) -> GenerationSemanticEvalCaseResultV1:
    judge = None
    if judge_status == "succeeded":
        judge = GenerationSemanticJudgeCaseResultV1(
            judge_status="succeeded",
            answer_correctness=answer_correctness,  # type: ignore[arg-type]
            faithfulness=faithfulness,  # type: ignore[arg-type]
            completeness=completeness,  # type: ignore[arg-type]
            citation_coverage=citation_coverage,  # type: ignore[arg-type]
            citation_usefulness=citation_usefulness,  # type: ignore[arg-type]
            rationale="ok",
        )
    elif judge_status == "judge_failed":
        judge = GenerationSemanticJudgeCaseResultV1(
            judge_status="judge_failed",
            judge_failure_reason="invalid_json",
        )
    elif judge_status == "not_applicable":
        judge = GenerationSemanticJudgeCaseResultV1(judge_status="not_applicable")

    return GenerationSemanticEvalCaseResultV1(
        case_id=case_id,
        query=f"query for {case_id}",
        label_cohort=cohort,  # type: ignore[arg-type]
        status=status,
        abstention_reason=abstention_reason,
        citation_ids=["ev_1"],
        deterministic_metrics=GenerationDeterministicCaseMetricsV1(
            gold_positive_count=1,
            cited_evidence_count=1,
            gold_citation_recall=recall,
            grade2_citation_hit=True if recall is not None else None,
        ),
        judge_result=judge,
        latency_ms=latency_ms,
    )


def _result(
    *,
    run_id: str,
    prompt: str,
    evidence_contract: str = GOLD_EVIDENCE_V1,
    expected_behavior: str = "answer",
    cases: list[GenerationSemanticEvalCaseResultV1],
    gold_dataset_id: str = "gold_same",
    evidence_set_id: str = "genevidence_same",
    model: str = "test-model",
    temperature: float = 0.0,
    judgecfg: str = "judgecfg_same",
    gencfg: str = "gencfg_x",
) -> GenerationSemanticEvalResultV1:
    semantics = _semantics(prompt=prompt)
    semantics["model"] = model
    semantics["temperature"] = temperature

    det_full = GenerationCohortAggregateV1(
        cohort="full",
        case_count=len(cases),
        answer_rate=sum(1 for c in cases if c.status == "answered")
        / max(len(cases), 1),
        false_abstention_rate=sum(
            1
            for c in cases
            if c.status == "insufficient_evidence"
            and c.abstention_reason == "model_abstain"
        )
        / max(len(cases), 1),
        generation_failed_rate=0.0,
        citation_invalid_rate=0.0,
        empty_context_rate=0.0,
        mean_gold_citation_recall=GenerationMetricValueV1(
            value=1.0, applicable_count=1
        ),
        grade2_citation_hit_rate=GenerationMetricValueV1(value=1.0, applicable_count=1),
    )
    human_cases = [c for c in cases if c.label_cohort == "human_reviewed"]
    asst_cases = [c for c in cases if c.label_cohort == "assistant_only"]
    det = GenerationDeterministicAggregatesV1(
        answer_rate=det_full.answer_rate,
        false_abstention_rate=det_full.false_abstention_rate,
        generation_failed_rate=0.0,
        citation_invalid_rate=0.0,
        empty_context_rate=0.0,
        mean_gold_citation_recall=det_full.mean_gold_citation_recall,
        grade2_citation_hit_rate=det_full.grade2_citation_hit_rate,
        cohorts={
            "full": det_full,
            "human_reviewed": GenerationCohortAggregateV1(
                cohort="human_reviewed",
                case_count=len(human_cases),
                answer_rate=(
                    sum(1 for c in human_cases if c.status == "answered")
                    / len(human_cases)
                    if human_cases
                    else None
                ),
                false_abstention_rate=0.0 if human_cases else None,
            ),
            "assistant_only": GenerationCohortAggregateV1(
                cohort="assistant_only",
                case_count=len(asst_cases),
                answer_rate=(
                    sum(1 for c in asst_cases if c.status == "answered")
                    / len(asst_cases)
                    if asst_cases
                    else None
                ),
            ),
        },
    )

    answered = [c for c in cases if c.status == "answered"]
    succeeded = [
        c
        for c in answered
        if c.judge_result is not None and c.judge_result.judge_status == "succeeded"
    ]
    sem_cohort = GenerationSemanticCohortAggregateV1(
        cohort="full",
        case_count=len(cases),
        answered_count=len(answered),
        eligible_answered_cases=len(answered),
        judge_succeeded=len(succeeded),
        judge_failed=0,
        judge_unavailable=0,
        fully_correct_rate=GenerationMetricValueV1(
            value=(
                sum(
                    1
                    for c in succeeded
                    if c.judge_result
                    and c.judge_result.answer_correctness == "fully_correct"
                )
                / len(succeeded)
                if succeeded
                else None
            ),
            applicable_count=len(succeeded),
        ),
        fully_supported_rate=GenerationMetricValueV1(
            value=(
                sum(
                    1
                    for c in succeeded
                    if c.judge_result
                    and c.judge_result.faithfulness == "fully_supported"
                )
                / len(succeeded)
                if succeeded
                else None
            ),
            applicable_count=len(succeeded),
        ),
        complete_answer_rate=GenerationMetricValueV1(
            value=0.0, applicable_count=len(succeeded)
        ),
        complete_citation_coverage_rate=GenerationMetricValueV1(
            value=0.0, applicable_count=len(succeeded)
        ),
        all_citations_useful_rate=GenerationMetricValueV1(
            value=0.0, applicable_count=len(succeeded)
        ),
    )
    semantic = GenerationSemanticAggregatesV1(
        metric_contract="generation-semantic-metrics-v1",
        eligible_answered_cases=len(answered),
        judge_succeeded=len(succeeded),
        judge_failed=0,
        judge_unavailable=0,
        fully_correct_rate=sem_cohort.fully_correct_rate,
        fully_supported_rate=sem_cohort.fully_supported_rate,
        complete_answer_rate=sem_cohort.complete_answer_rate,
        complete_citation_coverage_rate=sem_cohort.complete_citation_coverage_rate,
        all_citations_useful_rate=sem_cohort.all_citations_useful_rate,
        cohorts={
            "full": sem_cohort,
            "human_reviewed": sem_cohort.model_copy(
                update={"cohort": "human_reviewed", "case_count": len(human_cases)}
            ),
            "assistant_only": GenerationSemanticCohortAggregateV1(
                cohort="assistant_only", case_count=len(asst_cases)
            ),
        },
    )

    abstention = None
    if expected_behavior == "abstain":
        from offline_rag.evaluation.generation_semantic.models import (
            GenerationAbstentionCohortAggregateV1,
        )

        n = len(cases)
        correct = sum(
            1
            for c in cases
            if c.status == "insufficient_evidence"
            and c.abstention_reason == "model_abstain"
        )
        false_ans = sum(1 for c in cases if c.status == "answered")
        full_cohort = GenerationAbstentionCohortAggregateV1(
            cohort="full",
            case_count=n,
            correct_abstention_rate=correct / n if n else None,
            false_answer_rate=false_ans / n if n else None,
            generation_failed_rate=0.0,
            citation_invalid_rate=0.0,
            empty_context_rate=0.0,
        )
        abstention = GenerationAbstentionAggregatesV1(
            metric_contract=GENERATION_ABSTENTION_DETERMINISTIC_V1,
            total_cases=n,
            correct_abstention_rate=correct / n if n else None,
            false_answer_rate=false_ans / n if n else None,
            generation_failed_rate=0.0,
            citation_invalid_rate=0.0,
            empty_context_rate=0.0,
            cohorts={
                "full": full_cohort,
                "human_reviewed": full_cohort.model_copy(
                    update={"cohort": "human_reviewed"}
                ),
                "assistant_only": GenerationAbstentionCohortAggregateV1(
                    cohort="assistant_only", case_count=0
                ),
            },
        )

    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    return GenerationSemanticEvalResultV1(
        run_id=run_id,
        gold_dataset_id=gold_dataset_id,
        evidence_set_id=evidence_set_id,
        evidence_contract=evidence_contract,
        expected_behavior=expected_behavior,  # type: ignore[arg-type]
        corpus_id="corpus_x",
        chunk_set_id="chunkset_x",
        generation_config_hash=gencfg,
        generation_semantic_provenance=semantics,
        judge_enabled=True,
        judge_provenance=_judge_prov(judgecfg=judgecfg),
        population=GenerationSemanticPopulationV1(
            total_cases=len(cases),
            executed_cases=len(cases),
            human_reviewed_cases=len(human_cases),
            assistant_only_cases=len(asst_cases),
            answered=sum(1 for c in cases if c.status == "answered"),
            model_abstain=sum(
                1
                for c in cases
                if c.status == "insufficient_evidence"
                and c.abstention_reason == "model_abstain"
            ),
        ),
        deterministic_aggregates=det,
        semantic_aggregates=semantic,
        abstention_aggregates=abstention,
        cases=cases,
        started_at=stamp,
        completed_at=stamp,
    )


def test_controlled_prompt_pair_compare_succeeds() -> None:
    a = _result(
        run_id="run_a",
        prompt=CONTROLLED_PROMPT_A,
        cases=[_case("c1"), _case("c2", cohort="assistant_only")],
        gencfg="gencfg_a",
    )
    b = _result(
        run_id="run_b",
        prompt=CONTROLLED_PROMPT_B,
        cases=[
            _case(
                "c1", answer_correctness="fully_correct", faithfulness="fully_supported"
            ),
            _case("c2", cohort="assistant_only", answer_correctness="fully_correct"),
        ],
        gencfg="gencfg_b",
    )
    comparison = compare_generation_semantic_results(a, b)
    assert comparison.comparison_id.startswith("gencompare_")
    assert comparison.compatibility.prompt_pair_accepted is True
    assert comparison.positive_aggregates is not None
    assert "full" in comparison.positive_aggregates.cohorts
    assert "human_reviewed" in comparison.positive_aggregates.cohorts
    assert comparison.cases[0].answer_correctness_transition == "improved"


def test_same_evidence_required_and_prompt_pair_enforced() -> None:
    a = _result(run_id="a", prompt=CONTROLLED_PROMPT_A, cases=[_case("c1")])
    b = _result(
        run_id="b",
        prompt=CONTROLLED_PROMPT_B,
        evidence_set_id="genevidence_other",
        cases=[_case("c1")],
    )
    with pytest.raises(GenerationCompareError, match="evidence_set_id"):
        compare_generation_semantic_results(a, b)

    b2 = _result(run_id="b", prompt=CONTROLLED_PROMPT_A, cases=[_case("c1")])
    with pytest.raises(GenerationCompareError, match="controlled prompt pair"):
        compare_generation_semantic_results(a, b2)

    b3 = _result(run_id="b", prompt=CONTROLLED_PROMPT_B, cases=[_case("c1")])
    compare_generation_semantic_results(b3, a, require_controlled_prompt_pair=False)
    # still computes, but controlled default rejects reverse
    with pytest.raises(GenerationCompareError, match="controlled prompt pair"):
        compare_generation_semantic_results(b3, a)


def test_rejects_different_gold_cases_model_temperature_judge() -> None:
    base_cases = [_case("c1")]
    a = _result(run_id="a", prompt=CONTROLLED_PROMPT_A, cases=base_cases)

    with pytest.raises(GenerationCompareError, match="gold_dataset_id"):
        compare_generation_semantic_results(
            a,
            _result(
                run_id="b",
                prompt=CONTROLLED_PROMPT_B,
                cases=base_cases,
                gold_dataset_id="gold_other",
            ),
        )

    with pytest.raises(GenerationCompareError, match="case ID"):
        compare_generation_semantic_results(
            a,
            _result(
                run_id="b",
                prompt=CONTROLLED_PROMPT_B,
                cases=[_case("c9")],
            ),
        )

    with pytest.raises(GenerationCompareError, match="model"):
        compare_generation_semantic_results(
            a,
            _result(
                run_id="b",
                prompt=CONTROLLED_PROMPT_B,
                cases=base_cases,
                model="other-model",
            ),
        )

    with pytest.raises(GenerationCompareError, match="temperature"):
        bad = _result(
            run_id="b",
            prompt=CONTROLLED_PROMPT_B,
            cases=base_cases,
            temperature=0.2,
        )
        compare_generation_semantic_results(a, bad)

    with pytest.raises(GenerationCompareError, match="judge"):
        compare_generation_semantic_results(
            a,
            _result(
                run_id="b",
                prompt=CONTROLLED_PROMPT_B,
                cases=base_cases,
                judgecfg="judgecfg_other",
            ),
        )


def test_semantic_transitions_and_judge_failure_not_comparable() -> None:
    assert (
        classify_semantic_transition(
            "incorrect",
            "fully_correct",
            ("incorrect", "partially_correct", "fully_correct"),
        )
        == "improved"
    )
    assert (
        classify_semantic_transition(
            "fully_correct",
            "incorrect",
            ("incorrect", "partially_correct", "fully_correct"),
        )
        == "regressed"
    )
    assert (
        classify_semantic_transition(
            "fully_correct",
            "fully_correct",
            ("incorrect", "partially_correct", "fully_correct"),
        )
        == "unchanged"
    )
    assert (
        classify_semantic_transition(None, "fully_correct", ("incorrect",))
        == "not_comparable"
    )

    a = _result(
        run_id="a",
        prompt=CONTROLLED_PROMPT_A,
        cases=[_case("c1"), _case("c2", judge_status="judge_failed")],
    )
    b = _result(
        run_id="b",
        prompt=CONTROLLED_PROMPT_B,
        cases=[
            _case("c1", answer_correctness="incorrect"),
            _case("c2", judge_status="judge_failed"),
        ],
    )
    comparison = compare_generation_semantic_results(a, b)
    by_id = {c.case_id: c for c in comparison.cases}
    assert by_id["c1"].answer_correctness_transition == "regressed"
    assert by_id["c2"].answer_correctness_transition == "not_comparable"
    assert comparison.semantic_transitions is not None
    assert comparison.semantic_transitions.answer_correctness.not_comparable == 1


def test_negative_abstention_transitions() -> None:
    a = _result(
        run_id="a",
        prompt=CONTROLLED_PROMPT_A,
        evidence_contract=HUMAN_GRADE0_HARD_NEGATIVE_V1,
        expected_behavior="abstain",
        evidence_set_id="genevidence_neg",
        cases=[
            _case(
                "n1",
                status="insufficient_evidence",
                abstention_reason="model_abstain",
                judge_status="not_applicable",
                recall=None,
            ),
            _case("n2", status="answered", recall=None),
        ],
    )
    b = _result(
        run_id="b",
        prompt=CONTROLLED_PROMPT_B,
        evidence_contract=HUMAN_GRADE0_HARD_NEGATIVE_V1,
        expected_behavior="abstain",
        evidence_set_id="genevidence_neg",
        cases=[
            _case("n1", status="answered", recall=None),
            _case(
                "n2",
                status="insufficient_evidence",
                abstention_reason="model_abstain",
                judge_status="not_applicable",
                recall=None,
            ),
        ],
    )
    comparison = compare_generation_semantic_results(a, b)
    assert comparison.negative_aggregates is not None
    transitions = comparison.negative_aggregates.abstention_outcome_transitions
    assert transitions["correct_abstention->false_answer"] == 1
    assert transitions["false_answer->correct_abstention"] == 1


def test_comparison_id_deterministic_and_directional(tmp_path: Path) -> None:
    a = _result(run_id="a", prompt=CONTROLLED_PROMPT_A, cases=[_case("c1")])
    b = _result(run_id="b", prompt=CONTROLLED_PROMPT_B, cases=[_case("c1")])
    c1 = compare_generation_semantic_results(a, b)
    c2 = compare_generation_semantic_results(a, b)
    assert c1.comparison_id == c2.comparison_id
    assert compute_generation_comparison_id(c1) == c1.comparison_id

    # metadata path noise excluded from identity
    c1.metadata["a_path"] = "/tmp/a.json"
    c2.metadata["a_path"] = "/other/a.json"
    assert generation_comparison_semantic_payload(
        c1
    ) == generation_comparison_semantic_payload(c2)

    swapped = compare_generation_semantic_results(
        b, a, require_controlled_prompt_pair=False
    )
    assert swapped.comparison_id != c1.comparison_id

    out = tmp_path / "cmp.json"
    persist_generation_comparison(c1, path=out)
    persist_generation_comparison(c1, path=out)  # identical reuse
    c1_mut = c1.model_copy(update={"a_run_id": "run_mut"})
    c1_mut = c1_mut.model_copy(
        update={"comparison_id": compute_generation_comparison_id(c1_mut)}
    )
    with pytest.raises(GenerationCompareError, match="different payload"):
        persist_generation_comparison(c1_mut, path=out)


def test_comparator_never_invokes_generator_judge_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for cls in (
        DenseRetriever,
        LexicalRetriever,
        HybridRetriever,
        GroundedGenerationExecutor,
    ):
        monkeypatch.setattr(
            cls,
            "__init__",
            MagicMock(side_effect=AssertionError(f"{cls.__name__} must not run")),
        )
    a = _result(run_id="a", prompt=CONTROLLED_PROMPT_A, cases=[_case("c1")])
    b = _result(run_id="b", prompt=CONTROLLED_PROMPT_B, cases=[_case("c1")])
    compare_generation_semantic_results(a, b)


def test_prompt_constants_match_contracts() -> None:
    assert CONTROLLED_PROMPT_A == PROMPT_GROUNDED_V1
    assert CONTROLLED_PROMPT_B == PROMPT_GROUNDED_PROVENANCE_V2
