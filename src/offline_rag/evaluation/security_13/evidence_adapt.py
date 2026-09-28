"""Map security fixture evidence onto real EvidenceUnit objects."""

from __future__ import annotations

from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.evaluation.security_13.contracts import AdversarialEvidenceUnitV1
from offline_rag.evaluation.security_13.evaluators import SecurityCaseView


def evidence_units_from_case(case: SecurityCaseView) -> list[EvidenceUnit]:
    """Construct real ``EvidenceUnit[]`` from fixture/control evidence.

    Body text uses ``unit.text``. Metadata placement preserves nested
    ``metadata`` on the EvidenceUnit without promoting it into the prompt
    (prompt-grounded-v1 renders text only).
    """
    units: list[EvidenceUnit] = []
    for index, item in enumerate(case.evidence):
        units.append(_to_evidence_unit(item, index=index))
    return units


def _to_evidence_unit(item: AdversarialEvidenceUnitV1, *, index: int) -> EvidenceUnit:
    doc_id = f"sec13b_doc_{item.evidence_id}"
    chunk_id = f"sec13b_chunk_{item.evidence_id}"
    # For metadata placement, keep a non-empty body (required by EvidenceUnit)
    # while the noisy nested metadata remains on ``metadata``.
    text = item.text
    metadata = dict(item.metadata)
    metadata["security_13_role"] = item.role
    metadata["security_13_placement"] = item.placement
    return EvidenceUnit(
        evidence_unit_id=item.evidence_id,
        source_chunk_id=chunk_id,
        kind="parent",
        text=text,
        clipped=False,
        token_count=max(1, len(text.split())),
        primary_anchor_chunk_id=chunk_id,
        contributing_anchor_chunk_ids=[chunk_id],
        document_id=doc_id,
        parent_chunk_id=chunk_id,
        section_path=[],
        metadata=metadata,
    )
