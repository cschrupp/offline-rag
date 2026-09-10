"""Deterministic FakeReranker for CI (fake-rerank-digest-v1)."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence

from offline_rag.core.ids import FAKE_RERANK_DIGEST_CONTRACT
from offline_rag.rerank.protocol import RerankerPair


class FakeRerankerError(ValueError):
    pass


def fake_rerank_digest_score(query_text: str, passage_text: str) -> float:
    """Map ``(query, passage)`` to a score in ``[-10.0, 10.0)`` via SHA-256."""
    payload = query_text.encode("utf-8") + b"\x00" + passage_text.encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    u = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return (u / 2**64) * 20.0 - 10.0


class FakeReranker:
    """Test-only reranker; never an automatic production fallback."""

    contract = FAKE_RERANK_DIGEST_CONTRACT

    def __init__(
        self,
        *,
        score_map: Mapping[tuple[str, str], float] | None = None,
    ) -> None:
        self._score_map = dict(score_map or {})
        for key, value in self._score_map.items():
            if not math.isfinite(value):
                raise FakeRerankerError(
                    f"score_map override for {key!r} must be a finite scalar (got {value!r})"
                )

    def score_pairs(self, pairs: Sequence[RerankerPair]) -> list[float]:
        if not pairs:
            return []
        scores: list[float] = []
        for pair in pairs:
            override = self._score_map.get((pair.query_text, pair.chunk_id))
            if override is not None:
                if not math.isfinite(override):
                    raise FakeRerankerError(
                        f"override score for ({pair.query_text!r}, {pair.chunk_id!r}) "
                        "must be finite"
                    )
                scores.append(float(override))
            else:
                score = fake_rerank_digest_score(pair.query_text, pair.passage_text)
                if not math.isfinite(score):
                    raise FakeRerankerError("fake-rerank-digest-v1 produced a non-finite score")
                scores.append(score)
        return scores
