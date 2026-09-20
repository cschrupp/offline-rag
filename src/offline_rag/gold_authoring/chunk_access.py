"""Compatibility facade — prefer ``offline_rag.chunking.access`` for new code."""

from __future__ import annotations

from offline_rag.chunking.access import (
    ChunkAccessError,
    CorpusChunkSnapshot,
    load_chunk_set_snapshot,
    load_current_corpus_chunk_snapshot,
    resolve_seed_text_from_chunk_set,
)

__all__ = [
    "ChunkAccessError",
    "CorpusChunkSnapshot",
    "load_chunk_set_snapshot",
    "load_current_corpus_chunk_snapshot",
    "resolve_seed_text_from_chunk_set",
]
