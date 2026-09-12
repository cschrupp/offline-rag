"""Embedding-text builders for dense indexing."""

from __future__ import annotations

from typing import Protocol

from offline_rag.core.ids import PLAIN_EMBEDDING_TEXT_CONTRACT, TITLE_SECTION_TEXT_V1
from offline_rag.retrieval.ranking_text import (
    RankingTextInputs,
    render_title_section_text_v1,
)


class EmbeddingTextBuilder(Protocol):
    """Derive the exact string sent to an embedder for one chunk."""

    strategy: str
    contract_version: str

    def build(self, inputs: RankingTextInputs) -> str:
        """Return embedding input text for ``inputs``."""


class PlainEmbeddingTextBuilder:
    """Baseline builder: embedding_text is the immutable Chunk.text exactly."""

    strategy = "plain"
    contract_version = PLAIN_EMBEDDING_TEXT_CONTRACT

    def build(self, inputs: RankingTextInputs) -> str:
        return inputs.chunk_text


class TitleSectionEmbeddingTextBuilder:
    """Metadata-aware builder: title-section-text-v1 ranking envelope."""

    strategy = "title_section"
    contract_version = TITLE_SECTION_TEXT_V1

    def build(self, inputs: RankingTextInputs) -> str:
        return render_title_section_text_v1(inputs)
