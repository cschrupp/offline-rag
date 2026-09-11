"""Load canonical parent/child structure for context expansion."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_artifact_path,
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.config.models import AppSettings
from offline_rag.domain.chunking import DocumentChunkArtifact
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.ingestion.discovery import validate_corpus_name


class ContextStructureError(RuntimeError):
    """Structural integrity failure in chunk artifacts used by context expansion."""


class ChunkStructureStore:
    """In-memory lookup over the active corpus ChunkSet."""

    def __init__(
        self,
        *,
        children: dict[str, Chunk],
        parents: dict[str, Chunk],
        chunk_set_id: str,
        corpus_id: str,
    ) -> None:
        self.children = children
        self.parents = parents
        self.chunk_set_id = chunk_set_id
        self.corpus_id = corpus_id

    def get_child(self, chunk_id: str) -> Chunk:
        try:
            return self.children[chunk_id]
        except KeyError as exc:
            raise ContextStructureError(f"missing child chunk: {chunk_id}") from exc

    def get_parent(self, parent_chunk_id: str) -> Chunk:
        try:
            parent = self.parents[parent_chunk_id]
        except KeyError as exc:
            raise ContextStructureError(f"missing parent chunk: {parent_chunk_id}") from exc
        if parent.kind != ChunkKind.PARENT:
            raise ContextStructureError(f"chunk {parent_chunk_id} is not a parent")
        return parent

    def resolve_parent_for_child(self, child: Chunk) -> Chunk:
        if not child.parent_chunk_id:
            raise ContextStructureError(
                f"child {child.chunk_id} lacks parent_chunk_id required by strategy"
            )
        parent = self.get_parent(child.parent_chunk_id)
        if parent.document_id != child.document_id:
            raise ContextStructureError(
                f"parent {parent.chunk_id} document mismatch for child {child.chunk_id}"
            )
        return parent


def _index_artifact(
    artifact: DocumentChunkArtifact,
    *,
    children: dict[str, Chunk],
    parents: dict[str, Chunk],
) -> None:
    for parent in artifact.parents:
        if parent.kind != ChunkKind.PARENT:
            raise ContextStructureError(
                f"non-parent in parents list: {parent.chunk_id} "
                f"(artifact {artifact.chunk_artifact_id})"
            )
        if parent.chunk_id in parents:
            raise ContextStructureError(f"duplicate parent chunk_id: {parent.chunk_id}")
        parents[parent.chunk_id] = parent
    for child in artifact.children:
        if child.kind != ChunkKind.CHILD:
            raise ContextStructureError(
                f"non-child in children list: {child.chunk_id} "
                f"(artifact {artifact.chunk_artifact_id})"
            )
        if child.chunk_id in children:
            raise ContextStructureError(f"duplicate child chunk_id: {child.chunk_id}")
        children[child.chunk_id] = child


def load_structure_store_for_corpus(
    settings: AppSettings,
    corpus_name: str,
) -> ChunkStructureStore:
    name = validate_corpus_name(corpus_name)
    state = load_chunk_state(chunk_state_path(settings.paths.corpora, name))
    manifest_path = settings.paths.chunk_manifests / Path(state.current_chunk_manifest).name
    if not manifest_path.exists():
        raise ContextStructureError(
            f"missing chunk-set manifest: {state.current_chunk_manifest}"
        )
    manifest = load_chunk_set_manifest(manifest_path)
    children: dict[str, Chunk] = {}
    parents: dict[str, Chunk] = {}
    for entry in manifest.documents:
        path = chunk_artifact_path(settings.paths.chunks, entry.chunk_artifact_id)
        if not path.exists():
            raise ContextStructureError(f"missing chunk artifact: {entry.chunk_artifact_id}")
        artifact = load_chunk_artifact(path)
        _index_artifact(artifact, children=children, parents=parents)
    return ChunkStructureStore(
        children=children,
        parents=parents,
        chunk_set_id=manifest.chunk_set_id,
        corpus_id=manifest.corpus_id,
    )


def validate_neighbor_links(store: ChunkStructureStore) -> list[str]:
    """Return structural neighbor integrity problems (empty if OK)."""
    problems: list[str] = []
    for chunk_id, child in store.children.items():
        for link_name, link_id in (
            ("previous_chunk_id", child.previous_chunk_id),
            ("next_chunk_id", child.next_chunk_id),
        ):
            if link_id is None:
                continue
            neighbor = store.children.get(link_id)
            if neighbor is None:
                problems.append(f"{chunk_id}.{link_name} missing neighbor {link_id}")
                continue
            if neighbor.document_id != child.document_id:
                problems.append(
                    f"{chunk_id}.{link_name} crosses document boundary to {link_id}"
                )
            if neighbor.kind != ChunkKind.CHILD:
                problems.append(f"{chunk_id}.{link_name} points to non-child {link_id}")
        if child.parent_chunk_id is not None and child.parent_chunk_id not in store.parents:
            # Parent missing is only a hard problem for parent strategies; still note it.
            problems.append(
                f"{chunk_id}.parent_chunk_id missing parent {child.parent_chunk_id}"
            )
    return problems


def validate_parent_links(store: ChunkStructureStore) -> list[str]:
    problems: list[str] = []
    for chunk_id, child in store.children.items():
        if not child.parent_chunk_id:
            problems.append(f"{chunk_id} lacks parent_chunk_id")
            continue
        parent = store.parents.get(child.parent_chunk_id)
        if parent is None:
            problems.append(f"{chunk_id} references missing parent {child.parent_chunk_id}")
            continue
        if parent.document_id != child.document_id:
            problems.append(
                f"{chunk_id} parent {parent.chunk_id} has mismatched document_id"
            )
    return problems
