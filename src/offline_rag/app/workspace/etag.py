"""Workspace revision ETag / ``If-Match`` grammar (S16-D14).

The workspace revision is the only concurrency token. It is a monotonic decimal
integer serialized as a *strong* entity tag. Everything else fails closed with
``request_invalid`` so a client can never silently skip the precondition:

- weak validators (``W/"3"``) carry no total-order guarantee;
- wildcard (``*``) means "any current state", which is not a precondition;
- validator lists (``"3", "4"``) make the expected revision ambiguous.

The scientific ``snapshot_id`` is deliberately *not* an ETag: display-only
metadata edits advance the revision without creating a snapshot (S16-D11).
"""

from __future__ import annotations

import re

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import WorkspaceRevision, parse_revision

# Strong, single, decimal entity tag. No weak prefix, no list, no wildcard.
_STRONG_ETAG_RE = re.compile(r'^"(0|[1-9][0-9]{0,17})"$')

MAX_IF_MATCH_CHARS = 64


def format_etag(revision: WorkspaceRevision) -> str:
    """Serialize a workspace revision as a strong entity tag."""
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_revision"),
        )
    return f'"{revision}"'


def _invalid(reason: str) -> AppError:
    return AppError(
        ErrorCode.REQUEST_INVALID, details=SafeErrorDetails(reason=reason)
    )


def parse_if_match(header: str | None) -> WorkspaceRevision:
    """Parse an ``If-Match`` header into an expected workspace revision.

    Rejects missing, wildcard, weak, list-valued, and malformed validators.
    """
    if header is None:
        raise _invalid("if_match_required")
    if not isinstance(header, str):
        raise _invalid("if_match_invalid")
    text = header.strip()
    if not text:
        raise _invalid("if_match_required")
    if len(text) > MAX_IF_MATCH_CHARS:
        raise _invalid("if_match_invalid")
    if text == "*":
        raise _invalid("if_match_wildcard_unsupported")
    if "," in text:
        raise _invalid("if_match_list_unsupported")
    if text.startswith(("W/", "w/")):
        raise _invalid("if_match_weak_unsupported")
    if not _STRONG_ETAG_RE.fullmatch(text):
        raise _invalid("if_match_invalid")
    # parse_revision enforces the >= 1 revision floor shared with the store.
    return parse_revision(text[1:-1])
