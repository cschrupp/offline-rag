"""Parser protocol and shared helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from offline_rag.domain.blocks import ParsedDocument


class DocumentParser(Protocol):
    """Project-owned parser boundary."""

    name: str
    version: str

    def parse(self, path: Path, *, source_bytes: bytes, document_id: str) -> ParsedDocument:
        """Parse source bytes into a project-owned ParsedDocument."""


SUPPORTED_EXTENSIONS = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".pdf": "application/pdf",
}


def media_type_for_path(path: Path) -> str | None:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower())


def decode_text(source_bytes: bytes) -> tuple[str, bool]:
    """Decode UTF-8; fall back to replacement decoding with a flag."""
    try:
        return source_bytes.decode("utf-8"), False
    except UnicodeDecodeError:
        return source_bytes.decode("utf-8", errors="replace"), True
