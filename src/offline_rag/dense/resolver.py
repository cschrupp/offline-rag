"""Resolve canonical chunk content from Slice 2 artifacts."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import load_chunk_artifact
from offline_rag.domain.chunking import DocumentChunkArtifact
from offline_rag.domain.documents import Chunk, ChunkKind


class ChunkResolutionError(LookupError):
    pass


def resolve_chunk_from_artifact(
    artifact: DocumentChunkArtifact,
    chunk_id: str,
) -> Chunk:
    """Return the child chunk identified by ``chunk_id`` from ``artifact``."""
    for chunk in artifact.children:
        if chunk.chunk_id == chunk_id:
            if chunk.kind != ChunkKind.CHILD:
                raise ChunkResolutionError(f"chunk {chunk_id} is not a child")
            return chunk
    raise ChunkResolutionError(
        f"chunk_id {chunk_id} not found in artifact {artifact.chunk_artifact_id}"
    )


def resolve_child_chunk(
    chunks_root: Path,
    *,
    chunk_artifact_id: str,
    chunk_id: str,
) -> Chunk:
    path = Path(chunks_root) / f"{chunk_artifact_id}.json"
    if not path.exists():
        raise ChunkResolutionError(f"missing chunk artifact: {chunk_artifact_id}")
    artifact = load_chunk_artifact(path)
    return resolve_chunk_from_artifact(artifact, chunk_id)


def load_chunk_lookup(
    chunks_root: Path,
    chunk_artifact_ids: list[str],
) -> dict[str, tuple[Chunk, DocumentChunkArtifact]]:
    """Map child chunk_id -> (Chunk, owning DocumentChunkArtifact)."""
    lookup: dict[str, tuple[Chunk, DocumentChunkArtifact]] = {}
    for artifact_id in chunk_artifact_ids:
        path = Path(chunks_root) / f"{artifact_id}.json"
        artifact = load_chunk_artifact(path)
        for chunk in artifact.children:
            if chunk.kind != ChunkKind.CHILD:
                continue
            if chunk.chunk_id in lookup:
                raise ChunkResolutionError(f"duplicate child chunk_id in chunk set: {chunk.chunk_id}")
            lookup[chunk.chunk_id] = (chunk, artifact)
    return lookup
