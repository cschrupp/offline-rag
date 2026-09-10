"""Dense retrieval service over the active Slice 3 index."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.backend import DenseIndexBackend, DenseSearchHit
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import Embedder, make_embedder
from offline_rag.dense.persistence import (
    index_state_path,
    load_index_manifest,
    load_index_state,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.resolver import resolve_child_chunk
from offline_rag.dense.status import indexing_status_for_corpus
from offline_rag.domain.indexing import DenseCandidate, DenseRetrievalResult
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state


class DenseRetrievalError(RuntimeError):
    pass


class DenseRetriever:
    """Project-owned dense-only retrieval over an active current index."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        embedder: Embedder | None = None,
        backend: DenseIndexBackend | None = None,
    ) -> None:
        self.settings = settings
        self._embedder = embedder
        self._backend = backend
        self._owned_backend = backend is None

    def close(self) -> None:
        if self._owned_backend and self._backend is not None:
            close = getattr(self._backend, "close", None)
            if callable(close):
                close()
            self._backend = None

    def _require_current(self, corpus_name: str) -> tuple[str, str, str]:
        status = indexing_status_for_corpus(self.settings, corpus_name)
        if status == "CORPUS_NOT_INITIALIZED":
            raise DenseRetrievalError(
                f"corpus '{corpus_name}' is not initialized; run offline-rag ingest first"
            )
        if status == "CHUNKS_STALE":
            raise DenseRetrievalError(
                "Dense index cannot be searched: chunking is stale.\n"
                f"Run:\noffline-rag chunk --corpus {corpus_name}"
            )
        if status == "NOT_INDEXED":
            raise DenseRetrievalError(
                "Dense index is not initialized.\n"
                f"Run:\noffline-rag index --corpus {corpus_name}"
            )
        if status in {"INDEX_STALE", "INDEX_CONFIG_STALE"}:
            index_state = load_index_state(index_state_path(self.settings.paths.corpora, corpus_name))
            chunk_state = load_chunk_state(chunk_state_path(self.settings.paths.corpora, corpus_name))
            raise DenseRetrievalError(
                "Dense index is stale.\n"
                f"Active chunk set:  {chunk_state.current_chunk_set_id}\n"
                f"Indexed chunk set: {index_state.source_chunk_set_id}\n"
                f"Status: {status}\n"
                f"Run:\noffline-rag index --corpus {corpus_name}"
            )
        if status != "CURRENT":
            raise DenseRetrievalError(f"Dense index is not searchable (status={status})")

        index_state = load_index_state(index_state_path(self.settings.paths.corpora, corpus_name))
        manifest = load_index_manifest(
            self.settings.paths.index_manifests / Path(index_state.current_index_manifest).name
        )
        return index_state.current_index_id, manifest.collection_name, index_state.source_chunk_set_id

    def retrieve(
        self,
        *,
        query: str,
        corpus_name: str = "default",
        top_k: int | None = None,
    ) -> DenseRetrievalResult:
        if not query or not query.strip():
            raise DenseRetrievalError("query must be non-empty")
        name = validate_corpus_name(corpus_name)
        k = int(top_k if top_k is not None else self.settings.dense.top_k)
        if k < 1:
            raise DenseRetrievalError("top_k must be >= 1")
        if k > 1000:
            raise DenseRetrievalError("top_k exceeds safety limit (1000)")

        corpus_path = corpus_state_path(self.settings.paths.corpora, name)
        if not corpus_path.exists():
            raise DenseRetrievalError(f"corpus '{name}' is not initialized")
        load_corpus_state(corpus_path)

        index_id, collection_name, chunk_set_id = self._require_current(name)
        embedder = self._embedder or make_embedder(self.settings)
        if self._backend is None:
            self._backend = QdrantLocalBackend(self.settings.paths.qdrant_storage)

        query_vector = embedder.embed_query(query.strip())
        hits = self._backend.search(collection_name, query_vector=query_vector, top_k=k)
        hits = sorted(
            hits,
            key=lambda hit: (-hit.score, str(hit.payload.get("chunk_id") or "")),
        )
        candidates = [self._hit_to_candidate(hit, rank=rank) for rank, hit in enumerate(hits, start=1)]
        return DenseRetrievalResult(
            query=query.strip(),
            index_id=index_id,
            top_k=k,
            candidates=candidates,
            metadata={
                "chunk_set_id": chunk_set_id,
                "collection_name": collection_name,
                "embedding_config_hash": build_embedding_config_hash(self.settings),
                "index_config_hash": build_index_config_hash(self.settings),
            },
        )

    def _hit_to_candidate(self, hit: DenseSearchHit, *, rank: int) -> DenseCandidate:
        payload = hit.payload
        chunk_id = str(payload.get("chunk_id") or "")
        chunk_artifact_id = str(payload.get("chunk_artifact_id") or "")
        if not chunk_id or not chunk_artifact_id:
            raise DenseRetrievalError("search hit missing chunk identity payload")
        chunk = resolve_child_chunk(
            self.settings.paths.chunks,
            chunk_artifact_id=chunk_artifact_id,
            chunk_id=chunk_id,
        )
        expected_point = dense_point_uuid(chunk_id)
        if hit.point_id != expected_point:
            raise DenseRetrievalError(
                f"point ID mismatch for {chunk_id}: {hit.point_id} != {expected_point}"
            )
        return DenseCandidate(
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
            point_id=hit.point_id,
            embedding_id=str(payload.get("embedding_id") or "") or None,
            chunk_artifact_id=chunk_artifact_id,
        )
