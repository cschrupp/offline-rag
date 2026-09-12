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


def generation_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return READY or NOT_READY for offline-rag query (derived)."""
    name = validate_corpus_name(corpus_name)
    if not settings.generation.enabled:
        return "NOT_READY"
    if context_status_for_corpus(settings, name) != "READY":
        return "NOT_READY"
    ok, _ = _generation_config_ok(settings)
    if not ok:
        return "NOT_READY"
    gen = settings.generation
    if settings.security.reject_unapproved_generation_endpoint and not endpoint_authorized(
        gen.base_url, list(gen.approved_endpoints)
    ):
        return "NOT_READY"
    if settings.security.reject_unapproved_generation_model and (
        gen.model not in gen.approved_models
    ):
        return "NOT_READY"
    generator = OpenAICompatibleGenerator(settings)
    try:
        probe = generator.probe()
    finally:
        generator.close()
    if not probe.ok:
        return "NOT_READY"
    return "READY"


def describe_generation_status(
    settings: AppSettings, corpus_name: str
) -> dict[str, object]:
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
        if settings.security.reject_unapproved_generation_endpoint:
            endpoint_authorized_flag = endpoint_authorized(
                gen.base_url, list(gen.approved_endpoints)
            )
            if not endpoint_authorized_flag:
                reasons.append("configured endpoint is not approved")
        else:
            endpoint_authorized_flag = True

        if settings.security.reject_unapproved_generation_model:
            model_authorized_flag = gen.model in gen.approved_models
            if not model_authorized_flag:
                reasons.append("configured model is not approved")
        else:
            model_authorized_flag = True

        if (
            context_status == "READY"
            and endpoint_authorized_flag
            and model_authorized_flag
        ):
            probed = True
            generator = OpenAICompatibleGenerator(settings)
            try:
                probe = generator.probe()
            finally:
                generator.close()
            endpoint_reachable = probe.ok or "unreachable" not in probe.reason
            model_available = probe.ok
            if not probe.ok:
                reasons.append(probe.reason)

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
        "reasons": reasons,
    }
