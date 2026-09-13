"""Project-owned ranking-text contracts (document-title-v1, title-section-text-v1)."""

from __future__ import annotations

from dataclasses import dataclass

from offline_rag.core.document_metadata import (
    DocumentMetadataError,
    render_section_path_v1,
    resolve_document_title_v1,
)
from offline_rag.core.ids import DOCUMENT_TITLE_V1, TITLE_SECTION_TEXT_V1

DOCUMENT_TITLE_CONTRACT = DOCUMENT_TITLE_V1
RANKING_TEXT_TITLE_SECTION_CONTRACT = TITLE_SECTION_TEXT_V1

# Compatibility alias: ranking callers historically catch RankingTextError.
RankingTextError = DocumentMetadataError

__all__ = [
    "DOCUMENT_TITLE_CONTRACT",
    "RANKING_TEXT_TITLE_SECTION_CONTRACT",
    "RankingTextError",
    "RankingTextInputs",
    "ranking_inputs_for_chunk",
    "render_section_path_v1",
    "render_title_section_text_v1",
    "resolve_document_title_v1",
    "resolve_document_titles_from_source_names",
]


@dataclass(frozen=True, slots=True)
class RankingTextInputs:
    """Semantic inputs for ranking-text builders (no domain object references)."""

    document_title: str | None
    section_path: tuple[str, ...]
    chunk_text: str


def render_title_section_text_v1(inputs: RankingTextInputs) -> str:
    """Render title-section-text-v1 ranking envelope.

    Requires a non-empty ``document_title``. Leaves ``chunk_text`` byte-identical.
    """
    title = inputs.document_title
    if title is None or not str(title).strip():
        raise RankingTextError(
            "title-section-text-v1 requires a non-empty document_title"
        )
    header_lines = [f"DOCUMENT: {title}"]
    section = render_section_path_v1(inputs.section_path)
    if section is not None:
        header_lines.append(f"SECTION: {section}")
    return "\n".join(header_lines) + "\n\n" + inputs.chunk_text


def ranking_inputs_for_chunk(
    *,
    chunk_text: str,
    section_path: list[str] | tuple[str, ...],
    document_title: str | None,
) -> RankingTextInputs:
    """Build RankingTextInputs from chunk fields + resolved title."""
    return RankingTextInputs(
        document_title=document_title,
        section_path=tuple(section_path),
        chunk_text=chunk_text,
    )


def resolve_document_titles_from_source_names(
    *,
    document_ids: set[str],
    source_name_by_document_id: dict[str, str],
    require: bool,
) -> dict[str, str | None]:
    """Resolve document_title once per document_id from authoritative source_name.

    When ``require`` is True (metadata-aware indexing), missing/blank/empty titles
    raise ``RankingTextError``. When False (plain-v1), titles are optional ``None``.
    """
    titles: dict[str, str | None] = {}
    for document_id in sorted(document_ids):
        if document_id not in source_name_by_document_id:
            if require:
                raise RankingTextError(
                    f"document_id not found in authoritative corpus metadata: {document_id}"
                )
            titles[document_id] = None
            continue
        source_name = source_name_by_document_id[document_id]
        if not require:
            titles[document_id] = None
            continue
        if source_name is None or not str(source_name).strip():
            raise RankingTextError(
                f"authoritative source_name missing/blank for document_id={document_id}"
            )
        titles[document_id] = resolve_document_title_v1(str(source_name))
    return titles
