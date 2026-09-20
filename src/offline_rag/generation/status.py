"""Derived Generation readiness (no persisted GenerationState)."""

from __future__ import annotations

from pydantic import ValidationError

from offline_rag.config.models import AppSettings, GenerationSettings
from offline_rag.context.status import (
    context_status_for_corpus,
    describe_context_status,
)
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    OpenAICompatibleGeneratorError,
    endpoint_authorized,
    normalize_endpoint,
)
from offline_rag.ingestion.discovery import validate_corpus_name


def _generation_config_ok(settings: AppSettings) -> tuple[bool, str | None]:
    try:
        GenerationSettings.model_validate(settings.generation.model_dump())
    except ValidationError as exc:
        return False, f"invalid generation configuration: {exc.errors()[0]['msg']}"
    gen = settings.generation
    if gen.provider != "openai_compatible":
        return False, f"unsupported generation provider: {gen.provider}"
    if not gen.model.strip():
        return False, "generation.model must be non-empty"
    if gen.max_output_tokens < 1:
        return False, "generation.max_output_tokens must be >= 1"
    if gen.timeout_seconds <= 0:
        return False, "generation.timeout_seconds must be > 0"
    if not gen.approved_endpoints:
        return False, "generation.approved_endpoints must be non-empty"
    if not gen.approved_models:
        return False, "generation.approved_models must be non-empty"
    try:
        normalize_endpoint(gen.base_url)
    except OpenAICompatibleGeneratorError as exc:
        return False, str(exc)
    return True, None


def _authorization_flags(
    settings: AppSettings,
) -> tuple[bool, bool, list[str]]:
    """Return (endpoint_ok, model_ok, reasons) for allowlist policy."""
    reasons: list[str] = []
    gen = settings.generation
    if settings.security.reject_unapproved_generation_endpoint:
        endpoint_ok = endpoint_authorized(gen.base_url, list(gen.approved_endpoints))
        if not endpoint_ok:
            reasons.append("configured endpoint is not approved")
    else:
        endpoint_ok = True
    if settings.security.reject_unapproved_generation_model:
        model_ok = gen.model in gen.approved_models
        if not model_ok:
            reasons.append("configured model is not approved")
    else:
        model_ok = True
    return endpoint_ok, model_ok, reasons


def _probe_provider(
    settings: AppSettings,
) -> tuple[bool, bool, bool, str | None]:
    """Return (probed, endpoint_reachable, model_available, failure_reason)."""
    generator = OpenAICompatibleGenerator(settings)
    try:
        probe = generator.probe()
    finally:
        generator.close()
    endpoint_reachable = probe.ok or "unreachable" not in probe.reason
    return True, endpoint_reachable, probe.ok, (None if probe.ok else probe.reason)


def generation_provider_status(settings: AppSettings) -> str:
    """Return READY/NOT_READY for the generation provider only (no context).

    Used by fixed-evidence evaluation (``offline-rag eval generation``).
    Does not require dense/lexical/hybrid/reranker/context readiness.
    """
    if not settings.generation.enabled:
        return "NOT_READY"
    ok, _ = _generation_config_ok(settings)
    if not ok:
        return "NOT_READY"
    endpoint_ok, model_ok, _ = _authorization_flags(settings)
    if not endpoint_ok or not model_ok:
        return "NOT_READY"
    _, _, model_available, _ = _probe_provider(settings)
    return "READY" if model_available else "NOT_READY"


def describe_generation_provider_status(settings: AppSettings) -> dict[str, object]:
    """Explain generation-provider readiness without upstream context checks."""
    reasons: list[str] = []
    gen = settings.generation
    if not gen.enabled:
        reasons.append("generation.enabled is false")
    ok, reason = _generation_config_ok(settings)
    if not ok and reason:
        reasons.append(reason)

    endpoint_authorized_flag = False
    model_authorized_flag = False
    endpoint_reachable = False
    model_available = False
    probed = False

    if gen.enabled and ok:
        endpoint_authorized_flag, model_authorized_flag, auth_reasons = (
            _authorization_flags(settings)
        )
        reasons.extend(auth_reasons)
        if endpoint_authorized_flag and model_authorized_flag:
            probed, endpoint_reachable, model_available, fail = _probe_provider(
                settings
            )
            if fail:
                reasons.append(fail)

    return {
        "status": generation_provider_status(settings),
        "generation_enabled": "true" if gen.enabled else "false",
        "provider": gen.provider,
        "model": gen.model,
        "api_key_configured": bool(gen.api_key),
        "endpoint_authorized": endpoint_authorized_flag,
        "model_authorized": model_authorized_flag,
        "endpoint_reachable": endpoint_reachable if probed else False,
        "model_available": model_available if probed else False,
        "probed": probed,
        "reasons": reasons,
    }


def generation_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return READY or NOT_READY for offline-rag query (context + provider)."""
    name = validate_corpus_name(corpus_name)
    if context_status_for_corpus(settings, name) != "READY":
        return "NOT_READY"
    return generation_provider_status(settings)


def describe_generation_status(
    settings: AppSettings, corpus_name: str
) -> dict[str, object]:
    """Explain Slice 8 generation readiness (context + provider).

    Live endpoint probe runs only when upstream Context is READY, matching
    historical doctor diagnostics.
    """
    name = validate_corpus_name(corpus_name)
    reasons: list[str] = []
    gen = settings.generation
    if not gen.enabled:
        reasons.append("generation.enabled is false")
    context_status = context_status_for_corpus(settings, name)
    if context_status != "READY":
        reasons.append("upstream Context is not ready")
    ok, reason = _generation_config_ok(settings)
    if not ok and reason:
        reasons.append(reason)

    endpoint_authorized_flag = False
    model_authorized_flag = False
    endpoint_reachable = False
    model_available = False
    probed = False

    if gen.enabled and ok:
        endpoint_authorized_flag, model_authorized_flag, auth_reasons = (
            _authorization_flags(settings)
        )
        reasons.extend(auth_reasons)
        if (
            context_status == "READY"
            and endpoint_authorized_flag
            and model_authorized_flag
        ):
            probed, endpoint_reachable, model_available, fail = _probe_provider(
                settings
            )
            if fail:
                reasons.append(fail)

    status = generation_status_for_corpus(settings, name)
    context_details = describe_context_status(settings, name)
    return {
        "status": status,
        "corpus_name": name,
        "context_status": context_status,
        "generation_enabled": "true" if gen.enabled else "false",
        "provider": gen.provider,
        "model": gen.model,
        "api_key_configured": bool(gen.api_key),
        "endpoint_authorized": endpoint_authorized_flag,
        "model_authorized": model_authorized_flag,
        "endpoint_reachable": endpoint_reachable if probed else False,
        "model_available": model_available if probed else False,
        "probed": probed,
        "context_details": context_details,
        "provider_status": generation_provider_status(settings),
        "reasons": reasons,
    }
