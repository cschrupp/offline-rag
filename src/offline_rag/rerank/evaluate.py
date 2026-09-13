"""Hybrid-rerank retrieval evaluation — Slice 9 common result envelope."""

from __future__ import annotations

from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.evaluation.result import RetrievalEvaluationResultV1
from offline_rag.evaluation.runner import (
    EvaluationError,
    load_gold_or_raise,
    persist_result,
    run_retrieval_evaluation,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.retrieve import HybridRerankRetriever


class HybridRerankRetrievalEvaluator:
    """Run hybrid-rerank metrics against a GoldDataset (native or legacy)."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        retriever: HybridRerankRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever or HybridRerankRetriever(settings)

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
        input_k = int(self.settings.reranker.input_k)
        depth = min(input_k, max(10, int(top_k)))
        fus_hash = build_fusion_config_hash(self.settings)
        rrk_hash = build_reranker_config_hash(self.settings)
        provenance: dict = {
            "fusion_config_hash": fus_hash,
            "reranker_config_hash": rrk_hash,
            "input_k": input_k,
            "top_k": depth,
            "dense_index_id": "",
            "lexical_index_id": "",
        }

        def _retrieve(case) -> tuple[list[str], dict]:
            result = self.retriever.retrieve(
                query=case.query, corpus_name=corpus_name, top_k=depth
            )
            if dataset.meta.chunk_set_id != str(result.metadata.get("chunk_set_id") or ""):
                raise EvaluationError(
                    "dataset chunk_set_id does not match hybrid-rerank chunk_set_id: "
                    f"{dataset.meta.chunk_set_id} != {result.metadata.get('chunk_set_id')}"
                )
            provenance["dense_index_id"] = result.dense_index_id
            provenance["lexical_index_id"] = result.lexical_index_id
            pool_ids = result.metadata.get("input_pool_chunk_ids") or []
            if not isinstance(pool_ids, list):
                pool_ids = []
            pool_id_set = {str(item) for item in pool_ids}
            gold_in_pool = bool(case.positive_chunk_ids() & pool_id_set)
            input_pool_size = int(result.metadata.get("input_pool_size") or len(pool_ids))
            return [c.chunk_id for c in result.candidates], {
                "dense_index_id": result.dense_index_id,
                "lexical_index_id": result.lexical_index_id,
                "gold_in_rerank_pool": gold_in_pool,
                "input_pool_size": input_pool_size,
                "input_pool_chunk_ids": [str(item) for item in pool_ids],
                "returned_count": len(result.candidates),
            }

        report = run_retrieval_evaluation(
            dataset=dataset,
            method="hybrid-rerank",
            run_prefix="evalhybrerank",
            requested_depth=depth,
            retrieve_fn=_retrieve,
            warmup_query=dataset.cases[0].query if dataset.cases else None,
            semantic_provenance=provenance,
            corpus_id=dataset.meta.corpus_id,
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
                subdirectory="hybrid-rerank-retrieval",
                output_path=Path(output_path) if output_path else None,
            )
        return report
