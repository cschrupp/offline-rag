"""Chunking pipeline persistence, reuse, failure, and staleness tests."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.persistence import (
    chunk_state_path,
    load_chunk_artifact,
    load_chunk_state,
    write_chunk_artifact,
)
from offline_rag.chunking.pipeline import (
    build_chunk_config_hash,
    chunking_status_for_corpus,
    make_token_counter,
    run_chunking,
)
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.domain.chunking import ChunkingStatus
from offline_rag.ingestion.pipeline import run_ingestion


def _settings(tmp_path: Path) -> AppSettings:
    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": tmp_path / "raw",
                    "manifests": tmp_path / "manifests",
                    "processed": tmp_path / "processed",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                    "qdrant_storage": tmp_path / "qdrant",
                    "retrieval_models": tmp_path / "models",
                    "docling_artifacts": tmp_path / "models" / "docling",
                    "tokenizer_artifacts": tmp_path / "models" / "tokenizers" / "tiktoken",
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
            "project": settings.project.model_copy(update={"strict_offline": False}),
        }
    )
    for path in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.eval_results,
        settings.paths.docling_artifacts,
        settings.paths.tokenizer_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _ingest_two_docs(settings: AppSettings, docs: Path) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "a.txt").write_text("# Intro\n\none two three four five\n", encoding="utf-8")
    (docs / "b.txt").write_text("# Methods\n\nsix seven eight nine ten\n", encoding="utf-8")
    report = run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    assert report.status.value in {"success", "no_op"}


def test_chunk_reuse_and_noop(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _ingest_two_docs(settings, docs)
    counter = FakeTokenCounter()

    first = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert first.status == ChunkingStatus.SUCCESS
    assert first.documents_chunked == 2
    assert first.documents_reused == 0
    assert first.chunk_set_id is not None

    second = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert second.status == ChunkingStatus.NO_OP
    assert second.documents_chunked == 0
    assert second.documents_reused == 2
    assert second.chunk_set_id == first.chunk_set_id
    assert chunking_status_for_corpus(settings, "eng") == "CURRENT"


def test_changed_document_rechunks_only_affected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _ingest_two_docs(settings, docs)
    counter = FakeTokenCounter()
    first = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert first.documents_chunked == 2

    (docs / "a.txt").write_text("# Intro\n\nchanged content alpha beta gamma\n", encoding="utf-8")
    ingest = run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    assert ingest.files_updated >= 1

    second = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert second.status == ChunkingStatus.SUCCESS
    assert second.documents_chunked == 1
    assert second.documents_reused == 1
    assert second.chunk_set_id != first.chunk_set_id


def test_failure_preserves_artifacts_and_state(tmp_path: Path, monkeypatch: object) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _ingest_two_docs(settings, docs)
    counter = FakeTokenCounter()
    first = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert first.status == ChunkingStatus.SUCCESS
    state_before = load_chunk_state(chunk_state_path(settings.paths.corpora, "eng"))

    # Force second document to fail after first artifact path exists by deleting processed for one.
    from offline_rag.ingestion.persistence import (
        load_corpus_manifest,
        load_corpus_state,
    )

    corpus_state = load_corpus_state(settings.paths.corpora / "eng" / "state.json")
    manifest = load_corpus_manifest(settings.paths.manifests / Path(corpus_state.current_manifest).name)
    # Remove all chunk artifacts and break one parsed artifact to force partial failure.
    for path in settings.paths.chunks.glob("*.json"):
        path.unlink()
    broken = settings.paths.processed / f"{manifest.documents[1].parsed_artifact_id}.json"
    broken.write_text("{not-json", encoding="utf-8")

    failed = run_chunking(settings=settings, corpus_name="eng", token_counter=counter)
    assert failed.status == ChunkingStatus.FAILED
    state_after = load_chunk_state(chunk_state_path(settings.paths.corpora, "eng"))
    assert state_after.current_chunk_set_id == state_before.current_chunk_set_id
    # First document may still have been written as immutable cache.
    assert any(settings.paths.chunks.glob("*.json"))


def test_staleness_after_newer_ingest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _ingest_two_docs(settings, docs)
    run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())
    assert chunking_status_for_corpus(settings, "eng") == "CURRENT"

    (docs / "c.txt").write_text("new doc text\n", encoding="utf-8")
    run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    assert chunking_status_for_corpus(settings, "eng") == "STALE"


def test_chunk_artifact_roundtrip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _ingest_two_docs(settings, docs)
    report = run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())
    entry = report.documents[0]
    assert entry.chunk_artifact_id
    path = settings.paths.chunks / f"{entry.chunk_artifact_id}.json"
    artifact = load_chunk_artifact(path)
    restored_path, digest = write_chunk_artifact(settings.paths.chunks, artifact)
    assert restored_path == path
    assert digest.startswith("art_")


def test_config_hash_includes_budgets() -> None:
    settings = AppSettings()
    base = build_chunk_config_hash(settings.chunking)
    changed = build_chunk_config_hash(
        settings.chunking.model_copy(
            update={"child": settings.chunking.child.model_copy(update={"max_tokens": 400})}
        )
    )
    assert base != changed


def test_make_token_counter_fake() -> None:
    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "chunking": settings.chunking.model_copy(
                update={
                    "tokenizer": settings.chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            )
        }
    )
    counter = make_token_counter(settings)
    assert counter.name == "fake"
