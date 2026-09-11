"""plain-evidence-v1 rendering."""

from __future__ import annotations

from offline_rag.domain.indexing import EvidenceUnit

EVIDENCE_JOINER = "\n\n"


def render_plain_evidence(units: list[EvidenceUnit]) -> str:
    """Join evidence unit texts with exactly ``\\n\\n``."""
    return EVIDENCE_JOINER.join(unit.text for unit in units)
