"""Derived hybrid readiness (no persisted HybridState)."""

from __future__ import annotations

from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.chunking.pipeline import chunking_status_for_corpus
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import RRF_FUSION_CONTRACT
from offline_rag.dense.persistence import index_state_path, try_load_index_state
from offline_rag.dense.status import indexing_status_for_corpus
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import corpus_state_path
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    try_load_lexical_index_state,
)
from offline_rag.lexical.status import lexical_indexing_status_for_corpus


def hybrid_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return READY or NOT_READY (derived)."""
    name = validate_corpus_name(corpus_name)
    if not corpus_state_path(settings.paths.corpora, name).exists():
        return "NOT_READY"

    fusion = settings.fusion
    if fusion.method != "rrf" or fusion.contract_version != RRF_FUSION_CONTRACT:
        return "NOT_READY"
    if fusion.rrf_k < 1 or fusion.dense_top_k < 1 or fusion.lexical_top_k < 1:
        return "NOT_READY"

    if chunking_status_for_corpus(settings, name) != "CURRENT":
        return "NOT_READY"

    dense_status = indexing_status_for_corpus(settings, name)
    lexical_status = lexical_indexing_status_for_corpus(settings, name)
    if dense_status != "CURRENT" or lexical_status != "CURRENT":
        return "NOT_READY"

    dense_state = try_load_index_state(index_state_path(settings.paths.corpora, name))
    lexical_state = try_load_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, name)
    )
    if dense_state is None or lexical_state is None:
        return "NOT_READY"

    chunk_state = load_chunk_state(chunk_state_path(settings.paths.corpora, name))
    active = chunk_state.current_chunk_set_id
    if dense_state.source_chunk_set_id != active:
        return "NOT_READY"
    if lexical_state.source_chunk_set_id != active:
        return "NOT_READY"
    if dense_state.source_chunk_set_id != lexical_state.source_chunk_set_id:
        return "NOT_READY"
    return "READY"


def describe_hybrid_status(settings: AppSettings, corpus_name: str) -> dict[str, str | None]:
    name = validate_corpus_name(corpus_name)
    status = hybrid_status_for_corpus(settings, name)
    dense_state = try_load_index_state(index_state_path(settings.paths.corpora, name))
    lexical_state = try_load_lexical_index_state(
        lexical_index_state_path(settings.paths.corpora, name)
    )
    chunk_path = chunk_state_path(settings.paths.corpora, name)
    active_chunk_set = None
    if chunk_path.exists():
        active_chunk_set = load_chunk_state(chunk_path).current_chunk_set_id
    return {
        "status": status,
        "corpus_name": name,
        "dense_status": indexing_status_for_corpus(settings, name),
        "lexical_status": lexical_indexing_status_for_corpus(settings, name),
        "dense_chunk_set_id": dense_state.source_chunk_set_id if dense_state else None,
        "lexical_chunk_set_id": lexical_state.source_chunk_set_id if lexical_state else None,
        "active_chunk_set_id": active_chunk_set,
        "dense_index_id": dense_state.current_index_id if dense_state else None,
        "lexical_index_id": lexical_state.current_lexical_index_id if lexical_state else None,
    }
