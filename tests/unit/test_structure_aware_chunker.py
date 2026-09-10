"""Structure-aware chunker unit tests (fake TokenCounter)."""

from __future__ import annotations

from datetime import UTC, datetime

from offline_rag.chunking.structure_aware import ChunkerBudgets, StructureAwareChunker
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.core.ids import chunk_artifact_id, chunk_config_hash
from offline_rag.domain.blocks import (
    ContentBlock,
    ContentType,
    ParsedDocument,
    SourceLocator,
)
from offline_rag.domain.documents import ChunkKind, Document


def _doc(blocks: list[ContentBlock], document_id: str = "doc_1") -> ParsedDocument:
    document = Document(
        document_id=document_id,
        source_uri="file://sample.txt",
        content_hash="hash",
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        parser_version="test",
    )
    return ParsedDocument(
        document=document,
        blocks=blocks,
        parser_name="test",
        parser_version="test",
        parsed_artifact_id="parsed_1",
        parse_config_hash="parsecfg_1",
    )


def _block(
    *,
    order: int,
    text: str,
    content_type: ContentType = ContentType.TEXT,
    section_path: list[str] | None = None,
    page_number: int | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    document_id: str = "doc_1",
) -> ContentBlock:
    locator = None
    if line_start is not None or line_end is not None:
        locator = SourceLocator(line_start=line_start, line_end=line_end)
    return ContentBlock(
        id=f"block_{order}",
        document_id=document_id,
        order=order,
        content_type=content_type,
        text=text,
        page_number=page_number,
        section_path=section_path or [],
        source_locator=locator,
    )


def _chunker(child_target: int = 8, child_max: int = 12, parent_max: int = 40) -> StructureAwareChunker:
    return StructureAwareChunker(
        FakeTokenCounter(),
        ChunkerBudgets(
            child_target=child_target,
            child_max=child_max,
            parent_target=20,
            parent_max=parent_max,
            parent_child=True,
        ),
    )


def _run(parsed: ParsedDocument, chunker: StructureAwareChunker | None = None):
    chunker = chunker or _chunker()
    cfg = chunk_config_hash({"strategy": "structure_aware", "child_max": 12})
    artifact_id = chunk_artifact_id("parsed_1", cfg)
    return chunker.chunk_document(
        parsed,
        chunk_cfg_hash=cfg,
        parsed_artifact_id="parsed_1",
        chunk_artifact_id=artifact_id,
    )


def test_section_aware_parents_and_child_assignment() -> None:
    parsed = _doc(
        [
            _block(order=0, text="Intro", content_type=ContentType.HEADING, section_path=["Intro"]),
            _block(order=1, text="alpha beta gamma", section_path=["Intro"]),
            _block(order=2, text="Methods", content_type=ContentType.HEADING, section_path=["Methods"]),
            _block(order=3, text="delta epsilon zeta", section_path=["Methods"]),
        ]
    )
    artifact = _run(parsed)
    assert len(artifact.parents) == 2
    assert all(child.parent_chunk_id is not None for child in artifact.children)
    parent_ids = {parent.chunk_id for parent in artifact.parents}
    assert {child.parent_chunk_id for child in artifact.children} <= parent_ids
    assert artifact.parents[0].section_path == ["Intro"]
    assert artifact.parents[1].section_path == ["Methods"]


def test_small_blocks_merge_toward_target() -> None:
    words = [f"w{i}" for i in range(10)]
    blocks = [_block(order=i, text=word, section_path=["S"]) for i, word in enumerate(words)]
    artifact = _run(_doc(blocks), _chunker(child_target=4, child_max=6))
    assert len(artifact.children) < len(blocks)
    assert all(child.token_count <= 6 for child in artifact.children)


def test_oversized_text_splits_deterministically() -> None:
    text = " ".join(f"word{i}." for i in range(40))
    parsed = _doc([_block(order=0, text=text, section_path=["S"])])
    first = _run(parsed, _chunker(child_target=5, child_max=8))
    second = _run(parsed, _chunker(child_target=5, child_max=8))
    assert [c.text for c in first.children] == [c.text for c in second.children]
    assert all(c.token_count <= 8 or c.metadata.get("oversized_unsplittable") for c in first.children)


def test_list_and_code_split_on_lines() -> None:
    list_text = "\n".join(f"- item {i} extra tokens here" for i in range(20))
    code_text = "\n".join(f"line_{i} = {i}" for i in range(20))
    parsed = _doc(
        [
            _block(order=0, text=list_text, content_type=ContentType.LIST, section_path=["L"]),
            _block(order=1, text=code_text, content_type=ContentType.CODE, section_path=["C"]),
        ]
    )
    artifact = _run(parsed, _chunker(child_target=5, child_max=8, parent_max=200))
    assert artifact.child_count >= 2
    assert any(c.content_type == "list" or "item" in c.text for c in artifact.children)


def test_table_row_split_keeps_header() -> None:
    rows = ["col_a col_b"] + [f"r{i}_a r{i}_b extra" for i in range(30)]
    parsed = _doc(
        [_block(order=0, text="\n".join(rows), content_type=ContentType.TABLE, section_path=["T"])]
    )
    artifact = _run(parsed, _chunker(child_target=5, child_max=8, parent_max=400))
    table_children = [c for c in artifact.children if "col_a" in c.text]
    assert table_children
    assert all(c.text.splitlines()[0].startswith("col_a") for c in table_children)


def test_neighbor_chain_crosses_parents() -> None:
    parsed = _doc(
        [
            _block(order=0, text="A1 A2 A3 A4 A5 A6", section_path=["A"]),
            _block(order=1, text="B1 B2 B3 B4 B5 B6", section_path=["B"]),
        ]
    )
    artifact = _run(parsed, _chunker(child_target=3, child_max=4))
    children = artifact.children
    assert len(children) >= 2
    assert children[0].previous_chunk_id is None
    assert children[-1].next_chunk_id is None
    for index, child in enumerate(children[:-1]):
        assert child.next_chunk_id == children[index + 1].chunk_id
        assert children[index + 1].previous_chunk_id == child.chunk_id
    assert all(parent.previous_chunk_id is None and parent.next_chunk_id is None for parent in artifact.parents)


def test_provenance_aggregates_pages_and_lines() -> None:
    parsed = _doc(
        [
            _block(
                order=0,
                text="page one text here",
                section_path=["P"],
                page_number=2,
                line_start=10,
                line_end=12,
            ),
            _block(
                order=1,
                text="page two text here",
                section_path=["P"],
                page_number=4,
                line_start=20,
                line_end=22,
            ),
        ]
    )
    artifact = _run(parsed, _chunker(child_target=100, child_max=100))
    child = artifact.children[0]
    assert child.page_start == 2
    assert child.page_end == 4
    assert child.line_start == 10
    assert child.line_end == 22
    assert child.section_path == ["P"]
    assert child.source_block_ids == ["block_0", "block_1"]


def test_deterministic_ids() -> None:
    parsed = _doc(
        [
            _block(order=0, text="stable content alpha beta", section_path=["S"]),
            _block(order=1, text="more stable content gamma", section_path=["S"]),
        ]
    )
    first = _run(parsed)
    second = _run(parsed)
    assert first.chunk_artifact_id == second.chunk_artifact_id
    assert [p.chunk_id for p in first.parents] == [p.chunk_id for p in second.parents]
    assert [c.chunk_id for c in first.children] == [c.chunk_id for c in second.children]
    assert all(c.kind == ChunkKind.CHILD for c in first.children)
    assert all(p.kind == ChunkKind.PARENT for p in first.parents)


def test_config_hash_changes_artifact_id() -> None:
    parsed = _doc([_block(order=0, text="alpha beta gamma", section_path=["S"])])
    a = _run(parsed, _chunker(child_max=12))
    other = StructureAwareChunker(
        FakeTokenCounter(),
        ChunkerBudgets(child_target=8, child_max=20, parent_target=20, parent_max=40),
    )
    cfg = chunk_config_hash({"strategy": "structure_aware", "child_max": 20})
    b = other.chunk_document(
        parsed,
        chunk_cfg_hash=cfg,
        parsed_artifact_id="parsed_1",
        chunk_artifact_id=chunk_artifact_id("parsed_1", cfg),
    )
    assert a.chunk_artifact_id != b.chunk_artifact_id
