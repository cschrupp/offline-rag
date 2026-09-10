"""Lexical index manifest and LexicalIndexState persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.domain.indexing import LexicalIndexManifest, LexicalIndexState
from offline_rag.ingestion.io import atomic_write_text


def lexical_index_manifest_relpath(lexical_index_id: str) -> str:
    return f"lexical-index-manifests/{lexical_index_id}.json"


def lexical_index_manifest_path(manifests_root: Path, lexical_index_id: str) -> Path:
    return Path(manifests_root) / f"{lexical_index_id}.json"


def write_lexical_index_manifest(
    manifests_root: Path,
    manifest: LexicalIndexManifest,
) -> Path:
    path = lexical_index_manifest_path(manifests_root, manifest.lexical_index_id)
    if path.exists():
        existing = LexicalIndexManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            existing.lexical_index_id == manifest.lexical_index_id
            and existing.corpus_id == manifest.corpus_id
            and existing.chunk_set_id == manifest.chunk_set_id
            and existing.lexical_config_hash == manifest.lexical_config_hash
            and existing.backend == manifest.backend
            and existing.backend_contract == manifest.backend_contract
            and existing.expected_child_count == manifest.expected_child_count
            and existing.indexed_child_count == manifest.indexed_child_count
            and existing.bm25_contract == manifest.bm25_contract
            and existing.bm25_k1 == manifest.bm25_k1
            and existing.bm25_b == manifest.bm25_b
            and existing.physical_index_relpath == manifest.physical_index_relpath
        ):
            return path
        raise RuntimeError(f"lexical index manifest conflict for {manifest.lexical_index_id}")
    atomic_write_text(path, manifest.model_dump_json())
    return path


def load_lexical_index_manifest(path: Path) -> LexicalIndexManifest:
    return LexicalIndexManifest.model_validate_json(path.read_text(encoding="utf-8"))


def try_load_lexical_index_manifest(
    manifests_root: Path,
    lexical_index_id: str,
) -> LexicalIndexManifest | None:
    path = lexical_index_manifest_path(manifests_root, lexical_index_id)
    if not path.exists():
        return None
    try:
        manifest = load_lexical_index_manifest(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
    if manifest.lexical_index_id != lexical_index_id:
        return None
    return manifest


def lexical_index_state_path(corpora_root: Path, corpus_name: str) -> Path:
    return Path(corpora_root) / corpus_name / "lexical" / "state.json"


def load_lexical_index_state(path: Path) -> LexicalIndexState:
    return LexicalIndexState.model_validate_json(path.read_text(encoding="utf-8"))


def write_lexical_index_state(path: Path, state: LexicalIndexState) -> None:
    atomic_write_text(path, state.model_dump_json())


def try_load_lexical_index_state(path: Path) -> LexicalIndexState | None:
    if not path.exists():
        return None
    try:
        return load_lexical_index_state(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
