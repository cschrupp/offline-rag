"""Content-addressed EmbeddingArtifact cache."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.core.ids import artifact_bytes_hash
from offline_rag.domain.indexing import EmbeddingArtifact
from offline_rag.ingestion.io import atomic_write_text


def embedding_artifact_relpath(embedding_id: str) -> str:
    return f"embeddings/{embedding_id}.json"


def embedding_artifact_path(embeddings_root: Path, embedding_id: str) -> Path:
    return Path(embeddings_root) / f"{embedding_id}.json"


def write_embedding_artifact(
    embeddings_root: Path,
    artifact: EmbeddingArtifact,
) -> tuple[Path, str]:
    path = embedding_artifact_path(embeddings_root, artifact.embedding_id)
    payload = artifact.model_dump_json()
    digest = artifact_bytes_hash(payload.encode("utf-8"))
    if path.exists():
        existing = path.read_bytes()
        if artifact_bytes_hash(existing) != digest:
            raise RuntimeError(f"embedding artifact conflict at {path}")
        return path, digest
    atomic_write_text(path, payload)
    return path, digest


def load_embedding_artifact(path: Path) -> EmbeddingArtifact:
    return EmbeddingArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def try_load_reusable_embedding_artifact(
    embeddings_root: Path,
    embedding_id: str,
    *,
    expected_chunk_id: str,
    expected_embedding_text_hash: str,
    expected_embedding_config_hash: str,
    expected_dimension: int,
    expected_normalize: bool,
    expected_model_id: str,
    expected_model_revision: str,
    expected_adapter_contract: str,
) -> EmbeddingArtifact | None:
    path = embedding_artifact_path(embeddings_root, embedding_id)
    if not path.exists():
        return None
    try:
        artifact = load_embedding_artifact(path)
    except (OSError, ValueError, TypeError, ValidationError):
        return None
    if artifact.embedding_id != embedding_id:
        return None
    if artifact.chunk_id != expected_chunk_id:
        return None
    if artifact.embedding_text_hash != expected_embedding_text_hash:
        return None
    if artifact.embedding_config_hash != expected_embedding_config_hash:
        return None
    if artifact.dimension != expected_dimension:
        return None
    if artifact.normalize != expected_normalize:
        return None
    if artifact.model_id != expected_model_id:
        return None
    if artifact.model_revision != expected_model_revision:
        return None
    if artifact.adapter_contract != expected_adapter_contract:
        return None
    if len(artifact.vector) != expected_dimension:
        return None
    return artifact
