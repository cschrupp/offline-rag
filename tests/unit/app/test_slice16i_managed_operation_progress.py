"""Slice 16I — managed-operation progress telemetry."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.app.errors import AppError
from offline_rag.app.workspace.models import (
    MANAGED_OP_SCHEMA_VERSION,
    ManagedOperationKind,
    ManagedOperationProgress,
    ManagedOperationProgressStep,
    ManagedOperationProgressUnit,
    ManagedOperationRecord,
    ManagedOperationStatus,
    OperationProgressStage,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.config.models import AppSettings
from offline_rag.core.progress import ProgressEvent


def _settings(tmp_path: Path) -> AppSettings:
    root = tmp_path / "data"
    return AppSettings().model_copy(
        update={
            "paths": AppSettings().paths.model_copy(
                update={
                    "root": root,
                    "workspaces": root / "workspaces",
                    "corpora": root / "corpora",
                    "processed": root / "processed",
                    "chunks": root / "chunks",
                    "chunk_manifests": root / "chunk_manifests",
                    "manifests": root / "manifests",
                    "embeddings": root / "embeddings",
                    "indexes": root / "indexes",
                    "lexical": root / "lexical",
                    "staging": root / "staging",
                    "locks": root / "locks",
                }
            )
        }
    )


def test_old_record_without_progress_validates_and_projects_null() -> None:
    now = datetime.now(tz=UTC)
    legacy = {
        "schema_version": MANAGED_OP_SCHEMA_VERSION,
        "operation_id": "wop_legacy",
        "idempotency_key": "k1",
        "kind": "source_add",
        "workspace_id": "ws_1",
        "request_fingerprint": "fp",
        "expected_revision": 1,
        "status": "running",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "progress_stage": "building_indexes",
    }
    record = ManagedOperationRecord.model_validate(legacy)
    assert record.progress is None
    from offline_rag.api.workspace_views import operation_view

    view = operation_view(record)
    assert view["progress"] is None


def test_progress_bounds_reject_invalid() -> None:
    from pydantic import ValidationError

    now = datetime.now(tz=UTC)
    with pytest.raises(ValidationError):
        ManagedOperationProgress(
            step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
            current=-1,
            total=10,
            unit=ManagedOperationProgressUnit.CHUNKS,
            started_at=now,
        )
    with pytest.raises(ValidationError):
        ManagedOperationProgress(
            step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
            current=1,
            total=0,
            unit=ManagedOperationProgressUnit.CHUNKS,
            started_at=now,
        )
    with pytest.raises(ValidationError):
        ManagedOperationProgress(
            step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
            current=11,
            total=10,
            unit=ManagedOperationProgressUnit.CHUNKS,
            started_at=now,
        )


def test_store_update_progress_rules(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.paths.workspaces.mkdir(parents=True, exist_ok=True)
    ops = ManagedOperationStore(settings)
    rec, _ = ops.reserve(
        workspace_id="ws_1",
        idempotency_key="prog-1",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["a.pdf"]},
        expected_revision=1,
    )
    running = ops.update_status(
        rec.workspace_id,
        rec.operation_id,
        ManagedOperationStatus.RUNNING,
        progress_stage=OperationProgressStage.BUILDING_INDEXES,
    )
    first = ops.update_progress(
        rec.workspace_id,
        rec.operation_id,
        step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
        current=10,
        total=100,
        unit=ManagedOperationProgressUnit.CHUNKS,
    )
    assert first.status is ManagedOperationStatus.RUNNING
    assert first.progress is not None
    assert first.progress.current == 10
    assert first.updated_at >= running.updated_at
    started = first.progress.started_at

    second = ops.update_progress(
        rec.workspace_id,
        rec.operation_id,
        step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
        current=40,
        total=100,
        unit=ManagedOperationProgressUnit.CHUNKS,
    )
    assert second.progress is not None
    assert second.progress.started_at == started
    assert second.progress.current == 40

    with pytest.raises(AppError) as reg:
        ops.update_progress(
            rec.workspace_id,
            rec.operation_id,
            step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
            current=20,
            total=100,
            unit=ManagedOperationProgressUnit.CHUNKS,
        )
    assert reg.value.details["reason"] == "progress_current_regression"

    stepped = ops.update_progress(
        rec.workspace_id,
        rec.operation_id,
        step=ManagedOperationProgressStep.MATERIALIZING_DENSE_INDEX,
        current=0,
        total=None,
        unit=ManagedOperationProgressUnit.CHUNKS,
    )
    assert stepped.progress is not None
    assert stepped.progress.step is ManagedOperationProgressStep.MATERIALIZING_DENSE_INDEX
    assert stepped.progress.started_at > started

    ops.update_status(
        rec.workspace_id,
        rec.operation_id,
        ManagedOperationStatus.SUCCEEDED,
        progress_stage=OperationProgressStage.READY,
    )
    with pytest.raises(AppError) as term:
        ops.update_progress(
            rec.workspace_id,
            rec.operation_id,
            step=ManagedOperationProgressStep.FINALIZING,
            current=0,
            total=None,
            unit=ManagedOperationProgressUnit.DOCUMENTS,
        )
    assert term.value.details["reason"] == "illegal_operation_progress_on_terminal"


def test_progress_event_is_optional_noop() -> None:
    # Domain reporters must tolerate None without raising.
    from offline_rag.core.progress import report_progress

    report_progress(
        None,
        step="embedding_chunks",
        current=1,
        total=2,
        unit="chunks",
    )
    seen: list[ProgressEvent] = []
    report_progress(
        seen.append,
        step="embedding_chunks",
        current=1,
        total=2,
        unit="chunks",
    )
    assert seen[0].current == 1


def test_api_projection_includes_progress(tmp_path: Path) -> None:
    from offline_rag.api.workspace_views import operation_view

    settings = _settings(tmp_path)
    settings.paths.workspaces.mkdir(parents=True, exist_ok=True)
    ops = ManagedOperationStore(settings)
    rec, _ = ops.reserve(
        workspace_id="ws_1",
        idempotency_key="prog-api",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["a.pdf"]},
        expected_revision=1,
    )
    ops.update_status(
        rec.workspace_id,
        rec.operation_id,
        ManagedOperationStatus.RUNNING,
        progress_stage=OperationProgressStage.BUILDING_INDEXES,
    )
    updated = ops.update_progress(
        rec.workspace_id,
        rec.operation_id,
        step=ManagedOperationProgressStep.EMBEDDING_CHUNKS,
        current=3,
        total=10,
        unit=ManagedOperationProgressUnit.CHUNKS,
    )
    view = operation_view(updated)
    assert view["progress"]["step"] == "embedding_chunks"
    assert view["progress"]["current"] == 3
    assert view["progress"]["total"] == 10
    assert view["progress"]["unit"] == "chunks"
    assert "started_at" in view["progress"]
    blob = str(view)
    assert "staging" not in blob
    assert "/home/" not in blob


def test_dense_embedding_progress_monotonic(tmp_path: Path) -> None:
    from offline_rag.chunking.pipeline import run_chunking
    from offline_rag.chunking.tokenize import FakeTokenCounter
    from offline_rag.dense.embedder import FakeEmbedder
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.dense.qdrant_local import QdrantLocalBackend
    from offline_rag.ingestion.pipeline import run_ingestion

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
                            "adapter_contract": "fake-embedder-v1",
                            "batch_size": 2,
                        }
                    )
                }
            ),
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
    ):
        path.mkdir(parents=True, exist_ok=True)

    src = settings.paths.raw_data / "a.txt"
    src.write_text("Alpha paragraph one.\n\nBeta paragraph two.\n\nGamma paragraph three.\n")
    ingest = run_ingestion(settings=settings, inputs=[src], corpus_name="default")
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(
        settings=settings, corpus_name="default", token_counter=FakeTokenCounter()
    )
    assert chunk.status.value in {"success", "no_op"}

    events: list[ProgressEvent] = []
    backend = QdrantLocalBackend(settings.paths.qdrant_storage)
    report = run_indexing(
        settings=settings,
        corpus_name="default",
        embedder=FakeEmbedder(dimension=8),
        backend=backend,
        on_progress=events.append,
    )
    assert report.status.value in {"success", "no_op"}
    embed_events = [e for e in events if e.step == "embedding_chunks"]
    assert embed_events
    currents = [e.current for e in embed_events]
    assert currents == sorted(currents)
    assert embed_events[-1].current == embed_events[-1].total
    assert any(e.step == "materializing_dense_index" for e in events)
