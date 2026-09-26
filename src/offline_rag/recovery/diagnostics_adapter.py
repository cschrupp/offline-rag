"""Deterministic HybridRerankContextResult → RecoveryDiagnosticsV1 adapter."""

from __future__ import annotations

from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.recovery.contracts import (
    CONTEXT_STOP_REASONS_V1,
    AssemblyStopReasonV1,
    RecoveryDiagnosticsV1,
    RecoveryErrorCodeV1,
    RecoveryProtocolError,
)


def adapt_context_to_recovery_diagnostics(
    result: HybridRerankContextResult,
) -> RecoveryDiagnosticsV1:
    """Project allowlisted diagnostics only. Never includes corpus free text."""
    diag = result.diagnostics
    stop = diag.stop_reason
    if stop not in CONTEXT_STOP_REASONS_V1:
        raise RecoveryProtocolError(
            RecoveryErrorCodeV1.INVALID_STATE,
            f"unsupported context stop_reason for recovery diagnostics: {stop!r}",
        )
    anchors = list(result.anchors)
    units = list(result.evidence_units)
    top_score: float | None = None
    margin: float | None = None
    cross: bool | None = None
    if anchors:
        top = anchors[0]
        top_score = float(top.hybrid_rerank.reranker_score)
        cross = (
            top.hybrid_rerank.dense_rank is not None
            and top.hybrid_rerank.lexical_rank is not None
        )
        if len(anchors) >= 2:
            margin = top_score - float(anchors[1].hybrid_rerank.reranker_score)
    document_ids = {unit.document_id for unit in units}
    section_ids = {(unit.document_id, tuple(unit.section_path)) for unit in units}
    return RecoveryDiagnosticsV1(
        anchor_count=len(anchors),
        evidence_unit_count=len(units),
        top_reranker_score=top_score,
        top1_top2_margin=margin,
        top_anchor_cross_retriever_support=cross,
        distinct_document_count=len(document_ids),
        distinct_section_count=len(section_ids),
        clipping_occurred=bool(diag.clipping_occurred),
        budget_exhausted=bool(diag.budget_exhausted),
        stop_reason=AssemblyStopReasonV1(stop),
    )
