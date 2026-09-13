"""Load CURRENT / historical ChunkSet children for gold authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_artifact_path,
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.config.models import AppSettings
from offline_rag.domain.documents import Chunk
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)


class ChunkAccessError(RuntimeError):
    """Corpus / ChunkSet resolution failure."""


@dataclass(frozen=True, slots=True)
class CorpusChunkSnapshot:
    corpus_name: str
    corpus_id: str
    chunk_set_id: str
    chunks: list[Chunk]
    source_name_by_document_id: dict[str, str]


def load_current_corpus_chunk_snapshot(
    settings: AppSettings,
    *,
    corpus_name: str,
) -> CorpusChunkSnapshot:
    corpora_root = settings.paths.corpora
    corpus_path = corpus_state_path(corpora_root, corpus_name)
    if not corpus_path.exists():
        raise ChunkAccessError(f"corpus state missing: {corpus_name}")
    try:
        corpus_state = load_corpus_state(corpus_path)
    except Exception as exc:  # noqa: BLE001
        raise ChunkAccessError(f"failed to load corpus state: {exc}") from exc

    chunk_path = chunk_state_path(corpora_root, corpus_name)
    if not chunk_path.exists():
        raise ChunkAccessError(f"chunk state missing for corpus: {corpus_name}")
    try:
        chunk_state = load_chunk_state(chunk_path)
    except Exception as exc:  # noqa: BLE001
        raise ChunkAccessError(f"failed to load chunk state: {exc}") from exc

    if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
        raise ChunkAccessError(
            "CURRENT chunk set is stale relative to corpus "
            f"(chunk source_corpus_id={chunk_state.source_corpus_id}, "
            f"corpus_id={corpus_state.current_corpus_id})"
        )

    chunk_set_id = chunk_state.current_chunk_set_id
    return load_chunk_set_snapshot(
        settings,
        corpus_name=corpus_name,
        corpus_id=corpus_state.current_corpus_id,
        chunk_set_id=chunk_set_id,
        corpus_manifest_name=Path(corpus_state.current_manifest).name,
    )


def load_chunk_set_snapshot(
    settings: AppSettings,
    *,
    corpus_name: str,
    corpus_id: str,
    chunk_set_id: str,
    corpus_manifest_name: str | None = None,
) -> CorpusChunkSnapshot:
    manifest_path = settings.paths.chunk_manifests / f"{chunk_set_id}.json"
    if not manifest_path.exists():
        raise ChunkAccessError(
            f"chunk-set manifest unavailable for chunk_set_id={chunk_set_id}"
        )
    try:
        chunk_manifest = load_chunk_set_manifest(manifest_path)
    except Exception as exc:  # noqa: BLE001
        raise ChunkAccessError(f"failed to load chunk-set manifest: {exc}") from exc

    source_names: dict[str, str] = {}
    if corpus_manifest_name is not None:
        corpus_manifest_path = settings.paths.manifests / corpus_manifest_name
        if not corpus_manifest_path.exists():
            raise ChunkAccessError(
                f"corpus manifest missing: {corpus_manifest_name}"
            )
        try:
            corpus_manifest = load_corpus_manifest(corpus_manifest_path)
        except Exception as exc:  # noqa: BLE001
            raise ChunkAccessError(f"failed to load corpus manifest: {exc}") from exc
        source_names = {
            entry.document_id: entry.source_name for entry in corpus_manifest.documents
        }

    chunks: list[Chunk] = []
    for entry in chunk_manifest.documents:
        artifact_path = chunk_artifact_path(
            settings.paths.chunks, entry.chunk_artifact_id
        )
        if not artifact_path.exists():
            raise ChunkAccessError(
                f"chunk artifact missing: {entry.chunk_artifact_id}"
            )
        artifact = load_chunk_artifact(artifact_path)
        chunks.extend(artifact.parents)
        chunks.extend(artifact.children)

    return CorpusChunkSnapshot(
        corpus_name=corpus_name,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        chunks=chunks,
        source_name_by_document_id=source_names,
    )


def resolve_seed_text_from_chunk_set(
    settings: AppSettings,
    *,
    chunk_set_id: str,
    chunk_id: str,
) -> str:
    """Reconstruct exact seed text from an immutable historical ChunkSet."""
    manifest_path = settings.paths.chunk_manifests / f"{chunk_set_id}.json"
    if not manifest_path.exists():
        raise ChunkAccessError(
            f"historical chunk-set unavailable: {chunk_set_id}"
        )
    chunk_manifest = load_chunk_set_manifest(manifest_path)
    for entry in chunk_manifest.documents:
        artifact_path = chunk_artifact_path(
            settings.paths.chunks, entry.chunk_artifact_id
        )
        if not artifact_path.exists():
            continue
        artifact = load_chunk_artifact(artifact_path)
        for chunk in (*artifact.parents, *artifact.children):
            if chunk.chunk_id == chunk_id:
                return chunk.text
    raise ChunkAccessError(
        f"chunk_id {chunk_id} not found in chunk_set_id={chunk_set_id}"
    )
