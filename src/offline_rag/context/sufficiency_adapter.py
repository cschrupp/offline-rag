"""Deterministic HybridRerankContextResult → SufficiencyProvenanceV1 adapter.

Lives outside ``sufficiency/`` (OD-11-32 / OD-11-33). Slice 11 uses attempt 0 /
role ``initial`` with ``original_query == active_retrieval_query``.
"""

from __future__ import annotations

from typing import Any

from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankCandidate,
    HybridRerankContextResult,
)
from offline_rag.sufficiency.contracts import (
    SufficiencyAnchorProvenance,
    SufficiencyAssemblyDiagnosticsV1,
    SufficiencyDerivationError,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyEvidenceUnitProvenance,
    SufficiencyProvenanceV1,
)


class SufficiencyAdapterError(SufficiencyDerivationError):
    """Fail-closed adapter projection error (missing/ambiguous upstream fields)."""


def _require_nonblank(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or value == "" or value.strip() == "":
        raise SufficiencyAdapterError(
            SufficiencyErrorCodeV1.MISSING_REQUIRED_LINEAGE,
            f"required lineage/query field {field_name!r} is missing or blank",
            details=SufficiencyErrorDetailsV1(
                field_name=field_name,
                actual=None if value is None else str(value),
            ),
        )
    return value


def _metadata_str(metadata: dict[str, Any], key: str) -> str:
    return _require_nonblank(metadata.get(key), field_name=key)


def _map_anchor(candidate: HybridRerankCandidate) -> SufficiencyAnchorProvenance:
    prov = candidate.hybrid_rerank
    return SufficiencyAnchorProvenance(
        chunk_id=candidate.chunk_id,
        rerank_rank=candidate.rank,
        reranker_score=float(prov.reranker_score),
        hybrid_rank=prov.hybrid_rank,
        rrf_score=float(prov.rrf_score),
        dense_rank=prov.dense_rank,
        dense_score=(None if prov.dense_score is None else float(prov.dense_score)),
        lexical_rank=prov.lexical_rank,
        lexical_score=(
            None if prov.lexical_score is None else float(prov.lexical_score)
        ),
    )


def _map_evidence_unit(unit: EvidenceUnit) -> SufficiencyEvidenceUnitProvenance:
    return SufficiencyEvidenceUnitProvenance(
        evidence_unit_id=unit.evidence_unit_id,
        document_id=unit.document_id,
        section_path=list(unit.section_path),
        source_chunk_id=unit.source_chunk_id,
        primary_anchor_chunk_id=unit.primary_anchor_chunk_id,
    )


def _map_diagnostics(
    diagnostics: ContextAssemblyDiagnostics,
) -> SufficiencyAssemblyDiagnosticsV1:
    return SufficiencyAssemblyDiagnosticsV1(
        evidence_unit_count=diagnostics.evidence_unit_count,
        context_token_count=diagnostics.context_token_count,
        clipping_occurred=diagnostics.clipping_occurred,
        budget_exhausted=diagnostics.budget_exhausted,
        stop_reason=diagnostics.stop_reason,
        dedup_hits=diagnostics.dedup_hits,
        containment_suppressions=diagnostics.containment_suppressions,
    )


def adapt_hybrid_rerank_context_to_provenance(
    result: HybridRerankContextResult,
    *,
    case_id: str,
) -> SufficiencyProvenanceV1:
    """Project a context result into neutral sufficiency provenance (lossless).

    Does not sort, renumber, synthesize, or repair retrieval provenance.
    Latency/host/path/timestamps in ``result.metadata`` are ignored.
    """
    case = _require_nonblank(case_id, field_name="case_id")
    query = _require_nonblank(result.query, field_name="query")
    metadata = dict(result.metadata or {})

    corpus_id = _metadata_str(metadata, "corpus_id")
    chunk_set_id = _metadata_str(metadata, "chunk_set_id")
    dense_index_id = _require_nonblank(
        result.dense_index_id, field_name="dense_index_id"
    )
    lexical_index_id = _require_nonblank(
        result.lexical_index_id, field_name="lexical_index_id"
    )
    fusion_config_hash = _require_nonblank(
        result.fusion_config_hash, field_name="fusion_config_hash"
    )
    reranker_config_hash = _require_nonblank(
        result.reranker_config_hash, field_name="reranker_config_hash"
    )
    context_config_hash = _require_nonblank(
        result.context_config_hash, field_name="context_config_hash"
    )

    anchors = [_map_anchor(anchor) for anchor in result.anchors]
    units = [_map_evidence_unit(unit) for unit in result.evidence_units]

    return SufficiencyProvenanceV1(
        case_id=case,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id=dense_index_id,
        lexical_index_id=lexical_index_id,
        fusion_config_hash=fusion_config_hash,
        reranker_config_hash=reranker_config_hash,
        context_config_hash=context_config_hash,
        original_query=query,
        active_retrieval_query=query,
        attempt_number=0,
        attempt_role="initial",
        anchors=anchors,
        final_evidence_units=units,
        diagnostics=_map_diagnostics(result.diagnostics),
    )
