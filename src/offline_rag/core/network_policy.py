"""Neutral endpoint destination / network-policy helpers.

Supports ``localhost_only`` and ``private_network`` with fail-closed DNS /
private-address behavior. Shared by gold-authoring and evaluation judge paths.
"""

from __future__ import annotations

import ipaddress
import socket
from enum import StrEnum
from urllib.parse import urlparse, urlunparse


class NetworkPolicyReason(StrEnum):
    NETWORK_POLICY_VIOLATION = "network_policy_violation"
    UNSUPPORTED_ENDPOINT_SCHEME = "unsupported_endpoint_scheme"
    HOSTNAME_RESOLUTION_FAILED = "hostname_resolution_failed"
    PUBLIC_ADDRESS_NOT_ALLOWED = "public_address_not_allowed"
    INVALID_ENDPOINT = "invalid_endpoint"


class NetworkPolicyError(RuntimeError):
    def __init__(self, message: str, *, reason: NetworkPolicyReason) -> None:
        super().__init__(message)
        self.reason = reason


SUPPORTED_NETWORK_POLICIES: frozenset[str] = frozenset(
    {"localhost_only", "private_network"}
)


def normalize_openai_compatible_endpoint(base_url: str) -> str:
    """Normalize OpenAI-compatible base URL for allowlist comparison."""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise NetworkPolicyError(
            f"unsupported endpoint scheme: {parsed.scheme}",
            reason=NetworkPolicyReason.UNSUPPORTED_ENDPOINT_SCHEME,
        )
    if not parsed.netloc:
        raise NetworkPolicyError(
            "endpoint missing host",
            reason=NetworkPolicyReason.INVALID_ENDPOINT,
        )
    path = parsed.path.rstrip("/")
    if path in {"", "/"}:
        path = "/v1"
    elif path.endswith("/v1/"):
        path = path.rstrip("/")
    elif not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def endpoint_in_allowlist(base_url: str, approved: list[str]) -> bool:
    try:
        selected = normalize_openai_compatible_endpoint(base_url)
    except NetworkPolicyError:
        return False
    approved_norm: list[str] = []
    for item in approved:
        try:
            approved_norm.append(normalize_openai_compatible_endpoint(item))
        except NetworkPolicyError:
            continue
    return selected in approved_norm


def _host_from_netloc(netloc: str) -> str:
    if netloc.startswith("["):
        end = netloc.find("]")
        if end == -1:
            raise NetworkPolicyError(
                "invalid IPv6 endpoint host",
                reason=NetworkPolicyReason.INVALID_ENDPOINT,
            )
        return netloc[1:end]
    if ":" in netloc:
        return netloc.rsplit(":", 1)[0]
    return netloc


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _is_loopback_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(addr.is_loopback)


def _is_private_network_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if addr.is_loopback:
        return True
    if addr.version == 4:
        return bool(addr.is_private)
    return bool(addr.is_private)


def _resolve_host_addresses(
    host: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise NetworkPolicyError(
            f"hostname resolution failed: {host}",
            reason=NetworkPolicyReason.HOSTNAME_RESOLUTION_FAILED,
        ) from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        ip_text = sockaddr[0]
        if ip_text in seen:
            continue
        seen.add(ip_text)
        parsed = _parse_ip(ip_text)
        if parsed is None:
            continue
        addresses.append(parsed)
    if not addresses:
        raise NetworkPolicyError(
            f"hostname resolution failed: {host}",
            reason=NetworkPolicyReason.HOSTNAME_RESOLUTION_FAILED,
        )
    return addresses


def destination_satisfies_policy(
    base_url: str,
    *,
    network_policy: str,
) -> NetworkPolicyReason | None:
    """Return None when OK, otherwise a rejection reason."""
    try:
        normalized = normalize_openai_compatible_endpoint(base_url)
    except NetworkPolicyError as exc:
        return exc.reason

    parsed = urlparse(normalized)
    host = _host_from_netloc(parsed.netloc)
    host_lower = host.lower()

    if network_policy == "localhost_only":
        if host_lower == "localhost":
            return None
        addr = _parse_ip(host)
        if addr is not None and _is_loopback_ip(addr):
            return None
        # Do not accept arbitrary hostnames that happen to resolve to loopback.
        return NetworkPolicyReason.NETWORK_POLICY_VIOLATION

    if network_policy == "private_network":
        addr = _parse_ip(host)
        if addr is not None:
            if _is_private_network_ip(addr):
                return None
            return NetworkPolicyReason.PUBLIC_ADDRESS_NOT_ALLOWED
        if host_lower == "localhost":
            return None
        try:
            resolved = _resolve_host_addresses(host)
        except NetworkPolicyError as exc:
            return exc.reason
        if any(not _is_private_network_ip(item) for item in resolved):
            return NetworkPolicyReason.PUBLIC_ADDRESS_NOT_ALLOWED
        return None

    return NetworkPolicyReason.NETWORK_POLICY_VIOLATION


def http_follow_redirects_allowed() -> bool:
    """Private OfflineRAG HTTP clients must not follow redirects."""
    return False
