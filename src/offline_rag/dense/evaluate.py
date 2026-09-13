"""Dense retrieval evaluation — Slice 9 common result envelope."""

from __future__ import annotations

from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dataset_id_from_bytes
from offline_rag.dense.config_hash import (
    build_dense_retrieval_config_hash,
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import Embedder
from offline_rag.dense.persistence import index_state_path, load_index_state
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.indexing import RetrievalEvalCase, RetrievalEvalDatasetMeta
from offline_rag.evaluation.metrics import (
    first_relevant_rank as _first_relevant_rank_strict,
)
from offline_rag.evaluation.metrics import (
    mean_reciprocal_rank as _mean_reciprocal_rank_strict,
)
from offline_rag.evaluation.metrics import (
    recall_at_k as _recall_at_k_strict,
)
from offline_rag.evaluation.result import RetrievalEvaluationResultV1
from offline_rag.evaluation.runner import (
    EvaluationError,
    load_gold_or_raise,
    persist_result,
    run_retrieval_evaluation,
)

# Re-export for generation eval and historical call sites.
__all__ = [
    "DenseEvaluationError",
    "DenseRetrievalEvaluator",
    "EvaluationError",
    "first_relevant_rank",
    "load_retrieval_dataset",
    "load_retrieval_eval_dataset",
    "mean_reciprocal_rank",
    "recall_at_k",
]

DenseEvaluationError = EvaluationError


def recall_at_k(relevant_ids: list[str] | set[str], retrieved_ids: list[str], k: int) -> float:
    """Classic multi-relevant Recall@k; empty relevant set → 0.0 (legacy helper)."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return _recall_at_k_strict(relevant, retrieved_ids, k)


def mean_reciprocal_rank(
    relevant_ids: list[str] | set[str], retrieved_ids: list[str]
) -> float:
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return _mean_reciprocal_rank_strict(relevant, retrieved_ids)


def first_relevant_rank(
    relevant_ids: list[str] | set[str], retrieved_ids: list[str]
) -> int | None:
    return _first_relevant_rank_strict(set(relevant_ids), retrieved_ids)


def load_retrieval_eval_dataset(
    dataset_path: Path,
) -> tuple[list[RetrievalEvalCase], RetrievalEvalDatasetMeta, str]:
    """Load JSONL cases plus optional meta.json sidecar bound to chunk_set_id."""
    meta, cases, canonical = load_retrieval_dataset(dataset_path)
    return cases, meta, dataset_id_from_bytes(canonical)


def load_retrieval_dataset(
    path: Path,
) -> tuple[RetrievalEvalDatasetMeta, list[RetrievalEvalCase], bytes]:
    """Legacy dataset loader retained for ``eval query`` and historical fixtures."""
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


class DenseRetrievalEvaluator:
    """Run dense retrieval metrics against a GoldDataset (native or legacy)."""

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
    ) -> RetrievalEvaluationResultV1:
        dataset = load_gold_or_raise(Path(dataset_path))
        index_path = index_state_path(self.settings.paths.corpora, corpus_name)
        if not index_path.exists():
            raise EvaluationError("index state missing; run offline-rag index first")
        index_state = load_index_state(index_path)
        if dataset.meta.chunk_set_id != index_state.source_chunk_set_id:
            raise EvaluationError(
                "dataset chunk_set_id does not match active IndexState source_chunk_set_id: "
                f"{dataset.meta.chunk_set_id} != {index_state.source_chunk_set_id}"
            )
        if (
            dataset.meta.corpus_id
            and dataset.meta.corpus_id != index_state.source_corpus_id
        ):
            raise EvaluationError(
                f"dataset corpus_id {dataset.meta.corpus_id} does not match indexed corpus "
                f"{index_state.source_corpus_id}"
            )

        depth = max(10, int(top_k))

        def _retrieve(case) -> tuple[list[str], dict]:
            result = self.retriever.retrieve(
                query=case.query, corpus_name=corpus_name, top_k=depth
            )
            return [c.chunk_id for c in result.candidates], {
                "index_id": result.index_id,
                "returned_count": len(result.candidates),
            }

        report = run_retrieval_evaluation(
            dataset=dataset,
            method="dense",
            run_prefix="evalretrieve",
            requested_depth=depth,
            retrieve_fn=_retrieve,
            warmup_query=dataset.cases[0].query if dataset.cases else None,
            semantic_provenance={
                "index_id": index_state.current_index_id,
                "embedding_config_hash": build_embedding_config_hash(self.settings),
                "index_config_hash": build_index_config_hash(self.settings),
                "model_id": self.settings.indexing.embedding.model_id,
                "model_revision": self.settings.indexing.embedding.revision,
                "top_k": depth,
                "query_text_strategy": self.settings.dense.query_text.strategy,
                "query_text_contract": self.settings.dense.query_text.contract_version,
                "dense_retrieval_config_hash": build_dense_retrieval_config_hash(
                    self.settings
                ),
            },
            corpus_id=index_state.source_corpus_id,
            corpus_name=corpus_name,
            metadata={
                "corpus_name": corpus_name,
                "dataset_path": str(dataset_path),
            },
        )

        if persist:
            report = persist_result(
                report,
                eval_results_root=self.settings.paths.eval_results,
                subdirectory="dense-retrieval",
                output_path=Path(output_path) if output_path else None,
            )
        return report
