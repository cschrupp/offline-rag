"""Native TXT/Markdown parser unit tests."""

from __future__ import annotations

from pathlib import Path

from offline_rag.core.ids import document_id_from_bytes
from offline_rag.domain.blocks import ContentType, ParsedDocument
from offline_rag.ingestion.markdown_parser import MarkdownParser
from offline_rag.ingestion.text_parser import TextParser

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingestion"


def test_text_parser_paragraphs_and_provenance() -> None:
    path = FIXTURES / "sample.txt"
    raw = path.read_bytes()
    parsed = TextParser().parse(path, source_bytes=raw, document_id=document_id_from_bytes(raw))
    assert isinstance(parsed, ParsedDocument)
    assert all(block.page_number is None for block in parsed.blocks)
    assert all(block.section_path == [] for block in parsed.blocks)
    assert len(parsed.blocks) >= 2
    assert parsed.blocks[0].content_type == ContentType.TEXT
    assert parsed.blocks[0].source_locator is not None
    assert parsed.blocks[0].source_locator.line_start == 1
    again = TextParser().parse(path, source_bytes=raw, document_id=document_id_from_bytes(raw))
    assert parsed.model_dump(mode="json") == again.model_dump(mode="json")


def test_markdown_heading_hierarchy_and_types() -> None:
    path = FIXTURES / "sample.md"
    raw = path.read_bytes()
    parsed = MarkdownParser().parse(path, source_bytes=raw, document_id=document_id_from_bytes(raw))
    types = [block.content_type for block in parsed.blocks]
    assert ContentType.HEADING in types
    assert ContentType.LIST in types
    assert ContentType.CODE in types
    assert ContentType.TABLE in types

    headings = [b for b in parsed.blocks if b.content_type == ContentType.HEADING]
    assert headings[0].text == "Operations"
    assert headings[0].section_path == ["Operations"]

    formation = next(b for b in parsed.blocks if b.text == "Formation Testing")
    assert formation.section_path == ["Operations", "Formation Testing"]

    sampling = next(b for b in parsed.blocks if b.text == "Sampling")
    assert sampling.section_path == ["Operations", "Sampling"]

    para = next(b for b in parsed.blocks if b.text.startswith("Formation testing paragraph"))
    assert para.section_path == ["Operations", "Formation Testing"]
    assert para.page_number is None
    assert para.source_locator is not None

    restored = ParsedDocument.model_validate_json(parsed.model_dump_json())
    assert restored == parsed


def test_markdown_pipe_in_paragraph_is_not_table() -> None:
    raw = b"pressure | temperature\n\nMore text.\n"
    path = Path("inline.md")
    parsed = MarkdownParser().parse(path, source_bytes=raw, document_id=document_id_from_bytes(raw))
    assert all(block.content_type != ContentType.TABLE for block in parsed.blocks)
