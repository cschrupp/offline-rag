"""Ingestion package."""

from offline_rag.ingestion.base import DocumentParseError
from offline_rag.ingestion.discovery import (
    DiscoveryError,
    discover_sources,
    validate_corpus_name,
)
from offline_rag.ingestion.docling_artifacts import (
    DoclingArtifactsUnavailableError,
    validate_docling_artifacts,
)
from offline_rag.ingestion.pipeline import (
    DocumentIngestionError,
    IngestionError,
    InternalIngestionError,
    run_ingestion,
)

__all__ = [
    "DiscoveryError",
    "DoclingArtifactsUnavailableError",
    "DocumentIngestionError",
    "DocumentParseError",
    "IngestionError",
    "InternalIngestionError",
    "discover_sources",
    "run_ingestion",
    "validate_corpus_name",
    "validate_docling_artifacts",
]
