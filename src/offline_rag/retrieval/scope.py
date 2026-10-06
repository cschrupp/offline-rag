"""Fail-closed document-scope invariants for retrieval stages (Slice 16D-A)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def assert_document_scope(
    candidates: Iterable[Any],
    document_ids: frozenset[str] | None,
    *,
    error_cls: type[Exception],
    stage: str,
) -> None:
    """Raise ``error_cls`` if any candidate escapes ``document_ids``.

    When ``document_ids`` is None the query is unscoped and no check runs.
    Escaped candidates are never dropped — scoped retrieval fails closed.
    """
    if document_ids is None:
        return
    for candidate in candidates:
        doc_id = str(getattr(candidate, "document_id", "") or "")
        if doc_id not in document_ids:
            raise error_cls(
                f"scoped {stage} candidate escaped allowed document set: {doc_id}"
            )
