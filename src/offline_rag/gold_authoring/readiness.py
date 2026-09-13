"""Authoring readiness (configuration + privacy authorization; no live probe)."""

from __future__ import annotations

from dataclasses import dataclass, field

from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.contracts import (
    ADAPTER_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    QUESTION_PROPOSAL_CONTRACT,
    RELEVANCE_PRELABEL_CONTRACT,
    SUPPORTED_PROVIDER,
)
from offline_rag.gold_authoring.privacy import (
    AuthoringAuthReason,
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)


@dataclass(frozen=True, slots=True)
class AuthoringReadiness:
    ready: bool
    reason_codes: list[str] = field(default_factory=list)
    provider_supported: bool = False
    adapter_supported: bool = False
    contracts_supported: bool = False
    endpoint_configured: bool = False
    endpoint_approved: bool = False
    network_policy_satisfied: bool = False
    model_configured: bool = False
    model_approved: bool = False
    connectivity_checked: bool = False
    enabled: bool = False
    provider: str = ""
    adapter_contract: str = ""
    model: str | None = None
    network_policy: str = ""
    base_url: str = ""
    api_key_configured: bool = False


def evaluate_authoring_readiness(settings: AppSettings) -> AuthoringReadiness:
    auth = settings.authoring
    reasons: list[str] = []

    if not auth.enabled:
        reasons.append("disabled")

    provider_supported = auth.provider == SUPPORTED_PROVIDER
    if not provider_supported:
        reasons.append("unsupported_provider")

    adapter_supported = auth.adapter_contract == ADAPTER_CONTRACT
    if not adapter_supported:
        reasons.append("unsupported_adapter")

    contracts_supported = (
        auth.contracts.question_proposal == QUESTION_PROPOSAL_CONTRACT
        and auth.contracts.relevance_prelabel == RELEVANCE_PRELABEL_CONTRACT
        and auth.contracts.artifact == AUTHORING_ARTIFACT_CONTRACT
    )
    if not contracts_supported:
        reasons.append("unsupported_contract")

    endpoint_configured = bool(auth.base_url and str(auth.base_url).strip())
    if not endpoint_configured:
        reasons.append("endpoint_not_configured")

    model_configured = auth.model is not None and bool(auth.model.strip())
    if not model_configured:
        reasons.append("model_unset")

    model_approved = bool(model_configured and auth.model in auth.approved_models)
    if model_configured and not model_approved:
        reasons.append("model_not_approved")

    endpoint_approved = False
    network_policy_satisfied = False
    if endpoint_configured:
        try:
            authorize_authoring_endpoint(settings)
            endpoint_approved = True
            network_policy_satisfied = True
        except AuthoringPrivacyError as exc:
            if exc.reason == AuthoringAuthReason.ENDPOINT_NOT_APPROVED:
                reasons.append("endpoint_not_approved")
            elif exc.reason in {
                AuthoringAuthReason.NETWORK_POLICY_VIOLATION,
                AuthoringAuthReason.PUBLIC_ADDRESS_NOT_ALLOWED,
            }:
                # Dual-gate: still note whether allowlist would have passed.
                from offline_rag.gold_authoring.privacy import endpoint_in_allowlist

                endpoint_approved = endpoint_in_allowlist(
                    auth.base_url, list(auth.approved_endpoints)
                )
                if not endpoint_approved:
                    reasons.append("endpoint_not_approved")
                reasons.append(str(exc.reason))
            else:
                reasons.append(str(exc.reason))

    ready = (
        auth.enabled
        and provider_supported
        and adapter_supported
        and contracts_supported
        and endpoint_configured
        and model_configured
        and model_approved
        and endpoint_approved
        and network_policy_satisfied
    )
    # Deduplicate while preserving order.
    deduped: list[str] = []
    seen: set[str] = set()
    for code in reasons:
        if code not in seen:
            seen.add(code)
            deduped.append(code)

    return AuthoringReadiness(
        ready=ready,
        reason_codes=deduped,
        provider_supported=provider_supported,
        adapter_supported=adapter_supported,
        contracts_supported=contracts_supported,
        endpoint_configured=endpoint_configured,
        endpoint_approved=endpoint_approved,
        network_policy_satisfied=network_policy_satisfied,
        model_configured=model_configured,
        model_approved=model_approved,
        connectivity_checked=False,
        enabled=auth.enabled,
        provider=auth.provider,
        adapter_contract=auth.adapter_contract,
        model=auth.model,
        network_policy=auth.network_policy,
        base_url=auth.base_url,
        api_key_configured=bool(auth.api_key),
    )


def authoring_status_label(readiness: AuthoringReadiness) -> str:
    return "READY" if readiness.ready else "NOT_READY"
