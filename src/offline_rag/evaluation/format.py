"""Human-readable formatting for retrieval-eval-result-v1."""

from __future__ import annotations

from offline_rag.evaluation.result import RetrievalEvaluationResultV1


def _fmt_metric(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def format_retrieval_result_human(report: RetrievalEvaluationResultV1) -> str:
    lines: list[str] = []
    title = {
        "dense": "Dense retrieval evaluation completed",
        "lexical": "Lexical retrieval evaluation completed",
        "hybrid": "Hybrid retrieval evaluation completed",
        "hybrid-rerank": "Hybrid-rerank retrieval evaluation completed",
        "hybrid-rerank-context": "Hybrid-rerank-context evaluation completed",
    }.get(report.method, "Retrieval evaluation completed")
    lines.append(title)
    lines.append("")
    lines.append(f"Run:          {report.run_id}")
    lines.append(f"Method:       {report.method}")
    lines.append(f"Gold:         {report.gold_dataset_id}")
    lines.append(f"Gold schema:  {report.gold_source_schema}")
    if report.gold_compatibility_mode:
        lines.append(f"Compat:       {report.gold_compatibility_mode}")
    lines.append(f"Chunk set:    {report.chunk_set_id}")
    lines.append(
        f"Cases:        total={report.population.total_cases} "
        f"executed={report.population.executed_cases} "
        f"quality_eligible={report.population.quality_eligible_cases}"
    )
    prov = report.semantic_provenance
    for key in (
        "index_id",
        "dense_index_id",
        "lexical_index_id",
        "fusion_config_hash",
        "reranker_config_hash",
        "context_config_hash",
        "lexical_config_hash",
        "top_k",
        "input_k",
        "anchor_k",
    ):
        if key in prov and prov[key] not in (None, ""):
            lines.append(f"{key + ':':<14}{prov[key]}")
    lines.append("")
    agg = report.aggregates
    lines.append(f"Recall@1:     {_fmt_metric(agg.recall_at_1.value)}")
    lines.append(f"Recall@5:     {_fmt_metric(agg.recall_at_5.value)}")
    lines.append(f"Recall@10:    {_fmt_metric(agg.recall_at_10.value)}")
    lines.append(f"Precision@1:  {_fmt_metric(agg.precision_at_1.value)}")
    lines.append(f"Precision@5:  {_fmt_metric(agg.precision_at_5.value)}")
    lines.append(f"Precision@10: {_fmt_metric(agg.precision_at_10.value)}")
    lines.append(f"HitRate@1:    {_fmt_metric(agg.hit_rate_at_1.value)}")
    lines.append(f"HitRate@5:    {_fmt_metric(agg.hit_rate_at_5.value)}")
    lines.append(f"HitRate@10:   {_fmt_metric(agg.hit_rate_at_10.value)}")
    lines.append(f"HitRate@30:   {_fmt_metric(agg.hit_rate_at_30.value)}")
    lines.append(f"MRR:          {_fmt_metric(agg.mrr.value)}")
    lines.append(f"nDCG@1:       {_fmt_metric(agg.ndcg_at_1.value)}")
    lines.append(f"nDCG@5:       {_fmt_metric(agg.ndcg_at_5.value)}")
    lines.append(f"nDCG@10:      {_fmt_metric(agg.ndcg_at_10.value)}")
    lines.append("")
    lines.append(f"Latency mean: {report.latency.mean_ms:.1f} ms")
    lines.append(f"Latency p50:  {report.latency.p50_ms:.1f} ms")
    lines.append(f"Latency p95:  {report.latency.p95_ms:.1f} ms")

    if report.category_aggregates:
        lines.append("")
        lines.append("By category:")
        for cat in report.category_aggregates:
            lines.append(
                f"  {cat.category}: eligible={cat.quality_eligible_cases}/"
                f"{cat.total_cases} nDCG@10={_fmt_metric(cat.metrics.ndcg_at_10.value)}"
            )

    assembly = report.metadata.get("assembly_summary")
    if isinstance(assembly, dict):
        lines.append("")
        lines.append("Assembly summary")
        lines.append(
            f"  tokens mean/min/max: "
            f"{assembly.get('context_tokens_mean', 0):.1f}/"
            f"{assembly.get('context_tokens_min', 0)}/"
            f"{assembly.get('context_tokens_max', 0)}"
        )
        lines.append(
            f"  units mean/min/max:  "
            f"{assembly.get('evidence_units_mean', 0):.1f}/"
            f"{assembly.get('evidence_units_min', 0)}/"
            f"{assembly.get('evidence_units_max', 0)}"
        )
        lines.append(f"  clipped cases:      {assembly.get('clipped_case_count', 0)}")
        lines.append(
            f"  budget exhausted:   {assembly.get('budget_exhausted_case_count', 0)}"
        )
        lines.append(f"  stop reasons:       {assembly.get('stop_reason_counts', {})}")

    result_path = report.metadata.get("result_path")
    if result_path:
        lines.append("")
        lines.append(f"Report:       {result_path}")
    return "\n".join(lines)
