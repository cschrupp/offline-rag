"""Hybrid retrieval evaluation using shared Recall@k / MRR helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dataset_id_from_bytes, new_execution_id
from offline_rag.dense.evaluate import (
    EvaluationError,
    first_relevant_rank,
    load_retrieval_dataset,
    mean_reciprocal_rank,
    recall_at_k,
)
from offline_rag.domain.indexing import (
    HybridRetrievalEvaluationResult,
    RetrievalCaseResult,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.retrieve import HybridRetrievalError, HybridRetriever
from offline_rag.ingestion.io import atomic_write_text


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


class HybridRetrievalEvaluator:
    """Run hybrid Recall@1/5/10 and MRR against a gold JSONL dataset."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever or HybridRetriever(settings)

    def evaluate(
        self,
        dataset_path: Path,
        *,
        corpus_name: str = "default",
        top_k: int = 10,
        output_path: Path | None = None,
        persist: bool = True,
    ) -> HybridRetrievalEvaluationResult:
        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="evalhybretrieve")
        meta, cases, canonical = load_retrieval_dataset(Path(dataset_path))
        dataset_id = dataset_id_from_bytes(canonical)

        # Warmup excluded from latency.
        if cases:
            try:
                self.retriever.retrieve(
                    query=cases[0].query,
                    corpus_name=corpus_name,
                    top_k=max(10, int(top_k)),
                )
            except HybridRetrievalError:
                pass

        depth = max(10, int(top_k))
        case_results: list[RetrievalCaseResult] = []
        latencies: list[float] = []
        recalls1: list[float] = []
        recalls5: list[float] = []
        recalls10: list[float] = []
        rrs: list[float] = []
        dense_index_id = ""
        lexical_index_id = ""
        chunk_set_id = meta.chunk_set_id
        corpus_id = meta.corpus_id
        fus_hash = build_fusion_config_hash(self.settings)

        for case in cases:
            if not case.relevant_chunk_ids:
                raise EvaluationError(
                    f"case {case.id} lacks relevant_chunk_ids; chunk-level metrics are required"
                )
            t0 = time.perf_counter()
            try:
                result = self.retriever.retrieve(
                    query=case.query,
                    corpus_name=corpus_name,
                    top_k=depth,
                )
                if meta.chunk_set_id != str(result.metadata.get("chunk_set_id") or ""):
                    raise EvaluationError(
                        "dataset chunk_set_id does not match hybrid retrieval chunk_set_id: "
                        f"{meta.chunk_set_id} != {result.metadata.get('chunk_set_id')}"
                    )
                dense_index_id = result.dense_index_id
                lexical_index_id = result.lexical_index_id
                chunk_set_id = str(result.metadata.get("chunk_set_id") or chunk_set_id)
                retrieved = [candidate.chunk_id for candidate in result.candidates]
                latency_ms = int((time.perf_counter() - t0) * 1000)
                rr = mean_reciprocal_rank(case.relevant_chunk_ids, retrieved)
                first_rank = first_relevant_rank(case.relevant_chunk_ids, retrieved)
                r1 = recall_at_k(case.relevant_chunk_ids, retrieved, 1)
                r5 = recall_at_k(case.relevant_chunk_ids, retrieved, 5)
                r10 = recall_at_k(case.relevant_chunk_ids, retrieved, 10)
                case_results.append(
                    RetrievalCaseResult(
                        case_id=case.id,
                        query=case.query,
                        relevant_chunk_ids=list(case.relevant_chunk_ids),
                        retrieved_chunk_ids=retrieved,
                        first_relevant_rank=first_rank,
                        reciprocal_rank=rr,
                        recall_at_1=r1,
                        recall_at_5=r5,
                        recall_at_10=r10,
                        latency_ms=latency_ms,
                    )
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                case_results.append(
                    RetrievalCaseResult(
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
            recalls10.append(r10)
            rrs.append(rr)

        completed = datetime.now(tz=UTC)
        report = HybridRetrievalEvaluationResult(
            run_id=run_id,
            dataset_id=dataset_id,
            case_count=len(cases),
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            dense_index_id=dense_index_id,
            lexical_index_id=lexical_index_id,
            fusion_config_hash=fus_hash,
            dense_top_k=self.settings.fusion.dense_top_k,
            lexical_top_k=self.settings.fusion.lexical_top_k,
            top_k=depth,
            recall_at_1=sum(recalls1) / len(recalls1) if recalls1 else 0.0,
            recall_at_5=sum(recalls5) / len(recalls5) if recalls5 else 0.0,
            recall_at_10=sum(recalls10) / len(recalls10) if recalls10 else 0.0,
            mrr=sum(rrs) / len(rrs) if rrs else 0.0,
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
                Path(self.settings.paths.eval_results) / "hybrid-retrieval" / f"{run_id}.json"
            )
            out.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(out, report.model_dump_json())
            report.metadata["result_path"] = str(out)
        return report
