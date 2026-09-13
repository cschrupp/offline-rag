"""Neutral document-title and section-path primitives (document-title-v1)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

_RECOGNIZED_EXTENSIONS = frozenset({".pdf", ".txt", ".md"})
_WHITESPACE_RUN = re.compile(r"\s+", flags=re.UNICODE)


class DocumentMetadataError(ValueError):
    """Fail-closed document-title / section-path resolution error."""


def resolve_document_title_v1(source_name: str) -> str:
    """Normalize authoritative ``source_name`` under document-title-v1.

    Raises ``DocumentMetadataError`` when the result would be empty.
    """
    if not isinstance(source_name, str):
        raise DocumentMetadataError("source_name must be a string")
    name = source_name.strip()
    if not name:
        raise DocumentMetadataError("source_name is blank")
    # Basename only: normalize separators then take final path segment.
    name = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not name:
        raise DocumentMetadataError("source_name basename is blank")

    lower = name.lower()
    for ext in sorted(_RECOGNIZED_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            name = name[: -len(ext)]
            break
    name = name.strip()
    name = _WHITESPACE_RUN.sub(" ", name)
    if not name:
        raise DocumentMetadataError("document_title normalized to empty")
    return name


def _normalize_section_component(component: str) -> str | None:
    text = component.strip()
    if not text:
        return None
    return _WHITESPACE_RUN.sub(" ", text)


def render_section_path_v1(section_path: Sequence[str]) -> str | None:
    """Render section_path components (None when empty after filter).

    Joins remaining components with ``" / "``. Does not include a ``SECTION:`` label.
    """
    parts: list[str] = []
    for component in section_path:
        if not isinstance(component, str):
            continue
        normalized = _normalize_section_component(component)
        if normalized is not None:
            parts.append(normalized)
    if not parts:
        return None
    return " / ".join(parts)
