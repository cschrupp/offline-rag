"""Lexical-text builders for BM25 indexing."""

from __future__ import annotations

from typing import Protocol

from offline_rag.core.ids import PLAIN_LEXICAL_TEXT_CONTRACT
from offline_rag.domain.documents import Chunk


class LexicalTextBuilder(Protocol):
    """Derive the exact string analyzed for one chunk."""

    strategy: str
    contract_version: str

    def build(self, chunk: Chunk) -> str:
        """Return lexical input text for ``chunk``."""


class PlainLexicalTextBuilder:
    """Baseline builder: lexical_text is the immutable Chunk.text exactly."""

    strategy = "plain"
    contract_version = PLAIN_LEXICAL_TEXT_CONTRACT

    def build(self, chunk: Chunk) -> str:
        text = chunk.text
        if not text.strip():
            raise ValueError(f"whitespace-only lexical text for chunk {chunk.chunk_id}")
        return text
