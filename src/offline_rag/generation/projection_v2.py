"""Public answer_blocks / citation_ref projection for grounded_answer_v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from offline_rag.domain.generation import GroundedAnswerBlock, ResolvedCitation
from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.generation.citations import resolve_citations
from offline_rag.generation.excerpts import build_citation_excerpt


@dataclass(frozen=True, slots=True)
class PublicAnswerBlock:
    text: str
    citation_refs: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "citation_refs": list(self.citation_refs)}


def project_plain_answer(blocks: list[GroundedAnswerBlock] | list[PublicAnswerBlock]) -> str:
    """Deterministic plain answer: block texts joined by blank lines."""
    return "\n\n".join(block.text for block in blocks)


def assign_public_citation_refs(
    blocks: list[GroundedAnswerBlock],
) -> tuple[list[PublicAnswerBlock], list[str]]:
    """Walk blocks in order; assign c1..cn by first-reference unique evidence ids.

    Returns ``(public_blocks, ordered_unique_evidence_unit_ids)``.
    """
    ordered_unique: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        for evidence_id in block.evidence_unit_ids:
            if evidence_id not in seen:
                seen.add(evidence_id)
                ordered_unique.append(evidence_id)

    id_to_ref = {
        evidence_id: f"c{index}"
        for index, evidence_id in enumerate(ordered_unique, start=1)
    }
    public_blocks = [
        PublicAnswerBlock(
            text=block.text,
            citation_refs=[id_to_ref[eid] for eid in block.evidence_unit_ids],
        )
        for block in blocks
    ]
    return public_blocks, ordered_unique


def project_public_citations(
    ordered_evidence_unit_ids: list[str],
    units: list[EvidenceUnit],
) -> list[dict[str, Any]]:
    """Build public citation objects with citation_ref + excerpt fields."""
    resolved = resolve_citations(ordered_evidence_unit_ids, units)
    by_id = {unit.evidence_unit_id: unit for unit in units}
    rows: list[dict[str, Any]] = []
    for index, citation in enumerate(resolved, start=1):
        unit = by_id[citation.evidence_unit_id]
        excerpt, clipped = build_citation_excerpt(unit.text)
        rows.append(_citation_public_row(citation, ref=f"c{index}", excerpt=excerpt, clipped=clipped))
    return rows


def _citation_public_row(
    citation: ResolvedCitation,
    *,
    ref: str,
    excerpt: str,
    clipped: bool,
) -> dict[str, Any]:
    return {
        "evidence_unit_id": citation.evidence_unit_id,
        "document_id": citation.document_id,
        "source_chunk_id": citation.source_chunk_id,
        "kind": citation.kind,
        "section_path": list(citation.section_path),
        "page_start": citation.page_start,
        "page_end": citation.page_end,
        "line_start": citation.line_start,
        "line_end": citation.line_end,
        "clipped": citation.clipped,
        "citation_ref": ref,
        "excerpt": excerpt,
        "excerpt_clipped": clipped,
    }
