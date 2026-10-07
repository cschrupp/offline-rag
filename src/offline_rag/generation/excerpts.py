"""Bounded plain-text citation excerpts from accepted EvidenceUnit text (A2-D15)."""

from __future__ import annotations

import re

EXCERPT_MAX_CHARS = 400
_TAG_RE = re.compile(r"<[^>]*>")


def build_citation_excerpt(text: str) -> tuple[str, bool]:
    """Return ``(excerpt, excerpt_clipped)`` from exact EvidenceUnit text.

    - plain text only
    - HTML-like tags stripped (not executed)
    - max 400 Unicode characters
    """
    if not isinstance(text, str):
        raise TypeError("excerpt source text must be a string")
    plain = _TAG_RE.sub("", text)
    plain = plain.replace("\x00", "")
    if len(plain) <= EXCERPT_MAX_CHARS:
        return plain, False
    return plain[:EXCERPT_MAX_CHARS], True
