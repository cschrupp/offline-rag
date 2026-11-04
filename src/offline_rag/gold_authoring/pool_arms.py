"""Historical six-arm retrieval for candidate-pooling-v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.embedder import EmbedderError, make_embedder
from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntimeError
from offline_rag.dense.failure import CudaMemoryExhaustedError
from offline_rag.dense.onnx_embedder import OnnxEmbedderError
from offline_rag.dense.persistence import try_load_index_manifest
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.resolver import resolve_child_chunk
from offline_rag.gold_authoring.chunk_access import resolve_seed_text_from_chunk_set
from offline_rag.gold_authoring.contracts import (
    POOLING_DEPTHS,
    RETRIEVER_DENSE_ARM_H_V1,
    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
    RETRIEVER_DENSE_PLAIN_V1,
    RETRIEVER_HYBRID_RERANK_V1,
    RETRIEVER_HYBRID_RRF_V1,
    RETRIEVER_LEXICAL_PLAIN_V1,
)
from offline_rag.gold_authoring.pool_contract import (
    settings_arm_h,
    settings_query_prompt,
)
from offline_rag.gold_authoring.pool_preflight import ResolvedPoolingArtifacts
from offline_rag.gold_authoring.pooling_models import (
    PoolExceptionCategory,
    PoolFailureReason,
    PoolFailureStage,
    RetrievalHit,
)
from offline_rag.hybrid.fusion import RankedBranchHit, ReciprocalRankFusion
from offline_rag.lexical.backend import LocalInvertedIndexBackend
from offline_rag.lexical.pipeline import make_lexical_analyzer
from offline_rag.rerank.cross_encoder import CrossEncoderReranker
from offline_rag.rerank.fake import FakeReranker
from offline_rag.rerank.protocol import Reranker, RerankerPair


class ArmExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reason: PoolFailureReason,
        retriever: str | None = None,
        stage: PoolFailureStage = PoolFailureStage.RETRIEVER_EXECUTION,
        exception_category: PoolExceptionCategory | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.retriever = retriever
        self.stage = stage
        self.exception_category = exception_category


def _safe_exception_category(exc: BaseException) -> PoolExceptionCategory:
    """Map internal errors to bounded diagnostic categories, never raw text."""
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, CudaMemoryExhaustedError):
            return PoolExceptionCategory.CUDA_MEMORY_EXHAUSTED
        if isinstance(
            current,
            (EmbedderError, OnnxEmbedderError, QualifiedEmbeddingRuntimeError),
        ):
            return PoolExceptionCategory.EMBEDDING_ERROR
        if isinstance(current, FileNotFoundError):
            return PoolExceptionCategory.ARTIFACT_MISSING
        if isinstance(current, (ValueError, TypeError)):
            return PoolExceptionCategory.INVALID_INPUT
        if isinstance(current, OSError):
            return PoolExceptionCategory.STORAGE_ERROR
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return PoolExceptionCategory.UNEXPECTED_ERROR


def _bind_arm_failure(
    exc: ArmExecutionError,
    *,
    retriever: str,
    default_reason: PoolFailureReason,
    safe_message: str,
) -> ArmExecutionError:
    """Attach the arm identity while retaining bounded diagnostic fields."""
    reason = (
        default_reason
        if exc.reason is PoolFailureReason.RETRIEVER_ERROR
        else exc.reason
    )
    return ArmExecutionError(
        safe_message,
        reason=reason,
        retriever=retriever,
        stage=exc.stage,
        exception_category=exc.exception_category,
    )


@dataclass(frozen=True, slots=True)
class ArmHit:
    chunk_id: str
    rank: int
    score: float | None
    document_id: str | None = None
    text: str | None = None
    section_path: tuple[str, ...] = ()


class PoolArmExecutor(Protocol):
    def execute_all(
        self,
        *,
        query: str,
        artifacts: ResolvedPoolingArtifacts,
    ) -> dict[str, list[RetrievalHit]]:
        """Return hits keyed by retriever id (1-based ranks)."""


class HistoricalPoolArmExecutor:
    """Execute all six pooling arms against historically bound artifacts."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        reranker: Reranker | None = None,
        qdrant: QdrantLocalBackend | None = None,
    ) -> None:
        self.settings = settings
        self._reranker = reranker
        self._lexical_backend: LocalInvertedIndexBackend | None = None
        # Product callers may inject the process-owned Qdrant Local backend so
        # pooling does not open a second exclusive storage client.
        self._qdrant: QdrantLocalBackend | None = qdrant
        self._owns_qdrant = qdrant is None

    def close(self) -> None:
        if self._lexical_backend is not None:
            self._lexical_backend.close()
            self._lexical_backend = None
        if self._owns_qdrant and self._qdrant is not None:
            self._qdrant.close()
            self._qdrant = None

    def _lexical_hits(self, *, query: str, index_id: str, top_k: int) -> list[ArmHit]:
        if self._lexical_backend is None:
            self._lexical_backend = LocalInvertedIndexBackend(
                self.settings.paths.lexical_indexes
            )
        self._lexical_backend.open(index_id)
        terms = make_lexical_analyzer(self.settings).analyze_query_terms(query)
        hits = self._lexical_backend.search(terms, top_k=top_k)
        out: list[ArmHit] = []
        for i, hit in enumerate(hits, start=1):
            out.append(
                ArmHit(
                    chunk_id=hit.chunk_id,
                    rank=i,
                    score=float(hit.score),
                    document_id=getattr(hit, "document_id", None),
                    text=getattr(hit, "text", None),
                    section_path=tuple(getattr(hit, "section_path", ()) or ()),
                )
            )
        return out

    def _dense_hits(
        self,
        *,
        query: str,
        index_id: str,
        top_k: int,
        settings: AppSettings,
    ) -> list[ArmHit]:
        manifest = try_load_index_manifest(settings.paths.index_manifests, index_id)
        if manifest is None:
            raise ArmExecutionError(
                "dense index manifest is missing",
                reason=PoolFailureReason.RETRIEVER_ERROR,
                stage=PoolFailureStage.INDEX_PREFLIGHT,
                exception_category=PoolExceptionCategory.ARTIFACT_MISSING,
            )
        if self._qdrant is None:
            try:
                self._qdrant = QdrantLocalBackend(settings.paths.qdrant_storage)
            except Exception as exc:
                raise ArmExecutionError(
                    "dense vector storage could not be opened",
                    reason=PoolFailureReason.RETRIEVER_ERROR,
                    stage=PoolFailureStage.VECTOR_SEARCH,
                    exception_category=_safe_exception_category(exc),
                ) from exc
        try:
            embedder = make_embedder(settings)
        except Exception as exc:
            raise ArmExecutionError(
                "dense embedding runtime initialization failed",
                reason=PoolFailureReason.RETRIEVER_ERROR,
                stage=PoolFailureStage.EMBEDDING_RUNTIME_INITIALIZATION,
                exception_category=_safe_exception_category(exc),
            ) from exc
        try:
            vector = embedder.embed_query(query.strip())
        except Exception as exc:
            raise ArmExecutionError(
                "dense query embedding failed",
                reason=PoolFailureReason.RETRIEVER_ERROR,
                stage=PoolFailureStage.QUERY_EMBEDDING,
                exception_category=_safe_exception_category(exc),
            ) from exc
        try:
            hits = self._qdrant.search(
                manifest.collection_name, query_vector=vector, top_k=top_k
            )
        except Exception as exc:
            raise ArmExecutionError(
                "dense vector search failed",
                reason=PoolFailureReason.RETRIEVER_ERROR,
                stage=PoolFailureStage.VECTOR_SEARCH,
                exception_category=_safe_exception_category(exc),
            ) from exc
        out: list[ArmHit] = []
        for i, hit in enumerate(hits, start=1):
            payload = hit.payload if isinstance(hit.payload, dict) else {}
            chunk_id = str(payload.get("chunk_id") or "")
            chunk_artifact_id = str(payload.get("chunk_artifact_id") or "")
            if not chunk_id or not chunk_artifact_id:
                raise ArmExecutionError(
                    "dense search hit missing chunk identity",
                    reason=PoolFailureReason.CANDIDATE_IDENTITY_INVALID,
                    stage=PoolFailureStage.CANDIDATE_IDENTITY,
                    exception_category=PoolExceptionCategory.INVALID_CANDIDATE,
                )
            chunk = resolve_child_chunk(
                settings.paths.chunks,
                chunk_artifact_id=chunk_artifact_id,
                chunk_id=chunk_id,
            )
            expected_point = dense_point_uuid(chunk_id)
            if hit.point_id != expected_point:
                raise ArmExecutionError(
                    "dense search point identity does not match the chunk",
                    reason=PoolFailureReason.CANDIDATE_IDENTITY_INVALID,
                    stage=PoolFailureStage.CANDIDATE_IDENTITY,
                    exception_category=PoolExceptionCategory.INVALID_CANDIDATE,
                )
            out.append(
                ArmHit(
                    chunk_id=chunk.chunk_id,
                    rank=i,
                    score=float(hit.score),
                    document_id=chunk.document_id,
                    text=chunk.text,
                    section_path=tuple(chunk.section_path),
                )
            )
        return out

    def _get_reranker(self) -> Reranker:
        if self._reranker is not None:
            return self._reranker
        if self.settings.reranker.implementation == "fake":
            self._reranker = FakeReranker()
        else:
            self._reranker = CrossEncoderReranker.from_settings(self.settings)
        return self._reranker

    def execute_all(
        self,
        *,
        query: str,
        artifacts: ResolvedPoolingArtifacts,
    ) -> dict[str, list[RetrievalHit]]:
        depths = POOLING_DEPTHS
        results: dict[str, list[ArmHit]] = {}

        try:
            results[RETRIEVER_LEXICAL_PLAIN_V1] = self._lexical_hits(
                query=query,
                index_id=artifacts.lexical_index_id,
                top_k=depths[RETRIEVER_LEXICAL_PLAIN_V1],
            )
        except Exception as exc:
            raise ArmExecutionError(
                "lexical retrieval failed",
                reason=PoolFailureReason.LEXICAL_RETRIEVAL_FAILED,
                retriever=RETRIEVER_LEXICAL_PLAIN_V1,
                stage=PoolFailureStage.RETRIEVER_EXECUTION,
                exception_category=_safe_exception_category(exc),
            ) from exc

        try:
            results[RETRIEVER_DENSE_PLAIN_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_baseline_index_id,
                top_k=depths[RETRIEVER_DENSE_PLAIN_V1],
                settings=self.settings,
            )
        except ArmExecutionError as exc:
            raise _bind_arm_failure(
                exc,
                retriever=RETRIEVER_DENSE_PLAIN_V1,
                default_reason=PoolFailureReason.DENSE_BASELINE_FAILED,
                safe_message="dense baseline retrieval failed",
            ) from exc
        except Exception as exc:
            raise ArmExecutionError(
                "dense baseline retrieval failed",
                reason=PoolFailureReason.DENSE_BASELINE_FAILED,
                retriever=RETRIEVER_DENSE_PLAIN_V1,
                stage=PoolFailureStage.RETRIEVER_EXECUTION,
                exception_category=_safe_exception_category(exc),
            ) from exc

        try:
            results[RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_baseline_index_id,
                top_k=depths[RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1],
                settings=settings_query_prompt(self.settings),
            )
        except ArmExecutionError as exc:
            raise _bind_arm_failure(
                exc,
                retriever=RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
                default_reason=PoolFailureReason.DENSE_QUERY_PROMPT_FAILED,
                safe_message="dense query-prompt retrieval failed",
            ) from exc
        except Exception as exc:
            raise ArmExecutionError(
                "dense query-prompt retrieval failed",
                reason=PoolFailureReason.DENSE_QUERY_PROMPT_FAILED,
                retriever=RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
                stage=PoolFailureStage.RETRIEVER_EXECUTION,
                exception_category=_safe_exception_category(exc),
            ) from exc

        try:
            results[RETRIEVER_DENSE_ARM_H_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_arm_h_index_id,
                top_k=depths[RETRIEVER_DENSE_ARM_H_V1],
                settings=settings_arm_h(self.settings),
            )
        except ArmExecutionError as exc:
            raise _bind_arm_failure(
                exc,
                retriever=RETRIEVER_DENSE_ARM_H_V1,
                default_reason=PoolFailureReason.DENSE_ARM_H_FAILED,
                safe_message="dense Arm H retrieval failed",
            ) from exc
        except Exception as exc:
            raise ArmExecutionError(
                "dense Arm H retrieval failed",
                reason=PoolFailureReason.DENSE_ARM_H_FAILED,
                retriever=RETRIEVER_DENSE_ARM_H_V1,
                stage=PoolFailureStage.RETRIEVER_EXECUTION,
                exception_category=_safe_exception_category(exc),
            ) from exc

        try:
            dense_branch = [
                RankedBranchHit(
                    chunk_id=h.chunk_id, rank=h.rank, score=float(h.score or 0.0)
                )
                for h in results[RETRIEVER_DENSE_PLAIN_V1]
            ]
            lex_branch = [
                RankedBranchHit(
                    chunk_id=h.chunk_id, rank=h.rank, score=float(h.score or 0.0)
                )
                for h in results[RETRIEVER_LEXICAL_PLAIN_V1]
            ]
            fusion = ReciprocalRankFusion(rrf_k=int(self.settings.fusion.rrf_k))
            fused = fusion.fuse(dense=dense_branch, lexical=lex_branch)
            hybrid_top = fused[: depths[RETRIEVER_HYBRID_RRF_V1]]
            results[RETRIEVER_HYBRID_RRF_V1] = [
                ArmHit(
                    chunk_id=item.chunk_id,
                    rank=i,
                    score=float(item.rrf_score),
                )
                for i, item in enumerate(hybrid_top, start=1)
            ]
        except Exception as exc:
            raise ArmExecutionError(
                "hybrid reciprocal-rank fusion failed",
                reason=PoolFailureReason.HYBRID_RRF_FAILED,
                retriever=RETRIEVER_HYBRID_RRF_V1,
                stage=PoolFailureStage.HYBRID_FUSION,
                exception_category=_safe_exception_category(exc),
            ) from exc

        try:
            # Rerank over hybrid depth-50 pool; emit top 20.
            pool = results[RETRIEVER_HYBRID_RRF_V1]
            text_by_id: dict[str, str] = {}
            for arm_hits in results.values():
                for hit in arm_hits:
                    if hit.text and hit.chunk_id not in text_by_id:
                        text_by_id[hit.chunk_id] = hit.text
            for hit in pool:
                if hit.chunk_id in text_by_id:
                    continue
                try:
                    text_by_id[hit.chunk_id] = resolve_seed_text_from_chunk_set(
                        self.settings,
                        chunk_set_id=artifacts.chunk_set_id,
                        chunk_id=hit.chunk_id,
                    )
                except Exception as exc:
                    raise ArmExecutionError(
                        "rerank candidate passage text is unavailable",
                        reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                        retriever=RETRIEVER_HYBRID_RERANK_V1,
                        stage=PoolFailureStage.CANDIDATE_PROVENANCE,
                        exception_category=_safe_exception_category(exc),
                    ) from exc
            pairs = [
                RerankerPair(
                    chunk_id=h.chunk_id,
                    query_text=query,
                    passage_text=text_by_id[h.chunk_id],
                )
                for h in pool
            ]
            scores = self._get_reranker().score_pairs(pairs)
            scored = list(zip(pool, scores, strict=True))
            scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
            top_n = scored[: depths[RETRIEVER_HYBRID_RERANK_V1]]
            results[RETRIEVER_HYBRID_RERANK_V1] = [
                ArmHit(
                    chunk_id=hit.chunk_id,
                    rank=i,
                    score=float(score),
                    document_id=hit.document_id,
                    text=text_by_id.get(hit.chunk_id),
                    section_path=hit.section_path,
                )
                for i, (hit, score) in enumerate(top_n, start=1)
            ]
        except ArmExecutionError as exc:
            raise _bind_arm_failure(
                exc,
                retriever=RETRIEVER_HYBRID_RERANK_V1,
                default_reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                safe_message="hybrid reranking failed",
            ) from exc
        except Exception as exc:
            raise ArmExecutionError(
                "hybrid reranking failed",
                reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                retriever=RETRIEVER_HYBRID_RERANK_V1,
                stage=PoolFailureStage.RERANK,
                exception_category=_safe_exception_category(exc),
            ) from exc

        return {
            arm: [
                RetrievalHit(
                    retriever=arm,
                    chunk_id=h.chunk_id,
                    rank=h.rank,
                    score=h.score,
                )
                for h in arm_hits
            ]
            for arm, arm_hits in results.items()
        }
