"""Authoring endpoint privacy authorization (Slice 9A).

Fail closed before any transport. Dual gate: allowlist AND network_policy.
Network destination checks delegate to ``offline_rag.core.network_policy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.core.network_policy import (
    NetworkPolicyError,
    NetworkPolicyReason,
    http_follow_redirects_allowed,
    normalize_openai_compatible_endpoint,
)
from offline_rag.core.network_policy import (
    destination_satisfies_policy as _destination_satisfies_policy,
)
from offline_rag.core.network_policy import (
    endpoint_in_allowlist as _endpoint_in_allowlist,
)


class AuthoringAuthReason(StrEnum):
    AUTHORIZED = "authorized"
    ENDPOINT_NOT_APPROVED = "endpoint_not_approved"
    NETWORK_POLICY_VIOLATION = NetworkPolicyReason.NETWORK_POLICY_VIOLATION.value
    UNSUPPORTED_ENDPOINT_SCHEME = NetworkPolicyReason.UNSUPPORTED_ENDPOINT_SCHEME.value
    HOSTNAME_RESOLUTION_FAILED = NetworkPolicyReason.HOSTNAME_RESOLUTION_FAILED.value
    PUBLIC_ADDRESS_NOT_ALLOWED = NetworkPolicyReason.PUBLIC_ADDRESS_NOT_ALLOWED.value
    INVALID_ENDPOINT = NetworkPolicyReason.INVALID_ENDPOINT.value
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
    try:
        return normalize_openai_compatible_endpoint(base_url)
    except NetworkPolicyError as exc:
        raise AuthoringPrivacyError(
            str(exc),
            reason=AuthoringAuthReason(exc.reason.value),
        ) from exc


def endpoint_in_allowlist(base_url: str, approved: list[str]) -> bool:
    return _endpoint_in_allowlist(base_url, approved)


def destination_satisfies_policy(
    base_url: str,
    *,
    network_policy: str,
) -> AuthoringAuthReason | None:
    """Return None when OK, otherwise a rejection reason."""
    reason = _destination_satisfies_policy(base_url, network_policy=network_policy)
    if reason is None:
        return None
    return AuthoringAuthReason(reason.value)


def authorize_authoring_endpoint(
    settings: AppSettings | AuthoringSettings,
) -> AuthorizedEndpoint:
    """Authorize the configured authoring endpoint under allowlist ∧ policy."""
    auth = settings.authoring if isinstance(settings, AppSettings) else settings
    normalized = normalize_authoring_endpoint(auth.base_url)

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
    return http_follow_redirects_allowed()
