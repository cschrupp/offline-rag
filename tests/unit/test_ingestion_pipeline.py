"""Ingestion pipeline unit tests for TXT/Markdown (no Docling artifacts)."""

from __future__ import annotations

from pathlib import Path

from offline_rag.config import load_settings
from offline_rag.domain.ingestion import FileIngestionStatus, IngestionStatus
from offline_rag.ingestion.pipeline import run_ingestion


def _settings(tmp_path: Path):
    settings = load_settings(yaml_paths=[], environ={})
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "processed": tmp_path / "processed",
                    "manifests": tmp_path / "manifests",
                    "corpora": tmp_path / "corpora",
                    "docling_artifacts": tmp_path / "docling",
                }
            )
        }
    )


def test_ingest_idempotent_reuse(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("hello world\n\nsecond\n", encoding="utf-8")
    settings = _settings(tmp_path)

    first = run_ingestion(settings=settings, inputs=[docs], corpus_name="default")
    assert first.status == IngestionStatus.SUCCESS
    assert first.files_parsed == 1
    assert first.corpus_id

    second = run_ingestion(settings=settings, inputs=[docs], corpus_name="default")
    assert second.status == IngestionStatus.NO_OP
    assert second.files_reused == 1
    assert second.files_parsed == 0
    assert second.corpus_id == first.corpus_id


def test_additive_corpus_and_isolation(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("aaa\n", encoding="utf-8")
    (docs / "b.txt").write_text("bbb\n", encoding="utf-8")
    settings = _settings(tmp_path)

    first = run_ingestion(settings=settings, inputs=[docs / "a.txt"], corpus_name="alpha")
    assert first.files_added == 1
    second = run_ingestion(settings=settings, inputs=[docs / "b.txt"], corpus_name="alpha")
    assert second.status == IngestionStatus.SUCCESS
    assert second.corpus_id != first.corpus_id

    # Partial re-ingest of A must keep B.
    third = run_ingestion(settings=settings, inputs=[docs / "a.txt"], corpus_name="alpha")
    assert third.status == IngestionStatus.NO_OP
    assert third.corpus_id == second.corpus_id

    other = run_ingestion(settings=settings, inputs=[docs / "a.txt"], corpus_name="beta")
    assert other.corpus_id  # may match content snapshot, but state is isolated
    assert (tmp_path / "corpora" / "alpha" / "state.json").exists()
    assert (tmp_path / "corpora" / "beta" / "state.json").exists()


def test_failed_file_does_not_commit_state(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ok.txt").write_text("ok\n", encoding="utf-8")
    (docs / "bad.pdf").write_bytes(b"%PDF-1.4 broken")
    settings = _settings(tmp_path)

    report = run_ingestion(settings=settings, inputs=[docs], corpus_name="default")
    assert report.status == IngestionStatus.FAILED
    assert report.corpus_id is None
    assert any(item.status == FileIngestionStatus.FAILED for item in report.files)
    assert not (tmp_path / "corpora" / "default" / "state.json").exists()
