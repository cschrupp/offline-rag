"""Closed-world citation membership validation and provenance resolution."""

from __future__ import annotations

from offline_rag.domain.generation import ResolvedCitation
from offline_rag.domain.indexing import EvidenceUnit


def allowed_evidence_ids(units: list[EvidenceUnit]) -> set[str]:
    return {unit.evidence_unit_id for unit in units}


def validate_citation_membership(
    citation_ids: list[str],
    units: list[EvidenceUnit],
) -> list[str]:
    """Return invalid citation IDs (empty list means all valid)."""
    allowed = allowed_evidence_ids(units)
    return [citation_id for citation_id in citation_ids if citation_id not in allowed]


def resolve_citations(
    citation_ids: list[str],
    units: list[EvidenceUnit],
) -> list[ResolvedCitation]:
    by_id = {unit.evidence_unit_id: unit for unit in units}
    resolved: list[ResolvedCitation] = []
    for citation_id in citation_ids:
        unit = by_id[citation_id]
        representation = "clipped" if unit.clipped else "full"
        clip_payload = None
        if unit.clip is not None:
            clip_payload = unit.clip.model_dump()
        resolved.append(
            ResolvedCitation(
                evidence_unit_id=unit.evidence_unit_id,
                source_chunk_id=unit.source_chunk_id,
                kind=unit.kind,
                document_id=unit.document_id,
                representation=representation,
                clipped=unit.clipped,
                section_path=list(unit.section_path),
                page_start=unit.page_start,
                page_end=unit.page_end,
                line_start=unit.line_start,
                line_end=unit.line_end,
                clip=clip_payload,
                primary_anchor_chunk_id=unit.primary_anchor_chunk_id,
            )
        )
    return resolved
