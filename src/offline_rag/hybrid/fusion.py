"""Project-owned Reciprocal Rank Fusion (rrf-v1)."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.core.ids import RRF_FUSION_CONTRACT


@dataclass(frozen=True, slots=True)
class RankedBranchHit:
    """One unique chunk from a single retrieval branch."""

    chunk_id: str
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class FusedHit:
    """RRF result for one chunk with branch provenance."""

    chunk_id: str
    rrf_score: float
    dense_rank: int | None
    dense_score: float | None
    lexical_rank: int | None
    lexical_score: float | None


def _unique_branch_hits(hits: list[RankedBranchHit], *, branch: str) -> list[RankedBranchHit]:
    """Keep first occurrence of each chunk_id; raise if duplicate ranks conflict unexpectedly."""
    seen: dict[str, RankedBranchHit] = {}
    for hit in hits:
        if hit.rank < 1:
            raise ValueError(f"{branch} ranks must be 1-based (got {hit.rank})")
        existing = seen.get(hit.chunk_id)
        if existing is None:
            seen[hit.chunk_id] = hit
            continue
        # Defensive: keep best (lowest) rank; never double-contribute.
        if hit.rank < existing.rank:
            seen[hit.chunk_id] = hit
    # Re-emit in original rank order among survivors.
    return sorted(seen.values(), key=lambda item: (item.rank, item.chunk_id))


class ReciprocalRankFusion:
    """Equal-weight RRF over dense and lexical ranked lists."""

    contract_version = RRF_FUSION_CONTRACT

    def __init__(self, *, rrf_k: int = 60) -> None:
        if rrf_k < 1:
            raise ValueError("rrf_k must be >= 1")
        self.rrf_k = int(rrf_k)

    def fuse(
        self,
        *,
        dense: list[RankedBranchHit],
        lexical: list[RankedBranchHit],
    ) -> list[FusedHit]:
        dense_hits = _unique_branch_hits(dense, branch="dense")
        lexical_hits = _unique_branch_hits(lexical, branch="lexical")

        dense_by_id = {hit.chunk_id: hit for hit in dense_hits}
        lexical_by_id = {hit.chunk_id: hit for hit in lexical_hits}
        chunk_ids = set(dense_by_id) | set(lexical_by_id)

        fused: list[FusedHit] = []
        for chunk_id in chunk_ids:
            dense_hit = dense_by_id.get(chunk_id)
            lexical_hit = lexical_by_id.get(chunk_id)
            score = 0.0
            if dense_hit is not None:
                score += 1.0 / float(self.rrf_k + dense_hit.rank)
            if lexical_hit is not None:
                score += 1.0 / float(self.rrf_k + lexical_hit.rank)
            fused.append(
                FusedHit(
                    chunk_id=chunk_id,
                    rrf_score=score,
                    dense_rank=dense_hit.rank if dense_hit else None,
                    dense_score=dense_hit.score if dense_hit else None,
                    lexical_rank=lexical_hit.rank if lexical_hit else None,
                    lexical_score=lexical_hit.score if lexical_hit else None,
                )
            )

        fused.sort(key=lambda item: (-item.rrf_score, item.chunk_id))
        return fused
