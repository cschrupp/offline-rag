"""Ingestion pipeline unit tests for TXT/Markdown (no Docling artifacts)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.config import load_settings
from offline_rag.domain.blocks import (
    ContentBlock,
    ContentType,
    ParsedDocument,
    ParseWarning,
    WarningCategory,
)
from offline_rag.domain.documents import Document
from offline_rag.domain.ingestion import FileIngestionStatus, IngestionStatus
from offline_rag.ingestion.docling_parser import DoclingPdfParser
from offline_rag.ingestion.persistence import write_parsed_document
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


def _parsed_pdf(
    *,
    path: Path,
    document_id: str,
    content_hash: str,
    body: str | None,
    include_ocr_warning: bool,
    parse_config_hash: str = "f" * 64,
) -> ParsedDocument:
    blocks = []
    if body:
        blocks.append(
            ContentBlock(
                id=f"{document_id}_block_0",
                document_id=document_id,
                order=0,
                content_type=ContentType.TEXT,
                text=body,
            )
        )
    warnings = []
    if include_ocr_warning:
        warnings.append(
            ParseWarning(
                category=WarningCategory.OCR_REQUIRED,
                message="OCR is disabled.",
                source_path=path.name,
            )
        )
    return ParsedDocument(
        document=Document(
            document_id=document_id,
            source_uri=path.name,
            title=path.stem,
            mime_type="application/pdf",
            content_hash=content_hash,
            ingested_at=datetime(1970, 1, 1, tzinfo=UTC),
            parser_version="synthetic",
        ),
        blocks=blocks,
        parser_name="docling_pdf",
        parser_version="synthetic",
        warnings=warnings,
        parse_config_hash=parse_config_hash,
    )


def _patch_pdf_parser(monkeypatch: pytest.MonkeyPatch, parsed_factory) -> None:
    monkeypatch.setattr(DoclingPdfParser, "parse_config_hash", lambda self: "f" * 64)

    def parse(self, path, *, document_id, content_hash):
        return parsed_factory(path, document_id, content_hash)

    monkeypatch.setattr(DoclingPdfParser, "parse", parse)


def test_empty_ocr_required_pdf_rejects_mixed_batch_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.app.ingest import _map_ingestion_failure

    docs = tmp_path / "docs"
    docs.mkdir()
    existing = docs / "existing.txt"
    existing.write_text("Previously published source.\n", encoding="utf-8")
    settings = _settings(tmp_path)
    initial = run_ingestion(settings=settings, inputs=[existing], corpus_name="default")
    assert initial.status == IngestionStatus.SUCCESS
    state_path = tmp_path / "corpora" / "default" / "state.json"
    state_before = state_path.read_bytes()

    added = docs / "valid-new.txt"
    added.write_text("A valid additional source.\n", encoding="utf-8")
    scanned = docs / "scanned.pdf"
    scanned.write_bytes(b"%PDF synthetic scanned file")

    def parsed_factory(path: Path, document_id: str, content_hash: str):
        if path.suffix == ".pdf":
            return _parsed_pdf(
                path=path,
                document_id=document_id,
                content_hash=content_hash,
                body=None,
                include_ocr_warning=True,
            )
        raise AssertionError("TXT parser is not replaced")

    _patch_pdf_parser(monkeypatch, parsed_factory)
    report = run_ingestion(
        settings=settings, inputs=[added, scanned], corpus_name="default"
    )

    assert report.status == IngestionStatus.FAILED
    assert report.metadata["failure_class"] == "document"
    assert report.metadata["failure_reason"] == "ocr_required"
    failed_pdf = next(
        item for item in report.files if item.source_name == "scanned.pdf"
    )
    assert failed_pdf.metadata["failure_reason"] == "ocr_required"
    error = _map_ingestion_failure(report)
    assert error.code.value == "document_invalid"
    assert error.details["reason"] == "ocr_required"
    assert "ocr tool" in failed_pdf.error.lower()
    assert state_path.read_bytes() == state_before


def test_cached_empty_ocr_required_pdf_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.core.ids import content_hash_from_path, parsed_artifact_id

    docs = tmp_path / "docs"
    docs.mkdir()
    scanned = docs / "scanned.pdf"
    scanned.write_bytes(b"%PDF synthetic scanned file")
    settings = _settings(tmp_path)
    content_hash = content_hash_from_path(scanned)
    document_id = f"doc_{content_hash}"
    cfg_hash = "f" * 64
    parsed = _parsed_pdf(
        path=scanned,
        document_id=document_id,
        content_hash=content_hash,
        body=None,
        include_ocr_warning=True,
        parse_config_hash=cfg_hash,
    ).model_copy(
        update={
            "parsed_artifact_id": parsed_artifact_id(document_id, cfg_hash),
        }
    )
    write_parsed_document(settings.paths.processed, parsed)

    _patch_pdf_parser(
        monkeypatch,
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("cached parsed artifact should be reused")
        ),
    )
    report = run_ingestion(settings=settings, inputs=[scanned], corpus_name="default")
    assert report.status == IngestionStatus.FAILED
    assert report.files_reused == 0
    assert report.metadata["failure_reason"] == "ocr_required"
    assert not (tmp_path / "corpora" / "default" / "state.json").exists()


@pytest.mark.parametrize(
    ("body", "warning"),
    [
        ("Short but useful.", True),
        ("Partial native text from one page of a larger scan.", False),
    ],
)
def test_pdf_with_usable_blocks_remains_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    warning: bool,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    pdf = docs / "partially-readable.pdf"
    pdf.write_bytes(b"%PDF synthetic text-bearing file")
    settings = _settings(tmp_path)

    _patch_pdf_parser(
        monkeypatch,
        lambda path, document_id, content_hash: _parsed_pdf(
            path=path,
            document_id=document_id,
            content_hash=content_hash,
            body=body,
            include_ocr_warning=warning,
        ),
    )
    report = run_ingestion(settings=settings, inputs=[pdf], corpus_name="default")
    assert report.status == IngestionStatus.SUCCESS
    assert report.files_parsed == 1
    assert report.blocks_total == 1
