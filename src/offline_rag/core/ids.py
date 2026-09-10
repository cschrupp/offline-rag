"""Deterministic identity helpers for durable corpus objects.

Document and chunk IDs are content-derived and stable across re-ingestion when
inputs are unchanged. Runtime execution IDs (query/eval runs) may be random
because they identify an event, not durable corpus content.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

PARSER_SCHEMA_VERSION = "offline-rag-parsed-v1"
TEXT_PARSER_VERSION = "offline-rag-text-v1"
MARKDOWN_PARSER_VERSION = "offline-rag-markdown-v1"
DOCLING_PDF_PARSER_VERSION = "offline-rag-docling-pdf-v1"
STRUCTURE_AWARE_CHUNKER_VERSION = "structure-aware-chunker-v1"
TIKTOKEN_TOKENIZER_CONTRACT = "tiktoken-cl100k-v1"
PLAIN_EMBEDDING_TEXT_CONTRACT = "plain-v1"
SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT = "sentence-transformers-v1"
DENSE_INDEX_CONTRACT_VERSION = "dense-index-v1"
QWEN3_EMBEDDING_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
QWEN3_EMBEDDING_PINNED_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
QWEN3_EMBEDDING_ARTIFACT_CONTRACT = "qwen3-embedding-local-v1"
# Fixed namespace for deterministic UUID5 Qdrant point IDs (must never change).
OFFLINE_RAG_DENSE_POINT_NAMESPACE = uuid.UUID("a01f11e0-7a9d-4c0d-9e51-0ff11e000001")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash_from_bytes(content: bytes) -> str:
    """Return hex SHA-256 of source bytes (no prefix)."""
    if not content:
        raise ValueError("content bytes must be non-empty")
    return _sha256_hex(content)


def document_id_from_bytes(content: bytes) -> str:
    """Return ``doc_<sha256>`` derived from canonical source bytes."""
    return f"doc_{content_hash_from_bytes(content)}"


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


def block_id_from_parts(
    document_id: str,
    order: int,
    content_type: str,
    text: str,
) -> str:
    """Return ``block_<sha256>`` for a structural ContentBlock."""
    if not document_id.strip():
        raise ValueError("document_id must be a non-empty string")
    if order < 0:
        raise ValueError("order must be >= 0")
    payload = {
        "document_id": document_id,
        "order": order,
        "content_type": content_type,
        "text": text.strip("\n"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"block_{_sha256_hex(encoded.encode('utf-8'))}"


def canonical_config_hash(data: Mapping[str, Any]) -> str:
    """Return ``cfg_<sha256>`` for normalized configuration mappings.

    Key ordering is canonicalized so semantically identical mappings hash the
    same regardless of insertion order.
    """
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return f"cfg_{_sha256_hex(encoded.encode('utf-8'))}"


def parse_config_hash(
    *,
    parser_name: str,
    parser_version: str,
    ocr_enabled: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Hash only settings that can change normalized parser output."""
    payload: dict[str, Any] = {
        "parser_schema_version": PARSER_SCHEMA_VERSION,
        "parser_name": parser_name,
        "parser_version": parser_version,
        "ocr_enabled": ocr_enabled,
    }
    if extra:
        payload["extra"] = dict(extra)
    return canonical_config_hash(payload)


def parsed_artifact_id(
    document_id: str,
    parse_cfg_hash: str,
    *,
    parser_contract_version: str = PARSER_SCHEMA_VERSION,
) -> str:
    """Return ``parsed_<sha256>`` for content-addressed ParsedDocument artifacts."""
    if not document_id.strip():
        raise ValueError("document_id must be a non-empty string")
    if not parse_cfg_hash.strip():
        raise ValueError("parse_config_hash must be a non-empty string")
    payload = {
        "document_id": document_id,
        "parse_config_hash": parse_cfg_hash,
        "parser_contract_version": parser_contract_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"parsed_{_sha256_hex(encoded.encode('utf-8'))}"


def corpus_id_from_entries(
    *,
    schema_version: str,
    parse_cfg_hash: str,
    document_identities: Sequence[Mapping[str, str]],
) -> str:
    """Derive deterministic ``corpus_<sha256>`` from sorted content identities.

    ``document_identities`` entries should include document_id and
    source_content_hash (and optionally processed_artifact_hash). Source paths
    must not participate.
    """
    normalized = sorted(
        (
            {
                "document_id": item["document_id"],
                "source_content_hash": item["source_content_hash"],
                "processed_artifact_hash": item.get("processed_artifact_hash", ""),
                "parsed_artifact_id": item.get("parsed_artifact_id", ""),
            }
            for item in document_identities
        ),
        key=lambda row: (row["document_id"], row["source_content_hash"], row["parsed_artifact_id"]),
    )
    payload = {
        "schema_version": schema_version,
        "parse_config_hash": parse_cfg_hash,
        "documents": normalized,
    }
    digest = _sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return f"corpus_{digest}"


def artifact_bytes_hash(data: bytes) -> str:
    return f"art_{_sha256_hex(data)}"


def chunk_config_hash(data: Mapping[str, Any]) -> str:
    """Return ``chunkcfg_<sha256>`` for chunk-output-affecting configuration."""
    return canonical_config_hash(data).replace("cfg_", "chunkcfg_", 1)


def chunk_artifact_id(
    parsed_artifact_id: str,
    chunk_cfg_hash: str,
    *,
    chunker_version: str = STRUCTURE_AWARE_CHUNKER_VERSION,
) -> str:
    payload = {
        "parsed_artifact_id": parsed_artifact_id,
        "chunk_config_hash": chunk_cfg_hash,
        "chunker_version": chunker_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"chunkartifact_{_sha256_hex(encoded.encode('utf-8'))}"


def parent_chunk_id_from_parts(
    document_id: str,
    *,
    chunk_cfg_hash: str,
    source_block_ids: Sequence[str],
    text: str,
    chunker_version: str = STRUCTURE_AWARE_CHUNKER_VERSION,
) -> str:
    payload = {
        "document_id": document_id,
        "chunk_config_hash": chunk_cfg_hash,
        "chunker_version": chunker_version,
        "source_block_ids": list(source_block_ids),
        "text": text.strip("\n"),
        "kind": "parent",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"parent_{_sha256_hex(encoded.encode('utf-8'))}"


def child_chunk_id_from_parts(
    document_id: str,
    *,
    parent_chunk_id: str | None,
    chunk_cfg_hash: str,
    source_block_ids: Sequence[str],
    text: str,
    chunker_version: str = STRUCTURE_AWARE_CHUNKER_VERSION,
) -> str:
    payload = {
        "document_id": document_id,
        "parent_chunk_id": parent_chunk_id or "",
        "chunk_config_hash": chunk_cfg_hash,
        "chunker_version": chunker_version,
        "source_block_ids": list(source_block_ids),
        "text": text.strip("\n"),
        "kind": "child",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"chunk_{_sha256_hex(encoded.encode('utf-8'))}"


def chunk_set_id_from_entries(
    *,
    corpus_id: str,
    chunk_cfg_hash: str,
    chunker_version: str,
    document_entries: Sequence[Mapping[str, str]],
) -> str:
    normalized = sorted(
        (
            {
                "document_id": item["document_id"],
                "parsed_artifact_id": item["parsed_artifact_id"],
                "chunk_artifact_id": item["chunk_artifact_id"],
            }
            for item in document_entries
        ),
        key=lambda row: row["document_id"],
    )
    payload = {
        "corpus_id": corpus_id,
        "chunk_config_hash": chunk_cfg_hash,
        "chunker_version": chunker_version,
        "documents": normalized,
    }
    digest = _sha256_hex(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return f"chunkset_{digest}"


def new_execution_id(*, prefix: str = "run") -> str:
    """Return a runtime execution ID for query/eval events (not corpus identity)."""
    if not prefix.strip():
        raise ValueError("prefix must be a non-empty string")
    return f"{prefix}_{uuid.uuid4().hex}"


def embedding_config_hash(data: Mapping[str, Any]) -> str:
    return canonical_config_hash(data).replace("cfg_", "embcfg_", 1)


def index_config_hash(data: Mapping[str, Any]) -> str:
    return canonical_config_hash(data).replace("cfg_", "idxcfg_", 1)


def embedding_text_hash(text: str) -> str:
    return f"embtxt_{_sha256_hex(text.encode('utf-8'))}"


def embedding_id_from_parts(
    chunk_id: str,
    *,
    embedding_text_digest: str,
    emb_cfg_hash: str,
) -> str:
    payload = {
        "chunk_id": chunk_id,
        "embedding_text_hash": embedding_text_digest,
        "embedding_config_hash": emb_cfg_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"emb_{_sha256_hex(encoded.encode('utf-8'))}"


def dense_index_id(
    chunk_set_id: str,
    idx_cfg_hash: str,
    *,
    index_contract_version: str = DENSE_INDEX_CONTRACT_VERSION,
) -> str:
    payload = {
        "chunk_set_id": chunk_set_id,
        "index_config_hash": idx_cfg_hash,
        "index_contract_version": index_contract_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"denseindex_{_sha256_hex(encoded.encode('utf-8'))}"


def dense_collection_name(index_id: str) -> str:
    digest = index_id.removeprefix("denseindex_")
    return f"dense_{digest[:48]}"


def dense_point_uuid(chunk_id: str) -> str:
    return str(uuid.uuid5(OFFLINE_RAG_DENSE_POINT_NAMESPACE, chunk_id))


def dataset_id_from_bytes(content: bytes) -> str:
    return f"evaldataset_{_sha256_hex(content)}"
