"""Human-readable formatting for generation-semantic-eval-result-v1."""

from __future__ import annotations

from offline_rag.evaluation.generation_semantic.models import (
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
    lines.append("")
    lines.append(f"Latency mean: {det.latency.mean_ms:.1f} ms")

    evidence_path = result.metadata.get("evidence_path")
    result_path = result.metadata.get("result_path")
    if evidence_path or result_path:
        lines.append("")
        if evidence_path:
            lines.append(f"Evidence artifact: {evidence_path}")
        if result_path:
            lines.append(f"Result artifact:   {result_path}")
    return "\n".join(lines)
