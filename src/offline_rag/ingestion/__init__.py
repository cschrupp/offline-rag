"""Ingestion package."""

from offline_rag.ingestion.discovery import (
    DiscoveryError,
    discover_sources,
    validate_corpus_name,
)
from offline_rag.ingestion.docling_artifacts import (
    DoclingArtifactsUnavailableError,
    validate_docling_artifacts,
)
from offline_rag.ingestion.pipeline import IngestionError, run_ingestion

__all__ = [
    "DiscoveryError",
    "DoclingArtifactsUnavailableError",
    "IngestionError",
    "discover_sources",
    "run_ingestion",
    "validate_corpus_name",
    "validate_docling_artifacts",
]
