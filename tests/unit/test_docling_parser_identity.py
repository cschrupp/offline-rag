"""Parser-stack identity and artifact-reuse regression tests."""

from __future__ import annotations

from pathlib import Path

from offline_rag.core.ids import (
    DOCLING_PDF_PARSER_VERSION,
    MARKDOWN_PARSER_VERSION,
    TEXT_PARSER_VERSION,
    parse_config_hash,
    parsed_artifact_id,
)
from offline_rag.domain.blocks import ContentBlock, ContentType, ParsedDocument
from offline_rag.domain.documents import Document
from offline_rag.ingestion.docling_parser import DoclingPdfParser
from offline_rag.ingestion.markdown_parser import MarkdownParser
from offline_rag.ingestion.persistence import (
    processed_artifact_path,
    try_load_reusable_artifact,
    write_parsed_document,
)
from offline_rag.ingestion.text_parser import TextParser


def test_pdf_stack_version_changes_parse_and_artifact_identity(tmp_path: Path) -> None:
    parser = DoclingPdfParser(artifacts_path=tmp_path, ocr_enabled=False)
    old_config_hash = parse_config_hash(
        parser_name="docling_pdf",
        parser_version="offline-rag-docling-pdf-v1",
        ocr_enabled=False,
    )
    new_config_hash = parser.parse_config_hash()
    document_id = "doc_" + "a" * 64

    old_artifact_id = parsed_artifact_id(document_id, old_config_hash)
    new_artifact_id = parsed_artifact_id(document_id, new_config_hash)

    assert DOCLING_PDF_PARSER_VERSION == "offline-rag-docling-pdf-v2"
    assert new_config_hash != old_config_hash
    assert new_artifact_id != old_artifact_id


def test_old_pdf_artifact_is_not_reusable_under_new_stack(tmp_path: Path) -> None:
    parser = DoclingPdfParser(artifacts_path=tmp_path, ocr_enabled=False)
    document_id = "doc_" + "b" * 64
    old_config_hash = parse_config_hash(
        parser_name=parser.name,
        parser_version="offline-rag-docling-pdf-v1",
        ocr_enabled=False,
    )
    old_artifact_id = parsed_artifact_id(document_id, old_config_hash)
    historical_blocks = [
        ContentBlock(
            id=f"historical_{index}",
            document_id=document_id,
            order=index,
            content_type=ContentType.TEXT,
            text="legacy parser-stack block",
        )
        for index in range(2679)
    ]
    historical = ParsedDocument(
        document=Document(
            document_id=document_id,
            source_uri="representative.pdf",
            title="representative",
            mime_type="application/pdf",
            content_hash="b" * 64,
            ingested_at="1970-01-01T00:00:00Z",
            parser_version="offline-rag-docling-pdf-v1",
        ),
        blocks=historical_blocks,
        parser_name=parser.name,
        parser_version="offline-rag-docling-pdf-v1",
        parsed_artifact_id=old_artifact_id,
        parse_config_hash=old_config_hash,
        metadata={"docling_version": "2.126.0"},
    )
    write_parsed_document(tmp_path, historical)

    new_config_hash = parser.parse_config_hash()
    new_artifact_id = parsed_artifact_id(document_id, new_config_hash)
    assert processed_artifact_path(tmp_path, old_artifact_id).exists()
    assert try_load_reusable_artifact(
        tmp_path,
        new_artifact_id,
        expected_document_id=document_id,
        expected_parse_config_hash=new_config_hash,
    ) is None

    current_blocks = [
        ContentBlock(
            id=f"current_{index}",
            document_id=document_id,
            order=index,
            content_type=ContentType.TEXT,
            text="current parser-stack block",
        )
        for index in range(2641)
    ]
    current = historical.model_copy(
        update={
            "blocks": current_blocks,
            "parser_version": parser.version,
            "parse_config_hash": new_config_hash,
            "parsed_artifact_id": new_artifact_id,
            "metadata": {"parser_stack": parser.parser_stack_provenance()},
        }
    )
    persisted_path, _ = write_parsed_document(tmp_path, current)
    assert persisted_path == processed_artifact_path(tmp_path, new_artifact_id)
    reusable = try_load_reusable_artifact(
        tmp_path,
        new_artifact_id,
        expected_document_id=document_id,
        expected_parse_config_hash=new_config_hash,
    )
    assert reusable is not None
    assert reusable[0].parsed_artifact_id == new_artifact_id
    assert len(reusable[0].blocks) == 2641


def test_text_and_markdown_parser_identities_are_unchanged(tmp_path: Path) -> None:
    document_id = "doc_" + "c" * 64
    text = TextParser().parse(
        tmp_path / "sample.txt",
        document_id=document_id,
        content_hash="c" * 64,
        source_bytes=b"plain text",
    )
    markdown = MarkdownParser().parse(
        tmp_path / "sample.md",
        document_id=document_id,
        content_hash="c" * 64,
        source_bytes=b"# Heading\n\nMarkdown text",
    )

    assert TEXT_PARSER_VERSION == "offline-rag-text-v1"
    assert MARKDOWN_PARSER_VERSION == "offline-rag-markdown-v1"
    assert text.parse_config_hash == parse_config_hash(
        parser_name="text", parser_version="offline-rag-text-v1"
    )
    assert markdown.parse_config_hash == parse_config_hash(
        parser_name="markdown", parser_version="offline-rag-markdown-v1"
    )
