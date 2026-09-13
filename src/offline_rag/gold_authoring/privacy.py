"""Authoring endpoint privacy authorization (Slice 9A).

Fail closed before any transport. Dual gate: allowlist AND network_policy.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse, urlunparse

from offline_rag.config.models import AppSettings, AuthoringSettings


class AuthoringAuthReason(StrEnum):
    AUTHORIZED = "authorized"
    ENDPOINT_NOT_APPROVED = "endpoint_not_approved"
    NETWORK_POLICY_VIOLATION = "network_policy_violation"
    UNSUPPORTED_ENDPOINT_SCHEME = "unsupported_endpoint_scheme"
    HOSTNAME_RESOLUTION_FAILED = "hostname_resolution_failed"
    PUBLIC_ADDRESS_NOT_ALLOWED = "public_address_not_allowed"
    INVALID_ENDPOINT = "invalid_endpoint"
    REDIRECT_NOT_ALLOWED = "redirect_not_allowed"


class AuthoringPrivacyError(RuntimeError):
    def __init__(self, message: str, *, reason: AuthoringAuthReason) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuthorizedEndpoint:
    endpoint: str
    network_policy: str
    reason: AuthoringAuthReason = AuthoringAuthReason.AUTHORIZED


def normalize_authoring_endpoint(base_url: str) -> str:
    """Normalize OpenAI-compatible base URL for allowlist comparison."""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise AuthoringPrivacyError(
            f"unsupported endpoint scheme: {parsed.scheme}",
            reason=AuthoringAuthReason.UNSUPPORTED_ENDPOINT_SCHEME,
        )
    if not parsed.netloc:
        raise AuthoringPrivacyError(
            "endpoint missing host",
            reason=AuthoringAuthReason.INVALID_ENDPOINT,
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
        selected = normalize_authoring_endpoint(base_url)
    except AuthoringPrivacyError:
        return False
    approved_norm: list[str] = []
    for item in approved:
        try:
            approved_norm.append(normalize_authoring_endpoint(item))
        except AuthoringPrivacyError:
            continue
    return selected in approved_norm


def _host_from_netloc(netloc: str) -> str:
    if netloc.startswith("["):
        end = netloc.find("]")
        if end == -1:
            raise AuthoringPrivacyError(
                "invalid IPv6 endpoint host",
                reason=AuthoringAuthReason.INVALID_ENDPOINT,
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
    # IPv6 unique-local fc00::/7; exclude link-local unless explicitly required.
    return bool(addr.is_private)


def _resolve_host_addresses(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AuthoringPrivacyError(
            f"hostname resolution failed: {host}",
            reason=AuthoringAuthReason.HOSTNAME_RESOLUTION_FAILED,
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
        raise AuthoringPrivacyError(
            f"hostname resolution failed: {host}",
            reason=AuthoringAuthReason.HOSTNAME_RESOLUTION_FAILED,
        )
    return addresses


def destination_satisfies_policy(
    base_url: str,
    *,
    network_policy: str,
) -> AuthoringAuthReason | None:
    """Return None when OK, otherwise a rejection reason."""
    try:
        normalized = normalize_authoring_endpoint(base_url)
    except AuthoringPrivacyError as exc:
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
        return AuthoringAuthReason.NETWORK_POLICY_VIOLATION

    if network_policy == "private_network":
        addr = _parse_ip(host)
        if addr is not None:
            if _is_private_network_ip(addr):
                return None
            return AuthoringAuthReason.PUBLIC_ADDRESS_NOT_ALLOWED
        if host_lower == "localhost":
            return None
        try:
            resolved = _resolve_host_addresses(host)
        except AuthoringPrivacyError as exc:
            return exc.reason
        if any(not _is_private_network_ip(item) for item in resolved):
            return AuthoringAuthReason.PUBLIC_ADDRESS_NOT_ALLOWED
        return None

    return AuthoringAuthReason.NETWORK_POLICY_VIOLATION


def authorize_authoring_endpoint(
    settings: AppSettings | AuthoringSettings,
) -> AuthorizedEndpoint:
    """Authorize the configured authoring endpoint under allowlist ∧ policy."""
    auth = settings.authoring if isinstance(settings, AppSettings) else settings
    try:
        normalized = normalize_authoring_endpoint(auth.base_url)
    except AuthoringPrivacyError:
        raise

    if not endpoint_in_allowlist(auth.base_url, list(auth.approved_endpoints)):
        raise AuthoringPrivacyError(
            "configured authoring endpoint is not approved",
            reason=AuthoringAuthReason.ENDPOINT_NOT_APPROVED,
        )

    policy_failure = destination_satisfies_policy(
        auth.base_url, network_policy=auth.network_policy
    )
    if policy_failure is not None:
        raise AuthoringPrivacyError(
            f"authoring endpoint rejected by network_policy={auth.network_policy}",
            reason=policy_failure,
        )

    return AuthorizedEndpoint(
        endpoint=normalized,
        network_policy=auth.network_policy,
    )


def authoring_follow_redirects() -> bool:
    """Authoring HTTP clients must not follow redirects (Slice 9A)."""
    return False
