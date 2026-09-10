"""Lexical indexing staleness diagnostics for a logical corpus."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    try_load_lexical_index_state,
)


def lexical_indexing_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return NOT_INDEXED/CURRENT/CHUNKS_STALE/LEXICAL_INDEX_STALE/LEXICAL_CONFIG_STALE/CORPUS_NOT_INITIALIZED."""
    name = validate_corpus_name(corpus_name)
    corpus_path = corpus_state_path(settings.paths.corpora, name)
    if not corpus_path.exists():
        return "CORPUS_NOT_INITIALIZED"

    corpus_state = load_corpus_state(corpus_path)
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    lexical_path = lexical_index_state_path(settings.paths.corpora, name)
    lexical_state = try_load_lexical_index_state(lexical_path)

    if not chunk_path.exists():
        return "NOT_INDEXED" if lexical_state is None else "LEXICAL_INDEX_STALE"

    chunk_state = load_chunk_state(chunk_path)
    if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
        return "CHUNKS_STALE"

    if lexical_state is None:
        return "NOT_INDEXED"

    if lexical_state.source_corpus_id != corpus_state.current_corpus_id:
        return "LEXICAL_INDEX_STALE"
    if lexical_state.source_chunk_set_id != chunk_state.current_chunk_set_id:
        return "LEXICAL_INDEX_STALE"

    expected_lex_cfg = build_lexical_config_hash(settings)
    if lexical_state.lexical_config_hash != expected_lex_cfg:
        return "LEXICAL_CONFIG_STALE"

    return "CURRENT"


def describe_lexical_indexing_status(
    settings: AppSettings,
    corpus_name: str,
) -> dict[str, str | None]:
    status = lexical_indexing_status_for_corpus(settings, corpus_name)
    name = validate_corpus_name(corpus_name)
    lexical_state = try_load_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, name)
    )
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    chunk_set_id = None
    if chunk_path.exists():
        chunk_set_id = load_chunk_state(chunk_path).current_chunk_set_id
    return {
        "status": status,
        "corpus_name": name,
        "current_lexical_index_id": (
            lexical_state.current_lexical_index_id if lexical_state else None
        ),
        "source_chunk_set_id": lexical_state.source_chunk_set_id if lexical_state else None,
        "active_chunk_set_id": chunk_set_id,
        "lexical_config_hash": lexical_state.lexical_config_hash if lexical_state else None,
        "expected_lexical_config_hash": build_lexical_config_hash(settings),
        "lexical_index_state_path": str(
            lexical_index_state_path(Path(settings.paths.corpora), name)
        ),
    }
