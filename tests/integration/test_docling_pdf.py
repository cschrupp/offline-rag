"""Required Docling PDF integration tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from offline_rag.config import load_settings
from offline_rag.core.ids import document_id_from_bytes
from offline_rag.domain.blocks import ContentType, ParsedDocument
from offline_rag.ingestion.docling_artifacts import validate_docling_artifacts
from offline_rag.ingestion.docling_parser import DoclingPdfParser
from offline_rag.ingestion.pipeline import run_ingestion

PDF = Path(__file__).resolve().parents[1] / "fixtures" / "ingestion" / "pdf" / "born_digital_reference.pdf"
EXPECTED_SHA256 = "d81dc0d89641eb0cad9176051865e1ef13e8ee77f926f3f157e935eac08cfcbf"
ARTIFACTS = Path(__file__).resolve().parents[2] / "models" / "docling"


@pytest.mark.integration
def test_pdf_fixture_checksum() -> None:
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256


@pytest.mark.integration
def test_docling_born_digital_pdf_parse() -> None:
    status = validate_docling_artifacts(ARTIFACTS)
    assert status.ready, (
        f"Docling artifacts not provisioned at {ARTIFACTS}: {status.reason}. "
        "Run: uv run python scripts/provision_docling.py"
    )

    raw = PDF.read_bytes()
    doc_id = document_id_from_bytes(raw)
    parser = DoclingPdfParser(
        artifacts_path=ARTIFACTS,
        strict_offline=True,
        ocr_enabled=False,
    )
    parsed = parser.parse(PDF, source_bytes=raw, document_id=doc_id)
    assert isinstance(parsed, ParsedDocument)
    assert parsed.parser_name == "docling_pdf"
    assert parsed.document.document_id == doc_id

    text_blob = "\n".join(block.text for block in parsed.blocks)
    assert "OFFLINERAG_FIXTURE_PAGE_1" in text_blob
    assert "OFFLINERAG_FIXTURE_PAGE_2" in text_blob
    assert "OFFLINERAG_FIXTURE_PAGE_3" in text_blob
    assert "Alpha" in text_blob
    assert "Beta" in text_blob
    assert "Gamma" in text_blob
    assert "15,000 psi" in text_blob or "15,000" in text_blob

    # Page provenance for sentinels when page numbers are available.
    by_page = {}
    for block in parsed.blocks:
        for sentinel in (
            "OFFLINERAG_FIXTURE_PAGE_1",
            "OFFLINERAG_FIXTURE_PAGE_2",
            "OFFLINERAG_FIXTURE_PAGE_3",
        ):
            if sentinel in block.text and block.page_number is not None:
                by_page[sentinel] = block.page_number
    if by_page:
        assert by_page.get("OFFLINERAG_FIXTURE_PAGE_1") == 1
        assert by_page.get("OFFLINERAG_FIXTURE_PAGE_2") == 2
        assert by_page.get("OFFLINERAG_FIXTURE_PAGE_3") == 3

    assert any(block.content_type == ContentType.HEADING for block in parsed.blocks) or any(
        "System Overview" in block.text for block in parsed.blocks
    )

    restored = ParsedDocument.model_validate_json(parsed.model_dump_json())
    assert restored.model_dump(mode="json") == parsed.model_dump(mode="json")
    # Ensure no accidental Docling types in serialization values.
    dumped = parsed.model_dump(mode="json")
    assert "docling.document" not in str(type(dumped))


@pytest.mark.integration
def test_ingest_pdf_via_pipeline(tmp_path: Path) -> None:
    status = validate_docling_artifacts(ARTIFACTS)
    assert status.ready, status.reason
    settings = load_settings(yaml_paths=[], environ={})
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "processed": tmp_path / "processed",
                    "manifests": tmp_path / "manifests",
                    "corpora": tmp_path / "corpora",
                    "docling_artifacts": ARTIFACTS,
                }
            )
        }
    )
    report = run_ingestion(settings=settings, inputs=[PDF], corpus_name="pdfdemo")
    assert report.status.value in {"success", "no_op"}
    assert report.files_failed == 0
    assert report.corpus_id
