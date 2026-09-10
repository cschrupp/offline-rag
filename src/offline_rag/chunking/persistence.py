"""Chunk artifact and chunk-set persistence."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.core.ids import artifact_bytes_hash
from offline_rag.domain.chunking import (
    ChunkSetManifest,
    ChunkState,
    DocumentChunkArtifact,
)
from offline_rag.ingestion.io import atomic_write_text


def chunk_artifact_relpath(chunk_artifact_id: str) -> str:
    return f"chunks/{chunk_artifact_id}.json"


def chunk_artifact_path(chunks_root: Path, chunk_artifact_id: str) -> Path:
    return chunks_root / f"{chunk_artifact_id}.json"


def write_chunk_artifact(chunks_root: Path, artifact: DocumentChunkArtifact) -> tuple[Path, str]:
    path = chunk_artifact_path(chunks_root, artifact.chunk_artifact_id)
    payload = artifact.model_dump_json()
    digest = artifact_bytes_hash(payload.encode("utf-8"))
    if path.exists():
        existing = path.read_bytes()
        if artifact_bytes_hash(existing) != digest:
            raise RuntimeError(f"chunk artifact conflict at {path}")
        return path, digest
    atomic_write_text(path, payload)
    return path, digest


def load_chunk_artifact(path: Path) -> DocumentChunkArtifact:
    return DocumentChunkArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def try_load_reusable_chunk_artifact(
    chunks_root: Path,
    chunk_artifact_id: str,
    *,
    expected_parsed_artifact_id: str,
    expected_chunk_config_hash: str,
) -> tuple[DocumentChunkArtifact, str] | None:
    path = chunk_artifact_path(chunks_root, chunk_artifact_id)
    if not path.exists():
        return None
    try:
        artifact = load_chunk_artifact(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
    if artifact.chunk_artifact_id != chunk_artifact_id:
        return None
    if artifact.parsed_artifact_id != expected_parsed_artifact_id:
        return None
    if artifact.chunk_config_hash != expected_chunk_config_hash:
        return None
    digest = artifact_bytes_hash(path.read_bytes())
    return artifact, digest


def write_chunk_set_manifest(root: Path, manifest: ChunkSetManifest) -> Path:
    path = root / f"{manifest.chunk_set_id}.json"
    if path.exists():
        existing = ChunkSetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if (
            existing.chunk_set_id == manifest.chunk_set_id
            and existing.corpus_id == manifest.corpus_id
            and existing.chunk_config_hash == manifest.chunk_config_hash
            and existing.documents == manifest.documents
            and existing.total_parent_count == manifest.total_parent_count
            and existing.total_child_count == manifest.total_child_count
        ):
            return path
        raise RuntimeError(f"chunk-set manifest conflict for {manifest.chunk_set_id}")
    atomic_write_text(path, manifest.model_dump_json())
    return path


def load_chunk_set_manifest(path: Path) -> ChunkSetManifest:
    return ChunkSetManifest.model_validate_json(path.read_text(encoding="utf-8"))


def chunk_state_path(corpora_root: Path, corpus_name: str) -> Path:
    return corpora_root / corpus_name / "chunking" / "state.json"


def load_chunk_state(path: Path) -> ChunkState:
    return ChunkState.model_validate_json(path.read_text(encoding="utf-8"))


def write_chunk_state(path: Path, state: ChunkState) -> None:
    atomic_write_text(path, state.model_dump_json())
