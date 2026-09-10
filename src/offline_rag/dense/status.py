"""Dense indexing staleness diagnostics for a logical corpus."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.config.models import AppSettings
from offline_rag.dense.config_hash import build_index_config_hash
from offline_rag.dense.persistence import index_state_path, try_load_index_state
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state


def indexing_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return NOT_INDEXED/CURRENT/CHUNKS_STALE/INDEX_STALE/INDEX_CONFIG_STALE/CORPUS_NOT_INITIALIZED."""
    name = validate_corpus_name(corpus_name)
    corpus_path = corpus_state_path(settings.paths.corpora, name)
    if not corpus_path.exists():
        return "CORPUS_NOT_INITIALIZED"

    corpus_state = load_corpus_state(corpus_path)
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    index_path = index_state_path(settings.paths.corpora, name)
    index_state = try_load_index_state(index_path)

    if not chunk_path.exists():
        return "NOT_INDEXED" if index_state is None else "INDEX_STALE"

    chunk_state = load_chunk_state(chunk_path)
    if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
        return "CHUNKS_STALE"

    if index_state is None:
        return "NOT_INDEXED"

    if index_state.source_corpus_id != corpus_state.current_corpus_id:
        return "INDEX_STALE"
    if index_state.source_chunk_set_id != chunk_state.current_chunk_set_id:
        return "INDEX_STALE"

    expected_index_cfg = build_index_config_hash(settings)
    if index_state.index_config_hash != expected_index_cfg:
        return "INDEX_CONFIG_STALE"

    return "CURRENT"


def describe_indexing_status(settings: AppSettings, corpus_name: str) -> dict[str, str | None]:
    status = indexing_status_for_corpus(settings, corpus_name)
    name = validate_corpus_name(corpus_name)
    index_state = try_load_index_state(index_state_path(settings.paths.corpora, name))
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    chunk_set_id = None
    if chunk_path.exists():
        chunk_set_id = load_chunk_state(chunk_path).current_chunk_set_id
    return {
        "status": status,
        "corpus_name": name,
        "current_index_id": index_state.current_index_id if index_state else None,
        "source_chunk_set_id": index_state.source_chunk_set_id if index_state else None,
        "active_chunk_set_id": chunk_set_id,
        "index_config_hash": index_state.index_config_hash if index_state else None,
        "expected_index_config_hash": build_index_config_hash(settings),
        "index_state_path": str(index_state_path(Path(settings.paths.corpora), name)),
    }
