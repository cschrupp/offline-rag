"""Embedding-text builders for dense indexing."""

from __future__ import annotations

from typing import Protocol

from offline_rag.core.ids import PLAIN_EMBEDDING_TEXT_CONTRACT
from offline_rag.domain.documents import Chunk


class EmbeddingTextBuilder(Protocol):
    """Derive the exact string sent to an embedder for one chunk."""

    strategy: str
    contract_version: str

    def build(self, chunk: Chunk) -> str:
        """Return embedding input text for ``chunk``."""


class PlainEmbeddingTextBuilder:
    """Baseline builder: embedding_text is the immutable Chunk.text exactly."""

    strategy = "plain"
    contract_version = PLAIN_EMBEDDING_TEXT_CONTRACT

    def build(self, chunk: Chunk) -> str:
        return chunk.text
