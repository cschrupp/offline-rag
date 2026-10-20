"""Dense indexing pipeline over an active ChunkSet."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from offline_rag.core.observability import (
    ActivityReporter,
    ObservabilityReporter,
    report_document_activity,
    report_document_phase,
)
from offline_rag.core.progress import ProgressReporter, report_progress
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
from offline_rag.dense.failure import (
    DENSE_FAILURE_EMBEDDING_GENERATION,
    DENSE_FAILURE_EMBEDDING_PERSISTENCE,
    DENSE_FAILURE_MATERIALIZATION,
    DENSE_FAILURE_PRECONDITION,
    DENSE_FAILURE_STAGE,
    DENSE_FAILURE_VALIDATION,
    DenseStageError,
    log_dense_failure,
)
from offline_rag.dense.persistence import (
    index_manifest_relpath,
    index_state_path,
    try_load_index_manifest,
    try_load_index_state,
    write_index_manifest,
    write_index_state,
)
from offline_rag.dense.points import build_dense_point
from offline_rag.dense.profiling import (
    dense_practical_timing_session,
    dense_profile_session,
    get_dense_profile_collector,
    get_practical_timing_collector,
    observe_cuda_allocator_state,
    observe_model_input_token_counts,
    observe_peak_vram_bytes,
    profiled_encode_timing,
    reset_peak_vram_stats,
    sample_external_gpu_state,
    timed_ms,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.searchable_units import (
    DenseSearchableUnitsError,
    filter_dense_searchable_children,
)
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


def _dense_execution_metadata(
    embedder: Embedder,
    *,
    batch_size: int,
) -> dict[str, Any]:
    """Non-perturbing dense execution facts for SUCCESS and FAILED reports.

    Captures resolved device, configured batch size, and embedding dimension
    whenever an embedder exists. dtype/attention come only from the existing
    non-loading observer (null when the model is not already loaded).
    """
    from offline_rag.dense.embedder import observe_embedder_execution_facts

    dense_device = getattr(
        embedder, "resolved_device", getattr(embedder, "device", None)
    )
    observed = observe_embedder_execution_facts(embedder)
    dense_dtype = observed.get("dtype")
    dense_attention = observed.get("attention_backend")
    return {
        "device": str(dense_device) if dense_device is not None else None,
        "dtype": str(dense_dtype) if dense_dtype is not None else None,
        "batch_size": int(batch_size),
        "attention_backend": (
            str(dense_attention) if dense_attention is not None else None
        ),
        "embedding_dimension": int(embedder.dimension),
    }


def _failed_report(
    *,
    run_id: str,
    corpus_name: str,
    started: datetime,
    classification: str,
    errors: list[str],
    corpus_id: str | None = None,
    chunk_set_id: str | None = None,
    embedding_config_hash: str | None = None,
    index_config_hash: str | None = None,
    children_total: int = 0,
    embeddings_generated: int = 0,
    embeddings_reused: int = 0,
    embeddings_failed: int = 0,
    documents_total: int = 0,
    index_id: str | None = None,
    collection_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> IndexingReport:
    completed = datetime.now(tz=UTC)
    return IndexingReport(
        run_id=run_id,
        corpus_name=corpus_name,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        embedding_config_hash=embedding_config_hash,
        index_config_hash=index_config_hash,
        status=IndexingStatus.FAILED,
        started_at=started,
        completed_at=completed,
        duration_ms=int((completed - started).total_seconds() * 1000),
        children_total=children_total,
        embeddings_generated=embeddings_generated,
        embeddings_reused=embeddings_reused,
        embeddings_failed=embeddings_failed,
        documents_total=documents_total,
        index_id=index_id,
        collection_name=collection_name,
        failure_classification=classification,
        errors=errors,
        metadata=metadata or {},
    )


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


def child_jobs_from_chunk_set(
    *,
    settings: AppSettings,
    chunk_set_id: str,
    chunk_manifest_name: str,
    expected_corpus_id: str | None = None,
) -> tuple[list[tuple[Chunk, str]], int]:
    """Return (child, chunk_artifact_id) pairs and unique document count.

    Historical-safe: takes an explicit chunk_set_id and manifest name; does not
    read ChunkState / CURRENT pointers. When ``expected_corpus_id`` is set, the
    chunk-set manifest corpus_id must match.
    """
    manifest_path = settings.paths.chunk_manifests / Path(chunk_manifest_name).name
    if not manifest_path.exists():
        raise IndexingError(f"missing chunk-set manifest: {chunk_manifest_name}")
    chunk_set = load_chunk_set_manifest(manifest_path)
    if chunk_set.chunk_set_id != chunk_set_id:
        raise IndexingError("chunk state/manifest ID mismatch")
    if expected_corpus_id is not None and chunk_set.corpus_id != expected_corpus_id:
        raise IndexingError(
            f"chunk-set corpus_id mismatch: {chunk_set.corpus_id} != {expected_corpus_id}"
        )

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


def _child_jobs_from_chunk_set(
    *,
    settings: AppSettings,
    chunk_set_id: str,
    chunk_manifest_name: str,
) -> tuple[list[tuple[Chunk, str]], int]:
    """Backward-compatible alias for :func:`child_jobs_from_chunk_set`."""
    return child_jobs_from_chunk_set(
        settings=settings,
        chunk_set_id=chunk_set_id,
        chunk_manifest_name=chunk_manifest_name,
    )


def _ensure_embeddings(
    *,
    settings: AppSettings,
    jobs: list[tuple[Chunk, str]],
    text_builder: EmbeddingTextBuilder,
    embedder: Embedder,
    emb_cfg_hash: str,
    document_titles: dict[str, str | None],
    on_progress: ProgressReporter | None = None,
    on_document_activity: ActivityReporter | None = None,
    control_checkpoint: Callable[[str], None] | None = None,
) -> tuple[list[tuple[Chunk, str, EmbeddingArtifact]], int, int, int]:
    """Return materialized (chunk, artifact_id, embedding), generated/reused/failed counts."""
    settings.paths.embeddings.mkdir(parents=True, exist_ok=True)
    results: list[tuple[Chunk, str, EmbeddingArtifact]] = []
    generated = reused = failed = 0
    pending_chunks: list[tuple[Chunk, str, str, str]] = []
    profile = get_dense_profile_collector()
    oversized_unsplittable = 0

    for chunk, chunk_artifact_id in jobs:
        if bool((chunk.metadata or {}).get("oversized_unsplittable")):
            oversized_unsplittable += 1
        try:
            inputs = ranking_inputs_for_chunk(
                chunk_text=chunk.text,
                section_path=list(chunk.section_path or []),
                document_title=document_titles.get(chunk.document_id),
            )
            emb_text = text_builder.build(inputs)
        except RankingTextError as exc:
            raise DenseStageError(
                str(exc),
                classification=DENSE_FAILURE_VALIDATION,
                embeddings_generated=generated,
                embeddings_reused=reused,
                embeddings_failed=failed,
            ) from exc
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

    if profile is not None:
        profile.oversized_unsplittable_count = oversized_unsplittable
        profile.cold_or_warm = (
            "cold"
            if reused == 0 and pending_chunks
            else ("warm" if not pending_chunks else "mixed")
        )

    children_total = len(jobs)
    report_progress(
        on_progress,
        step="embedding_chunks",
        current=reused,
        total=children_total if children_total > 0 else None,
        unit="chunks",
    )

    batch_size = max(1, settings.indexing.embedding.batch_size)
    for batch_index, start in enumerate(range(0, len(pending_chunks), batch_size)):
        # Authoritative cooperative control between interruptible dense batches.
        # Must not rely on progress callbacks (best-effort / exception-isolated).
        if control_checkpoint is not None:
            control_checkpoint(f"dense_batch_{start}")
        batch = pending_chunks[start : start + batch_size]
        # Truthful current activity = documents contributing to this batch only.
        batch_doc_ids = sorted({item[0].document_id for item in batch})
        report_document_activity(
            on_document_activity,
            document_ids=batch_doc_ids,
            stage="dense_batch",
        )
        texts = [item[2] for item in batch]
        # Observational token counts on the exact payloads about to be encoded.
        # SentenceTransformersEmbedder may prefix document_instruction; mirror that.
        encode_payloads = texts
        doc_instruction = getattr(embedder, "document_instruction", None)
        if isinstance(doc_instruction, str) and doc_instruction:
            encode_payloads = [f"{doc_instruction}{text}" for text in texts]
        token_counts: list[int] | None = None
        max_seq: int | None = None
        encode_ms = 0.0
        encode_cuda_device_ms: float | None = None
        encode_cuda_device_status = "not_attempted"
        encode_cuda_device_error: str | None = None
        process_cpu_delta: dict[str, Any] | None = None
        gpu_before: dict[str, Any] | None = None
        gpu_after: dict[str, Any] | None = None
        cuda_allocator_after: dict[str, Any] | None = None
        batch_chunk_ids: list[str] | None = None
        if profile is not None:
            token_counts, max_seq = observe_model_input_token_counts(
                embedder, encode_payloads, profile
            )
            batch_chunk_ids = [item[0].chunk_id for item in batch]
            # External GPU sample outside encode path (does not sync the model).
            gpu_before = sample_external_gpu_state()
        try:
            practical = get_practical_timing_collector()
            if profile is not None:
                with profiled_encode_timing() as encode_timing:
                    vectors = embedder.embed_documents(texts)
                encode_ms = float(encode_timing["encode_ms"])
                encode_cuda_device_ms = encode_timing["encode_cuda_device_ms"]
                encode_cuda_device_status = str(
                    encode_timing["encode_cuda_device_status"]
                )
                encode_cuda_device_error = encode_timing["encode_cuda_device_error"]
                process_cpu_delta = encode_timing["process_cpu_delta"]
                gpu_after = sample_external_gpu_state()
                cuda_allocator_after = observe_cuda_allocator_state()
                if practical is not None:
                    practical.encode_ms += encode_ms
            else:
                with timed_ms() as encode_bucket:
                    vectors = embedder.embed_documents(texts)
                encode_ms = float(encode_bucket[0])
                if practical is not None:
                    practical.encode_ms += encode_ms
        except Exception as exc:
            failed += len(batch)
            report_document_activity(
                on_document_activity, document_ids=(), stage="dense_batch"
            )
            raise DenseStageError(
                f"embedding generation failed: {exc}",
                classification=DENSE_FAILURE_EMBEDDING_GENERATION,
                embeddings_generated=generated,
                embeddings_reused=reused,
                embeddings_failed=failed,
            ) from exc
        if len(vectors) != len(batch):
            failed += len(batch)
            report_document_activity(
                on_document_activity, document_ids=(), stage="dense_batch"
            )
            raise DenseStageError(
                "embedder returned unexpected batch size",
                classification=DENSE_FAILURE_EMBEDDING_GENERATION,
                embeddings_generated=generated,
                embeddings_reused=reused,
                embeddings_failed=failed,
            )
        persist_ms = 0.0
        for (chunk, chunk_artifact_id, emb_text, emb_id), vector in zip(
            batch, vectors, strict=True
        ):
            if len(vector) != embedder.dimension:
                failed += 1
                report_document_activity(
                    on_document_activity, document_ids=(), stage="dense_batch"
                )
                raise DenseStageError(
                    (
                        f"embedding dimension mismatch for {chunk.chunk_id}: "
                        f"{len(vector)} != {embedder.dimension}"
                    ),
                    classification=DENSE_FAILURE_EMBEDDING_GENERATION,
                    embeddings_generated=generated,
                    embeddings_reused=reused,
                    embeddings_failed=failed,
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
            try:
                practical = get_practical_timing_collector()
                with timed_ms() as persist_bucket:
                    write_embedding_artifact(settings.paths.embeddings, artifact)
                persist_ms += persist_bucket[0]
                if practical is not None:
                    practical.embedding_persistence_ms += persist_bucket[0]
            except Exception as exc:
                failed += 1
                report_document_activity(
                    on_document_activity, document_ids=(), stage="dense_batch"
                )
                raise DenseStageError(
                    f"embedding artifact persistence failed: {exc}",
                    classification=DENSE_FAILURE_EMBEDDING_PERSISTENCE,
                    embeddings_generated=generated,
                    embeddings_reused=reused,
                    embeddings_failed=failed,
                ) from exc
            generated += 1
            results.append((chunk, chunk_artifact_id, artifact))
        if profile is not None:
            peak_after = observe_peak_vram_bytes(profile)
            profile.record_batch(
                batch_index=batch_index,
                item_count=len(batch),
                token_counts=token_counts,
                max_sequence_length=max_seq,
                encode_ms=encode_ms,
                persistence_ms=persist_ms,
                peak_vram_bytes_after=peak_after,
                chunk_ids=batch_chunk_ids,
                encode_cuda_device_ms=encode_cuda_device_ms,
                encode_cuda_device_status=encode_cuda_device_status,
                encode_cuda_device_error=encode_cuda_device_error,
                process_cpu_delta=process_cpu_delta,
                cuda_allocator_after=cuda_allocator_after,
                gpu_external_before=gpu_before,
                gpu_external_after=gpu_after,
            )
        report_document_activity(
            on_document_activity, document_ids=(), stage="dense_batch"
        )
        report_progress(
            on_progress,
            step="embedding_chunks",
            current=reused + generated,
            total=children_total if children_total > 0 else None,
            unit="chunks",
        )

    if profile is not None:
        profile.embeddings_generated = generated
        profile.embeddings_reused = reused

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
    on_progress: ProgressReporter | None = None,
    on_document_phase: ObservabilityReporter | None = None,
    on_document_activity: ActivityReporter | None = None,
    control_checkpoint: Callable[[str], None] | None = None,
) -> IndexingReport:
    started = datetime.now(tz=UTC)
    run_id = new_execution_id(prefix="index")
    name = validate_corpus_name(corpus_name)
    owned_backend = backend is None

    with dense_profile_session() as profile_session:
        if profile_session is not None:
            reset_peak_vram_stats()
        with dense_practical_timing_session() as practical_timing:
            return _run_indexing_inner(
                settings=settings,
                corpus_name=name,
                embedder=embedder,
                backend=backend,
                on_progress=on_progress,
                on_document_phase=on_document_phase,
                on_document_activity=on_document_activity,
                control_checkpoint=control_checkpoint,
                started=started,
                run_id=run_id,
                owned_backend=owned_backend,
                profile_session=profile_session,
                practical_timing=practical_timing,
            )


def _run_indexing_inner(
    *,
    settings: AppSettings,
    corpus_name: str,
    embedder: Embedder | None,
    backend: DenseIndexBackend | None,
    on_progress: ProgressReporter | None,
    on_document_phase: ObservabilityReporter | None,
    on_document_activity: ActivityReporter | None,
    control_checkpoint: Callable[[str], None] | None,
    started: datetime,
    run_id: str,
    owned_backend: bool,
    profile_session: Any,
    practical_timing: Any = None,
) -> IndexingReport:
    name = corpus_name
    backend_impl: DenseIndexBackend | None = None
    corpus_id: str | None = None
    chunk_set_id: str | None = None
    emb_cfg_hash: str | None = None
    idx_cfg_hash: str | None = None
    index_id: str | None = None
    collection_name: str | None = None
    children_total = 0
    documents_total = 0
    embeddings_generated = 0
    embeddings_reused = 0
    embeddings_failed = 0
    report_metadata: dict[str, Any] = {}
    active_embedder: Embedder | None = None

    try:
        corpus_path = corpus_state_path(settings.paths.corpora, name)
        if not corpus_path.exists():
            return _failed_report(
                run_id=run_id,
                corpus_name=name,
                started=started,
                classification=DENSE_FAILURE_PRECONDITION,
                errors=[
                    f"corpus '{name}' is not initialized; run offline-rag ingest first"
                ],
            )

        corpus_state = load_corpus_state(corpus_path)
        corpus_id = corpus_state.current_corpus_id
        if corpus_state.corpus_name != name:
            raise DenseStageError(
                "corpus state name mismatch",
                classification=DENSE_FAILURE_PRECONDITION,
            )

        chunk_path = chunk_state_path(settings.paths.corpora, name)
        if not chunk_path.exists():
            return _failed_report(
                run_id=run_id,
                corpus_name=name,
                started=started,
                classification=DENSE_FAILURE_PRECONDITION,
                corpus_id=corpus_id,
                errors=[
                    f"corpus '{name}' has no chunk state; run offline-rag chunk first"
                ],
            )

        chunk_state = load_chunk_state(chunk_path)
        chunk_set_id = chunk_state.current_chunk_set_id
        if chunk_state.source_corpus_id != corpus_state.current_corpus_id:
            return _failed_report(
                run_id=run_id,
                corpus_name=name,
                started=started,
                classification=DENSE_FAILURE_PRECONDITION,
                corpus_id=corpus_id,
                chunk_set_id=chunk_set_id,
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
        chunk_set_child_count = len(jobs)
        try:
            eligible_jobs, excluded_jobs = filter_dense_searchable_children(jobs, settings)
        except DenseSearchableUnitsError as exc:
            return _failed_report(
                run_id=run_id,
                corpus_name=name,
                started=started,
                classification=DENSE_FAILURE_PRECONDITION,
                corpus_id=corpus_id,
                chunk_set_id=chunk_set_id,
                embedding_config_hash=emb_cfg_hash,
                index_config_hash=idx_cfg_hash,
                index_id=index_id,
                collection_name=collection_name,
                errors=[str(exc)],
            )
        jobs = eligible_jobs
        children_total = len(jobs)
        excluded_heading_only_count = len(excluded_jobs)
        if children_total < 1:
            return _failed_report(
                run_id=run_id,
                corpus_name=name,
                started=started,
                classification=DENSE_FAILURE_PRECONDITION,
                corpus_id=corpus_id,
                chunk_set_id=chunk_set_id,
                embedding_config_hash=emb_cfg_hash,
                index_config_hash=idx_cfg_hash,
                index_id=index_id,
                collection_name=collection_name,
                children_total=0,
                documents_total=documents_total,
                errors=[
                    (
                        "dense searchable-unit policy excluded all children; "
                        "refusing empty dense index"
                    )
                ],
            )

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
        # Capture non-perturbing execution facts as soon as the embedder exists
        # so FAILED reports retain device/batch/dimension (and loaded dtype).
        report_metadata["dense_execution"] = _dense_execution_metadata(
            active_embedder,
            batch_size=settings.indexing.embedding.batch_size,
        )
        text_builder = make_embedding_text_builder(settings)
        if embedder is None and active_embedder.dimension != settings.indexing.embedding.dimension:
            raise DenseStageError(
                "embedder dimension does not match settings",
                classification=DENSE_FAILURE_EMBEDDING_GENERATION,
            )

        manifest_path = settings.paths.manifests / Path(corpus_state.current_manifest).name
        if not manifest_path.exists():
            raise DenseStageError(
                f"missing corpus manifest: {corpus_state.current_manifest}",
                classification=DENSE_FAILURE_PRECONDITION,
            )
        corpus_manifest = load_corpus_manifest(manifest_path)
        source_names = {
            entry.document_id: entry.source_name for entry in corpus_manifest.documents
        }
        document_ids = {chunk.document_id for chunk, _ in jobs}
        # Phase progression only — current activity comes from batch membership.
        for document_id in sorted(document_ids):
            report_document_phase(
                on_document_phase,
                document_id=document_id,
                source_name=source_names.get(document_id, document_id),
                phase="indexing",
            )
        report_document_activity(
            on_document_activity, document_ids=(), stage="dense_batch"
        )
        try:
            document_titles = resolve_document_titles_from_source_names(
                document_ids=document_ids,
                source_name_by_document_id=source_names,
                require=_requires_document_titles(text_builder),
            )
        except RankingTextError as exc:
            raise DenseStageError(
                str(exc),
                classification=DENSE_FAILURE_VALIDATION,
            ) from exc

        generation_started = datetime.now(tz=UTC)
        rows, embeddings_generated, embeddings_reused, embeddings_failed = (
            _ensure_embeddings(
                settings=settings,
                jobs=jobs,
                text_builder=text_builder,
                embedder=active_embedder,
                emb_cfg_hash=emb_cfg_hash,
                document_titles=document_titles,
                on_progress=on_progress,
                on_document_activity=on_document_activity,
                control_checkpoint=control_checkpoint,
            )
        )
        generation_completed = datetime.now(tz=UTC)
        dense_generation_ms = int(
            (generation_completed - generation_started).total_seconds() * 1000
        )
        report_metadata["dense_generation_ms"] = dense_generation_ms
        report_progress(
            on_progress,
            step="materializing_dense_index",
            current=0,
            total=None,
            unit="chunks",
        )
        materialization_started = datetime.now(tz=UTC)
        try:
            _validate_point_ids(rows)
        except IndexingError as exc:
            raise DenseStageError(
                str(exc),
                classification=DENSE_FAILURE_VALIDATION,
                embeddings_generated=embeddings_generated,
                embeddings_reused=embeddings_reused,
                embeddings_failed=embeddings_failed,
            ) from exc

        with timed_ms() as point_bucket:
            points = [
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
        if profile_session is not None:
            profile_session.point_construction_ms = point_bucket[0]
        if practical_timing is not None:
            practical_timing.point_construction_ms += point_bucket[0]

        try:
            # Incomplete/unpublished collection: delete and rebuild. Never mutate published.
            with timed_ms() as qdrant_bucket:
                if backend_impl.collection_exists(collection_name):
                    if published_complete:
                        raise DenseStageError(
                            (
                                f"published collection {collection_name} exists; "
                                "refusing mutation"
                            ),
                            classification=DENSE_FAILURE_VALIDATION,
                            embeddings_generated=embeddings_generated,
                            embeddings_reused=embeddings_reused,
                            embeddings_failed=embeddings_failed,
                        )
                    backend_impl.delete_collection(collection_name)

                backend_impl.create_collection(
                    collection_name,
                    dimension=active_embedder.dimension,
                    metric=settings.indexing.metric,
                )
                backend_impl.upsert(collection_name, points)
                actual_count = backend_impl.count(collection_name)
            if profile_session is not None:
                profile_session.qdrant_materialization_ms = qdrant_bucket[0]
            if practical_timing is not None:
                practical_timing.qdrant_ms += qdrant_bucket[0]
        except DenseStageError:
            raise
        except Exception as exc:
            raise DenseStageError(
                f"dense materialization failed: {exc}",
                classification=DENSE_FAILURE_MATERIALIZATION,
                embeddings_generated=embeddings_generated,
                embeddings_reused=embeddings_reused,
                embeddings_failed=embeddings_failed,
            ) from exc

        if actual_count != children_total:
            backend_impl.delete_collection(collection_name)
            raise DenseStageError(
                f"collection count validation failed: {actual_count} != {children_total}",
                classification=DENSE_FAILURE_VALIDATION,
                embeddings_generated=embeddings_generated,
                embeddings_reused=embeddings_reused,
                embeddings_failed=embeddings_failed,
            )
        dense_materialization_ms = int(
            (datetime.now(tz=UTC) - materialization_started).total_seconds() * 1000
        )
        report_metadata["dense_materialization_ms"] = dense_materialization_ms
        for document_id in sorted(document_ids):
            report_document_phase(
                on_document_phase,
                document_id=document_id,
                source_name=source_names.get(document_id, document_id),
                phase="indexed",
            )

        completed = datetime.now(tz=UTC)
        dense_execution = _dense_execution_metadata(
            active_embedder,
            batch_size=settings.indexing.embedding.batch_size,
        )
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
            metadata={
                "searchable_units_strategy": settings.indexing.searchable_units.strategy,
                "searchable_units_contract": (
                    settings.indexing.searchable_units.contract_version
                ),
                "excluded_heading_only_count": excluded_heading_only_count,
                "chunk_set_child_count": chunk_set_child_count,
            },
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

        success_metadata: dict[str, Any] = {
            "dense_generation_ms": dense_generation_ms,
            "dense_materialization_ms": dense_materialization_ms,
            "dense_execution": dense_execution,
        }
        tokens_per_sec: float | None = None
        tokens_status = "not_collected"
        if profile_session is not None:
            observe_peak_vram_bytes(profile_session)
            profile_summary = profile_session.summarize()
            success_metadata["dense_profile"] = profile_summary
            token_rate = profile_summary.get("throughput", {}).get(
                "model_input_tokens_per_sec_encode"
            )
            if isinstance(token_rate, (int, float)):
                # Reuse the existing 16K-B aggregate slot when reliably measured.
                success_metadata["model_input_tokens_per_sec"] = float(token_rate)
                tokens_per_sec = float(token_rate)
                tokens_status = "observed"
        if practical_timing is not None:
            duration_s = max(
                (completed - started).total_seconds(),
                1e-9,
            )
            success_metadata["practical_timing"] = {
                "encode_ms": float(practical_timing.encode_ms),
                "embedding_persistence_ms": float(
                    practical_timing.embedding_persistence_ms
                ),
                "point_construction_ms": float(practical_timing.point_construction_ms),
                "qdrant_ms": float(practical_timing.qdrant_ms),
                "wall_clock_ms": int(duration_s * 1000.0),
                "chunks_per_sec": float(children_total) / duration_s,
                "tokens_per_sec": tokens_per_sec,
                "tokens_per_sec_status": tokens_status,
            }
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
            embeddings_generated=embeddings_generated,
            embeddings_reused=embeddings_reused,
            embeddings_failed=embeddings_failed,
            vectors_materialized=actual_count,
            documents_total=documents_total,
            index_id=index_id,
            collection_name=collection_name,
            index_manifest_path=state.current_index_manifest,
            metadata=success_metadata,
        )
    except Exception as exc:
        # Cooperative control (cancel/shutdown) must remain authoritative.
        # Lazy import avoids dense ↔ app circular import at module load.
        from offline_rag.app.errors import AppError

        if isinstance(exc, AppError):
            raise
        classification = DENSE_FAILURE_STAGE
        if isinstance(exc, DenseStageError):
            classification = exc.classification
            embeddings_generated = exc.embeddings_generated
            embeddings_reused = exc.embeddings_reused
            embeddings_failed = exc.embeddings_failed
        elif isinstance(exc, EmbedderError):
            classification = DENSE_FAILURE_EMBEDDING_GENERATION
        # Refresh after a possible mid-run model load so dtype/attention, when
        # already safely observable, survive on the FAILED report.
        if active_embedder is not None:
            report_metadata["dense_execution"] = _dense_execution_metadata(
                active_embedder,
                batch_size=settings.indexing.embedding.batch_size,
            )
        log_dense_failure(
            run_id=run_id,
            corpus_name=name,
            classification=classification,
            exc=exc,
        )
        return _failed_report(
            run_id=run_id,
            corpus_name=name,
            started=started,
            classification=classification,
            errors=[str(exc)],
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            embedding_config_hash=emb_cfg_hash,
            index_config_hash=idx_cfg_hash,
            children_total=children_total,
            embeddings_generated=embeddings_generated,
            embeddings_reused=embeddings_reused,
            embeddings_failed=embeddings_failed,
            documents_total=documents_total,
            index_id=index_id,
            collection_name=collection_name,
            metadata=report_metadata,
        )
    finally:
        if owned_backend and backend_impl is not None:
            close = getattr(backend_impl, "close", None)
            if callable(close):
                close()
