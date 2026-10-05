"""D14 HTTP bind policy — pure checks, no DNS resolution."""

from __future__ import annotations

_LOOPBACK_LITERALS = frozenset(
    {
        "127.0.0.1",
        "::1",
        "localhost",
    }
)


class BindPolicyError(ValueError):
    """Raised when a configured bind host violates D14 policy."""


def normalize_bind_host(host: str) -> str:
    """Strip whitespace and optional IPv6 brackets; no DNS lookup."""
    text = str(host).strip()
    if text.startswith("[") and text.endswith("]") and len(text) > 2:
        inner = text[1:-1].strip()
        if ":" in inner:
            return inner
    return text


def is_loopback_bind_host(host: str) -> bool:
    """Return True for loopback literals recognized without network resolution."""
    return normalize_bind_host(host).lower() in _LOOPBACK_LITERALS


def enforce_bind_policy(host: str, *, allow_non_loopback: bool) -> None:
    """Fail closed for non-loopback binds unless explicitly opted in.

    This is a startup/configuration failure, not a product HTTP (D08) error.
    """
    if is_loopback_bind_host(host):
        return
    if allow_non_loopback:
        return
    raise BindPolicyError(
        "non-loopback HTTP bind refused without "
        f"OFFLINE_RAG_ALLOW_NON_LOOPBACK=true (host={host!r})"
    )
