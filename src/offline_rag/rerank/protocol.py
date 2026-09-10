"""Project-owned reranker scoring protocol."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RerankerPair:
    """One query–passage pair prepared for cross-encoder scoring."""

    chunk_id: str
    query_text: str
    passage_text: str


class Reranker(Protocol):
    """Score already-constructed query–passage pairs (source-agnostic)."""

    def score_pairs(self, pairs: Sequence[RerankerPair]) -> list[float]:
        """Return one finite scalar score per pair (higher = more relevant)."""
        ...
