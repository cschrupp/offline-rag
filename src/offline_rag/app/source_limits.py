"""Media-aware product source limits shared by transport and workspace paths."""

from __future__ import annotations

from offline_rag.config.models import AppSettings

PDF_MEDIA_TYPE = "application/pdf"


def source_limit_bytes(settings: AppSettings, media_type: str | None) -> int:
    """Return the authoritative incoming-source limit for a media type."""
    if media_type == PDF_MEDIA_TYPE:
        return int(settings.api.max_pdf_bytes_per_document)
    return int(settings.api.max_bytes_per_document)
