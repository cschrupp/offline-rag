"""Product full-replace ingest use case (Phase 15D / D20)."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from offline_rag.app.candidate_recovery import candidates_dir
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import SpooledIngestUpload, cleanup_staging
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.operations import OperationHandle
from offline_rag.app.snapshot import (
    PRODUCT_MODE_GROUNDED_V1,
    CanonicalSnapshotManifest,
)

if TYPE_CHECKING:
    from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.chunking.persistence import chunk_state_path, load_chunk_state
from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import TiktokenTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.core.ids import document_id_from_bytes
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.persistence import index_state_path, load_index_state
from offline_rag.dense.pipeline import run_indexing
from offline_rag.domain.chunking import ChunkingReport, ChunkingStatus
from offline_rag.domain.indexing import (
    IndexingReport,
    IndexingStatus,
    LexicalIndexingReport,
)
from offline_rag.domain.ingestion import IngestionReport, IngestionStatus
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.persistence import corpus_state_path, load_corpus_state
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import (
    lexical_index_state_path,
    load_lexical_index_state,
)
from offline_rag.lexical.pipeline import run_lexical_indexing
from offline_rag.rerank.config_hash import build_reranker_config_hash


@dataclass(frozen=True)
class ProductIngestResult:
    corpus: str
    snapshot_id: str
    document_count: int


@dataclass
class _CandidateContext:
    candidate_id: str
    candidate_root: Path
    stage_corpora_root: Path
    sources_root: Path
    settings: AppSettings


def _candidate_settings(base: AppSettings, stage_corpora_root: Path) -> AppSettings:
    """Isolate mutable corpus stage state; keep shared immutable artifact roots."""
    paths = base.paths.model_copy(update={"corpora": stage_corpora_root})
    return base.model_copy(update={"paths": paths})


def _validate_document_identities(upload: SpooledIngestUpload) -> None:
    """Reject ambiguous canonical document identity before mutation."""
    seen: dict[str, str] = {}
    for item in upload.files:
        doc_id = document_id_from_bytes(item.absolute_path.read_bytes())
        prior = seen.get(doc_id)
        if prior is not None:
            raise AppError(
                ErrorCode.DOCUMENT_INVALID,
                details=SafeErrorDetails(reason="document_identity_conflict"),
            )
        seen[doc_id] = item.source_name


def _establish_candidate(
    settings: AppSettings,
    upload: SpooledIngestUpload,
) -> _CandidateContext:
    candidate_id = uuid.uuid4().hex
    candidate_root = (
        candidates_dir(settings.paths.corpora, upload.corpus_name) / candidate_id
    )
    stage_corpora_root = candidate_root / "corpora"
    sources_root = candidate_root / "sources"
    stage_corpora_root.mkdir(parents=True, exist_ok=False)
    # Move staged sources under the corpus tree so post-lease validity is not
    # coupled to the live request body / staging lifetime.
    shutil.move(str(upload.files_root), str(sources_root))
    # Drop empty staging remainder (upload root may still exist).
    cleanup_staging(upload.staging_root)
    candidate_settings = _candidate_settings(settings, stage_corpora_root)
    return _CandidateContext(
        candidate_id=candidate_id,
        candidate_root=candidate_root,
        stage_corpora_root=stage_corpora_root,
        sources_root=sources_root,
        settings=candidate_settings,
    )


def _source_inputs(candidate: _CandidateContext) -> list[Path]:
    # Physical names are server-generated document identities (order-independent).
    return sorted(path for path in candidate.sources_root.iterdir() if path.is_file())


def _run_stage(hooks: ProductIngestHooks | None, name: str, fn: Callable[[], object]) -> object:
    if hooks is not None and hooks.before_stage is not None:
        hooks.before_stage(name)
    result = fn()
    if hooks is not None and hooks.after_stage is not None:
        hooks.after_stage(name)
    return result


def _map_ingestion_failure(report: IngestionReport) -> AppError:
    failure_class = str(report.metadata.get("failure_class", "")).lower()
    if failure_class == "internal":
        return AppError(
            ErrorCode.INGEST_FAILED,
            details=SafeErrorDetails(reason="internal_ingest_failure"),
        )
    return AppError(
        ErrorCode.DOCUMENT_INVALID,
        details=SafeErrorDetails(reason="document_unparseable"),
    )


def build_canonical_snapshot_manifest(
    *,
    settings: AppSettings,
    candidate_settings: AppSettings,
    corpus_name: str,
) -> CanonicalSnapshotManifest:
    """Derive CanonicalSnapshotManifest from actual immutable stage outputs."""
    corpora = candidate_settings.paths.corpora
    corpus_state = load_corpus_state(corpus_state_path(corpora, corpus_name))
    chunk_state = load_chunk_state(chunk_state_path(corpora, corpus_name))
    index_state = load_index_state(index_state_path(corpora, corpus_name))
    lexical_state = load_lexical_index_state(lexical_index_state_path(corpora, corpus_name))

    counter = TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )
    return CanonicalSnapshotManifest(
        product_mode_id=PRODUCT_MODE_GROUNDED_V1,
        corpus_id=corpus_state.current_corpus_id,
        corpus_manifest=Path(corpus_state.current_manifest).name,
        chunk_set_id=chunk_state.current_chunk_set_id,
        chunk_manifest=Path(chunk_state.current_chunk_manifest).name,
        dense_index_id=index_state.current_index_id,
        dense_index_manifest=Path(index_state.current_index_manifest).name,
        lexical_index_id=lexical_state.current_lexical_index_id,
        lexical_index_manifest=Path(lexical_state.current_lexical_index_manifest).name,
        embedding_config_hash=build_embedding_config_hash(settings),
        index_config_hash=build_index_config_hash(settings),
        lexical_config_hash=build_lexical_config_hash(settings),
        fusion_config_hash=build_fusion_config_hash(settings),
        reranker_config_hash=build_reranker_config_hash(settings),
        context_config_hash=build_context_config_hash(settings, token_counter=counter),
    )


def run_product_replace_ingest(
    runtime: ApplicationRuntime,
    upload: SpooledIngestUpload,
    *,
    hooks: ProductIngestHooks | None = None,
    control: OperationHandle | None = None,
) -> ProductIngestResult:
    """Execute the post-spool full-replace ingest transaction.

    Caller must already hold ingest-class capacity. This function acquires the
    per-corpus mutation lease, builds an isolated candidate, runs scientific
    stages, and publishes via ProductPublicationRegistry.
    """
    runtime.require_ready()
    if runtime.resources is None:
        raise AppError(ErrorCode.RUNTIME_NOT_READY)
    if control is not None:
        control.checkpoint("pre_validate")

    _validate_document_identities(upload)

    lease = CorpusMutationLease(runtime.settings, upload.corpus_name)
    candidate: _CandidateContext | None = None
    leased = False
    try:
        if control is not None:
            control.checkpoint("pre_lease")
        lease.acquire()
        leased = True
        # Cancellation-aware PRE_LEASE → POST_LEASE: disconnect/shutdown/deadline
        # discovered before this transition aborts without candidate mutation.
        if control is not None:
            control.complete_lease_acquire()

        candidate = _establish_candidate(runtime.settings, upload)
        if hooks is not None and hooks.after_lease_acquired is not None:
            hooks.after_lease_acquired(upload.corpus_name, candidate.candidate_root)

        inputs = _source_inputs(candidate)
        if not inputs:
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="candidate_sources_missing"),
            )

        embedder = runtime.resources.embedder
        qdrant = runtime.resources.qdrant

        def _gated(stage: str, fn: Callable[[], object]) -> object:
            if control is not None:
                control.checkpoint(f"pre_{stage}")
            return _run_stage(hooks, stage, fn)

        source_names = upload.source_name_by_storage_name()
        ingest_report = _gated(
            "ingest",
            lambda: run_ingestion(
                settings=candidate.settings,
                inputs=inputs,
                corpus_name=upload.corpus_name,
                recursive=False,
                root=candidate.sources_root,
                source_name_by_path=source_names,
            ),
        )
        assert isinstance(ingest_report, IngestionReport)
        if ingest_report.status not in {IngestionStatus.SUCCESS, IngestionStatus.NO_OP}:
            raise _map_ingestion_failure(ingest_report)

        # Full-replace guard: candidate stage must equal uploaded set exactly.
        corpus_state = load_corpus_state(
            corpus_state_path(candidate.stage_corpora_root, upload.corpus_name)
        )
        if len(corpus_state.sources) != len(upload.files):
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="replace_set_mismatch"),
            )
        doc_ids = [
            entry.document_id for entry in corpus_state.sources.values()
        ]
        if len(doc_ids) != len(set(doc_ids)):
            raise AppError(
                ErrorCode.DOCUMENT_INVALID,
                details=SafeErrorDetails(reason="document_identity_conflict"),
            )

        chunk_report = _gated(
            "chunk",
            lambda: run_chunking(
                settings=candidate.settings,
                corpus_name=upload.corpus_name,
            ),
        )
        assert isinstance(chunk_report, ChunkingReport)
        if chunk_report.status not in {ChunkingStatus.SUCCESS, ChunkingStatus.NO_OP}:
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(stage="chunk", reason="stage_failed"),
            )

        index_report = _gated(
            "dense",
            lambda: run_indexing(
                settings=candidate.settings,
                corpus_name=upload.corpus_name,
                embedder=embedder,
                backend=qdrant,
            ),
        )
        assert isinstance(index_report, IndexingReport)
        if index_report.status not in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}:
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(stage="dense", reason="stage_failed"),
            )

        lexical_report = _gated(
            "lexical",
            lambda: run_lexical_indexing(
                settings=candidate.settings,
                corpus_name=upload.corpus_name,
            ),
        )
        assert isinstance(lexical_report, LexicalIndexingReport)
        if lexical_report.status not in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}:
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(stage="lexical", reason="stage_failed"),
            )

        identity = build_canonical_snapshot_manifest(
            settings=runtime.settings,
            candidate_settings=candidate.settings,
            corpus_name=upload.corpus_name,
        )

        if control is not None:
            control.checkpoint("pre_publish")
        if hooks is not None and hooks.before_stage is not None:
            hooks.before_stage("publish")
        # Publication critical section begins at ProductPublicationRegistry.publish.
        if control is not None:
            control.enter_publication()
        snapshot_id = runtime.publication.publish(upload.corpus_name, identity)
        if hooks is not None and hooks.after_stage is not None:
            hooks.after_stage("publish")

        return ProductIngestResult(
            corpus=upload.corpus_name,
            snapshot_id=snapshot_id,
            document_count=len(upload.files),
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.INGEST_FAILED,
            details=SafeErrorDetails(reason="internal_ingest_failure"),
        ) from exc
    finally:
        if leased:
            lease.release()
