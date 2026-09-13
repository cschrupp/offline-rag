"""Hybrid-rerank-context evaluation — Slice 9 common result envelope.

Quality metrics score anchor child chunk_ids (never EvidenceUnit IDs).
"""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.evaluation.result import RetrievalEvaluationResultV1
from offline_rag.evaluation.runner import (
    EvaluationError,
    load_gold_or_raise,
    persist_result,
    run_retrieval_evaluation,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash


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
    ) -> RetrievalEvaluationResultV1:
        dataset = load_gold_or_raise(Path(dataset_path))
        anchor_k = int(self.settings.context.anchor_k)
        counter = make_token_counter(self.settings)
        ctx_hash = build_context_config_hash(self.settings, token_counter=counter)
        fus_hash = build_fusion_config_hash(self.settings)
        rrk_hash = build_reranker_config_hash(self.settings)
        provenance: dict = {
            "fusion_config_hash": fus_hash,
            "reranker_config_hash": rrk_hash,
            "context_config_hash": ctx_hash,
            "anchor_k": anchor_k,
            "top_k": anchor_k,
            "dense_index_id": "",
            "lexical_index_id": "",
        }
        assembly_acc = {
            "token_counts": [],
            "unit_counts": [],
            "stop_reason_counts": {},
            "clipped_cases": 0,
            "budget_cases": 0,
            "total_dedup": 0,
            "total_suppress": 0,
        }

        def _retrieve(case) -> tuple[list[str], dict]:
            result = self.assembler.assemble(query=case.query, corpus_name=corpus_name)
            if dataset.meta.chunk_set_id != str(result.metadata.get("chunk_set_id") or ""):
                raise EvaluationError(
                    "dataset chunk_set_id does not match context chunk_set_id: "
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
            diag = result.diagnostics
            assembly_acc["token_counts"].append(int(result.context_token_count))
            assembly_acc["unit_counts"].append(int(diag.evidence_unit_count))
            reasons = assembly_acc["stop_reason_counts"]
            reasons[diag.stop_reason] = reasons.get(diag.stop_reason, 0) + 1
            if diag.clipping_occurred:
                assembly_acc["clipped_cases"] += 1
            if diag.budget_exhausted:
                assembly_acc["budget_cases"] += 1
            assembly_acc["total_dedup"] += int(diag.dedup_hits)
            assembly_acc["total_suppress"] += int(diag.containment_suppressions)
            anchors = [anchor.chunk_id for anchor in result.anchors]
            return anchors, {
                "dense_index_id": result.dense_index_id,
                "lexical_index_id": result.lexical_index_id,
                "gold_in_rerank_pool": gold_in_pool,
                "input_pool_size": input_pool_size,
                "evidence_unit_count": diag.evidence_unit_count,
                "context_token_count": result.context_token_count,
                "clipping_occurred": diag.clipping_occurred,
                "budget_exhausted": diag.budget_exhausted,
                "stop_reason": diag.stop_reason,
                "dedup_hits": diag.dedup_hits,
                "containment_suppressions": diag.containment_suppressions,
                "returned_count": len(anchors),
            }

        report = run_retrieval_evaluation(
            dataset=dataset,
            method="hybrid-rerank-context",
            run_prefix="evalctx",
            requested_depth=anchor_k,
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

        tokens = assembly_acc["token_counts"]
        units = assembly_acc["unit_counts"]
        assembly_summary = {
            "context_tokens_mean": (sum(tokens) / len(tokens)) if tokens else 0.0,
            "context_tokens_min": min(tokens) if tokens else 0,
            "context_tokens_max": max(tokens) if tokens else 0,
            "evidence_units_mean": (sum(units) / len(units)) if units else 0.0,
            "evidence_units_min": min(units) if units else 0,
            "evidence_units_max": max(units) if units else 0,
            "clipped_case_count": assembly_acc["clipped_cases"],
            "budget_exhausted_case_count": assembly_acc["budget_cases"],
            "stop_reason_counts": assembly_acc["stop_reason_counts"],
            "total_dedup_hits": assembly_acc["total_dedup"],
            "total_containment_suppressions": assembly_acc["total_suppress"],
        }
        report = report.model_copy(
            update={
                "metadata": {
                    **report.metadata,
                    "assembly_summary": assembly_summary,
                }
            }
        )

        if persist:
            report = persist_result(
                report,
                eval_results_root=self.settings.paths.eval_results,
                subdirectory="hybrid-rerank-context",
                output_path=Path(output_path) if output_path else None,
            )
        return report
