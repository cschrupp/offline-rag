"""Frozen reviewable-case predicate for Gold Lab (R3-01)."""

from __future__ import annotations

from offline_rag.gold_authoring.models import SilverCase
from offline_rag.gold_authoring.review_models import canonicalize_query


def is_reviewable_case(case: SilverCase) -> bool:
    """Return True only for cases that may receive Gold Lab tasks / Hard Calls."""
    if case.proposed_query is None:
        return False
    if not str(case.proposed_query).strip():
        return False
    try:
        canonicalize_query(case.proposed_query)
    except ValueError:
        return False
    return len(case.candidates) > 0
