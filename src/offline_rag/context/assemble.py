"""HybridRerankContextAssembler — public Slice 7 orchestrator."""

from __future__ import annotations

import time
from typing import Any

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.chunking.tokenize import TokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import (
    build_context_config_hash,
    build_context_semantic_payload,
)
from offline_rag.context.expand import ContextExpander
from offline_rag.context.status import (
    context_status_for_corpus,
    describe_context_status,
)
from offline_rag.context.store import (
    ChunkStructureStore,
    load_structure_store_for_corpus,
)
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.rerank.retrieve import (
    HybridRerankRetrievalError,
    HybridRerankRetriever,
)


class HybridRerankContextError(RuntimeError):
    pass


class HybridRerankContextAssembler:
    """Wire HybridRerankRetriever + ContextExpander into hybrid-rerank-context."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        retriever: HybridRerankRetriever | None = None,
        store: ChunkStructureStore | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.settings = settings
        self._retriever = retriever or HybridRerankRetriever(settings)
        self._owned_retriever = retriever is None
        self._store = store
        self._token_counter = token_counter

    def close(self) -> None:
        if self._owned_retriever:
            self._retriever.close()

    def _require_ready(self, corpus_name: str) -> None:
        status = context_status_for_corpus(self.settings, corpus_name)
        if status == "READY":
            return
        details = describe_context_status(self.settings, corpus_name)
        reasons = details.get("reasons") or []
        reason_text = "; ".join(str(item) for item in reasons) if reasons else "unknown"
        raise HybridRerankContextError(
            "Context assembly unavailable.\n"
            f"Context status:       {details.get('status')}\n"
            f"Hybrid-rerank status: {details.get('hybrid_rerank_status')}\n"
            f"Context enabled:      {details.get('context_enabled')}\n"
            f"Reasons:              {reason_text}"
        )

    def _counter(self) -> TokenCounter:
        if self._token_counter is not None:
            return self._token_counter
        return make_token_counter(self.settings)

    def _structure(self, corpus_name: str) -> ChunkStructureStore:
        if self._store is not None:
            return self._store
        return load_structure_store_for_corpus(self.settings, corpus_name)

    def assemble(
        self,
        *,
        query: str,
        corpus_name: str = "default",
    ) -> HybridRerankContextResult:
        if not query or not query.strip():
            raise HybridRerankContextError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        self._require_ready(name)

        ctx = self.settings.context
        if not ctx.enabled:
            raise HybridRerankContextError("context.enabled is false")

        counter = self._counter()
        total_t0 = time.perf_counter()

        hybrid_t0 = time.perf_counter()
        try:
            upstream = self._retriever.retrieve(
                query=query,
                corpus_name=name,
                top_k=int(ctx.anchor_k),
            )
        except HybridRerankRetrievalError as exc:
            raise HybridRerankContextError(str(exc)) from exc
        hybrid_ms = int((time.perf_counter() - hybrid_t0) * 1000)

        expand_t0 = time.perf_counter()
        store = self._structure(name)
        expander = ContextExpander(store=store, counter=counter, context=ctx)
        expanded = expander.expand(list(upstream.candidates))
        expand_ms = int((time.perf_counter() - expand_t0) * 1000)
        total_ms = int((time.perf_counter() - total_t0) * 1000)

        semantics = build_context_semantic_payload(self.settings, token_counter=counter)
        cfg_hash = build_context_config_hash(self.settings, token_counter=counter)
        diagnostics = expanded.diagnostics
        if diagnostics is None:
            raise HybridRerankContextError("expander returned no diagnostics")

        upstream_latency = {}
        if isinstance(upstream.metadata, dict):
            raw = upstream.metadata.get("latency_ms")
            if isinstance(raw, dict):
                upstream_latency = dict(raw)

        latency_ms: dict[str, Any] = {
            "hybrid_rerank": hybrid_ms,
            "context_expand": expand_ms,
            "total": total_ms,
            "hybrid_rerank_breakdown": upstream_latency,
        }

        metadata: dict[str, Any] = {
            "corpus_id": upstream.metadata.get("corpus_id") if upstream.metadata else None,
            "chunk_set_id": upstream.metadata.get("chunk_set_id")
            if upstream.metadata
            else store.chunk_set_id,
            "latency_ms": latency_ms,
            "input_k": upstream.metadata.get("input_k") if upstream.metadata else None,
            "input_pool_size": upstream.metadata.get("input_pool_size")
            if upstream.metadata
            else None,
            "input_pool_chunk_ids": upstream.metadata.get("input_pool_chunk_ids")
            if upstream.metadata
            else None,
        }

        return HybridRerankContextResult(
            query=query,
            method="hybrid-rerank-context",
            evidence_units=expanded.evidence_units,
            assembled_text=expanded.assembled_text,
            context_token_count=expanded.context_token_count,
            max_context_tokens=int(ctx.max_context_tokens),
            context_config_hash=cfg_hash,
            effective_context_semantics=semantics,
            anchors=list(upstream.candidates),
            dense_index_id=upstream.dense_index_id,
            lexical_index_id=upstream.lexical_index_id,
            fusion_config_hash=upstream.fusion_config_hash,
            reranker_config_hash=upstream.reranker_config_hash,
            diagnostics=diagnostics,
            metadata=metadata,
        )
