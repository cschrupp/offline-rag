"""Hybrid retrieval: sequential dense + lexical + rrf-v1."""

from __future__ import annotations

import time

from offline_rag.config.models import AppSettings
from offline_rag.dense.persistence import index_state_path, try_load_index_state
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.indexing import (
    FusionProvenance,
    HybridCandidate,
    HybridRetrievalResult,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.fusion import RankedBranchHit, ReciprocalRankFusion
from offline_rag.hybrid.status import describe_hybrid_status, hybrid_status_for_corpus
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.lexical.retrieve import LexicalRetriever


class HybridRetrievalError(RuntimeError):
    pass


class HybridRetriever:
    """Compose CURRENT DenseRetriever + LexicalRetriever with rrf-v1."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        dense: DenseRetriever | None = None,
        lexical: LexicalRetriever | None = None,
        fusion: ReciprocalRankFusion | None = None,
    ) -> None:
        self.settings = settings
        self._dense = dense or DenseRetriever(settings)
        self._lexical = lexical or LexicalRetriever(settings)
        self._owned_dense = dense is None
        self._owned_lexical = lexical is None
        self._fusion = fusion or ReciprocalRankFusion(rrf_k=settings.fusion.rrf_k)

    def close(self) -> None:
        if self._owned_dense:
            self._dense.close()
        if self._owned_lexical:
            self._lexical.close()

    def _require_ready(self, corpus_name: str) -> None:
        status = hybrid_status_for_corpus(self.settings, corpus_name)
        if status == "READY":
            return
        details = describe_hybrid_status(self.settings, corpus_name)
        raise HybridRetrievalError(
            "Hybrid retrieval unavailable.\n"
            f"Dense index:   {details['dense_status']}\n"
            f"Lexical index: {details['lexical_status']}\n"
            f"Active chunk set:  {details['active_chunk_set_id']}\n"
            f"Dense chunk set:   {details['dense_chunk_set_id']}\n"
            f"Lexical chunk set: {details['lexical_chunk_set_id']}\n"
            f"Status: Hybrid {status}\n"
            "Ensure both indexes are CURRENT for the same chunk set:\n"
            f"  offline-rag index --corpus {corpus_name}\n"
            f"  offline-rag index lexical --corpus {corpus_name}"
        )

    def retrieve(
        self,
        *,
        query: str,
        corpus_name: str = "default",
        top_k: int | None = None,
    ) -> HybridRetrievalResult:
        if not query or not query.strip():
            raise HybridRetrievalError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        fusion_cfg = self.settings.fusion
        if fusion_cfg.method != "rrf" or fusion_cfg.contract_version != "rrf-v1":
            raise HybridRetrievalError(
                f"unsupported fusion method/contract: {fusion_cfg.method}/{fusion_cfg.contract_version}"
            )
        final_k = int(top_k if top_k is not None else fusion_cfg.output_top_k)
        if final_k < 1:
            raise HybridRetrievalError("top_k must be >= 1")
        if final_k > 1000:
            raise HybridRetrievalError("top_k exceeds safety limit (1000)")

        self._require_ready(name)
        fus_hash = build_fusion_config_hash(self.settings)
        dense_depth = int(fusion_cfg.dense_top_k)
        lexical_depth = int(fusion_cfg.lexical_top_k)
        details = describe_hybrid_status(self.settings, name)
        corpus_id = None
        dense_state = try_load_index_state(index_state_path(self.settings.paths.corpora, name))
        if dense_state is not None:
            corpus_id = dense_state.source_corpus_id

        wall_t0 = time.perf_counter()
        t0 = time.perf_counter()
        dense_result = self._dense.retrieve(
            query=query.strip(),
            corpus_name=name,
            top_k=dense_depth,
        )
        dense_ms = int((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        try:
            lexical_result = self._lexical.retrieve(
                query=query.strip(),
                corpus_name=name,
                top_k=lexical_depth,
            )
            lexical_ms = int((time.perf_counter() - t1) * 1000)
            lexical_branch_hits = [
                RankedBranchHit(
                    chunk_id=candidate.chunk_id,
                    rank=candidate.rank,
                    score=float(candidate.score),
                )
                for candidate in lexical_result.candidates
            ]
            lexical_by_id = {c.chunk_id: c for c in lexical_result.candidates}
            lexical_index_id = lexical_result.index_id
            lexical_chunk_set = str(lexical_result.metadata.get("chunk_set_id") or "")
        except Exception as exc:
            # Distinguish analyzer zero-term (valid empty) from hard failure.
            message = str(exc)
            if "zero analyzed terms" in message:
                lexical_ms = int((time.perf_counter() - t1) * 1000)
                lexical_branch_hits = []
                lexical_by_id = {}
                lexical_index_id = details["lexical_index_id"] or ""
                lexical_chunk_set = details["lexical_chunk_set_id"] or ""
                if not lexical_index_id:
                    raise HybridRetrievalError(message) from exc
            else:
                raise HybridRetrievalError(f"lexical branch failed: {exc}") from exc

        dense_by_id = {c.chunk_id: c for c in dense_result.candidates}
        dense_branch_hits = [
            RankedBranchHit(
                chunk_id=candidate.chunk_id,
                rank=candidate.rank,
                score=float(candidate.score),
            )
            for candidate in dense_result.candidates
        ]

        dense_chunk_set = str(dense_result.metadata.get("chunk_set_id") or "")
        if lexical_chunk_set and dense_chunk_set and lexical_chunk_set != dense_chunk_set:
            raise HybridRetrievalError(
                "dense and lexical retrieval targeted different chunk sets: "
                f"{dense_chunk_set} != {lexical_chunk_set}"
            )

        t2 = time.perf_counter()
        fused = self._fusion.fuse(dense=dense_branch_hits, lexical=lexical_branch_hits)
        fusion_ms = int((time.perf_counter() - t2) * 1000)
        truncated = fused[:final_k]

        candidates: list[HybridCandidate] = []
        for rank, hit in enumerate(truncated, start=1):
            dense_c = dense_by_id.get(hit.chunk_id)
            lexical_c = lexical_by_id.get(hit.chunk_id)
            source = dense_c or lexical_c
            if source is None:
                raise HybridRetrievalError(f"missing canonical candidate for {hit.chunk_id}")
            candidates.append(
                HybridCandidate(
                    rank=rank,
                    score=float(hit.rrf_score),
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
                    fusion=FusionProvenance(
                        rrf_score=float(hit.rrf_score),
                        dense_rank=hit.dense_rank,
                        dense_score=hit.dense_score,
                        lexical_rank=hit.lexical_rank,
                        lexical_score=hit.lexical_score,
                    ),
                )
            )

        total_ms = int((time.perf_counter() - wall_t0) * 1000)
        return HybridRetrievalResult(
            query=query.strip(),
            method="hybrid",
            top_k=final_k,
            candidates=candidates,
            dense_index_id=dense_result.index_id,
            lexical_index_id=lexical_index_id,
            fusion_config_hash=fus_hash,
            metadata={
                "corpus_id": corpus_id,
                "chunk_set_id": dense_chunk_set or lexical_chunk_set,
                "dense_top_k": dense_depth,
                "lexical_top_k": lexical_depth,
                "rrf_k": fusion_cfg.rrf_k,
                "fusion_contract": fusion_cfg.contract_version,
                "latency_ms": {
                    "dense": dense_ms,
                    "lexical": lexical_ms,
                    "fusion": fusion_ms,
                    "total": total_ms,
                },
            },
        )
