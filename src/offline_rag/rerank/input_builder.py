"""plain-pair-v1 query–passage construction for Slice 6."""

from __future__ import annotations

from collections.abc import Sequence

from offline_rag.core.ids import PLAIN_PAIR_INPUT_CONTRACT
from offline_rag.domain.indexing import HybridCandidate
from offline_rag.rerank.protocol import RerankerPair


class PairInputError(ValueError):
    """Raised when plain-pair-v1 construction fails validation."""


class PlainPairInputBuilder:
    """Build ``plain-pair-v1`` pairs from hybrid candidates."""

    contract = PLAIN_PAIR_INPUT_CONTRACT

    def build(self, *, query: str, candidates: Sequence[HybridCandidate]) -> list[RerankerPair]:
        query_text = query.strip()
        if not query_text:
            raise PairInputError("query must be non-empty after strip for plain-pair-v1")

        pairs: list[RerankerPair] = []
        for candidate in candidates:
            passage = candidate.text
            if not passage or not passage.strip():
                raise PairInputError(
                    "plain-pair-v1 invariant failure: empty or whitespace-only passage "
                    f"for chunk_id={candidate.chunk_id!r}"
                )
            pairs.append(
                RerankerPair(
                    chunk_id=candidate.chunk_id,
                    query_text=query_text,
                    passage_text=passage,
                )
            )
        return pairs
