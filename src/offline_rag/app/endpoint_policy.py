"""Strict-offline / private-network endpoint classification for Seneca Settings.

Used by Settings validate / probe / save so product-managed approvals cannot
approve public Internet destinations under ``project.strict_offline``.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from offline_rag.generation.openai_compatible import normalize_endpoint

_DOCKER_HOST_NAMES = frozenset({"host.docker.internal"})


class EndpointPolicyError(ValueError):
    """Candidate endpoint rejected by network policy."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _host_is_private(host: str) -> bool:
    lowered = host.strip().lower().rstrip(".")
    if not lowered:
        return False
    if lowered in {"localhost"} | _DOCKER_HOST_NAMES:
        return True
    # Strip IPv6 brackets if present.
    if lowered.startswith("[") and lowered.endswith("]"):
        lowered = lowered[1:-1]
    try:
        addr = ipaddress.ip_address(lowered)
    except ValueError:
        # Arbitrary DNS hostnames are not treated as private under strict-offline.
        return False
    if addr.is_loopback:
        return True
    if isinstance(addr, ipaddress.IPv4Address):
        return bool(addr.is_private)
    # IPv6: private (ULA) + link-local; reject global unicast.
    return bool(addr.is_private or addr.is_link_local)


def classify_endpoint_host(base_url: str) -> str:
    """Return a coarse host class for diagnostics (never used as a allowlist)."""
    normalized = normalize_endpoint(base_url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").strip().lower()
    if host in {"localhost"} or host in _DOCKER_HOST_NAMES:
        return "docker_or_loopback_name"
    try:
        addr = ipaddress.ip_address(host[1:-1] if host.startswith("[") else host)
    except ValueError:
        return "dns_hostname"
    if addr.is_loopback:
        return "loopback"
    if addr.is_private or addr.is_link_local:
        return "private"
    return "public"


def validate_endpoint_network_policy(
    base_url: str,
    *,
    strict_offline: bool,
) -> str:
    """Normalize and enforce network policy.

    Returns the normalized endpoint on success.
    Raises ``EndpointPolicyError`` on rejection.
    """
    try:
        normalized = normalize_endpoint(base_url)
    except Exception as exc:  # noqa: BLE001 — surface as policy reject
        raise EndpointPolicyError("malformed_endpoint") from exc

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise EndpointPolicyError("unsupported_scheme")
    if not parsed.hostname:
        raise EndpointPolicyError("missing_host")
    if parsed.username is not None or parsed.password is not None:
        raise EndpointPolicyError("embedded_credentials_forbidden")

    if not strict_offline:
        return normalized

    host = parsed.hostname.strip().lower()
    if not _host_is_private(host):
        raise EndpointPolicyError("public_endpoint_forbidden")
    return normalized


__all__ = [
    "EndpointPolicyError",
    "classify_endpoint_host",
    "validate_endpoint_network_policy",
]
