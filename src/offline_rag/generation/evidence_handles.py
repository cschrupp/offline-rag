"""Response-local evidence handles (E1, E2, …) for grounded-answer-v2."""

from __future__ import annotations

import re
from collections.abc import Sequence

from offline_rag.domain.indexing import EvidenceUnit

_HANDLE_RE = re.compile(r"^E([1-9][0-9]*)$")


def assign_evidence_handles(
    evidence_units: Sequence[EvidenceUnit],
) -> tuple[dict[str, str], dict[str, EvidenceUnit]]:
    """Map accepted context order → E-handles and handle → EvidenceUnit.

    Returns ``(handle_to_evidence_unit_id, handle_to_unit)``.
    """
    handle_to_id: dict[str, str] = {}
    handle_to_unit: dict[str, EvidenceUnit] = {}
    for index, unit in enumerate(evidence_units, start=1):
        handle = f"E{index}"
        handle_to_id[handle] = unit.evidence_unit_id
        handle_to_unit[handle] = unit
    return handle_to_id, handle_to_unit


def is_valid_handle_syntax(handle: str) -> bool:
    return isinstance(handle, str) and _HANDLE_RE.fullmatch(handle) is not None


def resolve_handles_to_evidence_ids(
    handles: Sequence[str],
    *,
    handle_to_id: dict[str, str],
) -> list[str]:
    return [handle_to_id[handle] for handle in handles]
