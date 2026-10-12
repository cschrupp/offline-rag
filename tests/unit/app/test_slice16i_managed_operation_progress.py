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


def _failing_reporter(_event: ProgressEvent) -> None:
    raise RuntimeError("deliberate progress telemetry failure")


def _ingest_science(report) -> tuple:
    return (
        report.status.value,
        report.corpus_id,
        report.files_discovered,
        report.files_parsed,
        report.files_failed,
        report.files_added,
        tuple(
            sorted(
                (
                    item.source_path,
                    item.status.value,
                    item.document_id,
                    item.error,
                )
                for item in report.files
            )
        ),
    )


def _chunk_science(report) -> tuple:
    return (
        report.status.value,
        report.corpus_id,
        report.chunk_set_id,
        report.chunk_config_hash,
        report.documents_total,
        report.documents_chunked,
        report.documents_failed,
        report.parent_chunks,
        report.child_chunks,
        tuple(
            sorted(
                (d.document_id, d.status.value, d.chunk_artifact_id)
                for d in report.documents
            )
        ),
    )


def _dense_science(report) -> tuple:
    return (
        report.status.value,
        report.corpus_id,
        report.chunk_set_id,
        report.index_id,
        report.index_config_hash,
        report.embedding_config_hash,
        report.children_total,
        report.embeddings_generated,
        report.embeddings_reused,
        report.vectors_materialized,
    )


def _lexical_science(report) -> tuple:
    return (
        report.status.value,
        report.corpus_id,
        report.chunk_set_id,
        report.lexical_index_id,
        report.lexical_config_hash,
        report.children_total,
        report.indexed_child_count,
        report.vocabulary_size,
    )


def _pipeline_settings(tmp_path: Path) -> AppSettings:
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
                    "lexical": tmp_path / "lexical",
                    "lexical_indexes": tmp_path / "lexical-indexes",
                    "lexical_index_manifests": tmp_path / "lexical-index-manifests",
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
        settings.paths.lexical,
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def test_report_progress_isolates_reporter_exceptions() -> None:
    from offline_rag.core.progress import report_progress

    report_progress(
        None,
        step="parsing_documents",
        current=0,
        total=1,
        unit="documents",
    )
    seen: list[ProgressEvent] = []
    report_progress(
        seen.append,
        step="parsing_documents",
        current=1,
        total=1,
        unit="documents",
    )
    assert len(seen) == 1
    report_progress(
        _failing_reporter,
        step="parsing_documents",
        current=1,
        total=1,
        unit="documents",
    )


def test_ingestion_progress_and_failing_reporter_identity(tmp_path: Path) -> None:
    from offline_rag.domain.ingestion import FileIngestionStatus, IngestionStatus
    from offline_rag.ingestion.pipeline import run_ingestion

    docs_a = tmp_path / "docs_a"
    docs_b = tmp_path / "docs_b"
    docs_c = tmp_path / "docs_c"
    for docs in (docs_a, docs_b, docs_c):
        docs.mkdir()
        (docs / "a.txt").write_text("Alpha one.\n\nAlpha two.\n", encoding="utf-8")
        (docs / "b.txt").write_text("Beta one.\n\nBeta two.\n", encoding="utf-8")
        (docs / "bad.pdf").write_bytes(b"%PDF-1.4 broken")

    settings_a = _pipeline_settings(tmp_path / "root_a")
    settings_b = _pipeline_settings(tmp_path / "root_b")
    settings_c = _pipeline_settings(tmp_path / "root_c")

    baseline = run_ingestion(
        settings=settings_a, inputs=[docs_a], corpus_name="default", recursive=False
    )
    events: list[ProgressEvent] = []
    recorded = run_ingestion(
        settings=settings_b,
        inputs=[docs_b],
        corpus_name="default",
        recursive=False,
        on_progress=events.append,
    )
    isolated = run_ingestion(
        settings=settings_c,
        inputs=[docs_c],
        corpus_name="default",
        recursive=False,
        on_progress=_failing_reporter,
    )

    assert baseline.status is IngestionStatus.FAILED
    assert _ingest_science(baseline) == _ingest_science(recorded) == _ingest_science(isolated)
    assert any(f.status is FileIngestionStatus.FAILED for f in recorded.files)
    parse_events = [e for e in events if e.step == "parsing_documents"]
    assert parse_events[0].current == 0
    assert parse_events[0].total == 3
    assert parse_events[-1].current == parse_events[-1].total == 3
    currents = [e.current for e in parse_events]
    assert currents == sorted(currents)


def test_chunking_progress_identity(tmp_path: Path) -> None:
    from offline_rag.chunking.pipeline import run_chunking
    from offline_rag.chunking.tokenize import FakeTokenCounter
    from offline_rag.ingestion.pipeline import run_ingestion

    def _prepare(root: Path) -> AppSettings:
        settings = _pipeline_settings(root)
        docs = root / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("Alpha paragraph one.\n\nAlpha paragraph two.\n")
        (docs / "b.txt").write_text("Beta paragraph one.\n\nBeta paragraph two.\n")
        ingest = run_ingestion(
            settings=settings, inputs=[docs], corpus_name="eng", recursive=False
        )
        assert ingest.status.value in {"success", "no_op"}
        return settings

    settings_a = _prepare(tmp_path / "chunk_a")
    settings_b = _prepare(tmp_path / "chunk_b")
    events: list[ProgressEvent] = []
    base = run_chunking(
        settings=settings_a, corpus_name="eng", token_counter=FakeTokenCounter()
    )
    recorded = run_chunking(
        settings=settings_b,
        corpus_name="eng",
        token_counter=FakeTokenCounter(),
        on_progress=events.append,
    )
    assert _chunk_science(base) == _chunk_science(recorded)
    chunk_events = [e for e in events if e.step == "chunking_documents"]
    assert chunk_events[0].current == 0
    assert chunk_events[-1].current == chunk_events[-1].total == 2


def test_dense_progress_identity(tmp_path: Path) -> None:
    from offline_rag.chunking.pipeline import run_chunking
    from offline_rag.chunking.tokenize import FakeTokenCounter
    from offline_rag.dense.embedder import FakeEmbedder
    from offline_rag.dense.pipeline import run_indexing
    from offline_rag.dense.qdrant_local import QdrantLocalBackend
    from offline_rag.ingestion.pipeline import run_ingestion

    def _prepare(root: Path) -> AppSettings:
        settings = _pipeline_settings(root)
        docs = settings.paths.raw_data
        (docs / "a.txt").write_text("Alpha paragraph one.\n\nAlpha paragraph two.\n")
        (docs / "b.txt").write_text("Beta paragraph one.\n\nBeta paragraph two.\n")
        assert run_ingestion(
            settings=settings, inputs=[docs], corpus_name="eng", recursive=False
        ).status.value in {"success", "no_op"}
        assert run_chunking(
            settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
        ).status.value in {"success", "no_op"}
        return settings

    settings_a = _prepare(tmp_path / "dense_a")
    settings_b = _prepare(tmp_path / "dense_b")
    events: list[ProgressEvent] = []
    base = run_indexing(
        settings=settings_a,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8),
        backend=QdrantLocalBackend(settings_a.paths.qdrant_storage),
    )
    recorded = run_indexing(
        settings=settings_b,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8),
        backend=QdrantLocalBackend(settings_b.paths.qdrant_storage),
        on_progress=events.append,
    )
    assert _dense_science(base) == _dense_science(recorded)
    assert base.index_id == recorded.index_id
    embed_events = [e for e in events if e.step == "embedding_chunks"]
    assert embed_events
    assert embed_events[-1].current == embed_events[-1].total
    assert any(e.step == "materializing_dense_index" for e in events)


def test_lexical_progress_identity(tmp_path: Path) -> None:
    from offline_rag.chunking.pipeline import run_chunking
    from offline_rag.chunking.tokenize import FakeTokenCounter
    from offline_rag.ingestion.pipeline import run_ingestion
    from offline_rag.lexical.pipeline import run_lexical_indexing

    def _prepare(root: Path) -> AppSettings:
        settings = _pipeline_settings(root)
        docs = settings.paths.raw_data
        (docs / "a.txt").write_text(
            "Beta tool maximum pressure is 15000 psi for continuous operation.\n"
        )
        (docs / "b.txt").write_text(
            "Alpha sensor temperature rating is 175 deg C under load.\n"
        )
        assert run_ingestion(
            settings=settings, inputs=[docs], corpus_name="eng", recursive=False
        ).status.value in {"success", "no_op"}
        assert run_chunking(
            settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
        ).status.value in {"success", "no_op"}
        return settings

    settings_a = _prepare(tmp_path / "lex_a")
    settings_b = _prepare(tmp_path / "lex_b")
    events: list[ProgressEvent] = []
    base = run_lexical_indexing(settings=settings_a, corpus_name="eng")
    recorded = run_lexical_indexing(
        settings=settings_b, corpus_name="eng", on_progress=events.append
    )
    assert _lexical_science(base) == _lexical_science(recorded)
    assert base.lexical_index_id == recorded.lexical_index_id
    analyze = [e for e in events if e.step == "analyzing_lexical_chunks"]
    assert analyze[0].current == 0
    assert analyze[-1].current == analyze[-1].total
    currents = [e.current for e in analyze]
    assert currents == sorted(currents)
    assert any(e.step == "materializing_lexical_index" for e in events)


def test_gold_propose_progress_identity(tmp_path: Path) -> None:
    import json

    from offline_rag.config.models import AuthoringSettings
    from offline_rag.domain.documents import Chunk, ChunkKind
    from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
    from offline_rag.gold_authoring.propose import run_gold_propose_on_snapshot

    class Scripted:
        def __init__(self, responses: list[str]) -> None:
            self.responses = list(responses)

        def propose(self, *, system_prompt: str, user_content: str) -> str:
            _ = system_prompt, user_content
            return self.responses.pop(0)

        def close(self) -> None:
            return None

    def _chunk(cid: str, text: str) -> Chunk:
        return Chunk(
            chunk_id=cid,
            document_id="doc_a",
            kind=ChunkKind.CHILD,
            text=text,
            order=0,
            token_count=8,
            content_type="text",
            content_hash="hash",
            source_block_ids=["b1"],
            section_path=["SECTION"],
        )

    def _science(run) -> tuple:
        return (
            run.successful_count,
            run.failed_count,
            tuple(run.selected_chunk_ids),
            tuple(
                (
                    a.status.value,
                    None if a.failure_reason is None else a.failure_reason.value,
                    None if a.proposal is None else a.proposal.query,
                )
                for a in run.attempts
            ),
            tuple(sorted(c.proposed_query or "" for c in run.cases)),
            run.chunk_set_id,
            run.authorcfg_id,
        )

    settings = AppSettings(
        authoring=AuthoringSettings(
            enabled=True,
            model="test-model",
            approved_models=["test-model"],
            approved_endpoints=["http://127.0.0.1:11434/v1"],
            base_url="http://127.0.0.1:11434/v1",
            api_key="author-secret",
            network_policy="localhost_only",
        )
    )
    chunks = [
        _chunk("chunk_00", "Useful technical sentence number 0."),
        _chunk("chunk_01", "Useful technical sentence number 1."),
        _chunk("chunk_02", "Useful technical sentence number 2."),
    ]
    snapshot = CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_demo",
        chunks=chunks,
        source_name_by_document_id={"doc_a": "Module 1.pdf"},
    )
    responses = [
        json.dumps(
            {
                "query": "What is useful technical sentence number 0?",
                "category": "fact",
                "tags": ["demo"],
                "rationale": None,
            }
        ),
        "{not-json",
        json.dumps(
            {
                "query": "What is useful technical sentence number 2?",
                "category": None,
                "tags": [],
                "rationale": None,
            }
        ),
    ]

    events: list[ProgressEvent] = []
    base = run_gold_propose_on_snapshot(
        settings,
        snapshot=snapshot,
        authoring_run_id="authorrun_base",
        count=3,
        seed=0,
        output=tmp_path / "base.json",
        adapter=Scripted(list(responses)),  # type: ignore[arg-type]
    )
    recorded = run_gold_propose_on_snapshot(
        settings,
        snapshot=snapshot,
        authoring_run_id="authorrun_rec",
        count=3,
        seed=0,
        output=tmp_path / "rec.json",
        adapter=Scripted(list(responses)),  # type: ignore[arg-type]
        on_progress=events.append,
    )
    assert base.run is not None and recorded.run is not None
    assert _science(base.run) == _science(recorded.run)
    propose_events = [e for e in events if e.step == "proposing_questions"]
    assert propose_events[0].current == 0
    assert propose_events[-1].current == propose_events[-1].total == 3
    # Rejected/failed attempts still increment the attempt counter.
    assert any(a.status.value != "succeeded" for a in recorded.run.attempts)


def test_gold_pool_progress_identity(tmp_path: Path) -> None:
    from datetime import UTC, datetime
    from unittest.mock import patch

    from offline_rag.domain.documents import Chunk, ChunkKind
    from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
    from offline_rag.gold_authoring.contracts import (
        POOLING_CONTRACT,
        POOLING_DEPTHS,
        POOLING_RETRIEVER_IDS,
        RETRIEVER_DENSE_ARM_H_V1,
        RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
        RETRIEVER_DENSE_PLAIN_V1,
        RETRIEVER_HYBRID_RERANK_V1,
        RETRIEVER_HYBRID_RRF_V1,
        RETRIEVER_LEXICAL_PLAIN_V1,
    )
    from offline_rag.gold_authoring.models import (
        GoldAuthoringRun,
        SilverCase,
        SourceSeed,
    )
    from offline_rag.gold_authoring.persist import (
        load_authoring_run,
        write_authoring_run,
    )
    from offline_rag.gold_authoring.pool import run_gold_pool
    from offline_rag.gold_authoring.pool_arms import ArmExecutionError
    from offline_rag.gold_authoring.pool_preflight import ResolvedPoolingArtifacts
    from offline_rag.gold_authoring.pooling_models import (
        PoolFailureReason,
        PoolingProvenance,
        RetrievalHit,
    )

    def _artifacts() -> ResolvedPoolingArtifacts:
        return ResolvedPoolingArtifacts(
            chunk_set_id="chunkset_A",
            corpus_id="corpus_A",
            corpus_name="default",
            lexical_index_id="lex_A",
            dense_baseline_index_id="dense_A",
            dense_arm_h_index_id="dense_armh_A",
            provenance=PoolingProvenance(
                pooling_contract=POOLING_CONTRACT,
                source_chunk_set_id="chunkset_A",
                artifact_ids={
                    RETRIEVER_LEXICAL_PLAIN_V1: "lex_A",
                    RETRIEVER_DENSE_PLAIN_V1: "dense_A",
                    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: "dense_A",
                    RETRIEVER_DENSE_ARM_H_V1: "dense_armh_A",
                    RETRIEVER_HYBRID_RRF_V1: "hybrid(lex_A+dense_A)",
                    RETRIEVER_HYBRID_RERANK_V1: "hybrid-rerank(lex_A+dense_A)",
                },
            ),
        )

    class RecordingExecutor:
        def __init__(self, *, fail_second: bool = False) -> None:
            self.fail_second = fail_second
            self.calls = 0

        def execute_all(self, *, query: str, artifacts):
            _ = artifacts
            self.calls += 1
            if self.fail_second and self.calls == 2:
                raise ArmExecutionError(
                    "forced",
                    reason=PoolFailureReason.HYBRID_RERANK_FAILED,
                    retriever=RETRIEVER_HYBRID_RERANK_V1,
                )
            out = {}
            for arm in POOLING_RETRIEVER_IDS:
                depth = POOLING_DEPTHS[arm]
                out[arm] = [
                    RetrievalHit(retriever=arm, chunk_id="c1", rank=1, score=1.0)
                ][:depth]
            return out

    def _case(draft_id: str, query: str) -> SilverCase:
        return SilverCase(
            draft_case_id=draft_id,
            proposed_query=query,
            source_seed=SourceSeed(chunk_id="seed_1", document_id="doc_a"),
            candidates=[],
        )

    def _run(cases: list[SilverCase]) -> GoldAuthoringRun:
        return GoldAuthoringRun(
            authoring_run_id="authorrun_test",
            authorcfg_id="authorcfg_testhash",
            network_policy="localhost_only",
            corpus_id="corpus_A",
            corpus_name="default",
            chunk_set_id="chunkset_A",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            cases=cases,
        )

    def _science(path: Path) -> tuple:
        run = load_authoring_run(path)
        return (
            tuple(
                (
                    c.draft_case_id,
                    c.proposed_query,
                    tuple(
                        (
                            cand.chunk_id,
                            tuple(
                                (h.retriever, h.chunk_id, h.rank)
                                for h in cand.retrieval_hits
                            ),
                        )
                        for cand in c.candidates
                    ),
                )
                for c in run.cases
            ),
            tuple(
                (
                    o.draft_case_id,
                    o.status.value,
                    None if o.failure_reason is None else o.failure_reason.value,
                )
                for o in (run.pool_outcomes or [])
            ),
        )

    snap = CorpusChunkSnapshot(
        corpus_name="default",
        corpus_id="corpus_A",
        chunk_set_id="chunkset_A",
        chunks=[
            Chunk(
                chunk_id="c1",
                document_id="doc_a",
                kind=ChunkKind.CHILD,
                text="body",
                order=0,
                token_count=8,
                content_type="text",
                content_hash="hash",
                source_block_ids=["b1"],
                section_path=["SECTION"],
            )
        ],
        source_name_by_document_id={"doc_a": "Guide.pdf"},
    )
    arts = _artifacts()
    cases = [_case("d1", "what is ndm?"), _case("d2", "what is alpha?")]

    path_a = tmp_path / "pool_a.json"
    path_b = tmp_path / "pool_b.json"
    write_authoring_run(path_a, _run(cases))
    write_authoring_run(path_b, _run(cases))

    patches = (
        patch(
            "offline_rag.gold_authoring.pool.preflight_pooling_artifacts",
            return_value=arts,
        ),
        patch(
            "offline_rag.gold_authoring.pool._load_historical_snapshot",
            return_value=snap,
        ),
    )
    events: list[ProgressEvent] = []
    with patches[0], patches[1]:
        run_gold_pool(
            AppSettings(),
            run_path=path_a,
            executor=RecordingExecutor(fail_second=True),
        )
    with patches[0], patches[1]:
        run_gold_pool(
            AppSettings(),
            run_path=path_b,
            executor=RecordingExecutor(fail_second=True),
            on_progress=events.append,
        )
    assert _science(path_a) == _science(path_b)
    pool_events = [e for e in events if e.step == "pooling_cases"]
    assert pool_events[0].current == 0
    assert pool_events[-1].current == pool_events[-1].total == 2
    # Failed case still increments.
    assert any(
        o.status.value != "succeeded"
        for o in (load_authoring_run(path_b).pool_outcomes or [])
    )


def test_gold_prelabel_progress_identity(tmp_path: Path) -> None:
    import json
    from datetime import UTC, datetime
    from unittest.mock import patch

    from offline_rag.config.models import AuthoringSettings
    from offline_rag.domain.documents import Chunk, ChunkKind
    from offline_rag.gold_authoring.chunk_access import CorpusChunkSnapshot
    from offline_rag.gold_authoring.models import (
        GoldAuthoringRun,
        SilverCase,
        SourceSeed,
    )
    from offline_rag.gold_authoring.persist import (
        load_authoring_run,
        write_authoring_run,
    )
    from offline_rag.gold_authoring.pooling_models import PoolCandidate, RetrievalHit
    from offline_rag.gold_authoring.prelabel import run_gold_prelabel

    body_a = "UNIQUE_PRIVATE_BODY_A_16I"
    body_b = "UNIQUE_PRIVATE_BODY_B_16I"

    class ScriptedClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def prelabel(self, *, system_prompt: str, user_content: str) -> str:
            _ = system_prompt
            self.calls.append(user_content)
            body = user_content.split("CANDIDATE:\n", 1)[-1]
            grade = 2 if body_a in body else 0
            return json.dumps({"grade": grade, "rationale": f"Grade {grade}."})

        def close(self) -> None:
            return None

    def _candidate(chunk_id: str, *, rank: int = 1) -> PoolCandidate:
        return PoolCandidate(
            chunk_id=chunk_id,
            document_id="doc_a",
            document_title="Guide",
            section_path=["SECTION"],
            retrieval_hits=[
                RetrievalHit(
                    retriever="lexical-plain-v1",
                    chunk_id=chunk_id,
                    rank=rank,
                    score=1.0,
                )
            ],
        )

    def _case(draft_id: str) -> SilverCase:
        return SilverCase(
            draft_case_id=draft_id,
            proposed_query="What is NDM?",
            source_seed=SourceSeed(chunk_id="c_a", document_id="doc_a"),
            candidates=[_candidate("c_a", rank=1), _candidate("c_b", rank=2)],
        )

    def _run() -> GoldAuthoringRun:
        return GoldAuthoringRun(
            authoring_run_id="authorrun_test",
            authorcfg_id="authorcfg_testhash",
            network_policy="localhost_only",
            corpus_id="corpus_A",
            corpus_name="default",
            chunk_set_id="chunkset_A",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            cases=[_case("d1")],
        )

    def _science(path: Path) -> tuple:
        run = load_authoring_run(path)
        case = run.cases[0]
        return (
            tuple(
                (
                    j.chunk_id,
                    j.pass_id,
                    j.grade,
                    j.rationale,
                )
                for j in case.model_judgments
            ),
            None
            if case.prelabel_summary is None
            else case.prelabel_summary.model_dump(mode="json"),
            None
            if case.prelabel_provenance is None
            else case.prelabel_provenance.model_dump(mode="json"),
            tuple(c.chunk_id for c in case.candidates),
        )

    settings = AppSettings(
        authoring=AuthoringSettings(
            enabled=True,
            model="test-model",
            approved_models=["test-model"],
            approved_endpoints=["http://127.0.0.1:11434/v1"],
            base_url="http://127.0.0.1:11434/v1",
            api_key="author-secret",
            network_policy="localhost_only",
        )
    )
    snap = CorpusChunkSnapshot(
        corpus_name="default",
        corpus_id="corpus_A",
        chunk_set_id="chunkset_A",
        chunks=[
            Chunk(
                chunk_id="c_a",
                document_id="doc_a",
                kind=ChunkKind.CHILD,
                text=body_a,
                order=0,
                token_count=8,
                content_type="text",
                content_hash="hash",
                source_block_ids=["b1"],
                section_path=["SECTION"],
            ),
            Chunk(
                chunk_id="c_b",
                document_id="doc_a",
                kind=ChunkKind.CHILD,
                text=body_b,
                order=1,
                token_count=8,
                content_type="text",
                content_hash="hash",
                source_block_ids=["b2"],
                section_path=["SECTION"],
            ),
        ],
        source_name_by_document_id={"doc_a": "Guide.pdf"},
    )
    path_a = tmp_path / "pre_a.json"
    path_b = tmp_path / "pre_b.json"
    write_authoring_run(path_a, _run())
    write_authoring_run(path_b, _run())
    events: list[ProgressEvent] = []
    with patch(
        "offline_rag.gold_authoring.prelabel._load_historical_snapshot",
        return_value=snap,
    ):
        run_gold_prelabel(settings, run_path=path_a, adapter=ScriptedClient())  # type: ignore[arg-type]
        run_gold_prelabel(
            settings,
            run_path=path_b,
            adapter=ScriptedClient(),  # type: ignore[arg-type]
            on_progress=events.append,
        )
    assert _science(path_a) == _science(path_b)
    pre = [e for e in events if e.step == "prelabeling_candidates"]
    assert pre[0].current == 0
    assert pre[0].total == 4  # 2 candidates * 2 passes
    assert pre[-1].current == pre[-1].total == 4
    currents = [e.current for e in pre]
    assert currents == sorted(currents)


def test_durable_progress_publisher_throttling(tmp_path: Path) -> None:
    from offline_rag.app.progress_publish import DurableProgressPublisher
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationStatus,
    )
    from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
    from offline_rag.core.progress import ProgressEvent

    settings = _settings(tmp_path)
    settings.paths.workspaces.mkdir(parents=True, exist_ok=True)
    ops = ManagedOperationStore(settings)
    rec, _ = ops.reserve(
        workspace_id="ws_1",
        idempotency_key="throttle-1",
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

    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    pub = DurableProgressPublisher(
        operations=ops,
        workspace_id=rec.workspace_id,
        operation_id=rec.operation_id,
        clock=now,
    )

    total = 10000
    # Initial event at t=0.
    pub(
        ProgressEvent(
            step="analyzing_lexical_chunks",
            current=0,
            total=total,
            unit="chunks",
        )
    )
    assert pub.write_count == 1

    # Sub-1% advances within 1s must not all become durable writes.
    for current in range(1, 50):  # 0.5% at most
        clock["t"] = 0.01 * current
        pub(
            ProgressEvent(
                step="analyzing_lexical_chunks",
                current=current,
                total=total,
                unit="chunks",
            )
        )
    assert pub.write_count == 1

    # >=1 percentage-point advance writes.
    clock["t"] = 0.5
    pub(
        ProgressEvent(
            step="analyzing_lexical_chunks",
            current=100,  # 1%
            total=total,
            unit="chunks",
        )
    )
    assert pub.write_count == 2

    # Heartbeat ~1s even without percent advance.
    clock["t"] = 1.6
    pub(
        ProgressEvent(
            step="analyzing_lexical_chunks",
            current=150,  # still 1%
            total=total,
            unit="chunks",
        )
    )
    assert pub.write_count == 3

    # Many small increments must stay far below one-write-per-chunk.
    start_writes = pub.write_count
    for current in range(151, 5000):
        clock["t"] = 1.6 + (current - 151) * 0.0001  # stay under 1s between most
        pub(
            ProgressEvent(
                step="analyzing_lexical_chunks",
                current=current,
                total=total,
                unit="chunks",
            )
        )
    # Percent gates (~1% steps) dominate; nowhere near 5000 writes.
    assert pub.write_count - start_writes < 100
    assert pub.write_count < total / 10

    # Step transition always writes.
    clock["t"] = 2.0
    pub(
        ProgressEvent(
            step="materializing_lexical_index",
            current=0,
            total=None,
            unit="chunks",
        )
    )
    after_step = pub.write_count

    # Final current == total always writes (return to analyzing for bounded total).
    pub(
        ProgressEvent(
            step="analyzing_lexical_chunks",
            current=0,
            total=total,
            unit="chunks",
        )
    )
    clock["t"] = 3.0
    pub(
        ProgressEvent(
            step="analyzing_lexical_chunks",
            current=total,
            total=total,
            unit="chunks",
        )
    )
    assert pub.write_count >= after_step + 2
    final = ops.get(rec.workspace_id, rec.operation_id)
    assert final.progress is not None
    assert final.progress.current == total
    assert final.progress.total == total


def test_durable_publisher_contains_update_progress_failures(tmp_path: Path) -> None:
    from offline_rag.app.progress_publish import DurableProgressPublisher
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationStatus,
    )
    from offline_rag.core.progress import ProgressEvent

    settings = _settings(tmp_path)
    settings.paths.workspaces.mkdir(parents=True, exist_ok=True)
    ops = ManagedOperationStore(settings)
    rec, _ = ops.reserve(
        workspace_id="ws_1",
        idempotency_key="pub-iso-1",
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

    def boom(*_a, **_k):
        raise RuntimeError("deliberate progress persistence failure")

    ops.update_progress = boom  # type: ignore[method-assign]
    pub = DurableProgressPublisher(
        operations=ops,
        workspace_id=rec.workspace_id,
        operation_id=rec.operation_id,
    )
    pub(
        ProgressEvent(
            step="publishing",
            current=0,
            total=None,
            unit="documents",
        )
    )
    assert pub.write_count == 0
    # Coarse status was not touched by the telemetry path.
    current = ops.get(rec.workspace_id, rec.operation_id)
    assert current.status is ManagedOperationStatus.RUNNING
    assert current.progress_stage is OperationProgressStage.BUILDING_INDEXES


def test_lifecycle_publish_finalize_survive_progress_persistence_failure(
    tmp_path: Path,
) -> None:
    from offline_rag.app.workspace.lifecycle import WorkspaceLifecycleService
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationStatus,
    )

    settings = _settings(tmp_path)
    settings.paths.workspaces.mkdir(parents=True, exist_ok=True)
    ops = ManagedOperationStore(settings)
    rec, _ = ops.reserve(
        workspace_id="ws_1",
        idempotency_key="pub-iso-2",
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

    progress_calls = {"n": 0}

    def boom(*_a, **_k):
        progress_calls["n"] += 1
        raise RuntimeError("deliberate progress persistence failure")

    ops.update_progress = boom  # type: ignore[method-assign]

    svc = object.__new__(WorkspaceLifecycleService)
    svc.operations = ops
    hooks = WorkspaceLifecycleService._progress_hooks(
        svc, rec.workspace_id, rec.operation_id, None  # type: ignore[arg-type]
    )
    assert hooks.before_stage is not None
    assert hooks.after_stage is not None

    hooks.before_stage("publish")
    after_publish = ops.get(rec.workspace_id, rec.operation_id)
    assert after_publish.status is ManagedOperationStatus.RUNNING
    assert after_publish.progress_stage is OperationProgressStage.PUBLISHING
    assert progress_calls["n"] >= 1

    hooks.after_stage("publish")
    after_finalize = ops.get(rec.workspace_id, rec.operation_id)
    assert after_finalize.status is ManagedOperationStatus.RUNNING
    assert after_finalize.progress_stage is OperationProgressStage.FINALIZING
    assert progress_calls["n"] >= 2
