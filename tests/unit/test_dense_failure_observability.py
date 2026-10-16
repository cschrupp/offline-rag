"""16K-B post-qual: dense failure observability remediation regressions."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from offline_rag.app.errors import AppError
from offline_rag.app.ingest import _map_dense_failure
from offline_rag.app.workspace.models import (
    ManagedOperationDocumentPhase,
    ManagedOperationMetrics,
    ManagedOperationRecord,
    ManagedOperationWorklistDocument,
    build_managed_operation_worklist,
)
from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.dense.backend import DensePointRecord
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.failure import (
    DENSE_FAILURE_EMBEDDING_GENERATION,
    DENSE_FAILURE_EMBEDDING_PERSISTENCE,
    DENSE_FAILURE_MATERIALIZATION,
    DENSE_FAILURE_VALIDATION,
)
from offline_rag.dense.pipeline import run_indexing
from offline_rag.domain.indexing import IndexingReport, IndexingStatus
from offline_rag.ingestion.pipeline import run_ingestion


def _settings(tmp_path: Path, *, batch_size: int = 2) -> AppSettings:
    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "project": settings.project.model_copy(update={"strict_offline": False}),
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": tmp_path / "raw",
                    "manifests": tmp_path / "manifests",
                    "processed": tmp_path / "processed",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                    "embeddings": tmp_path / "embeddings",
                    "index_manifests": tmp_path / "index-manifests",
                    "qdrant_storage": tmp_path / "qdrant",
                    "retrieval_models": tmp_path / "models",
                    "docling_artifacts": tmp_path / "models" / "docling",
                    "tokenizer_artifacts": tmp_path / "models" / "tokenizers" / "tiktoken",
                    "embedding_artifacts": tmp_path / "models" / "embeddings",
                    "eval_results": tmp_path / "eval" / "results",
                }
            ),
            "chunking": settings.chunking.model_copy(
                update={
                    "tokenizer": settings.chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            ),
            "indexing": settings.indexing.model_copy(
                update={
                    "embedding": settings.indexing.embedding.model_copy(
                        update={
                            "implementation": "fake",
                            "model_id": "fake",
                            "revision": "fake-v1",
                            "dimension": 8,
                            "batch_size": batch_size,
                            "adapter_contract": "fake-embedder-v1",
                        }
                    )
                }
            ),
            "dense": settings.dense.model_copy(update={"top_k": 5}),
        }
    )
    for path in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.eval_results,
        settings.paths.docling_artifacts,
        settings.paths.tokenizer_artifacts,
        settings.paths.embedding_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _write_docs(docs: Path, texts: list[str]) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    for idx, text in enumerate(texts):
        (docs / f"d{idx}.txt").write_text(text, encoding="utf-8")


def _prepare(settings: AppSettings, docs: Path, texts: list[str]) -> None:
    _write_docs(docs, texts)
    ingest = run_ingestion(
        settings=settings, inputs=[docs], corpus_name="eng", recursive=False
    )
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(
        settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
    )
    assert chunk.status.value in {"success", "no_op"}


class _FailingEmbedder(FakeEmbedder):
    """Fails on the Nth embed_documents call (1-based)."""

    def __init__(self, *, fail_on_call: int = 1, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._fail_on_call = fail_on_call
        self._calls = 0
        self.secret_marker = "SECRET_PATH_/tmp/leak_token_xyz"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self._calls += 1
        if self._calls >= self._fail_on_call:
            raise RuntimeError(
                f"synthetic embed boom {self.secret_marker} texts={list(texts)[:1]}"
            )
        return super().embed_documents(texts)


class _LoadedFailingEmbedder(FakeEmbedder):
    """Embedder that already exposes loaded-model dtype/attention facts."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.resolved_device = "cuda"
        self.device = "cuda"
        self.load_calls = 0

    def _load(self) -> object:
        self.load_calls += 1
        raise AssertionError("telemetry must not call _load()")

    def observe_execution_facts(self) -> dict[str, str | None]:
        return {"dtype": "bfloat16", "attention_backend": "sdpa"}

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        raise RuntimeError("synthetic loaded-model embed boom")


class _BoomUpsertBackend:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self._counts

    def create_collection(self, name: str, *, dimension: int, metric: str) -> None:
        self._counts[name] = 0

    def delete_collection(self, name: str) -> None:
        self._counts.pop(name, None)

    def upsert(self, name: str, points: list[DensePointRecord]) -> None:
        raise RuntimeError("qdrant upsert refused: SECRET_BACKEND_TOKEN")

    def count(self, name: str) -> int:
        return self._counts.get(name, 0)

    def close(self) -> None:
        return None


class _WrongCountBackend:
    def __init__(self) -> None:
        self._names: set[str] = set()

    def collection_exists(self, name: str) -> bool:
        return name in self._names

    def create_collection(self, name: str, *, dimension: int, metric: str) -> None:
        self._names.add(name)

    def delete_collection(self, name: str) -> None:
        self._names.discard(name)

    def upsert(self, name: str, points: list[DensePointRecord]) -> None:
        return None

    def count(self, name: str) -> int:
        return 0

    def close(self) -> None:
        return None


def test_first_pending_batch_failure_preserves_cache_reuse(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Fireground shape: N cache hits, first pending batch fails → reused=N."""
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "docs"
    # Enough distinct docs for multiple children under fake tokenizer.
    texts = [
        f"Document {i} describes valve pressure rating {1000 + i} psi continuous.\n"
        for i in range(6)
    ]
    _prepare(settings, docs, texts)
    emb_hash_before = build_embedding_config_hash(settings)
    idx_hash_before = build_index_config_hash(settings)

    good = FakeEmbedder(dimension=8, normalize=True)
    first = run_indexing(settings=settings, corpus_name="eng", embedder=good)
    assert first.status is IndexingStatus.SUCCESS
    reused_target = first.children_total
    assert reused_target >= 2

    # Add new pending children while keeping prior embedding artifacts.
    extra = [
        "New pending alpha describes orifice diameter 0.25 inch under load.\n",
        "New pending beta describes temperature rating 175 deg C continuous.\n",
        "New pending gamma describes flow coefficient Cv equals 12.5 nominal.\n",
        "New pending delta describes seal material PTFE for corrosive service.\n",
    ]
    for idx, text in enumerate(extra):
        (docs / f"extra_{idx}.txt").write_text(text, encoding="utf-8")
    run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())

    failing = _FailingEmbedder(dimension=8, normalize=True, fail_on_call=1)
    with caplog.at_level(logging.ERROR, logger="offline_rag.dense.failure"):
        failed = run_indexing(settings=settings, corpus_name="eng", embedder=failing)

    assert failed.status is IndexingStatus.FAILED
    assert failed.failure_classification == DENSE_FAILURE_EMBEDDING_GENERATION
    assert failed.embeddings_reused == reused_target
    assert failed.embeddings_generated == 0
    assert failed.embeddings_failed >= 1
    assert failed.children_total > reused_target
    assert failed.embedding_config_hash == emb_hash_before
    assert failed.index_config_hash == idx_hash_before
    assert any("dense indexing failed" in rec.message for rec in caplog.records)
    assert any(rec.exc_info is not None for rec in caplog.records)

    public = _map_dense_failure(failed)
    assert isinstance(public, AppError)
    details = public.details
    assert details is not None
    assert details["stage"] == "dense"
    assert details["reason"] == DENSE_FAILURE_EMBEDDING_GENERATION
    blob = str(details)
    assert "SECRET_PATH_" not in blob
    assert "leak_token" not in blob
    assert "synthetic embed boom" not in blob


def test_failure_after_persisted_batches_reports_generated_truthfully(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "docs"
    texts = [
        f"Batch doc {i} covers sensor calibration offset {i}.{i} units.\n"
        for i in range(5)
    ]
    _prepare(settings, docs, texts)
    # Fail on second embed_documents call → first batch of 2 persisted.
    failing = _FailingEmbedder(dimension=8, normalize=True, fail_on_call=2)
    report = run_indexing(settings=settings, corpus_name="eng", embedder=failing)
    assert report.status is IndexingStatus.FAILED
    assert report.failure_classification == DENSE_FAILURE_EMBEDDING_GENERATION
    assert report.embeddings_generated == 2
    assert report.embeddings_reused == 0
    assert report.embeddings_failed >= 1


def test_artifact_write_failure_distinct_from_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "docs"
    _prepare(
        settings,
        docs,
        ["Write-fail doc covers maximum continuous pressure 15000 psi.\n"],
    )

    def boom(*_args: object, **_kwargs: object) -> tuple[Path, str]:
        raise OSError("disk full SECRET_FS_/var/lib/offline")

    monkeypatch.setattr(
        "offline_rag.dense.pipeline.write_embedding_artifact", boom
    )
    report = run_indexing(
        settings=settings,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8, normalize=True),
    )
    assert report.status is IndexingStatus.FAILED
    assert report.failure_classification == DENSE_FAILURE_EMBEDDING_PERSISTENCE
    assert report.embeddings_generated == 0
    assert report.embeddings_reused == 0
    public = _map_dense_failure(report)
    assert public.details is not None
    assert public.details["reason"] == DENSE_FAILURE_EMBEDDING_PERSISTENCE
    assert "SECRET_FS_" not in str(public.details)


def test_materialization_failure_distinct_from_embedding(tmp_path: Path) -> None:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "docs"
    _prepare(
        settings,
        docs,
        ["Materialization doc covers orifice diameter under load 0.25 inch.\n"],
    )
    report = run_indexing(
        settings=settings,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8, normalize=True),
        backend=_BoomUpsertBackend(),  # type: ignore[arg-type]
    )
    assert report.status is IndexingStatus.FAILED
    assert report.failure_classification == DENSE_FAILURE_MATERIALIZATION
    assert report.embeddings_generated >= 1
    assert report.embeddings_reused == 0
    public = _map_dense_failure(report)
    assert public.details is not None
    assert public.details["reason"] == DENSE_FAILURE_MATERIALIZATION
    assert "SECRET_BACKEND_TOKEN" not in str(public.details)


def test_validation_failure_distinct_from_materialization(tmp_path: Path) -> None:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "docs"
    _prepare(
        settings,
        docs,
        ["Validation doc covers temperature rating 175 deg C under load.\n"],
    )
    report = run_indexing(
        settings=settings,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8, normalize=True),
        backend=_WrongCountBackend(),  # type: ignore[arg-type]
    )
    assert report.status is IndexingStatus.FAILED
    assert report.failure_classification == DENSE_FAILURE_VALIDATION
    assert report.embeddings_generated >= 1


def test_first_uncached_batch_failure_preserves_dense_execution_facts(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, batch_size=32)
    docs = tmp_path / "docs"
    _prepare(
        settings,
        docs,
        [
            "Exec fact alpha covers continuous pressure rating 15000 psi.\n",
            "Exec fact beta covers orifice diameter 0.25 inch under load.\n",
        ],
    )
    failing = _FailingEmbedder(
        dimension=8, normalize=True, fail_on_call=1, configured_device="cuda"
    )
    failing.resolved_device = "cuda"
    failing.device = "cuda"
    report = run_indexing(settings=settings, corpus_name="eng", embedder=failing)
    assert report.status is IndexingStatus.FAILED
    execution = report.metadata.get("dense_execution")
    assert isinstance(execution, dict)
    assert execution["device"] == "cuda"
    assert execution["batch_size"] == 32
    assert execution["embedding_dimension"] == 8
    # FakeEmbedder has no loaded model → dtype/attention stay null.
    assert execution["dtype"] is None
    assert execution["attention_backend"] is None


def test_failure_after_model_load_preserves_dtype_attention_without_loading(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, batch_size=16)
    docs = tmp_path / "docs"
    _prepare(
        settings,
        docs,
        ["Loaded-model failure covers temperature rating 175 deg C.\n"],
    )
    failing = _LoadedFailingEmbedder(dimension=8, normalize=True)
    report = run_indexing(settings=settings, corpus_name="eng", embedder=failing)
    assert report.status is IndexingStatus.FAILED
    execution = report.metadata.get("dense_execution")
    assert isinstance(execution, dict)
    assert execution["device"] == "cuda"
    assert execution["batch_size"] == 16
    assert execution["embedding_dimension"] == 8
    assert execution["dtype"] == "bfloat16"
    assert execution["attention_backend"] == "sdpa"
    assert failing.load_calls == 0


def test_precondition_failure_before_embedder_omits_dense_execution(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, batch_size=32)
    report = run_indexing(
        settings=settings,
        corpus_name="missing",
        embedder=FakeEmbedder(dimension=8, normalize=True),
    )
    assert report.status is IndexingStatus.FAILED
    assert "dense_execution" not in report.metadata


def test_failed_report_projects_dense_execution_into_managed_metrics(
    tmp_path: Path,
) -> None:
    from offline_rag.app.observability_publish import DurableObservabilityPublisher

    store = MagicMock()
    pub = DurableObservabilityPublisher(
        operations=store,
        workspace_id="ws_exec",
        operation_id="wop_exec",
    )
    pub.freeze_admission(
        documents=[
            ManagedOperationWorklistDocument(
                document_id="doc_a",
                display_name="a.md",
                phase=ManagedOperationDocumentPhase.INDEXING,
            )
        ],
        requested_document_count=1,
        uploaded_raw_bytes=10,
        pre_active_source_count=0,
        post_active_source_count=1,
    )
    now = datetime.now(tz=UTC)
    failed = IndexingReport(
        run_id="index_exec",
        corpus_name="eng",
        status=IndexingStatus.FAILED,
        started_at=now,
        completed_at=now,
        duration_ms=10,
        children_total=100,
        embeddings_generated=0,
        embeddings_reused=50,
        embeddings_failed=32,
        failure_classification=DENSE_FAILURE_EMBEDDING_GENERATION,
        metadata={
            "dense_execution": {
                "device": "cuda",
                "dtype": "bfloat16",
                "batch_size": 32,
                "attention_backend": "sdpa",
                "embedding_dimension": 1024,
            }
        },
        errors=["internal only"],
    )
    pub.after_stage_report("dense", failed)
    snap = pub.snapshot_metrics()
    assert snap.dense_execution is not None
    assert snap.dense_execution.device == "cuda"
    assert snap.dense_execution.batch_size == 32
    assert snap.dense_execution.embedding_dimension == 1024
    assert snap.dense_execution.dtype == "bfloat16"
    assert snap.dense_execution.attention_backend == "sdpa"
    assert (
        pub._documents["doc_a"].phase is ManagedOperationDocumentPhase.INDEXING
    )


def test_failed_report_does_not_project_indexing_to_indexed(tmp_path: Path) -> None:
    from offline_rag.app.observability_publish import DurableObservabilityPublisher

    store = MagicMock()
    store.update_metrics_and_worklist = MagicMock()
    pub = DurableObservabilityPublisher(
        operations=store,
        workspace_id="ws_test",
        operation_id="wop_test",
    )
    docs = [
        ManagedOperationWorklistDocument(
            document_id="doc_a",
            display_name="a.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
        ManagedOperationWorklistDocument(
            document_id="doc_b",
            display_name="b.md",
            phase=ManagedOperationDocumentPhase.INDEXING,
        ),
    ]
    pub.freeze_admission(
        documents=docs,
        requested_document_count=12,
        uploaded_raw_bytes=100,
        pre_active_source_count=11,
        post_active_source_count=12,
    )
    now = datetime.now(tz=UTC)
    failed = IndexingReport(
        run_id="index_fail",
        corpus_name="eng",
        status=IndexingStatus.FAILED,
        started_at=now,
        completed_at=now,
        duration_ms=10,
        children_total=3113,
        embeddings_generated=0,
        embeddings_reused=2528,
        embeddings_failed=32,
        failure_classification=DENSE_FAILURE_EMBEDDING_GENERATION,
        embedding_config_hash="embhash",
        index_config_hash="idxhash",
        index_id="idx_1",
        collection_name="dense_idx_1",
        errors=["internal only"],
    )
    pub.after_stage_report("dense", failed)
    snap = pub.snapshot_metrics()
    assert snap.embeddings_reused == 2528
    assert snap.embeddings_generated == 0
    assert snap.embeddings_failed == 32
    assert snap.dense_failure_classification == DENSE_FAILURE_EMBEDDING_GENERATION
    worklist = build_managed_operation_worklist(list(pub._documents.values()))
    assert all(
        d.phase is ManagedOperationDocumentPhase.INDEXING for d in worklist.documents
    )
    assert not any(
        d.phase is ManagedOperationDocumentPhase.INDEXED for d in worklist.documents
    )


def test_success_and_noop_still_advance_indexing_to_indexed(tmp_path: Path) -> None:
    from offline_rag.app.observability_publish import DurableObservabilityPublisher

    settings = _settings(tmp_path)
    docs_path = tmp_path / "docs"
    _prepare(
        settings,
        docs_path,
        ["Success path doc covers continuous pressure rating 15000 psi.\n"],
    )
    emb_before = build_embedding_config_hash(settings)
    idx_before = build_index_config_hash(settings)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    first = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert first.status is IndexingStatus.SUCCESS
    assert first.failure_classification is None
    assert first.embedding_config_hash == emb_before
    assert first.index_config_hash == idx_before

    second = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert second.status is IndexingStatus.NO_OP
    assert second.embeddings_reused == second.children_total
    assert second.failure_classification is None

    store = MagicMock()
    store.update_metrics_and_worklist = MagicMock()
    pub = DurableObservabilityPublisher(
        operations=store,
        workspace_id="ws_ok",
        operation_id="wop_ok",
    )
    pub.freeze_admission(
        documents=[
            ManagedOperationWorklistDocument(
                document_id="doc_a",
                display_name="a.md",
                phase=ManagedOperationDocumentPhase.INDEXING,
            )
        ],
        requested_document_count=1,
        uploaded_raw_bytes=10,
        pre_active_source_count=0,
        post_active_source_count=1,
    )
    pub.after_stage_report("dense", first)
    assert (
        pub._documents["doc_a"].phase is ManagedOperationDocumentPhase.INDEXED
    )


def test_historical_managed_operation_record_remains_readable() -> None:
    now = datetime.now(tz=UTC)
    legacy = {
        "schema_version": "offline-rag-managed-op-v1",
        "operation_id": "wop_legacy_dense",
        "idempotency_key": "k",
        "kind": "source_add",
        "workspace_id": "ws_1",
        "request_fingerprint": "fp",
        "expected_revision": 1,
        "status": "failed",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "metrics": {
            "embeddings_generated": 0,
            "embeddings_reused": 0,
        },
    }
    record = ManagedOperationRecord.model_validate(legacy)
    assert record.metrics is not None
    assert record.metrics.embeddings_failed is None
    assert record.metrics.dense_failure_classification is None
    # New optional fields default cleanly on fresh metrics.
    fresh = ManagedOperationMetrics(
        embeddings_reused=2528,
        embeddings_failed=32,
        dense_failure_classification=DENSE_FAILURE_EMBEDDING_GENERATION,
    )
    assert fresh.embeddings_reused == 2528


def test_fireground_shape_synthetic_counters_and_phases() -> None:
    """3113 desired / 2528 reusable / first pending batch fails."""
    from offline_rag.app.observability_publish import DurableObservabilityPublisher

    now = datetime.now(tz=UTC)
    report = IndexingReport(
        run_id="index_fg",
        corpus_name="default",
        status=IndexingStatus.FAILED,
        started_at=now,
        completed_at=now,
        duration_ms=1000,
        children_total=3113,
        embeddings_generated=0,
        embeddings_reused=2528,
        embeddings_failed=32,
        failure_classification=DENSE_FAILURE_EMBEDDING_GENERATION,
        embedding_config_hash="h_emb",
        index_config_hash="h_idx",
        index_id="idx_fg",
        collection_name="dense_fg",
        errors=["embedding generation failed: cuda"],
    )
    store = MagicMock()
    store.update_metrics_and_worklist = MagicMock()
    pub = DurableObservabilityPublisher(
        operations=store,
        workspace_id="ws_fg",
        operation_id="wop_fg",
    )
    # 12-document reconstruction set stuck in INDEXING must not become INDEXED.
    docs = [
        ManagedOperationWorklistDocument(
            document_id=f"doc_{i}",
            display_name=f"d{i}.pdf",
            phase=ManagedOperationDocumentPhase.INDEXING,
        )
        for i in range(12)
    ]
    pub.freeze_admission(
        documents=docs,
        requested_document_count=1,
        uploaded_raw_bytes=1,
        pre_active_source_count=11,
        post_active_source_count=12,
    )
    pub.after_stage_report("dense", report)
    metrics = pub.snapshot_metrics()
    assert metrics.embeddings_reused == 2528
    assert metrics.embeddings_generated == 0
    assert metrics.dense_failure_classification == DENSE_FAILURE_EMBEDDING_GENERATION
    assert all(
        d.phase is ManagedOperationDocumentPhase.INDEXING
        for d in pub._documents.values()
    )
    public = _map_dense_failure(report)
    assert public.details is not None
    assert public.details["reason"] == DENSE_FAILURE_EMBEDDING_GENERATION
    assert "cuda" not in str(public.details)
