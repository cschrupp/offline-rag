"""Lexical retrieval service over the active Slice 4 index."""

from __future__ import annotations

from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.config.models import AppSettings
from offline_rag.dense.resolver import resolve_child_chunk
from offline_rag.domain.indexing import LexicalCandidate, LexicalRetrievalResult
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer
from offline_rag.lexical.backend import (
    LexicalIndexBackend,
    LexicalSearchHit,
    LocalInvertedIndexBackend,
)
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_state,
)
from offline_rag.lexical.pipeline import make_lexical_analyzer
from offline_rag.lexical.status import lexical_indexing_status_for_corpus


class LexicalRetrievalError(RuntimeError):
    pass


class LexicalRetriever:
    """Project-owned lexical-only retrieval over an active current index."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        backend: LexicalIndexBackend | None = None,
        analyzer: TechnicalLexicalAnalyzer | None = None,
    ) -> None:
        self.settings = settings
        self._backend = backend
        self._owned_backend = backend is None
        self._analyzer = analyzer
        self._open_index_id: str | None = None

    def close(self) -> None:
        if self._owned_backend and self._backend is not None:
            close = getattr(self._backend, "close", None)
            if callable(close):
                close()
            self._backend = None
        self._open_index_id = None

    def _require_current(self, corpus_name: str) -> tuple[str, str]:
        status = lexical_indexing_status_for_corpus(self.settings, corpus_name)
        if status == "CORPUS_NOT_INITIALIZED":
            raise LexicalRetrievalError(
                f"corpus '{corpus_name}' is not initialized; run offline-rag ingest first"
            )
        if status == "CHUNKS_STALE":
            raise LexicalRetrievalError(
                "Lexical index cannot be searched: chunking is stale.\n"
                f"Run:\noffline-rag chunk --corpus {corpus_name}"
            )
        if status == "NOT_INDEXED":
            raise LexicalRetrievalError(
                "Lexical index is not initialized.\n"
                f"Run:\noffline-rag index lexical --corpus {corpus_name}"
            )
        if status in {"LEXICAL_INDEX_STALE", "LEXICAL_CONFIG_STALE"}:
            lexical_state = load_lexical_index_state(
                lexical_index_state_path(self.settings.paths.corpora, corpus_name)
            )
            chunk_state = load_chunk_state(chunk_state_path(self.settings.paths.corpora, corpus_name))
            raise LexicalRetrievalError(
                "Lexical index is stale.\n"
                f"Active chunk set:  {chunk_state.current_chunk_set_id}\n"
                f"Indexed chunk set: {lexical_state.source_chunk_set_id}\n"
                f"Status: {status}\n"
                f"Run:\noffline-rag index lexical --corpus {corpus_name}"
            )
        if status != "CURRENT":
            raise LexicalRetrievalError(f"Lexical index is not searchable (status={status})")

        lexical_state = load_lexical_index_state(
            lexical_index_state_path(self.settings.paths.corpora, corpus_name)
        )
        return lexical_state.current_lexical_index_id, lexical_state.source_chunk_set_id

    def retrieve(
        self,
        *,
        query: str,
        corpus_name: str = "default",
        top_k: int | None = None,
    ) -> LexicalRetrievalResult:
        if not query or not query.strip():
            raise LexicalRetrievalError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        k = int(top_k if top_k is not None else self.settings.lexical.top_k)
        if k < 1:
            raise LexicalRetrievalError("top_k must be >= 1")
        if k > 1000:
            raise LexicalRetrievalError("top_k exceeds safety limit (1000)")

        corpus_path = corpus_state_path(self.settings.paths.corpora, name)
        if not corpus_path.exists():
            raise LexicalRetrievalError(f"corpus '{name}' is not initialized")
        load_corpus_state(corpus_path)

        index_id, chunk_set_id = self._require_current(name)
        analyzer = self._analyzer or make_lexical_analyzer(self.settings)
        query_terms = analyzer.analyze_query_terms(query.strip())
        if not query_terms:
            raise LexicalRetrievalError("query produced zero analyzed terms")

        if self._backend is None:
            self._backend = LocalInvertedIndexBackend(self.settings.paths.lexical_indexes)
        if self._open_index_id != index_id:
            self._backend.open(index_id)
            self._open_index_id = index_id

        hits = self._backend.search(query_terms, top_k=k)
        candidates = [
            self._hit_to_candidate(hit, rank=rank) for rank, hit in enumerate(hits, start=1)
        ]
        return LexicalRetrievalResult(
            query=query.strip(),
            method="lexical",
            index_id=index_id,
            top_k=k,
            candidates=candidates,
            metadata={
                "chunk_set_id": chunk_set_id,
                "lexical_config_hash": build_lexical_config_hash(self.settings),
                "query_terms": query_terms,
            },
        )

    def _hit_to_candidate(self, hit: LexicalSearchHit, *, rank: int) -> LexicalCandidate:
        chunk_artifact_id = hit.chunk_artifact_id
        if not chunk_artifact_id:
            raise LexicalRetrievalError(
                f"search hit missing chunk_artifact_id for {hit.chunk_id}"
            )
        chunk = resolve_child_chunk(
            self.settings.paths.chunks,
            chunk_artifact_id=chunk_artifact_id,
            chunk_id=hit.chunk_id,
        )
        return LexicalCandidate(
            rank=rank,
            score=float(hit.score),
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            parent_chunk_id=chunk.parent_chunk_id,
            previous_chunk_id=chunk.previous_chunk_id,
            next_chunk_id=chunk.next_chunk_id,
            text=chunk.text,
            section_path=list(chunk.section_path),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            line_start=chunk.line_start,
            line_end=chunk.line_end,
            token_count=chunk.token_count,
            chunk_artifact_id=chunk_artifact_id,
        )
