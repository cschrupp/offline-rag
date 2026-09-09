"""Docling PDF adapter translating Docling output into project-owned models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from offline_rag.core.ids import (
    DOCLING_PDF_PARSER_VERSION,
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
from offline_rag.ingestion.docling_artifacts import require_docling_artifacts


class DoclingPdfParser:
    name = "docling_pdf"
    version = DOCLING_PDF_PARSER_VERSION

    def __init__(
        self,
        *,
        artifacts_path: Path,
        strict_offline: bool = True,
        ocr_enabled: bool = False,
    ) -> None:
        self.artifacts_path = Path(artifacts_path)
        self.strict_offline = strict_offline
        self.ocr_enabled = ocr_enabled
        self._converter = None

    def _build_converter(self):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        resolved = require_docling_artifacts(self.artifacts_path)
        options = PdfPipelineOptions(
            artifacts_path=resolved,
            enable_remote_services=False,
            allow_external_plugins=False,
            do_ocr=self.ocr_enabled,
            do_table_structure=True,
            generate_page_images=False,
            generate_picture_images=False,
        )
        return DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

    def _converter_instance(self):
        if self._converter is None:
            self._converter = self._build_converter()
        return self._converter

    def parse(self, path: Path, *, source_bytes: bytes, document_id: str) -> ParsedDocument:
        # Ensure bytes identity matches on-disk path by writing is not required;
        # Docling reads the path. Callers must ensure path content matches bytes.
        converter = self._converter_instance()
        result = converter.convert(path)
        docling_doc = result.document

        blocks: list[ContentBlock] = []
        warnings: list[ParseWarning] = []
        heading_stack: list[str] = []
        text_chars = 0

        from docling_core.types.doc import DocItemLabel, TableItem, TextItem

        for item, _level in docling_doc.iterate_items():
            label = getattr(item, "label", None)
            page_no = None
            if getattr(item, "prov", None):
                try:
                    page_no = int(item.prov[0].page_no)
                except (AttributeError, IndexError, TypeError, ValueError):
                    page_no = None

            locator = SourceLocator(page_number=page_no) if page_no is not None else None

            if label in {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}:
                text = item.text.strip() if getattr(item, "text", None) else ""
                if not text:
                    continue
                # Reset stack for title; for section headers keep shallow hierarchy by text only.
                if label == DocItemLabel.TITLE:
                    heading_stack = [text]
                else:
                    # Approximate hierarchy: keep previous titles and append.
                    if heading_stack and heading_stack[-1] == text:
                        pass
                    else:
                        # Pop last heading when encountering a same-ish depth is unknown;
                        # keep a simple stack of recent headers for section_path inheritance.
                        if len(heading_stack) >= 3:
                            heading_stack = heading_stack[:1]
                        heading_stack.append(text)
                content_type = ContentType.HEADING
                body = text
                metadata: dict = {"docling_label": str(label.value if hasattr(label, "value") else label)}
            elif label == DocItemLabel.LIST_ITEM:
                text = item.text.strip() if getattr(item, "text", None) else ""
                if not text:
                    continue
                content_type = ContentType.LIST
                body = f"- {text}"
                metadata = {}
            elif label == DocItemLabel.CODE:
                text = item.text if getattr(item, "text", None) else ""
                if not text.strip():
                    continue
                content_type = ContentType.CODE
                body = text
                metadata = {}
            elif isinstance(item, TableItem) or label == DocItemLabel.TABLE:
                try:
                    body = item.export_to_markdown()
                except (AttributeError, TypeError, ValueError, RuntimeError):
                    body = getattr(item, "text", None) or " "
                if not str(body).strip():
                    continue
                content_type = ContentType.TABLE
                body = str(body).strip()
                metadata = {}
            elif isinstance(item, TextItem) or label in {
                DocItemLabel.TEXT,
                DocItemLabel.PARAGRAPH,
                DocItemLabel.CAPTION,
                DocItemLabel.FOOTNOTE,
                DocItemLabel.PAGE_HEADER,
                DocItemLabel.PAGE_FOOTER,
            }:
                text = item.text.strip() if getattr(item, "text", None) else ""
                if not text:
                    continue
                content_type = ContentType.TEXT
                body = text
                metadata = {}
            else:
                text = getattr(item, "text", None)
                if not text or not str(text).strip():
                    continue
                content_type = ContentType.TEXT
                body = str(text).strip()
                metadata = {
                    "docling_label": str(label.value if hasattr(label, "value") else label),
                }
                warnings.append(
                    ParseWarning(
                        category=WarningCategory.UNSUPPORTED_STRUCTURE,
                        message=f"Mapped unsupported Docling label to text: {label}",
                        source_path=path.name,
                    )
                )

            text_chars += len(body)
            order = len(blocks)
            section_path = list(heading_stack)
            # Heading block's section_path includes itself.
            blocks.append(
                ContentBlock(
                    id=block_id_from_parts(document_id, order, content_type.value, body),
                    document_id=document_id,
                    order=order,
                    content_type=content_type,
                    text=body,
                    page_number=page_no,
                    section_path=section_path,
                    source_locator=locator,
                    metadata=metadata,
                )
            )

        if text_chars < 40 and not self.ocr_enabled:
            warnings.append(
                ParseWarning(
                    category=WarningCategory.OCR_REQUIRED,
                    message=(
                        "PDF appears to contain little or no machine-readable text. "
                        "OCR is disabled by current parsing policy. "
                        "Re-ingest with parsing.pdf.ocr_enabled=true if appropriate."
                    ),
                    source_path=path.name,
                )
            )

        cfg_hash = parse_config_hash(
            parser_name=self.name,
            parser_version=self.version,
            ocr_enabled=self.ocr_enabled,
        )
        artifact_id = parsed_artifact_id(document_id, cfg_hash)
        import docling

        document = Document(
            document_id=document_id,
            source_uri=path.name,
            title=path.stem,
            mime_type="application/pdf",
            content_hash=content_hash_from_bytes(source_bytes),
            ingested_at=datetime(1970, 1, 1, tzinfo=UTC),
            parser_version=self.version,
            metadata={
                "parser_name": self.name,
                "docling_version": getattr(docling, "__version__", "unknown"),
                "ocr_enabled": self.ocr_enabled,
            },
        )
        return ParsedDocument(
            document=document,
            blocks=blocks,
            parser_name=self.name,
            parser_version=self.version,
            warnings=warnings,
            parsed_artifact_id=artifact_id,
            parse_config_hash=cfg_hash,
            metadata={"docling_version": getattr(docling, "__version__", "unknown")},
        )
