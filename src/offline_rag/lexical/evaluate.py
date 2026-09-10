"""Lexical retrieval evaluation metrics and runner."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dataset_id_from_bytes, new_execution_id
from offline_rag.dense.evaluate import (
    first_relevant_rank,
    load_retrieval_dataset,
    mean_reciprocal_rank,
    recall_at_k,
)
from offline_rag.domain.indexing import (
    LexicalRetrievalEvaluationResult,
    RetrievalCaseResult,
)
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_state,
)
from offline_rag.lexical.retrieve import LexicalRetrievalError, LexicalRetriever


class LexicalEvaluationError(RuntimeError):
    pass


def _percentile(values: list[float], pct: float) -> float:
    """``pct`` is in ``[0, 1]`` (e.g. 0.95 for p95)."""
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


class LexicalRetrievalEvaluator:
    """Run lexical Recall@1/5/10 and MRR against a gold JSONL dataset."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        retriever: LexicalRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever or LexicalRetriever(settings)

    def evaluate(
        self,
        dataset_path: Path,
        *,
        corpus_name: str = "default",
        top_k: int = 10,
        output_path: Path | None = None,
        persist: bool = True,
    ) -> LexicalRetrievalEvaluationResult:
        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="evallexretrieve")
        meta, cases, canonical = load_retrieval_dataset(Path(dataset_path))
        dataset_id = dataset_id_from_bytes(canonical)

        state_path = lexical_index_state_path(self.settings.paths.corpora, corpus_name)
        if not state_path.exists():
            raise LexicalEvaluationError(
                "lexical index state missing; run offline-rag index lexical first"
            )
        lexical_state = load_lexical_index_state(state_path)
        if meta.chunk_set_id != lexical_state.source_chunk_set_id:
            raise LexicalEvaluationError(
                "dataset chunk_set_id does not match active LexicalIndexState "
                f"source_chunk_set_id: {meta.chunk_set_id} != {lexical_state.source_chunk_set_id}"
            )
        if meta.corpus_id and meta.corpus_id != lexical_state.source_corpus_id:
            raise LexicalEvaluationError(
                f"dataset corpus_id {meta.corpus_id} does not match indexed corpus "
                f"{lexical_state.source_corpus_id}"
            )

        depth = max(10, int(top_k))

        if cases:
            try:
                self.retriever.retrieve(query=cases[0].query, corpus_name=corpus_name, top_k=depth)
            except LexicalRetrievalError:
                pass

        case_results: list[RetrievalCaseResult] = []
        latencies: list[float] = []
        recalls1: list[float] = []
        recalls5: list[float] = []
        recalls10: list[float] = []
        rrs: list[float] = []

        for case in cases:
            if not case.relevant_chunk_ids:
                raise LexicalEvaluationError(
                    f"case {case.id} lacks relevant_chunk_ids; chunk-level metrics are required"
                )
            t0 = time.perf_counter()
            try:
                result = self.retriever.retrieve(
                    query=case.query,
                    corpus_name=corpus_name,
                    top_k=depth,
                )
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
                raise LexicalEvaluationError(str(exc)) from exc

            latencies.append(float(latency_ms))
            recalls1.append(r1)
            recalls5.append(r5)
            recalls10.append(r10)
            rrs.append(rr)

        completed = datetime.now(tz=UTC)
        n = len(case_results)
        report = LexicalRetrievalEvaluationResult(
            run_id=run_id,
            dataset_id=dataset_id,
            case_count=n,
            corpus_id=lexical_state.source_corpus_id,
            chunk_set_id=lexical_state.source_chunk_set_id,
            index_id=lexical_state.current_lexical_index_id,
            lexical_config_hash=build_lexical_config_hash(self.settings),
            top_k=depth,
            recall_at_1=sum(recalls1) / n,
            recall_at_5=sum(recalls5) / n,
            recall_at_10=sum(recalls10) / n,
            mrr=sum(rrs) / n,
            latency_mean_ms=sum(latencies) / n,
            latency_p50_ms=_percentile(latencies, 0.50),
            latency_p95_ms=_percentile(latencies, 0.95),
            cases=case_results,
            started_at=started,
            completed_at=completed,
            metadata={"corpus_name": corpus_name, "dataset_path": str(dataset_path)},
        )

        if persist:
            out = output_path
            if out is None:
                out_dir = self.settings.paths.eval_results / "lexical-retrieval"
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{run_id}.json"
            else:
                out = Path(out)
                out.parent.mkdir(parents=True, exist_ok=True)
            report = report.model_copy(
                update={"metadata": {**report.metadata, "result_path": str(out)}}
            )
            atomic_write_text(out, report.model_dump_json())
        return report
