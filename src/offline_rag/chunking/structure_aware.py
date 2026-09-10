"""Structure-aware parent/child chunker over ParsedDocument ContentBlocks."""

from __future__ import annotations

import re
from dataclasses import dataclass

from offline_rag.chunking.tokenize import TokenCounter
from offline_rag.chunking.validation import validate_chunk_artifact
from offline_rag.core.ids import (
    STRUCTURE_AWARE_CHUNKER_VERSION,
    child_chunk_id_from_parts,
    content_hash_from_bytes,
    parent_chunk_id_from_parts,
)
from offline_rag.domain.blocks import ContentBlock, ContentType, ParsedDocument
from offline_rag.domain.chunking import DocumentChunkArtifact
from offline_rag.domain.documents import Chunk, ChunkKind

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ChunkerBudgets:
    child_target: int = 350
    child_max: int = 512
    parent_target: int = 1200
    parent_max: int = 2000
    parent_child: bool = True


def _join_blocks(blocks: list[ContentBlock]) -> str:
    parts: list[str] = []
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        parts.append(text)
    return "\n\n".join(parts)


def _aggregate_pages(blocks: list[ContentBlock]) -> tuple[int | None, int | None]:
    pages = [b.page_number for b in blocks if b.page_number is not None]
    if not pages:
        return None, None
    return min(pages), max(pages)


def _aggregate_lines(blocks: list[ContentBlock]) -> tuple[int | None, int | None]:
    starts: list[int] = []
    ends: list[int] = []
    for block in blocks:
        locator = block.source_locator
        if locator is None:
            continue
        if locator.line_start is not None:
            starts.append(locator.line_start)
        if locator.line_end is not None:
            ends.append(locator.line_end)
    if not starts and not ends:
        return None, None
    line_start = min(starts) if starts else (min(ends) if ends else None)
    line_end = max(ends) if ends else (max(starts) if starts else None)
    return line_start, line_end


def _content_hash(text: str) -> str:
    return content_hash_from_bytes(text.encode("utf-8"))


def _split_text_units(text: str, counter: TokenCounter, max_tokens: int) -> list[str]:
    if counter.count(text) <= max_tokens:
        return [text]
    # Prefer sentence-like boundaries, then lines, then whitespace words.
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    if len(sentences) <= 1:
        sentences = [line.strip() for line in text.splitlines() if line.strip()] or [text]
    units: list[str] = []
    for sentence in sentences:
        if counter.count(sentence) <= max_tokens:
            units.append(sentence)
            continue
        words = sentence.split()
        buf: list[str] = []
        for word in words:
            candidate = " ".join([*buf, word])
            if buf and counter.count(candidate) > max_tokens:
                units.append(" ".join(buf))
                buf = [word]
            else:
                buf.append(word)
        if buf:
            units.append(" ".join(buf))
    return units or [text]


def _split_table_text(text: str, counter: TokenCounter, max_tokens: int) -> list[str]:
    lines = text.splitlines()
    if not lines:
        return [text]
    header = lines[0]
    body = lines[1:]
    if not body:
        return [text]
    chunks: list[str] = []
    current = [header]
    for row in body:
        candidate = "\n".join([*current, row])
        if len(current) > 1 and counter.count(candidate) > max_tokens:
            chunks.append("\n".join(current))
            current = [header, row]
        else:
            current.append(row)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _split_code_or_list(text: str, counter: TokenCounter, max_tokens: int) -> list[str]:
    lines = text.splitlines() or [text]
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        candidate = "\n".join([*current, line])
        if current and counter.count(candidate) > max_tokens:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _group_parent_spans(
    blocks: list[ContentBlock],
    counter: TokenCounter,
    budgets: ChunkerBudgets,
) -> list[list[ContentBlock]]:
    if not blocks:
        return []
    # Prefer section_path identity for structured docs.
    has_sections = any(block.section_path for block in blocks)
    spans: list[list[ContentBlock]] = []
    if has_sections:
        current_key: tuple[str, ...] | None = None
        current: list[ContentBlock] = []
        for block in blocks:
            key = tuple(block.section_path)
            if current and key != current_key:
                spans.append(current)
                current = []
            current_key = key
            current.append(block)
            # Split oversized section into parent_max spans.
            if counter.count(_join_blocks(current)) > budgets.parent_max and len(current) > 1:
                overflow = current.pop()
                spans.append(current)
                current = [overflow]
                current_key = tuple(overflow.section_path)
        if current:
            spans.append(current)
        return spans

    # Unstructured: pack by parent_target/max.
    current = []
    for block in blocks:
        candidate = [*current, block]
        tokens = counter.count(_join_blocks(candidate))
        if current and tokens > budgets.parent_max:
            spans.append(current)
            current = [block]
        else:
            current = candidate
            if counter.count(_join_blocks(current)) >= budgets.parent_target and block.content_type != ContentType.HEADING:
                spans.append(current)
                current = []
    if current:
        spans.append(current)
    return spans


class StructureAwareChunker:
    version = STRUCTURE_AWARE_CHUNKER_VERSION

    def __init__(self, counter: TokenCounter, budgets: ChunkerBudgets | None = None) -> None:
        self.counter = counter
        self.budgets = budgets or ChunkerBudgets()

    def chunk_document(
        self,
        parsed: ParsedDocument,
        *,
        chunk_cfg_hash: str,
        parsed_artifact_id: str,
        chunk_artifact_id: str,
    ) -> DocumentChunkArtifact:
        blocks = list(parsed.blocks)
        for index, block in enumerate(blocks):
            if block.order != index:
                raise ValueError("ParsedDocument blocks must have contiguous order")
            if block.document_id != parsed.document.document_id:
                raise ValueError("block document_id mismatch")

        parents: list[Chunk] = []
        children: list[Chunk] = []
        warnings: list[str] = []
        document_id = parsed.document.document_id

        spans = _group_parent_spans(blocks, self.counter, self.budgets)
        for span in spans:
            parent_text = _join_blocks(span)
            if not parent_text.strip():
                continue
            page_start, page_end = _aggregate_pages(span)
            line_start, line_end = _aggregate_lines(span)
            source_ids = [block.id for block in span]
            parent_id = parent_chunk_id_from_parts(
                document_id,
                chunk_cfg_hash=chunk_cfg_hash,
                source_block_ids=source_ids,
                text=parent_text,
            )
            parent = Chunk(
                chunk_id=parent_id,
                document_id=document_id,
                kind=ChunkKind.PARENT,
                parent_chunk_id=None,
                text=parent_text,
                page_start=page_start,
                page_end=page_end,
                line_start=line_start,
                line_end=line_end,
                section_path=list(span[0].section_path),
                order=len(parents),
                token_count=self.counter.count(parent_text),
                content_type="parent",
                content_hash=_content_hash(parent_text),
                source_block_ids=source_ids,
            )
            parents.append(parent)

            # Build children within this parent span.
            child_units: list[tuple[list[ContentBlock], str, str]] = []
            # Accumulate by block, splitting oversized blocks.
            buffer_blocks: list[ContentBlock] = []
            for block in span:
                if block.content_type == ContentType.HEADING and not buffer_blocks:
                    # Keep heading with following content when possible.
                    buffer_blocks.append(block)
                    continue
                block_tokens = self.counter.count(block.text)
                if block_tokens > self.budgets.child_max:
                    if buffer_blocks:
                        text = _join_blocks(buffer_blocks)
                        child_units.append((buffer_blocks, text, "merged"))
                        buffer_blocks = []
                    if block.content_type == ContentType.TABLE:
                        parts = _split_table_text(block.text, self.counter, self.budgets.child_max)
                    elif block.content_type in {ContentType.CODE, ContentType.LIST}:
                        parts = _split_code_or_list(block.text, self.counter, self.budgets.child_max)
                    else:
                        parts = _split_text_units(block.text, self.counter, self.budgets.child_max)
                    for part in parts:
                        if self.counter.count(part) > self.budgets.child_max:
                            warnings.append(
                                f"oversized unsplittable block {block.id} exceeds child max_tokens"
                            )
                            child_units.append(([block], part, "oversized_unsplittable"))
                        else:
                            child_units.append(([block], part, "split"))
                    continue

                candidate_blocks = [*buffer_blocks, block]
                candidate_text = _join_blocks(candidate_blocks)
                if buffer_blocks and self.counter.count(candidate_text) > self.budgets.child_max:
                    text = _join_blocks(buffer_blocks)
                    child_units.append((buffer_blocks, text, "merged"))
                    buffer_blocks = [block]
                else:
                    buffer_blocks = candidate_blocks
                    if (
                        self.counter.count(_join_blocks(buffer_blocks)) >= self.budgets.child_target
                        and block.content_type != ContentType.HEADING
                    ):
                        text = _join_blocks(buffer_blocks)
                        child_units.append((buffer_blocks, text, "merged"))
                        buffer_blocks = []
            if buffer_blocks:
                text = _join_blocks(buffer_blocks)
                child_units.append((buffer_blocks, text, "merged"))

            for unit_blocks, text, mode in child_units:
                if not text.strip():
                    continue
                # Avoid heading-only children when associated content exists.
                if (
                    len(unit_blocks) == 1
                    and unit_blocks[0].content_type == ContentType.HEADING
                    and mode == "merged"
                    and len(span) > 1
                ):
                    continue
                page_start, page_end = _aggregate_pages(unit_blocks)
                line_start, line_end = _aggregate_lines(unit_blocks)
                source_ids = []
                for block in unit_blocks:
                    if block.id not in source_ids:
                        source_ids.append(block.id)
                child_id = child_chunk_id_from_parts(
                    document_id,
                    parent_chunk_id=parent_id if self.budgets.parent_child else None,
                    chunk_cfg_hash=chunk_cfg_hash,
                    source_block_ids=source_ids,
                    text=text,
                )
                metadata = {}
                if mode == "oversized_unsplittable":
                    metadata["oversized_unsplittable"] = True
                children.append(
                    Chunk(
                        chunk_id=child_id,
                        document_id=document_id,
                        kind=ChunkKind.CHILD,
                        parent_chunk_id=parent_id if self.budgets.parent_child else None,
                        text=text,
                        page_start=page_start,
                        page_end=page_end,
                        line_start=line_start,
                        line_end=line_end,
                        section_path=list(unit_blocks[0].section_path),
                        order=len(children),
                        token_count=self.counter.count(text),
                        content_type=unit_blocks[0].content_type.value
                        if len(unit_blocks) == 1
                        else "mixed",
                        content_hash=_content_hash(text),
                        source_block_ids=source_ids,
                        metadata=metadata,
                    )
                )

        # Wire neighbor links for children.
        wired: list[Chunk] = []
        for index, child in enumerate(children):
            wired.append(
                child.model_copy(
                    update={
                        "order": index,
                        "previous_chunk_id": children[index - 1].chunk_id if index > 0 else None,
                        "next_chunk_id": children[index + 1].chunk_id
                        if index + 1 < len(children)
                        else None,
                    }
                )
            )
        children = wired

        validate_chunk_artifact(
            parents=parents,
            children=children,
            document_id=document_id,
            parent_child=self.budgets.parent_child,
            child_max_tokens=self.budgets.child_max,
        )

        return DocumentChunkArtifact(
            chunk_artifact_id=chunk_artifact_id,
            parsed_artifact_id=parsed_artifact_id,
            document_id=document_id,
            chunk_config_hash=chunk_cfg_hash,
            chunker_version=self.version,
            tokenizer_name=self.counter.name,
            tokenizer_encoding=self.counter.encoding,
            parents=parents,
            children=children,
            parent_count=len(parents),
            child_count=len(children),
            warnings=warnings,
        )
