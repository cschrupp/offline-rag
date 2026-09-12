"""Dense indexing pipeline over an active ChunkSet."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_artifact_path,
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_set_manifest,
    load_chunk_state,
)
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    DENSE_INDEX_CONTRACT_VERSION,
    dense_collection_name,
    dense_index_id,
    dense_point_uuid,
    embedding_id_from_parts,
    embedding_text_hash,
    new_execution_id,
)
from offline_rag.dense.backend import DenseIndexBackend, DensePointRecord
from offline_rag.dense.cache import (
    try_load_reusable_embedding_artifact,
    write_embedding_artifact,
)
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import Embedder, EmbedderError, make_embedder
from offline_rag.dense.persistence import (
    index_manifest_relpath,
    index_state_path,
    try_load_index_manifest,
    try_load_index_state,
    write_index_manifest,
    write_index_state,
)
from offline_rag.dense.points import build_dense_point
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.text import (
    EmbeddingTextBuilder,
    PlainEmbeddingTextBuilder,
    TitleSectionEmbeddingTextBuilder,
)
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import (
    DenseIndexManifest,
    EmbeddingArtifact,
    IndexingReport,
    IndexingStatus,
    IndexState,
)
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)
from offline_rag.retrieval.ranking_text import (
    RankingTextError,
    ranking_inputs_for_chunk,
    resolve_document_titles_from_source_names,
)


class IndexingError(RuntimeError):
    pass


def make_embedding_text_builder(settings: AppSettings) -> EmbeddingTextBuilder:
    strategy = settings.indexing.embedding_text.strategy
    contract = settings.indexing.embedding_text.contract_version
    if strategy == "plain" and contract == PlainEmbeddingTextBuilder.contract_version:
        return PlainEmbeddingTextBuilder()
    if (
        strategy == TitleSectionEmbeddingTextBuilder.strategy
        and contract == TitleSectionEmbeddingTextBuilder.contract_version
    ):
        return TitleSectionEmbeddingTextBuilder()
    raise IndexingError(
        f"unsupported embedding text strategy/contract: {strategy}/{contract}"
    )


def _requires_document_titles(builder: EmbeddingTextBuilder) -> bool:
    return (
        builder.strategy == TitleSectionEmbeddingTextBuilder.strategy
        and builder.contract_version == TitleSectionEmbeddingTextBuilder.contract_version
    )


def _validate_collection(
    backend: DenseIndexBackend,
    *,
    collection_name: str,
    expected_count: int,
) -> bool:
    if not backend.collection_exists(collection_name):
        return False
    return backend.count(collection_name) == expected_count


def _child_jobs_from_chunk_set(
    *,
    settings: AppSettings,
    chunk_set_id: str,
    chunk_manifest_name: str,
) -> tuple[list[tuple[Chunk, str]], int]:
    """Return (child, chunk_artifact_id) pairs and unique document count."""
    manifest_path = settings.paths.chunk_manifests / Path(chunk_manifest_name).name
    if not manifest_path.exists():
        raise IndexingError(f"missing chunk-set manifest: {chunk_manifest_name}")
    chunk_set = load_chunk_set_manifest(manifest_path)
    if chunk_set.chunk_set_id != chunk_set_id:
        raise IndexingError("chunk state/manifest ID mismatch")

    jobs: list[tuple[Chunk, str]] = []
    documents: set[str] = set()
    for entry in sorted(chunk_set.documents, key=lambda item: item.document_id):
        artifact_path = chunk_artifact_path(settings.paths.chunks, entry.chunk_artifact_id)
        if not artifact_path.exists():
            raise IndexingError(f"missing chunk artifact: {entry.chunk_artifact_id}")
        artifact = load_chunk_artifact(artifact_path)
        if artifact.chunk_artifact_id != entry.chunk_artifact_id:
            raise IndexingError("chunk artifact ID mismatch")
        if artifact.document_id != entry.document_id:
            raise IndexingError("chunk artifact document_id mismatch")
        documents.add(artifact.document_id)
        for chunk in artifact.children:
            if chunk.kind != ChunkKind.CHILD:
                continue
            jobs.append((chunk, artifact.chunk_artifact_id))

    # Deterministic order by chunk_id for stable point UUID collision checks.
    jobs.sort(key=lambda item: item[0].chunk_id)
    if len(jobs) != chunk_set.total_child_count:
        raise IndexingError(
            f"child count mismatch: loaded {len(jobs)} vs manifest {chunk_set.total_child_count}"
        )
    return jobs, len(documents)


def _ensure_embeddings(
    *,
    settings: AppSettings,
    jobs: list[tuple[Chunk, str]],
    text_builder: EmbeddingTextBuilder,
    embedder: Embedder,
    emb_cfg_hash: str,
    document_titles: dict[str, str | None],
) -> tuple[list[tuple[Chunk, str, EmbeddingArtifact]], int, int, int]:
    """Return materialized (chunk, artifact_id, embedding), generated/reused/failed counts."""
    settings.paths.embeddings.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Chunk, str, EmbeddingArtifact]] = []
    generated = reused = failed = 0
    pending_chunks: list[tuple[Chunk, str, str, str]] = []

    for chunk, chunk_artifact_id in jobs:
        try:
            inputs = ranking_inputs_for_chunk(
                chunk_text=chunk.text,
                section_path=list(chunk.section_path or []),
                document_title=document_titles.get(chunk.document_id),
            )
            emb_text = text_builder.build(inputs)
        except RankingTextError as exc:
            raise IndexingError(str(exc)) from exc
        text_digest = embedding_text_hash(emb_text)
        emb_id = embedding_id_from_parts(
            chunk.chunk_id,
            embedding_text_digest=text_digest,
            emb_cfg_hash=emb_cfg_hash,
        )
        cached = try_load_reusable_embedding_artifact(
            settings.paths.embeddings,
            emb_id,
            expected_chunk_id=chunk.chunk_id,
            expected_embedding_text_hash=text_digest,
            expected_embedding_config_hash=emb_cfg_hash,
            expected_dimension=embedder.dimension,
            expected_normalize=embedder.normalize,
            expected_model_id=embedder.model_id,
            expected_model_revision=embedder.model_revision,
            expected_adapter_contract=embedder.adapter_contract,
        )
        if cached is not None:
            reused += 1
            results.append((chunk, chunk_artifact_id, cached))
            continue
        pending_chunks.append((chunk, chunk_artifact_id, emb_text, emb_id))

    batch_size = max(1, settings.indexing.embedding.batch_size)
    for start in range(0, len(pending_chunks), batch_size):
        batch = pending_chunks[start : start + batch_size]
        texts = [item[2] for item in batch]
        try:
            vectors = embedder.embed_documents(texts)
        except Exception as exc:
            failed += len(batch)
            raise IndexingError(f"embedding generation failed: {exc}") from exc
        if len(vectors) != len(batch):
            failed += len(batch)
            raise IndexingError("embedder returned unexpected batch size")
        for (chunk, chunk_artifact_id, emb_text, emb_id), vector in zip(batch, vectors, strict=True):
            if len(vector) != embedder.dimension:
                failed += 1
                raise IndexingError(
                    f"embedding dimension mismatch for {chunk.chunk_id}: "
                    f"{len(vector)} != {embedder.dimension}"
                )
            artifact = EmbeddingArtifact(
                embedding_id=emb_id,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                embedding_text_hash=embedding_text_hash(emb_text),
                embedding_config_hash=emb_cfg_hash,
                model_id=embedder.model_id,
                model_revision=embedder.model_revision,
                dimension=embedder.dimension,
                normalize=embedder.normalize,
                adapter_contract=embedder.adapter_contract,
                vector=list(vector),
            )
            write_embedding_artifact(settings.paths.embeddings, artifact)
            generated += 1
            results.append((chunk, chunk_artifact_id, artifact))

    results.sort(key=lambda item: item[0].chunk_id)
    return results, generated, reused, failed


def _validate_point_ids(rows: list[tuple[Chunk, str, EmbeddingArtifact]]) -> None:
    seen: dict[str, str] = {}
    for chunk, _, _ in rows:
        point_id = dense_point_uuid(chunk.chunk_id)
        prior = seen.get(point_id)
        if prior is not None and prior != chunk.chunk_id:
            raise IndexingError(
                f"UUID5 point ID collision between {prior} and {chunk.chunk_id}"
            )
        seen[point_id] = chunk.chunk_id


def _publish_index_state(
    *,
    settings: AppSettings,
    corpus_name: str,
    corpus_id: str,
    chunk_set_id: str,
    index_id: str,
    idx_cfg_hash: str,
    completed: datetime,
) -> IndexState:
    relative_manifest = index_manifest_relpath(index_id)
    new_state = IndexState(
        corpus_name=corpus_name,
        source_corpus_id=corpus_id,
        source_chunk_set_id=chunk_set_id,
        current_index_id=index_id,
        current_index_manifest=relative_manifest,
        index_config_hash=idx_cfg_hash,
        created_at=completed,
        updated_at=completed,
    )
    state_path = index_state_path(settings.paths.corpora, corpus_name)
    existing = try_load_index_state(state_path)
    if existing is not None and existing.created_at:
        new_state = new_state.model_copy(update={"created_at": existing.created_at})
    write_index_state(state_path, new_state)
    return new_state


def run_indexing(
    *,
    settings: AppSettings,
    corpus_name: str = "default",
    embedder: Embedder | None = None,
    backend: DenseIndexBackend | None = None,
) -> IndexingReport:
    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix="index")
    name = validate_corpus_name(corpus_name)
    owned_backend = backend is None
    backend_impl: DenseIndexBackend | None = None

    try:
        corpus_path = corpus_state_path(settings.paths.corpora, name)
        if not corpus_path.exists():
            completed = datetime.now(tz=UTC)
            return IndexingReport(
                run_id=run_id,
                corpus_name=name,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[f"corpus '{name}' is not initialized; run offline-rag ingest first"],
            )

        corpus_state = load_corpus_state(corpus_path)
        if corpus_state.corpus_name != name:
            raise IndexingError("corpus state name mismatch")

        chunk_path = chunk_state_path(settings.paths.corpora, name)
        if not chunk_path.exists():
            completed = datetime.now(tz=UTC)
            return IndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[f"corpus '{name}' has no chunk state; run offline-rag chunk first"],
            )

        chunk_state = load_chunk_state(chunk_path)
        if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
            completed = datetime.now(tz=UTC)
            return IndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                status=IndexingStatus.FAILED,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                errors=[
                    (
                        "ChunkState is stale relative to CorpusState; "
                        "re-run offline-rag chunk before indexing"
                    )
                ],
            )

        emb_cfg_hash = build_embedding_config_hash(settings)
        idx_cfg_hash = build_index_config_hash(settings)
        index_id = dense_index_id(chunk_state.current_chunk_set_id, idx_cfg_hash)
        collection_name = dense_collection_name(index_id)

        jobs, documents_total = _child_jobs_from_chunk_set(
            settings=settings,
            chunk_set_id=chunk_state.current_chunk_set_id,
            chunk_manifest_name=chunk_state.current_chunk_manifest,
        )
        children_total = len(jobs)

        backend_impl = backend or QdrantLocalBackend(settings.paths.qdrant_storage)
        settings.paths.index_manifests.mkdir(parents=True, exist_ok=True)

        existing_state = try_load_index_state(index_state_path(settings.paths.corpora, name))
        existing_manifest = try_load_index_manifest(settings.paths.index_manifests, index_id)
        collection_ok = _validate_collection(
            backend_impl,
            collection_name=collection_name,
            expected_count=children_total,
        )
        published_complete = (
            existing_manifest is not None
            and existing_manifest.index_id == index_id
            and existing_manifest.corpus_id == corpus_state.current_corpus_id
            and existing_manifest.chunk_set_id == chunk_state.current_chunk_set_id
            and existing_manifest.index_config_hash == idx_cfg_hash
            and existing_manifest.indexed_child_count == children_total
            and collection_ok
        )

        if (
            existing_state is not None
            and existing_state.current_index_id == index_id
            and existing_state.source_corpus_id == corpus_state.current_corpus_id
            and existing_state.source_chunk_set_id == chunk_state.current_chunk_set_id
            and existing_state.index_config_hash == idx_cfg_hash
            and existing_manifest is not None
            and existing_manifest.index_config_hash == idx_cfg_hash
            and existing_manifest.chunk_set_id == chunk_state.current_chunk_set_id
            and existing_manifest.indexed_child_count == children_total
            and collection_ok
        ):
            completed = datetime.now(tz=UTC)
            return IndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                embedding_config_hash=emb_cfg_hash,
                index_config_hash=idx_cfg_hash,
                status=IndexingStatus.NO_OP,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                children_total=children_total,
                embeddings_generated=0,
                embeddings_reused=children_total,
                embeddings_failed=0,
                vectors_materialized=children_total,
                documents_total=documents_total,
                index_id=index_id,
                collection_name=collection_name,
                index_manifest_path=existing_state.current_index_manifest,
            )

        # Published complete index exists but IndexState needs advance (no embedder).
        if published_complete:
            completed = datetime.now(tz=UTC)
            state = _publish_index_state(
                settings=settings,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                index_id=index_id,
                idx_cfg_hash=idx_cfg_hash,
                completed=completed,
            )
            return IndexingReport(
                run_id=run_id,
                corpus_name=name,
                corpus_id=corpus_state.current_corpus_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                embedding_config_hash=emb_cfg_hash,
                index_config_hash=idx_cfg_hash,
                status=IndexingStatus.SUCCESS,
                started_at=started,
                completed_at=completed,
                duration_ms=int((completed - started).total_seconds() * 1000),
                children_total=children_total,
                embeddings_generated=0,
                embeddings_reused=children_total,
                embeddings_failed=0,
                vectors_materialized=children_total,
                documents_total=documents_total,
                index_id=index_id,
                collection_name=collection_name,
                index_manifest_path=state.current_index_manifest,
                metadata={"reused_published_collection": True},
            )

        active_embedder = embedder or make_embedder(settings)
        text_builder = make_embedding_text_builder(settings)
        if embedder is None and active_embedder.dimension != settings.indexing.embedding.dimension:
            raise EmbedderError("embedder dimension does not match settings")

        manifest_path = settings.paths.manifests / Path(corpus_state.current_manifest).name
        if not manifest_path.exists():
            raise IndexingError(f"missing corpus manifest: {corpus_state.current_manifest}")
        corpus_manifest = load_corpus_manifest(manifest_path)
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
            raise IndexingError(str(exc)) from exc

        rows, generated, reused, failed = _ensure_embeddings(
            settings=settings,
            jobs=jobs,
            text_builder=text_builder,
            embedder=active_embedder,
            emb_cfg_hash=emb_cfg_hash,
            document_titles=document_titles,
        )
        _validate_point_ids(rows)

        points: list[DensePointRecord] = [
            build_dense_point(
                chunk,
                vector=artifact.vector,
                chunk_artifact_id=chunk_artifact_id,
                chunk_set_id=chunk_state.current_chunk_set_id,
                embedding_id=artifact.embedding_id,
                index_id=index_id,
            )
            for chunk, chunk_artifact_id, artifact in rows
        ]

        # Incomplete/unpublished collection: delete and rebuild. Never mutate published.
        if backend_impl.collection_exists(collection_name):
            if published_complete:
                raise IndexingError(
                    f"published collection {collection_name} exists; refusing mutation"
                )
            backend_impl.delete_collection(collection_name)

        backend_impl.create_collection(
            collection_name,
            dimension=active_embedder.dimension,
            metric=settings.indexing.metric,
        )
        backend_impl.upsert(collection_name, points)
        actual_count = backend_impl.count(collection_name)
        if actual_count != children_total:
            backend_impl.delete_collection(collection_name)
            raise IndexingError(
                f"collection count validation failed: {actual_count} != {children_total}"
            )

        completed = datetime.now(tz=UTC)
        manifest = DenseIndexManifest(
            index_id=index_id,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            embedding_config_hash=emb_cfg_hash,
            index_config_hash=idx_cfg_hash,
            index_contract_version=DENSE_INDEX_CONTRACT_VERSION,
            embedding_text_strategy=text_builder.strategy,
            embedding_text_contract=text_builder.contract_version,
            embedding_model_id=active_embedder.model_id,
            embedding_model_revision=active_embedder.model_revision,
            embedding_dimension=active_embedder.dimension,
            normalize=active_embedder.normalize,
            similarity_metric=settings.indexing.metric,
            backend=settings.indexing.backend,
            backend_contract=settings.indexing.backend_contract,
            collection_name=collection_name,
            expected_child_count=children_total,
            indexed_child_count=actual_count,
            created_at=completed,
        )
        write_index_manifest(settings.paths.index_manifests, manifest)
        state = _publish_index_state(
            settings=settings,
            corpus_name=name,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            index_id=index_id,
            idx_cfg_hash=idx_cfg_hash,
            completed=completed,
        )

        return IndexingReport(
            run_id=run_id,
            corpus_name=name,
            corpus_id=corpus_state.current_corpus_id,
            chunk_set_id=chunk_state.current_chunk_set_id,
            embedding_config_hash=emb_cfg_hash,
            index_config_hash=idx_cfg_hash,
            status=IndexingStatus.SUCCESS,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            children_total=children_total,
            embeddings_generated=generated,
            embeddings_reused=reused,
            embeddings_failed=failed,
            vectors_materialized=actual_count,
            documents_total=documents_total,
            index_id=index_id,
            collection_name=collection_name,
            index_manifest_path=state.current_index_manifest,
        )
    except Exception as exc:
        completed = datetime.now(tz=UTC)
        return IndexingReport(
            run_id=run_id,
            corpus_name=name,
            status=IndexingStatus.FAILED,
            started_at=started,
            completed_at=completed,
            duration_ms=int((completed - started).total_seconds() * 1000),
            errors=[str(exc)],
        )
    finally:
        if owned_backend and backend_impl is not None:
            close = getattr(backend_impl, "close", None)
            if callable(close):
                close()
