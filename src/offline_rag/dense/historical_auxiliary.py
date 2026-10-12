"""Immutable historical dense-index materializer (no CURRENT / index_state writes)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    DENSE_INDEX_CONTRACT_VERSION,
    dense_collection_name,
    dense_index_id,
)
from offline_rag.core.progress import ProgressReporter, report_progress
from offline_rag.dense.backend import DenseIndexBackend, DensePointRecord
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import Embedder
from offline_rag.dense.persistence import (
    index_manifest_path,
    try_load_index_manifest,
    write_index_manifest,
)
from offline_rag.dense.pipeline import (
    IndexingError,
    _ensure_embeddings,
    _requires_document_titles,
    _validate_collection,
    _validate_point_ids,
    child_jobs_from_chunk_set,
    make_embedding_text_builder,
)
from offline_rag.dense.points import build_dense_point
from offline_rag.dense.searchable_units import (
    DenseSearchableUnitsError,
    filter_dense_searchable_children,
)
from offline_rag.domain.indexing import DenseIndexManifest
from offline_rag.ingestion.persistence import load_corpus_manifest
from offline_rag.retrieval.ranking_text import (
    RankingTextError,
    resolve_document_titles_from_source_names,
)


class HistoricalAuxiliaryError(RuntimeError):
    """Historical auxiliary dense index materialization failure."""

    def __init__(self, message: str, *, subcause: str) -> None:
        super().__init__(message)
        self.subcause = subcause


@dataclass(frozen=True, slots=True)
class HistoricalAuxiliaryBuildResult:
    manifest: DenseIndexManifest
    embeddings_generated: int
    embeddings_reused: int
    reused_existing: bool


def _manifest_fully_compatible(
    existing: DenseIndexManifest,
    *,
    index_id: str,
    corpus_id: str,
    chunk_set_id: str,
    emb_cfg_hash: str,
    idx_cfg_hash: str,
    collection_name: str,
    children_total: int,
    embedder: Embedder,
    settings: AppSettings,
) -> bool:
    """Match write_index_manifest immutable compatibility fields exactly."""
    return (
        existing.index_id == index_id
        and existing.corpus_id == corpus_id
        and existing.chunk_set_id == chunk_set_id
        and existing.embedding_config_hash == emb_cfg_hash
        and existing.index_config_hash == idx_cfg_hash
        and existing.collection_name == collection_name
        and existing.expected_child_count == children_total
        and existing.indexed_child_count == children_total
        and existing.embedding_model_id == embedder.model_id
        and existing.embedding_model_revision == embedder.model_revision
        and existing.embedding_dimension == embedder.dimension
        and existing.normalize == embedder.normalize
        and existing.similarity_metric == settings.indexing.metric
    )


def build_historical_auxiliary_dense_index(
    *,
    settings: AppSettings,
    corpus_id: str,
    corpus_name: str,
    chunk_set_id: str,
    chunk_manifest_name: str,
    embedder: Embedder,
    backend: DenseIndexBackend,
    on_progress: ProgressReporter | None = None,
) -> HistoricalAuxiliaryBuildResult:
    """Materialize an immutable dense index for an exact historical ChunkSet.

    Does not read CURRENT corpus/chunk state and never writes index_state.json or
    publication CURRENT pointers. Caller supplies process-owned embedder/backend.
    """
    del corpus_name  # identity is corpus_id + chunk_set_id; name is for callers only
    emb_cfg_hash = build_embedding_config_hash(settings)
    idx_cfg_hash = build_index_config_hash(settings)
    index_id = dense_index_id(chunk_set_id, idx_cfg_hash)
    collection_name = dense_collection_name(index_id)

    try:
        jobs, documents_total = child_jobs_from_chunk_set(
            settings=settings,
            chunk_set_id=chunk_set_id,
            chunk_manifest_name=chunk_manifest_name,
            expected_corpus_id=corpus_id,
        )
    except IndexingError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="historical_chunk_set_missing"
        ) from exc

    chunk_set_child_count = len(jobs)
    try:
        eligible_jobs, excluded_jobs = filter_dense_searchable_children(jobs, settings)
    except DenseSearchableUnitsError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="arm_h_build_failed"
        ) from exc

    jobs = eligible_jobs
    children_total = len(jobs)
    excluded_heading_only_count = len(excluded_jobs)
    if children_total < 1:
        raise HistoricalAuxiliaryError(
            "dense searchable-unit policy excluded all children; "
            "refusing empty auxiliary dense index",
            subcause="arm_h_build_failed",
        )

    # Manifest-path gate BEFORE any Qdrant mutation.
    # absent → may materialize; present+compatible+collection ok → reuse;
    # present+corrupt / any immutable conflict → fail closed (no mutation);
    # present+fully compatible but collection incomplete → fail closed.
    manifest_path = index_manifest_path(settings.paths.index_manifests, index_id)
    if manifest_path.exists():
        existing_manifest = try_load_index_manifest(
            settings.paths.index_manifests, index_id
        )
        if existing_manifest is None:
            raise HistoricalAuxiliaryError(
                f"Arm-H auxiliary manifest corrupt for index_id={index_id}; "
                "refusing mutation",
                subcause="arm_h_manifest_conflict",
            )
        compatible = _manifest_fully_compatible(
            existing_manifest,
            index_id=index_id,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            emb_cfg_hash=emb_cfg_hash,
            idx_cfg_hash=idx_cfg_hash,
            collection_name=collection_name,
            children_total=children_total,
            embedder=embedder,
            settings=settings,
        )
        if not compatible:
            raise HistoricalAuxiliaryError(
                f"Arm-H auxiliary manifest conflict for index_id={index_id}; "
                "refusing mutation",
                subcause="arm_h_manifest_conflict",
            )
        collection_ok = _validate_collection(
            backend,
            collection_name=collection_name,
            expected_count=children_total,
        )
        if not collection_ok:
            raise HistoricalAuxiliaryError(
                f"Arm-H auxiliary index {index_id} claims complete but collection "
                f"{collection_name} is missing or count-mismatched; refusing mutation",
                subcause="arm_h_collection_incomplete",
            )
        return HistoricalAuxiliaryBuildResult(
            manifest=existing_manifest,
            embeddings_generated=0,
            embeddings_reused=children_total,
            reused_existing=True,
        )

    text_builder = make_embedding_text_builder(settings)
    corpus_manifest_path = settings.paths.manifests / f"{corpus_id}.json"
    if not corpus_manifest_path.exists():
        # Also accept Path.name from chunk_manifest convention via corpus_id file.
        raise HistoricalAuxiliaryError(
            f"missing corpus manifest for corpus_id={corpus_id}",
            subcause="historical_chunk_set_missing",
        )
    try:
        corpus_manifest = load_corpus_manifest(corpus_manifest_path)
    except Exception as exc:
        raise HistoricalAuxiliaryError(
            f"failed to load corpus manifest: {exc}",
            subcause="historical_chunk_set_missing",
        ) from exc
    if corpus_manifest.corpus_id != corpus_id:
        raise HistoricalAuxiliaryError(
            "corpus manifest corpus_id mismatch",
            subcause="arm_h_identity_mismatch",
        )

    source_names = {
        entry.document_id: entry.source_name for entry in corpus_manifest.documents
    }
    document_ids = {chunk.document_id for chunk, _ in jobs}
    try:
        document_titles = resolve_document_titles_from_source_names(
            document_ids=document_ids,
            source_name_by_document_id=source_names,
            require=_requires_document_titles(text_builder),
        )
    except RankingTextError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="arm_h_build_failed"
        ) from exc

    try:
        rows, generated, reused, _failed = _ensure_embeddings(
            settings=settings,
            jobs=jobs,
            text_builder=text_builder,
            embedder=embedder,
            emb_cfg_hash=emb_cfg_hash,
            document_titles=document_titles,
            on_progress=on_progress,
        )
    except IndexingError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="arm_h_build_failed"
        ) from exc

    report_progress(
        on_progress,
        step="materializing_dense_index",
        current=0,
        total=None,
        unit="chunks",
    )
    try:
        _validate_point_ids(rows)
    except IndexingError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="arm_h_build_failed"
        ) from exc

    points: list[DensePointRecord] = [
        build_dense_point(
            chunk,
            vector=artifact.vector,
            chunk_artifact_id=chunk_artifact_id,
            chunk_set_id=chunk_set_id,
            embedding_id=artifact.embedding_id,
            index_id=index_id,
        )
        for chunk, chunk_artifact_id, artifact in rows
    ]

    # Incomplete/unpublished auxiliary collection: delete and rebuild.
    # Never mutate a complete immutable pair (handled above via fail-closed).
    if backend.collection_exists(collection_name):
        backend.delete_collection(collection_name)

    try:
        backend.create_collection(
            collection_name,
            dimension=embedder.dimension,
            metric=settings.indexing.metric,
        )
        backend.upsert(collection_name, points)
        actual_count = backend.count(collection_name)
        if actual_count != children_total:
            backend.delete_collection(collection_name)
            raise HistoricalAuxiliaryError(
                f"collection count validation failed: {actual_count} != {children_total}",
                subcause="arm_h_build_failed",
            )
    except HistoricalAuxiliaryError:
        raise
    except Exception as exc:
        if backend.collection_exists(collection_name):
            try:
                backend.delete_collection(collection_name)
            except Exception as cleanup_exc:  # noqa: BLE001 — best-effort cleanup
                raise HistoricalAuxiliaryError(
                    f"Arm-H auxiliary Qdrant materialization failed: {exc}; "
                    f"cleanup also failed: {cleanup_exc}",
                    subcause="arm_h_build_failed",
                ) from exc
        raise HistoricalAuxiliaryError(
            f"Arm-H auxiliary Qdrant materialization failed: {exc}",
            subcause="arm_h_build_failed",
        ) from exc

    completed = datetime.now(tz=UTC)
    settings.paths.index_manifests.mkdir(parents=True, exist_ok=True)
    manifest = DenseIndexManifest(
        index_id=index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        embedding_config_hash=emb_cfg_hash,
        index_config_hash=idx_cfg_hash,
        index_contract_version=DENSE_INDEX_CONTRACT_VERSION,
        embedding_text_strategy=text_builder.strategy,
        embedding_text_contract=text_builder.contract_version,
        embedding_model_id=embedder.model_id,
        embedding_model_revision=embedder.model_revision,
        embedding_dimension=embedder.dimension,
        normalize=embedder.normalize,
        similarity_metric=settings.indexing.metric,
        backend=settings.indexing.backend,
        backend_contract=settings.indexing.backend_contract,
        collection_name=collection_name,
        expected_child_count=children_total,
        indexed_child_count=actual_count,
        created_at=completed,
        metadata={
            "searchable_units_strategy": settings.indexing.searchable_units.strategy,
            "searchable_units_contract": (
                settings.indexing.searchable_units.contract_version
            ),
            "excluded_heading_only_count": excluded_heading_only_count,
            "chunk_set_child_count": chunk_set_child_count,
            "documents_total": documents_total,
            "historical_auxiliary": True,
            "chunk_manifest": Path(chunk_manifest_name).name,
        },
    )
    try:
        write_index_manifest(settings.paths.index_manifests, manifest)
    except RuntimeError as exc:
        raise HistoricalAuxiliaryError(
            str(exc), subcause="arm_h_manifest_conflict"
        ) from exc
    return HistoricalAuxiliaryBuildResult(
        manifest=manifest,
        embeddings_generated=generated,
        embeddings_reused=reused,
        reused_existing=False,
    )
