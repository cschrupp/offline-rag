"""Application-owned /data root helpers (Residual A / D15)."""

from __future__ import annotations

from pathlib import Path

from offline_rag.config.models import AppSettings, PathSettings

# Required durable roots created at application startup (not by doctor).
_REQUIRED_PATH_ATTRS: tuple[str, ...] = (
    "raw_data",
    "qdrant_storage",
    "corpora",
    "manifests",
    "processed",
    "chunks",
    "chunk_manifests",
    "embeddings",
    "index_manifests",
    "lexical_indexes",
    "lexical_index_manifests",
    "traces",
    "staging",
    "locks",
    "workspaces",
)


def required_data_directories(settings: AppSettings | PathSettings) -> list[Path]:
    """Return the required application /data role directories."""
    paths = settings.paths if isinstance(settings, AppSettings) else settings
    return [getattr(paths, name) for name in _REQUIRED_PATH_ATTRS]


def ensure_data_directories(settings: AppSettings | PathSettings) -> list[Path]:
    """Create required /data role directories.

    Startup owns this behavior. Doctor must not create these paths.
    """
    created: list[Path] = []
    for path in required_data_directories(settings):
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
    return created
