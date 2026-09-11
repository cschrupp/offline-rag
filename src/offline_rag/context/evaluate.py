"""Hybrid-rerank-context evaluation adapter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.core.ids import dataset_id_from_bytes, new_execution_id
from offline_rag.dense.evaluate import (
    EvaluationError,
    first_relevant_rank,
    load_retrieval_dataset,
    mean_reciprocal_rank,
    recall_at_k,
)
from offline_rag.domain.indexing import (
    ContextAnchorRankingMetrics,
    ContextAssemblySummary,
    HybridRerankContextCaseResult,
    HybridRerankContextEvaluationResult,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.rerank.config_hash import build_reranker_config_hash


def _percentile(values: list[float], pct: float) -> float:
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


class HybridRerankContextEvaluator:
    """Evaluate hybrid-rerank-context via real assembly + anchor ranking metrics."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        assembler: HybridRerankContextAssembler | None = None,
    ) -> None:
        self.settings = settings
        self.assembler = assembler or HybridRerankContextAssembler(settings)

    def evaluate(
        self,
        dataset_path: Path,
        *,
        corpus_name: str = "default",
        output_path: Path | None = None,
        persist: bool = True,
    ) -> HybridRerankContextEvaluationResult:
        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="evalctx")
        meta, cases, canonical = load_retrieval_dataset(Path(dataset_path))
        dataset_id = dataset_id_from_bytes(canonical)
        anchor_k = int(self.settings.context.anchor_k)
        counter = make_token_counter(self.settings)
        ctx_hash = build_context_config_hash(self.settings, token_counter=counter)
        fus_hash = build_fusion_config_hash(self.settings)
        rrk_hash = build_reranker_config_hash(self.settings)

        if cases:
            try:
                self.assembler.assemble(query=cases[0].query, corpus_name=corpus_name)
            except HybridRerankContextError:
                pass

        case_results: list[HybridRerankContextCaseResult] = []
        latencies: list[float] = []
        recalls1: list[float] = []
        recalls5: list[float] = []
        rrs: list[float] = []
        token_counts: list[int] = []
        unit_counts: list[int] = []
        stop_reason_counts: dict[str, int] = {}
        clipped_cases = 0
        budget_cases = 0
        total_dedup = 0
        total_suppress = 0
        dense_index_id = ""
        lexical_index_id = ""
        chunk_set_id = meta.chunk_set_id
        corpus_id = meta.corpus_id

        for case in cases:
            if not case.relevant_chunk_ids:
                raise EvaluationError(
                    f"case {case.id} lacks relevant_chunk_ids; chunk-level metrics are required"
                )
            t0 = time.perf_counter()
            try:
                result = self.assembler.assemble(query=case.query, corpus_name=corpus_name)
                if meta.chunk_set_id != str(result.metadata.get("chunk_set_id") or ""):
                    raise EvaluationError(
                        "dataset chunk_set_id does not match context chunk_set_id: "
                        f"{meta.chunk_set_id} != {result.metadata.get('chunk_set_id')}"
                    )
                dense_index_id = result.dense_index_id
                lexical_index_id = result.lexical_index_id
                chunk_set_id = str(result.metadata.get("chunk_set_id") or chunk_set_id)
                retrieved = [anchor.chunk_id for anchor in result.anchors]
                latency_ms = int((time.perf_counter() - t0) * 1000)
                pool_ids = result.metadata.get("input_pool_chunk_ids") or []
                if not isinstance(pool_ids, list):
                    pool_ids = []
                pool_id_set = {str(item) for item in pool_ids}
                gold_in_pool = bool(set(case.relevant_chunk_ids) & pool_id_set)
                input_pool_size = int(result.metadata.get("input_pool_size") or len(pool_ids))
                rr = mean_reciprocal_rank(case.relevant_chunk_ids, retrieved)
                first_rank = first_relevant_rank(case.relevant_chunk_ids, retrieved)
                r1 = recall_at_k(case.relevant_chunk_ids, retrieved, 1)
                r5 = recall_at_k(case.relevant_chunk_ids, retrieved, min(5, max(anchor_k, 1)))
                diag = result.diagnostics
                case_results.append(
                    HybridRerankContextCaseResult(
                        case_id=case.id,
                        query=case.query,
                        relevant_chunk_ids=list(case.relevant_chunk_ids),
                        retrieved_anchor_chunk_ids=retrieved,
                        first_relevant_rank=first_rank,
                        reciprocal_rank=rr,
                        recall_at_1=r1,
                        recall_at_5=r5,
                        evidence_unit_count=diag.evidence_unit_count,
                        context_token_count=result.context_token_count,
                        clipping_occurred=diag.clipping_occurred,
                        budget_exhausted=diag.budget_exhausted,
                        stop_reason=diag.stop_reason,
                        gold_in_rerank_pool=gold_in_pool,
                        input_pool_size=input_pool_size,
                        latency_ms=latency_ms,
                    )
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                case_results.append(
                    HybridRerankContextCaseResult(
                        case_id=case.id,
                        query=case.query,
                        relevant_chunk_ids=list(case.relevant_chunk_ids),
                        latency_ms=latency_ms,
                        error=str(exc),
                    )
                )
                raise EvaluationError(str(exc)) from exc

            latencies.append(float(latency_ms))
            recalls1.append(r1)
            recalls5.append(r5)
            rrs.append(rr)
            token_counts.append(int(result.context_token_count))
            unit_counts.append(int(diag.evidence_unit_count))
            stop_reason_counts[diag.stop_reason] = stop_reason_counts.get(diag.stop_reason, 0) + 1
            if diag.clipping_occurred:
                clipped_cases += 1
            if diag.budget_exhausted:
                budget_cases += 1
            total_dedup += int(diag.dedup_hits)
            total_suppress += int(diag.containment_suppressions)

        completed = datetime.now(tz=UTC)
        assembly = ContextAssemblySummary(
            context_tokens_mean=(sum(token_counts) / len(token_counts)) if token_counts else 0.0,
            context_tokens_min=min(token_counts) if token_counts else 0,
            context_tokens_max=max(token_counts) if token_counts else 0,
            evidence_units_mean=(sum(unit_counts) / len(unit_counts)) if unit_counts else 0.0,
            evidence_units_min=min(unit_counts) if unit_counts else 0,
            evidence_units_max=max(unit_counts) if unit_counts else 0,
            clipped_case_count=clipped_cases,
            budget_exhausted_case_count=budget_cases,
            stop_reason_counts=stop_reason_counts,
            total_dedup_hits=total_dedup,
            total_containment_suppressions=total_suppress,
        )
        ranking = ContextAnchorRankingMetrics(
            recall_at_1=sum(recalls1) / len(recalls1) if recalls1 else 0.0,
            recall_at_5=sum(recalls5) / len(recalls5) if recalls5 else 0.0,
            mrr=sum(rrs) / len(rrs) if rrs else 0.0,
            evaluation_depth=anchor_k,
        )
        report = HybridRerankContextEvaluationResult(
            run_id=run_id,
            dataset_id=dataset_id,
            case_count=len(cases),
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            dense_index_id=dense_index_id,
            lexical_index_id=lexical_index_id,
            fusion_config_hash=fus_hash,
            reranker_config_hash=rrk_hash,
            context_config_hash=ctx_hash,
            anchor_k=anchor_k,
            anchor_ranking=ranking,
            assembly_summary=assembly,
            latency_mean_ms=sum(latencies) / len(latencies) if latencies else 0.0,
            latency_p50_ms=_percentile(latencies, 0.50),
            latency_p95_ms=_percentile(latencies, 0.95),
            cases=case_results,
            started_at=started,
            completed_at=completed,
            metadata={},
        )
        if persist:
            out = Path(output_path) if output_path else (
                Path(self.settings.paths.eval_results)
                / "hybrid-rerank-context"
                / f"{run_id}.json"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(out, report.model_dump_json())
            report.metadata["result_path"] = str(out)
        return report
