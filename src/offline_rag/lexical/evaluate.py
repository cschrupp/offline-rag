"""Lexical retrieval evaluation — Slice 9 common result envelope."""

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
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_state,
)
from offline_rag.lexical.retrieve import LexicalRetriever

LexicalEvaluationError = EvaluationError


class LexicalRetrievalEvaluator:
    """Run lexical retrieval metrics against a GoldDataset (native or legacy)."""

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
    ) -> RetrievalEvaluationResultV1:
        dataset = load_gold_or_raise(Path(dataset_path))
        state_path = lexical_index_state_path(self.settings.paths.corpora, corpus_name)
        if not state_path.exists():
            raise LexicalEvaluationError(
                "lexical index state missing; run offline-rag index lexical first"
            )
        lexical_state = load_lexical_index_state(state_path)
        if dataset.meta.chunk_set_id != lexical_state.source_chunk_set_id:
            raise LexicalEvaluationError(
                "dataset chunk_set_id does not match active LexicalIndexState "
                f"source_chunk_set_id: {dataset.meta.chunk_set_id} != "
                f"{lexical_state.source_chunk_set_id}"
            )
        if (
            dataset.meta.corpus_id
            and dataset.meta.corpus_id != lexical_state.source_corpus_id
        ):
            raise LexicalEvaluationError(
                f"dataset corpus_id {dataset.meta.corpus_id} does not match indexed corpus "
                f"{lexical_state.source_corpus_id}"
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
            method="lexical",
            run_prefix="evallexretrieve",
            requested_depth=depth,
            retrieve_fn=_retrieve,
            warmup_query=dataset.cases[0].query if dataset.cases else None,
            semantic_provenance={
                "index_id": lexical_state.current_lexical_index_id,
                "lexical_config_hash": build_lexical_config_hash(self.settings),
                "top_k": depth,
            },
            corpus_id=lexical_state.source_corpus_id,
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
                subdirectory="lexical-retrieval",
                output_path=Path(output_path) if output_path else None,
            )
        return report
