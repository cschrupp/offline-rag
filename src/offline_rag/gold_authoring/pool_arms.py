"""Historical six-arm retrieval for candidate-pooling-v1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from offline_rag.config.models import (
    AppSettings,
    DenseQueryTextSettings,
    DenseSearchableUnitsSettings,
)
from offline_rag.core.ids import EXCLUDE_HEADING_ONLY_V1, MODEL_QUERY_PROMPT_V1
from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.embedder import make_embedder
from offline_rag.dense.persistence import try_load_index_manifest
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.resolver import resolve_child_chunk
from offline_rag.dense.searchable_units import EXCLUDE_HEADING_ONLY_STRATEGY
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
from offline_rag.gold_authoring.pool_preflight import ResolvedPoolingArtifacts
from offline_rag.gold_authoring.pooling_models import PoolFailureReason, RetrievalHit
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
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.retriever = retriever


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


def _settings_query_prompt(settings: AppSettings) -> AppSettings:
    return settings.model_copy(
        update={
            "dense": settings.dense.model_copy(
                update={
                    "query_text": DenseQueryTextSettings(
                        strategy="model_query_prompt",
                        contract_version=MODEL_QUERY_PROMPT_V1,
                    )
                }
            )
        }
    )


def _settings_arm_h(settings: AppSettings) -> AppSettings:
    qp = _settings_query_prompt(settings)
    return qp.model_copy(
        update={
            "indexing": qp.indexing.model_copy(
                update={
                    "searchable_units": DenseSearchableUnitsSettings(
                        strategy=EXCLUDE_HEADING_ONLY_STRATEGY,
                        contract_version=EXCLUDE_HEADING_ONLY_V1,
                    )
                }
            )
        }
    )


class HistoricalPoolArmExecutor:
    """Execute all six pooling arms against historically bound artifacts."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        reranker: Reranker | None = None,
    ) -> None:
        self.settings = settings
        self._reranker = reranker
        self._lexical_backend: LocalInvertedIndexBackend | None = None
        self._qdrant: QdrantLocalBackend | None = None

    def close(self) -> None:
        if self._lexical_backend is not None:
            self._lexical_backend.close()
            self._lexical_backend = None
        if self._qdrant is not None:
            self._qdrant.close()
            self._qdrant = None

    def _lexical_hits(
        self, *, query: str, index_id: str, top_k: int
    ) -> list[ArmHit]:
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
                f"dense index missing: {index_id}",
                reason=PoolFailureReason.RETRIEVER_ERROR,
            )
        if self._qdrant is None:
            self._qdrant = QdrantLocalBackend(settings.paths.qdrant_storage)
        embedder = make_embedder(settings)
        vector = embedder.embed_query(query.strip())
        hits = self._qdrant.search(
            manifest.collection_name, query_vector=vector, top_k=top_k
        )
        out: list[ArmHit] = []
        for i, hit in enumerate(hits, start=1):
            payload = hit.payload if isinstance(hit.payload, dict) else {}
            chunk_id = str(payload.get("chunk_id") or "")
            chunk_artifact_id = str(payload.get("chunk_artifact_id") or "")
            if not chunk_id or not chunk_artifact_id:
                raise ArmExecutionError(
                    "dense search hit missing chunk identity",
                    reason=PoolFailureReason.CANDIDATE_IDENTITY_INVALID,
                )
            chunk = resolve_child_chunk(
                settings.paths.chunks,
                chunk_artifact_id=chunk_artifact_id,
                chunk_id=chunk_id,
            )
            expected_point = dense_point_uuid(chunk_id)
            if hit.point_id != expected_point:
                raise ArmExecutionError(
                    f"point ID mismatch for {chunk_id}",
                    reason=PoolFailureReason.CANDIDATE_IDENTITY_INVALID,
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
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.LEXICAL_RETRIEVAL_FAILED,
                retriever=RETRIEVER_LEXICAL_PLAIN_V1,
            ) from exc

        try:
            results[RETRIEVER_DENSE_PLAIN_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_baseline_index_id,
                top_k=depths[RETRIEVER_DENSE_PLAIN_V1],
                settings=self.settings,
            )
        except ArmExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.DENSE_BASELINE_FAILED,
                retriever=RETRIEVER_DENSE_PLAIN_V1,
            ) from exc

        try:
            results[RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_baseline_index_id,
                top_k=depths[RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1],
                settings=_settings_query_prompt(self.settings),
            )
        except ArmExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.DENSE_QUERY_PROMPT_FAILED,
                retriever=RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
            ) from exc

        try:
            results[RETRIEVER_DENSE_ARM_H_V1] = self._dense_hits(
                query=query,
                index_id=artifacts.dense_arm_h_index_id,
                top_k=depths[RETRIEVER_DENSE_ARM_H_V1],
                settings=_settings_arm_h(self.settings),
            )
        except ArmExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.DENSE_ARM_H_FAILED,
                retriever=RETRIEVER_DENSE_ARM_H_V1,
            ) from exc

        try:
            dense_branch = [
                RankedBranchHit(chunk_id=h.chunk_id, rank=h.rank, score=float(h.score or 0.0))
                for h in results[RETRIEVER_DENSE_PLAIN_V1]
            ]
            lex_branch = [
                RankedBranchHit(chunk_id=h.chunk_id, rank=h.rank, score=float(h.score or 0.0))
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
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.HYBRID_RRF_FAILED,
                retriever=RETRIEVER_HYBRID_RRF_V1,
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
                except Exception as exc:  # noqa: BLE001
                    raise ArmExecutionError(
                        f"missing passage text for rerank chunk {hit.chunk_id}: {exc}",
                        reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                        retriever=RETRIEVER_HYBRID_RERANK_V1,
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
        except ArmExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ArmExecutionError(
                str(exc),
                reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                retriever=RETRIEVER_HYBRID_RERANK_V1,
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
