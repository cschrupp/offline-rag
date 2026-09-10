"""Hybrid-rerank retrieval: HybridRetriever pool + cross-encoder reranking."""

from __future__ import annotations

import time
from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    CHUNK_ID_ASC_TIE_BREAK,
    PLAIN_PAIR_INPUT_CONTRACT,
    RAW_LOGIT_SCORE_CONTRACT,
)
from offline_rag.domain.indexing import (
    HybridCandidate,
    HybridRerankCandidate,
    HybridRerankProvenance,
    HybridRerankRetrievalResult,
)
from offline_rag.hybrid.retrieve import HybridRetrievalError, HybridRetriever
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.cross_encoder import CrossEncoderReranker
from offline_rag.rerank.fake import FakeReranker
from offline_rag.rerank.input_builder import PlainPairInputBuilder
from offline_rag.rerank.protocol import Reranker
from offline_rag.rerank.status import (
    describe_hybrid_rerank_status,
    hybrid_rerank_status_for_corpus,
)


class HybridRerankRetrievalError(RuntimeError):
    pass


def _sort_scored(
    candidates: list[HybridCandidate],
    scores: list[float],
) -> list[tuple[HybridCandidate, float]]:
    if len(candidates) != len(scores):
        raise HybridRerankRetrievalError(
            f"score association mismatch: {len(scores)} scores for {len(candidates)} candidates"
        )
    paired = list(zip(candidates, scores, strict=True))
    # raw logit DESC, chunk_id ASC
    paired.sort(key=lambda item: (-item[1], item[0].chunk_id))
    return paired


class HybridRerankRetriever:
    """Compose HybridRetriever + Reranker with plain-pair-v1 and raw-logit-v1."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        hybrid: HybridRetriever | None = None,
        reranker: Reranker | None = None,
        input_builder: PlainPairInputBuilder | None = None,
    ) -> None:
        self.settings = settings
        self._hybrid = hybrid or HybridRetriever(settings)
        self._owned_hybrid = hybrid is None
        self._input_builder = input_builder or PlainPairInputBuilder()
        self._reranker = reranker if reranker is not None else self._make_reranker()

    def _make_reranker(self) -> Reranker:
        implementation = self.settings.reranker.implementation
        if implementation == "fake":
            return FakeReranker()
        if implementation == "sentence_transformers":
            return CrossEncoderReranker.from_settings(self.settings)
        raise HybridRerankRetrievalError(
            f"unsupported reranker implementation: {implementation}"
        )

    def close(self) -> None:
        if self._owned_hybrid:
            self._hybrid.close()

    def _require_ready(self, corpus_name: str) -> None:
        status = hybrid_rerank_status_for_corpus(self.settings, corpus_name)
        if status == "READY":
            return
        details = describe_hybrid_rerank_status(self.settings, corpus_name)
        raise HybridRerankRetrievalError(
            "Hybrid-rerank retrieval unavailable.\n"
            f"Hybrid status:            {details['hybrid_status']}\n"
            f"Reranker artifacts:       {details['reranker_artifacts']}\n"
            f"Hybrid-rerank status:     {details['status']}\n"
            f"Reranker enabled:         {details['reranker_enabled']}\n"
            f"Reranker implementation:  {details['reranker_implementation']}\n"
            "Ensure hybrid indexes are CURRENT and the reranker is provisioned:\n"
            f"  offline-rag index --corpus {corpus_name}\n"
            f"  offline-rag index lexical --corpus {corpus_name}\n"
            "  offline-rag provision reranker"
        )

    def retrieve(
        self,
        *,
        query: str,
        corpus_name: str = "default",
        top_k: int | None = None,
    ) -> HybridRerankRetrievalResult:
        if not query or not query.strip():
            raise HybridRerankRetrievalError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        rrk = self.settings.reranker
        if not rrk.enabled:
            raise HybridRerankRetrievalError("reranker is disabled")
        if rrk.input_construction != PLAIN_PAIR_INPUT_CONTRACT:
            raise HybridRerankRetrievalError(
                f"unsupported input_construction: {rrk.input_construction}"
            )
        if rrk.score_transform != RAW_LOGIT_SCORE_CONTRACT:
            raise HybridRerankRetrievalError(
                f"unsupported score_transform: {rrk.score_transform}"
            )
        if rrk.tie_break != CHUNK_ID_ASC_TIE_BREAK:
            raise HybridRerankRetrievalError(f"unsupported tie_break: {rrk.tie_break}")

        input_k = int(rrk.input_k)
        final_k = int(top_k if top_k is not None else rrk.output_k)
        if final_k < 1:
            raise HybridRerankRetrievalError("top_k must be >= 1")
        if final_k > 1000:
            raise HybridRerankRetrievalError("top_k exceeds safety limit (1000)")
        if final_k > input_k:
            raise HybridRerankRetrievalError(
                f"top_k ({final_k}) cannot exceed reranker.input_k ({input_k})"
            )

        self._require_ready(name)
        rrk_hash = build_reranker_config_hash(self.settings)

        wall_t0 = time.perf_counter()
        t_hybrid = time.perf_counter()
        try:
            hybrid_result = self._hybrid.retrieve(
                query=query.strip(),
                corpus_name=name,
                top_k=input_k,
            )
        except HybridRetrievalError as exc:
            raise HybridRerankRetrievalError(str(exc)) from exc
        hybrid_ms = int((time.perf_counter() - t_hybrid) * 1000)

        pool = list(hybrid_result.candidates)
        pool_ids = [candidate.chunk_id for candidate in pool]
        hybrid_breakdown = hybrid_result.metadata.get("latency_ms")
        if not isinstance(hybrid_breakdown, dict):
            hybrid_breakdown = {}

        if not pool:
            total_ms = int((time.perf_counter() - wall_t0) * 1000)
            return HybridRerankRetrievalResult(
                query=query.strip(),
                method="hybrid-rerank",
                top_k=final_k,
                candidates=[],
                dense_index_id=hybrid_result.dense_index_id,
                lexical_index_id=hybrid_result.lexical_index_id,
                fusion_config_hash=hybrid_result.fusion_config_hash,
                reranker_config_hash=rrk_hash,
                metadata={
                    "corpus_id": hybrid_result.metadata.get("corpus_id"),
                    "chunk_set_id": hybrid_result.metadata.get("chunk_set_id"),
                    "input_k": input_k,
                    "input_pool_size": 0,
                    "input_pool_chunk_ids": [],
                    "output_k": final_k,
                    "latency_ms": {
                        "hybrid": hybrid_ms,
                        "pair_build": 0,
                        "rerank_infer": 0,
                        "sort": 0,
                        "total": total_ms,
                        "hybrid_breakdown": hybrid_breakdown,
                    },
                },
            )

        t_pairs = time.perf_counter()
        try:
            pairs = self._input_builder.build(query=query, candidates=pool)
        except Exception as exc:
            raise HybridRerankRetrievalError(f"pair construction failed: {exc}") from exc
        pair_build_ms = int((time.perf_counter() - t_pairs) * 1000)

        t_infer = time.perf_counter()
        try:
            scores = self._reranker.score_pairs(pairs)
        except Exception as exc:
            raise HybridRerankRetrievalError(f"reranker scoring failed: {exc}") from exc
        rerank_infer_ms = int((time.perf_counter() - t_infer) * 1000)

        t_sort = time.perf_counter()
        ordered = _sort_scored(pool, scores)
        truncated = ordered[:final_k]
        candidates: list[HybridRerankCandidate] = []
        for rank, (source, score) in enumerate(truncated, start=1):
            candidates.append(
                HybridRerankCandidate(
                    rank=rank,
                    score=float(score),
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                    parent_chunk_id=source.parent_chunk_id,
                    previous_chunk_id=source.previous_chunk_id,
                    next_chunk_id=source.next_chunk_id,
                    text=source.text,
                    section_path=list(source.section_path),
                    page_start=source.page_start,
                    page_end=source.page_end,
                    line_start=source.line_start,
                    line_end=source.line_end,
                    token_count=source.token_count,
                    chunk_artifact_id=source.chunk_artifact_id,
                    hybrid_rerank=HybridRerankProvenance(
                        reranker_score=float(score),
                        hybrid_rank=source.rank,
                        rrf_score=float(source.fusion.rrf_score),
                        dense_rank=source.fusion.dense_rank,
                        dense_score=source.fusion.dense_score,
                        lexical_rank=source.fusion.lexical_rank,
                        lexical_score=source.fusion.lexical_score,
                    ),
                )
            )
        sort_ms = int((time.perf_counter() - t_sort) * 1000)
        total_ms = int((time.perf_counter() - wall_t0) * 1000)

        metadata: dict[str, Any] = {
            "corpus_id": hybrid_result.metadata.get("corpus_id"),
            "chunk_set_id": hybrid_result.metadata.get("chunk_set_id"),
            "input_k": input_k,
            "input_pool_size": len(pool),
            "input_pool_chunk_ids": pool_ids,
            "output_k": final_k,
            "latency_ms": {
                "hybrid": hybrid_ms,
                "pair_build": pair_build_ms,
                "rerank_infer": rerank_infer_ms,
                "sort": sort_ms,
                "total": total_ms,
                "hybrid_breakdown": hybrid_breakdown,
            },
        }
        return HybridRerankRetrievalResult(
            query=query.strip(),
            method="hybrid-rerank",
            top_k=final_k,
            candidates=candidates,
            dense_index_id=hybrid_result.dense_index_id,
            lexical_index_id=hybrid_result.lexical_index_id,
            fusion_config_hash=hybrid_result.fusion_config_hash,
            reranker_config_hash=rrk_hash,
            metadata=metadata,
        )
