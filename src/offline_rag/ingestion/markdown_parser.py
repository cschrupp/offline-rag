"""Native lightweight Markdown structural parser."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.core.ids import (
    MARKDOWN_PARSER_VERSION,
    block_id_from_parts,
    content_hash_from_bytes,
    parse_config_hash,
    parsed_artifact_id,
)
from offline_rag.domain.blocks import (
    ContentBlock,
    ContentType,
    ParsedDocument,
    ParseWarning,
    SourceLocator,
    WarningCategory,
)
from offline_rag.domain.documents import Document
from offline_rag.ingestion.base import decode_text

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.+)$")
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")


class MarkdownParser:
    name = "markdown"
    version = MARKDOWN_PARSER_VERSION

    def parse(self, path: Path, *, source_bytes: bytes, document_id: str) -> ParsedDocument:
        text, used_fallback = decode_text(source_bytes)
        warnings: list[ParseWarning] = []
        if used_fallback:
            warnings.append(
                ParseWarning(
                    category=WarningCategory.ENCODING_FALLBACK,
                    message="Decoded Markdown with UTF-8 replacement characters",
                    source_path=path.name,
                )
            )

        lines = text.splitlines()
        blocks: list[ContentBlock] = []
        heading_stack: list[tuple[int, str]] = []
        index = 0

        def section_path() -> list[str]:
            return [title for _, title in heading_stack]

        def emit(
            content_type: ContentType,
            body: str,
            *,
            line_start: int,
            line_end: int,
            metadata: dict | None = None,
            page_path: list[str] | None = None,
        ) -> None:
            order = len(blocks)
            blocks.append(
                ContentBlock(
                    id=block_id_from_parts(document_id, order, content_type.value, body),
                    document_id=document_id,
                    order=order,
                    content_type=content_type,
                    text=body,
                    page_number=None,
                    section_path=list(page_path if page_path is not None else section_path()),
                    source_locator=SourceLocator(line_start=line_start, line_end=line_end),
                    metadata=metadata or {},
                )
            )

        while index < len(lines):
            line = lines[index]
            line_no = index + 1
            fence = _FENCE_RE.match(line)
            if fence:
                marker = fence.group(1)[0]
                fence_len = len(fence.group(1))
                info = fence.group(2).strip()
                code_lines: list[str] = []
                index += 1
                closed = False
                while index < len(lines):
                    candidate = lines[index]
                    close = _FENCE_RE.match(candidate)
                    if (
                        close
                        and close.group(1)[0] == marker
                        and len(close.group(1)) >= fence_len
                        and not close.group(2).strip()
                    ):
                        closed = True
                        end_line = index + 1
                        index += 1
                        break
                    code_lines.append(candidate)
                    index += 1
                body = "\n".join(code_lines)
                if not body.strip():
                    body = " "
                meta = {"language": info} if info else {}
                if not closed:
                    warnings.append(
                        ParseWarning(
                            category=WarningCategory.MALFORMED_STRUCTURE,
                            message="Unterminated Markdown code fence",
                            source_path=path.name,
                            details={"line_start": line_no},
                        )
                    )
                    end_line = len(lines)
                emit(
                    ContentType.CODE,
                    body if body.strip() else " ",
                    line_start=line_no,
                    line_end=end_line,
                    metadata=meta,
                )
                continue

            heading = _HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                title = heading.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, title))
                emit(
                    ContentType.HEADING,
                    title,
                    line_start=line_no,
                    line_end=line_no,
                    page_path=section_path(),
                )
                index += 1
                continue

            if index + 1 < len(lines) and "|" in line and _TABLE_SEP_RE.match(lines[index + 1]):
                table_lines = [line.rstrip()]
                start = line_no
                index += 1
                table_lines.append(lines[index].rstrip())
                index += 1
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    table_lines.append(lines[index].rstrip())
                    index += 1
                emit(
                    ContentType.TABLE,
                    "\n".join(table_lines),
                    line_start=start,
                    line_end=start + len(table_lines) - 1,
                )
                continue

            if _UL_RE.match(line) or _OL_RE.match(line):
                list_lines = [line.rstrip()]
                start = line_no
                index += 1
                while index < len(lines) and (_UL_RE.match(lines[index]) or _OL_RE.match(lines[index])):
                    list_lines.append(lines[index].rstrip())
                    index += 1
                emit(
                    ContentType.LIST,
                    "\n".join(list_lines),
                    line_start=start,
                    line_end=start + len(list_lines) - 1,
                )
                continue

            if not line.strip():
                index += 1
                continue

            para_lines = [line.strip()]
            start = line_no
            index += 1
            while index < len(lines):
                nxt = lines[index]
                if (
                    not nxt.strip()
                    or _HEADING_RE.match(nxt)
                    or _FENCE_RE.match(nxt)
                    or _UL_RE.match(nxt)
                    or _OL_RE.match(nxt)
                    or (
                        index + 1 < len(lines)
                        and "|" in nxt
                        and _TABLE_SEP_RE.match(lines[index + 1])
                    )
                ):
                    break
                para_lines.append(nxt.strip())
                index += 1
            body = " ".join(part for part in para_lines if part).strip()
            if body:
                emit(
                    ContentType.TEXT,
                    body,
                    line_start=start,
                    line_end=start + len(para_lines) - 1,
                )

        cfg_hash = parse_config_hash(parser_name=self.name, parser_version=self.version)
        artifact_id = parsed_artifact_id(document_id, cfg_hash)
        document = Document(
            document_id=document_id,
            source_uri=path.name,
            title=path.stem,
            mime_type="text/markdown",
            content_hash=content_hash_from_bytes(source_bytes),
            ingested_at=datetime(1970, 1, 1, tzinfo=UTC),
            parser_version=self.version,
            metadata={"parser_name": self.name},
        )
        return ParsedDocument(
            document=document,
            blocks=blocks,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parsed_artifact_id=artifact_id,
            parse_config_hash=cfg_hash,
        )
