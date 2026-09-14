"""Union / ordering helpers for candidate-pooling-v1."""

from __future__ import annotations

from collections import defaultdict

from offline_rag.gold_authoring.pooling_models import PoolCandidate, RetrievalHit


def union_candidates(hits_by_retriever: dict[str, list[RetrievalHit]]) -> list[PoolCandidate]:
    """Union RetrievalHit lists keyed by retriever into PoolCandidate shells.

    Provenance fields (document_*) are filled later.
    """
    by_chunk: dict[str, list[RetrievalHit]] = defaultdict(list)
    for retriever, hits in hits_by_retriever.items():
        seen_for_arm: dict[str, RetrievalHit] = {}
        for hit in hits:
            if hit.retriever != retriever:
                hit = RetrievalHit(
                    retriever=retriever,
                    chunk_id=hit.chunk_id,
                    rank=hit.rank,
                    score=hit.score,
                )
            prior = seen_for_arm.get(hit.chunk_id)
            if prior is None or hit.rank < prior.rank:
                seen_for_arm[hit.chunk_id] = hit
        for hit in seen_for_arm.values():
            by_chunk[hit.chunk_id].append(hit)

    candidates = [
        PoolCandidate(chunk_id=chunk_id, retrieval_hits=list(hits))
        for chunk_id, hits in by_chunk.items()
    ]
    return order_pool_candidates(candidates)


def order_pool_candidates(candidates: list[PoolCandidate]) -> list[PoolCandidate]:
    """9C-4: min rank ↑, distinct arm count ↓, chunk_id ↑."""

    def key(candidate: PoolCandidate) -> tuple[int, int, str]:
        if not candidate.retrieval_hits:
            return (10**9, 0, candidate.chunk_id)
        best = min(hit.rank for hit in candidate.retrieval_hits)
        arms = len({hit.retriever for hit in candidate.retrieval_hits})
        return (best, -arms, candidate.chunk_id)

    return sorted(candidates, key=key)
