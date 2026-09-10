"""Lean Qdrant payload construction for dense child points."""

from __future__ import annotations

from typing import Any

from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.backend import DensePointRecord
from offline_rag.dense.qdrant_local import payload_without_nulls
from offline_rag.domain.documents import Chunk, ChunkKind

DENSE_POINT_SCHEMA_VERSION = "offline-rag-dense-point-v1"


def build_dense_payload(
    chunk: Chunk,
    *,
    chunk_artifact_id: str,
    chunk_set_id: str,
    embedding_id: str,
    index_id: str | None = None,
) -> dict[str, Any]:
    """Build lean provenance payload (no full text)."""
    if chunk.kind != ChunkKind.CHILD:
        raise ValueError("dense points may only be built for child chunks")
    payload: dict[str, Any] = {
        "schema_version": DENSE_POINT_SCHEMA_VERSION,
        "kind": ChunkKind.CHILD.value,
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "parent_chunk_id": chunk.parent_chunk_id,
        "previous_chunk_id": chunk.previous_chunk_id,
        "next_chunk_id": chunk.next_chunk_id,
        "chunk_artifact_id": chunk_artifact_id,
        "chunk_set_id": chunk_set_id,
        "embedding_id": embedding_id,
        "section_path": list(chunk.section_path),
        "order": chunk.order,
        "token_count": chunk.token_count,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
    }
    if index_id is not None:
        payload["index_id"] = index_id
    return payload_without_nulls(payload)


def build_dense_point(
    chunk: Chunk,
    *,
    vector: list[float],
    chunk_artifact_id: str,
    chunk_set_id: str,
    embedding_id: str,
    index_id: str | None = None,
) -> DensePointRecord:
    point_id = dense_point_uuid(chunk.chunk_id)
    payload = build_dense_payload(
        chunk,
        chunk_artifact_id=chunk_artifact_id,
        chunk_set_id=chunk_set_id,
        embedding_id=embedding_id,
        index_id=index_id,
    )
    return DensePointRecord(point_id=point_id, vector=vector, payload=payload)
