"""Lexical-text builders for BM25 indexing."""

from __future__ import annotations

from typing import Protocol

from offline_rag.core.ids import PLAIN_LEXICAL_TEXT_CONTRACT, TITLE_SECTION_TEXT_V1
from offline_rag.retrieval.ranking_text import (
    RankingTextInputs,
    render_title_section_text_v1,
)


class LexicalTextBuilder(Protocol):
    """Derive the exact string analyzed for one chunk."""

    strategy: str
    contract_version: str

    def build(self, inputs: RankingTextInputs) -> str:
        """Return lexical input text for ``inputs``."""


class PlainLexicalTextBuilder:
    """Baseline builder: lexical_text is the immutable Chunk.text exactly."""

    strategy = "plain"
    contract_version = PLAIN_LEXICAL_TEXT_CONTRACT

    def build(self, inputs: RankingTextInputs) -> str:
        text = inputs.chunk_text
        if not text.strip():
            raise ValueError("whitespace-only lexical text")
        return text


class TitleSectionLexicalTextBuilder:
    """Metadata-aware builder: title-section-text-v1 ranking envelope."""

    strategy = "title_section"
    contract_version = TITLE_SECTION_TEXT_V1

    def build(self, inputs: RankingTextInputs) -> str:
        text = render_title_section_text_v1(inputs)
        if not text.strip():
            raise ValueError("whitespace-only lexical text after title-section rendering")
        return text
