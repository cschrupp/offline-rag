"""Human-readable formatting for generation-semantic-eval-result-v1."""

from __future__ import annotations

from offline_rag.evaluation.generation_semantic.models import (
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    GenerationMetricValueV1,
    GenerationSemanticEvalResultV1,
)


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def _fmt_metric(metric: GenerationMetricValueV1) -> str:
    if metric.value is None:
        return f"n/a (n={metric.applicable_count})"
    return f"{metric.value:.4f} (n={metric.applicable_count})"


def format_generation_semantic_result_human(
    result: GenerationSemanticEvalResultV1,
) -> str:
    if result.evidence_contract == HUMAN_GRADE0_HARD_NEGATIVE_V1:
        return _format_hard_negative(result)
    return _format_positive_gold(result)


def _format_positive_gold(result: GenerationSemanticEvalResultV1) -> str:
    pop = result.population
    det = result.deterministic_aggregates
    semantics = result.generation_semantic_provenance
    prompt = str(semantics.get("prompt_contract") or "unknown")
    model = str(semantics.get("model") or "unknown")

    lines: list[str] = [
        "Generation semantic evaluation completed",
        "",
        f"Run:           {result.run_id}",
        f"Gold:          {result.gold_dataset_id}",
        f"Evidence:      {result.evidence_set_id}",
        f"Prompt:        {prompt}",
        f"Model:         {model}",
        f"Cases:         {pop.total_cases}",
        "",
        "Positive evidence outcomes",
        f"  answered:             {pop.answered}",
        f"  false abstention:     {pop.model_abstain}",
        f"  generation failed:    {pop.generation_failed}",
        f"  citation invalid:     {pop.citation_invalid}",
        "",
        "Citation diagnostics",
        f"  gold citation recall: {_fmt_metric(det.mean_gold_citation_recall)}",
        f"  grade-2 citation hit: {_fmt_metric(det.grade2_citation_hit_rate)}",
        "",
        "Cohorts",
    ]
    for key in ("human_reviewed", "assistant_only"):
        cohort = det.cohorts.get(key)
        if cohort is None:
            lines.append(f"  {key}: n/a")
            continue
        lines.append(
            f"  {key}: cases={cohort.case_count} "
            f"answer_rate={_fmt_rate(cohort.answer_rate)}"
        )

    _append_judge_section(lines, result)
    lines.append("")
    lines.append(f"Latency mean: {det.latency.mean_ms:.1f} ms")
    _append_artifact_paths(lines, result)
    return "\n".join(lines)


def _format_hard_negative(result: GenerationSemanticEvalResultV1) -> str:
    pop = result.population
    abstention = result.abstention_aggregates
    semantics = result.generation_semantic_provenance
    prompt = str(semantics.get("prompt_contract") or "unknown")
    model = str(semantics.get("model") or "unknown")

    lines: list[str] = [
        "Generation semantic evaluation completed",
        "",
        "Evidence contract:",
        f"  {result.evidence_contract}",
        "",
        "Expected behavior:",
        f"  {result.expected_behavior}",
        "",
        f"Run:           {result.run_id}",
        f"Gold:          {result.gold_dataset_id}",
        f"Evidence:      {result.evidence_set_id}",
        f"Prompt:        {prompt}",
        f"Model:         {model}",
        f"Cases:         {pop.total_cases}",
        "",
        "Abstention stress test",
    ]
    if abstention is None:
        lines.append("  (abstention aggregates unavailable)")
    else:
        lines.extend(
            [
                f"  correct abstention: {_fmt_rate(abstention.correct_abstention_rate)}",
                f"  false answer:       {_fmt_rate(abstention.false_answer_rate)}",
                f"  generation failed:  {_fmt_rate(abstention.generation_failed_rate)}",
                f"  citation invalid:   {_fmt_rate(abstention.citation_invalid_rate)}",
                f"  empty context:      {_fmt_rate(abstention.empty_context_rate)}",
            ]
        )
        lines.append("")
        lines.append("Cohorts")
        for key in ("human_reviewed", "assistant_only"):
            cohort = abstention.cohorts.get(key)
            if cohort is None:
                lines.append(f"  {key}: n/a")
                continue
            if cohort.case_count == 0:
                lines.append(f"  {key}: cases=0 rates=n/a")
                continue
            lines.append(
                f"  {key}: cases={cohort.case_count} "
                f"correct_abstention={_fmt_rate(cohort.correct_abstention_rate)} "
                f"false_answer={_fmt_rate(cohort.false_answer_rate)}"
            )

    _append_judge_section(lines, result)

    latency = (
        abstention.latency.mean_ms
        if abstention is not None
        else result.deterministic_aggregates.latency.mean_ms
    )
    lines.append("")
    lines.append(f"Latency: {latency:.1f} ms")
    _append_artifact_paths(lines, result)
    return "\n".join(lines)


def _append_judge_section(
    lines: list[str],
    result: GenerationSemanticEvalResultV1,
) -> None:
    if not result.judge_enabled:
        return
    lines.append("")
    lines.append("Judge coverage:")
    prov = result.judge_provenance
    if prov is not None:
        lines.append(
            f"  requested:            {prov.judge_requested} "
            f"available={prov.judge_available}"
        )
        if prov.same_model_self_judge:
            lines.append(
                "  limitation:           same_model_self_judge=true "
                "(not independent evaluation)"
            )
        if not prov.judge_available:
            lines.append(
                "  coverage:             INCOMPLETE — judge unavailable; "
                "no semantic scores"
            )
            if prov.preflight_reason:
                lines.append(f"  preflight:            {prov.preflight_reason}")
    sem = result.semantic_aggregates
    if sem is not None:
        lines.append(f"  eligible answered:    {sem.eligible_answered_cases}")
        lines.append(f"  judge succeeded:      {sem.judge_succeeded}")
        lines.append(f"  judge failed:         {sem.judge_failed}")
        lines.append(f"  judge unavailable:    {sem.judge_unavailable}")
        lines.append(f"  fully correct rate:   {_fmt_metric(sem.fully_correct_rate)}")
        lines.append(f"  fully supported rate: {_fmt_metric(sem.fully_supported_rate)}")


def _append_artifact_paths(
    lines: list[str],
    result: GenerationSemanticEvalResultV1,
) -> None:
    evidence_path = result.metadata.get("evidence_path")
    result_path = result.metadata.get("result_path")
    if evidence_path or result_path:
        lines.append("")
        if evidence_path:
            lines.append(f"Evidence artifact: {evidence_path}")
        if result_path:
            lines.append(f"Result artifact:   {result_path}")
