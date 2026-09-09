"""Deterministic identity helpers for durable corpus objects.

Document and chunk IDs are content-derived and stable across re-ingestion when
inputs are unchanged. Runtime execution IDs (query/eval runs) may be random
because they identify an event, not durable corpus content.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def document_id_from_bytes(content: bytes) -> str:
    """Return ``doc_<sha256>`` derived from canonical source bytes."""
    if not content:
        raise ValueError("document content bytes must be non-empty")
    return f"doc_{_sha256_hex(content)}"


def chunk_id_from_parts(
    document_id: str,
    chunk_index: int,
    text: str,
    *,
    chunker_version: str | None = None,
) -> str:
    """Return ``chunk_<sha256>`` from document identity, locator, and text.

    Re-ingesting the same document with the same chunking inputs must yield the
    same chunk ID. Changing document ID, index, text, or chunker version changes
    the ID.
    """
    if not document_id.strip():
        raise ValueError("document_id must be a non-empty string")
    if chunk_index < 0:
        raise ValueError("chunk_index must be >= 0")

    normalized_text = text.strip("\n")
    payload = {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "text": normalized_text,
        "chunker_version": chunker_version or "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"chunk_{_sha256_hex(encoded.encode('utf-8'))}"


def canonical_config_hash(data: Mapping[str, Any]) -> str:
    """Return ``cfg_<sha256>`` for normalized configuration mappings.

    Key ordering is canonicalized so semantically identical mappings hash the
    same regardless of insertion order.
    """
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"cfg_{_sha256_hex(encoded.encode('utf-8'))}"


def new_execution_id(*, prefix: str = "run") -> str:
    """Return a runtime execution ID for query/eval events (not corpus identity)."""
    if not prefix.strip():
        raise ValueError("prefix must be a non-empty string")
    return f"{prefix}_{uuid.uuid4().hex}"
