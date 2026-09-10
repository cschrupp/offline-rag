"""Chunk-set relational validation."""

from __future__ import annotations

from offline_rag.domain.documents import Chunk, ChunkKind


class ChunkSetValidationError(ValueError):
    pass


def validate_chunk_artifact(
    *,
    parents: list[Chunk],
    children: list[Chunk],
    document_id: str,
    parent_child: bool,
    child_max_tokens: int,
) -> None:
    parent_by_id = {chunk.chunk_id: chunk for chunk in parents}
    child_by_id = {chunk.chunk_id: chunk for chunk in children}
    if len(parent_by_id) != len(parents):
        raise ChunkSetValidationError("duplicate parent chunk IDs")
    if len(child_by_id) != len(children):
        raise ChunkSetValidationError("duplicate child chunk IDs")

    for parent in parents:
        if parent.kind != ChunkKind.PARENT:
            raise ChunkSetValidationError("parents list contains non-parent chunk")
        if parent.document_id != document_id:
            raise ChunkSetValidationError("parent document_id mismatch")

    for index, child in enumerate(children):
        if child.kind != ChunkKind.CHILD:
            raise ChunkSetValidationError("children list contains non-child chunk")
        if child.document_id != document_id:
            raise ChunkSetValidationError("child document_id mismatch")
        if child.order != index:
            raise ChunkSetValidationError("child order must be contiguous from 0")
        if parent_child:
            if not child.parent_chunk_id:
                raise ChunkSetValidationError("child missing parent_chunk_id")
            parent = parent_by_id.get(child.parent_chunk_id)
            if parent is None:
                raise ChunkSetValidationError(f"missing parent {child.parent_chunk_id}")
            parent_blocks = set(parent.source_block_ids)
            if not set(child.source_block_ids).issubset(parent_blocks):
                raise ChunkSetValidationError("child source blocks outside parent span")
        if child.token_count > child_max_tokens and not child.metadata.get("oversized_unsplittable"):
            raise ChunkSetValidationError(
                f"child {child.chunk_id} exceeds max_tokens={child_max_tokens}"
            )
        if child.previous_chunk_id is not None:
            prev = child_by_id.get(child.previous_chunk_id)
            if prev is None:
                raise ChunkSetValidationError(f"missing previous neighbor {child.previous_chunk_id}")
            if prev.next_chunk_id != child.chunk_id:
                raise ChunkSetValidationError("neighbor link asymmetry (previous)")
        if child.next_chunk_id is not None:
            nxt = child_by_id.get(child.next_chunk_id)
            if nxt is None:
                raise ChunkSetValidationError(f"missing next neighbor {child.next_chunk_id}")
            if nxt.previous_chunk_id != child.chunk_id:
                raise ChunkSetValidationError("neighbor link asymmetry (next)")
        if child.previous_chunk_id == child.chunk_id or child.next_chunk_id == child.chunk_id:
            raise ChunkSetValidationError("self-neighbor links are invalid")

    for index, child in enumerate(children):
        expected_prev = children[index - 1].chunk_id if index > 0 else None
        expected_next = children[index + 1].chunk_id if index + 1 < len(children) else None
        if child.previous_chunk_id != expected_prev or child.next_chunk_id != expected_next:
            raise ChunkSetValidationError("neighbor chain does not match child order")
