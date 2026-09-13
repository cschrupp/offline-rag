"""Dense retrieval evaluation metrics and runner."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dataset_id_from_bytes, new_execution_id
from offline_rag.dense.config_hash import (
    build_dense_retrieval_config_hash,
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import Embedder
from offline_rag.dense.persistence import index_state_path, load_index_state
from offline_rag.dense.retrieve import DenseRetrievalError, DenseRetriever
from offline_rag.domain.indexing import (
    DenseRetrievalEvaluationResult,
    RetrievalCaseResult,
    RetrievalEvalCase,
    RetrievalEvalDatasetMeta,
)
from offline_rag.ingestion.io import atomic_write_text


class EvaluationError(RuntimeError):
    pass


# Backward-compatible alias used by some call sites.
DenseEvaluationError = EvaluationError


def recall_at_k(relevant_ids: list[str] | set[str], retrieved_ids: list[str], k: int) -> float:
    """Return classic multi-relevant Recall@k in ``[0, 1]``."""
    if k < 1:
        raise ValueError("k must be >= 1")
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    top = set(retrieved_ids[:k])
    return len(relevant & top) / len(relevant)


def mean_reciprocal_rank(relevant_ids: list[str] | set[str], retrieved_ids: list[str]) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant:
            return 1.0 / float(rank)
    return 0.0


def first_relevant_rank(relevant_ids: list[str] | set[str], retrieved_ids: list[str]) -> int | None:
    relevant = set(relevant_ids)
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant:
            return rank
    return None


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


def load_retrieval_eval_dataset(
    dataset_path: Path,
) -> tuple[list[RetrievalEvalCase], RetrievalEvalDatasetMeta, str]:
    """Load JSONL cases plus optional meta.json sidecar bound to chunk_set_id."""
    meta, cases, canonical = load_retrieval_dataset(dataset_path)
    return cases, meta, dataset_id_from_bytes(canonical)


def load_retrieval_dataset(
    path: Path,
) -> tuple[RetrievalEvalDatasetMeta, list[RetrievalEvalCase], bytes]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise EvaluationError(f"dataset not found: {dataset_path}")

    if dataset_path.is_dir():
        meta_path = dataset_path / "meta.json"
        cases_path = dataset_path / "cases.jsonl"
    elif dataset_path.suffix == ".jsonl":
        meta_path = dataset_path.with_name("meta.json")
        cases_path = dataset_path
    else:
        raise EvaluationError("dataset must be a .jsonl file or a directory with cases.jsonl")

    if not meta_path.exists():
        raise EvaluationError(f"dataset metadata missing: {meta_path}")
    if not cases_path.exists():
        raise EvaluationError(f"dataset cases missing: {cases_path}")

    meta = RetrievalEvalDatasetMeta.model_validate_json(meta_path.read_text(encoding="utf-8"))
    cases: list[RetrievalEvalCase] = []
    for line_no, line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = RetrievalEvalCase.model_validate_json(line)
        except Exception as exc:
            raise EvaluationError(f"invalid case on line {line_no}: {exc}") from exc
        if not case.relevant_chunk_ids and not case.relevant_document_ids:
            raise EvaluationError(f"case {case.id} has no relevance targets")
        cases.append(case)
    if not cases:
        raise EvaluationError("dataset contains no cases")

    canonical = meta.model_dump_json(exclude_none=True).encode("utf-8") + b"\n" + cases_path.read_bytes()
    return meta, cases, canonical


def write_evaluation_result(eval_results_root: Path, result: DenseRetrievalEvaluationResult) -> Path:
    root = Path(eval_results_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result.run_id}.json"
    atomic_write_text(path, result.model_dump_json())
    return path


class DenseRetrievalEvaluator:
    """Run dense Recall@1/5/10 and MRR against a gold JSONL dataset."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        embedder: Embedder | None = None,
        retriever: DenseRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever or DenseRetriever(settings, embedder=embedder)

    def evaluate(
        self,
        dataset_path: Path,
        *,
        corpus_name: str = "default",
        top_k: int = 10,
        output_path: Path | None = None,
        persist: bool = True,
    ) -> DenseRetrievalEvaluationResult:
        started = datetime.now(tz=UTC)
        run_id = new_execution_id(prefix="evalretrieve")
        meta, cases, canonical = load_retrieval_dataset(Path(dataset_path))
        dataset_id = dataset_id_from_bytes(canonical)

        index_path = index_state_path(self.settings.paths.corpora, corpus_name)
        if not index_path.exists():
            raise EvaluationError("index state missing; run offline-rag index first")
        index_state = load_index_state(index_path)
        if meta.chunk_set_id != index_state.source_chunk_set_id:
            raise EvaluationError(
                "dataset chunk_set_id does not match active IndexState source_chunk_set_id: "
                f"{meta.chunk_set_id} != {index_state.source_chunk_set_id}"
            )
        if meta.corpus_id and meta.corpus_id != index_state.source_corpus_id:
            raise EvaluationError(
                f"dataset corpus_id {meta.corpus_id} does not match indexed corpus "
                f"{index_state.source_corpus_id}"
            )

        depth = max(10, int(top_k))

        # Warmup excluded from steady-state latency.
        if cases:
            try:
                self.retriever.retrieve(query=cases[0].query, corpus_name=corpus_name, top_k=depth)
            except DenseRetrievalError:
                pass

        case_results: list[RetrievalCaseResult] = []
        latencies: list[float] = []
        recalls1: list[float] = []
        recalls5: list[float] = []
        recalls10: list[float] = []
        rrs: list[float] = []

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
        n = len(case_results)
        report = DenseRetrievalEvaluationResult(
            run_id=run_id,
            dataset_id=dataset_id,
            case_count=n,
            corpus_id=index_state.source_corpus_id,
            chunk_set_id=index_state.source_chunk_set_id,
            index_id=index_state.current_index_id,
            embedding_config_hash=build_embedding_config_hash(self.settings),
            index_config_hash=build_index_config_hash(self.settings),
            model_id=self.settings.indexing.embedding.model_id,
            model_revision=self.settings.indexing.embedding.revision,
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
            metadata={
                "corpus_name": corpus_name,
                "dataset_path": str(dataset_path),
                "query_text_strategy": self.settings.dense.query_text.strategy,
                "query_text_contract": self.settings.dense.query_text.contract_version,
                "dense_retrieval_config_hash": build_dense_retrieval_config_hash(
                    self.settings
                ),
            },
        )

        if persist:
            out = output_path
            if out is None:
                out_dir = self.settings.paths.eval_results / "dense-retrieval"
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{run_id}.json"
            else:
                out = Path(out)
                out.parent.mkdir(parents=True, exist_ok=True)
            report = report.model_copy(update={"metadata": {**report.metadata, "result_path": str(out)}})
            atomic_write_text(out, report.model_dump_json())
        return report
