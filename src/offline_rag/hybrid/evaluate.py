"""Hybrid retrieval evaluation — Slice 9 common result envelope."""

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
from offline_rag.hybrid.retrieve import HybridRetriever


class HybridRetrievalEvaluator:
    """Run hybrid retrieval metrics against a GoldDataset (native or legacy)."""

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
    ) -> RetrievalEvaluationResultV1:
        dataset = load_gold_or_raise(Path(dataset_path))
        depth = max(10, int(top_k))
        fus_hash = build_fusion_config_hash(self.settings)
        provenance: dict = {
            "fusion_config_hash": fus_hash,
            "dense_top_k": self.settings.fusion.dense_top_k,
            "lexical_top_k": self.settings.fusion.lexical_top_k,
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
                    "dataset chunk_set_id does not match hybrid retrieval chunk_set_id: "
                    f"{dataset.meta.chunk_set_id} != {result.metadata.get('chunk_set_id')}"
                )
            provenance["dense_index_id"] = result.dense_index_id
            provenance["lexical_index_id"] = result.lexical_index_id
            return [c.chunk_id for c in result.candidates], {
                "dense_index_id": result.dense_index_id,
                "lexical_index_id": result.lexical_index_id,
                "returned_count": len(result.candidates),
            }

        report = run_retrieval_evaluation(
            dataset=dataset,
            method="hybrid",
            run_prefix="evalhybretrieve",
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
                subdirectory="hybrid-retrieval",
                output_path=Path(output_path) if output_path else None,
            )
        return report
