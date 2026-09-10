"""Dense index manifest and IndexState persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.domain.indexing import DenseIndexManifest, IndexState
from offline_rag.ingestion.io import atomic_write_text


def index_manifest_relpath(index_id: str) -> str:
    return f"index-manifests/{index_id}.json"


def index_manifest_path(index_manifests_root: Path, index_id: str) -> Path:
    return Path(index_manifests_root) / f"{index_id}.json"


def write_index_manifest(index_manifests_root: Path, manifest: DenseIndexManifest) -> Path:
    path = index_manifest_path(index_manifests_root, manifest.index_id)
    if path.exists():
        existing = DenseIndexManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            existing.index_id == manifest.index_id
            and existing.corpus_id == manifest.corpus_id
            and existing.chunk_set_id == manifest.chunk_set_id
            and existing.embedding_config_hash == manifest.embedding_config_hash
            and existing.index_config_hash == manifest.index_config_hash
            and existing.collection_name == manifest.collection_name
            and existing.expected_child_count == manifest.expected_child_count
            and existing.indexed_child_count == manifest.indexed_child_count
            and existing.embedding_model_id == manifest.embedding_model_id
            and existing.embedding_model_revision == manifest.embedding_model_revision
            and existing.embedding_dimension == manifest.embedding_dimension
            and existing.normalize == manifest.normalize
            and existing.similarity_metric == manifest.similarity_metric
        ):
            return path
        raise RuntimeError(f"dense index manifest conflict for {manifest.index_id}")
    atomic_write_text(path, manifest.model_dump_json())
    return path


def load_index_manifest(path: Path) -> DenseIndexManifest:
    return DenseIndexManifest.model_validate_json(path.read_text(encoding="utf-8"))


def try_load_index_manifest(
    index_manifests_root: Path,
    index_id: str,
) -> DenseIndexManifest | None:
    path = index_manifest_path(index_manifests_root, index_id)
    if not path.exists():
        return None
    try:
        manifest = load_index_manifest(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
    if manifest.index_id != index_id:
        return None
    return manifest


def index_state_path(corpora_root: Path, corpus_name: str) -> Path:
    return Path(corpora_root) / corpus_name / "indexing" / "state.json"


def load_index_state(path: Path) -> IndexState:
    return IndexState.model_validate_json(path.read_text(encoding="utf-8"))


def write_index_state(path: Path, state: IndexState) -> None:
    atomic_write_text(path, state.model_dump_json())


def try_load_index_state(path: Path) -> IndexState | None:
    if not path.exists():
        return None
    try:
        return load_index_state(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
