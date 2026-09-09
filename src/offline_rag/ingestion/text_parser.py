"""Native TXT parser."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.core.ids import (
    TEXT_PARSER_VERSION,
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


class TextParser:
    name = "text"
    version = TEXT_PARSER_VERSION

    def parse(self, path: Path, *, source_bytes: bytes, document_id: str) -> ParsedDocument:
        text, used_fallback = decode_text(source_bytes)
        warnings: list[ParseWarning] = []
        if used_fallback:
            warnings.append(
                ParseWarning(
                    category=WarningCategory.ENCODING_FALLBACK,
                    message="Decoded TXT with UTF-8 replacement characters",
                    source_path=path.name,
                )
            )

        blocks: list[ContentBlock] = []
        lines = text.splitlines()
        paragraph: list[str] = []
        paragraph_start: int | None = None

        def flush_paragraph(end_line: int) -> None:
            nonlocal paragraph, paragraph_start
            if not paragraph:
                return
            body = " ".join(part.strip() for part in paragraph if part.strip()).strip()
            if not body:
                paragraph = []
                paragraph_start = None
                return
            order = len(blocks)
            blocks.append(
                ContentBlock(
                    id=block_id_from_parts(document_id, order, ContentType.TEXT.value, body),
                    document_id=document_id,
                    order=order,
                    content_type=ContentType.TEXT,
                    text=body,
                    page_number=None,
                    section_path=[],
                    source_locator=SourceLocator(
                        line_start=(paragraph_start or end_line),
                        line_end=end_line,
                    ),
                )
            )
            paragraph = []
            paragraph_start = None

        for index, line in enumerate(lines, start=1):
            if not line.strip():
                flush_paragraph(index - 1 if index > 1 else 1)
                continue
            if paragraph_start is None:
                paragraph_start = index
            paragraph.append(line)

        if paragraph:
            flush_paragraph(len(lines) if lines else 1)

        cfg_hash = parse_config_hash(parser_name=self.name, parser_version=self.version)
        artifact_id = parsed_artifact_id(document_id, cfg_hash)
        document = Document(
            document_id=document_id,
            source_uri=path.name,
            title=path.stem,
            mime_type="text/plain",
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
