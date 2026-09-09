"""Core utilities shared across OfflineRAG layers."""

from offline_rag.core.ids import (
    DOCLING_PDF_PARSER_VERSION,
    MARKDOWN_PARSER_VERSION,
    PARSER_SCHEMA_VERSION,
    TEXT_PARSER_VERSION,
    artifact_bytes_hash,
    block_id_from_parts,
    canonical_config_hash,
    chunk_id_from_parts,
    content_hash_from_bytes,
    corpus_id_from_entries,
    document_id_from_bytes,
    new_execution_id,
    parse_config_hash,
    parsed_artifact_id,
)

__all__ = [
    "DOCLING_PDF_PARSER_VERSION",
    "MARKDOWN_PARSER_VERSION",
    "PARSER_SCHEMA_VERSION",
    "TEXT_PARSER_VERSION",
    "artifact_bytes_hash",
    "block_id_from_parts",
    "canonical_config_hash",
    "chunk_id_from_parts",
    "content_hash_from_bytes",
    "corpus_id_from_entries",
    "document_id_from_bytes",
    "new_execution_id",
    "parse_config_hash",
    "parsed_artifact_id",
]
