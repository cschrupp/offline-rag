"""Canonical product corpus-name validation (D20)."""

from __future__ import annotations

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.ingestion.discovery import DiscoveryError, validate_corpus_name


def validate_product_corpus_name(name: str) -> str:
    """Validate a logical corpus name using accepted discovery semantics.

    Adapters must call this entrypoint rather than reimplementing grammar or
    silently normalizing names.
    """
    try:
        return validate_corpus_name(name)
    except DiscoveryError as exc:
        raise AppError(
            code=ErrorCode.REQUEST_INVALID,
            message="Invalid corpus name",
            details={"reason": str(exc)},
        ) from exc
