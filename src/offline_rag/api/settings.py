"""Seneca generation Settings API (Slice 16D-A)."""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.product_settings import (
    ApiKeyAction,
    SenecaGenerationBody,
    SenecaGenerationSettingsFile,
    build_validated_product_record,
    generation_field_locks,
    read_product_generation_settings,
    write_product_generation_settings,
)
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.config.models import AppSettings, GenerationSettings
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    normalize_endpoint,
)

router = APIRouter(tags=["settings"])

ApiKeyActionLiteral = Literal["keep", "set", "clear"]


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


def _public_generation_view(gen: GenerationSettings) -> dict[str, Any]:
    return {
        "enabled": bool(gen.enabled),
        "provider": str(gen.provider),
        "base_url": str(gen.base_url),
        "model": str(gen.model),
        "timeout_seconds": int(gen.timeout_seconds),
        "api_key_configured": bool(gen.api_key),
    }


def _pending_effective_view(
    settings: AppSettings,
    *,
    product: SenecaGenerationSettingsFile | None,
    locks: dict[str, bool],
) -> dict[str, Any] | None:
    """Return PENDING effective future config, or None when no restart needed.

    Locked fields keep ACTIVE (operator) values so shadowed product values are
    never presented as becoming active after restart.
    """
    if product is None:
        return None
    active = settings.generation
    body = product.generation
    try:
        normalized = normalize_endpoint(body.base_url)
    except Exception:  # noqa: BLE001
        normalized = body.base_url

    pending = {
        "enabled": bool(active.enabled) if locks.get("enabled") else bool(body.enabled),
        "provider": "openai_compatible",
        "base_url": str(active.base_url) if locks.get("base_url") else str(normalized),
        "model": str(active.model) if locks.get("model") else str(body.model),
        "timeout_seconds": (
            int(active.timeout_seconds)
            if locks.get("timeout_seconds")
            else int(body.timeout_seconds)
        ),
        "api_key_configured": (
            bool(active.api_key)
            if locks.get("api_key")
            else bool(body.api_key)
        ),
    }
    active_view = _public_generation_view(active)
    if (
        pending["enabled"] == active_view["enabled"]
        and pending["base_url"] == active_view["base_url"]
        and pending["model"] == active_view["model"]
        and pending["timeout_seconds"] == active_view["timeout_seconds"]
        and pending["api_key_configured"] == active_view["api_key_configured"]
    ):
        return None
    return pending


@router.get("/v1/settings/generation")
def get_generation_settings(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = generation_field_locks(os.environ)
    try:
        product = read_product_generation_settings(settings.paths.product_settings)
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="malformed_product_settings"),
        ) from exc
    pending = _pending_effective_view(settings, product=product, locks=locks)
    active = _public_generation_view(settings.generation)
    return {
        "active": active,
        "pending": pending,
        "restart_required": pending is not None,
        "locks": locks,
        "strict_offline": bool(settings.project.strict_offline),
    }


class GenerationProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str
    model: str
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    api_key: str | None = None
    api_key_action: ApiKeyActionLiteral = "keep"

    @field_validator("base_url", "model")
    @classmethod
    def _trim(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must be non-empty")
        return text


class GenerationSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str
    model: str
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    api_key: str | None = None
    api_key_action: ApiKeyActionLiteral = "keep"

    @field_validator("base_url", "model")
    @classmethod
    def _trim(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must be non-empty")
        return text


def _resolve_api_key_for_write(
    *,
    action: ApiKeyAction,
    supplied: str | None,
    existing: str | None,
) -> str | None:
    if action == "keep":
        return existing
    if action == "clear":
        return None
    text = (supplied or "").strip()
    if not text:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="api_key_required_for_set"),
        )
    return text


def _assert_unlocked(locks: dict[str, bool], fields: dict[str, Any], active: GenerationSettings) -> None:
    comparisons = {
        "enabled": bool(active.enabled),
        "base_url": str(active.base_url),
        "model": str(active.model),
        "timeout_seconds": int(active.timeout_seconds),
    }
    for field, current in comparisons.items():
        if not locks.get(field):
            continue
        if fields.get(field) != current:
            raise AppError(
                ErrorCode.SETTINGS_LOCKED,
                details=SafeErrorDetails(field=field, reason="operator_locked"),
            )


@router.post("/v1/settings/generation/probe")
def probe_generation_settings(
    request: Request, body: GenerationProbeRequest
) -> dict[str, Any]:
    """Probe a PROSPECTIVE candidate without activating or persisting it."""
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = generation_field_locks(os.environ)
    # Operator locks still apply to prospective probe values that differ.
    _assert_unlocked(
        locks,
        {
            "enabled": body.enabled,
            "base_url": body.base_url,
            "model": body.model,
            "timeout_seconds": body.timeout_seconds,
        },
        settings.generation,
    )
    try:
        normalized = validate_endpoint_network_policy(
            body.base_url, strict_offline=bool(settings.project.strict_offline)
        )
    except EndpointPolicyError as exc:
        return {
            "ok": False,
            "reason": "policy_rejected",
            "available_models": [],
            "details": {"policy_reason": exc.reason},
        }

    existing_key = None
    try:
        product = read_product_generation_settings(settings.paths.product_settings)
        if product is not None:
            existing_key = product.generation.api_key
    except ValueError:
        existing_key = settings.generation.api_key
    if locks.get("api_key"):
        resolved_key = settings.generation.api_key
    else:
        resolved_key = _resolve_api_key_for_write(
            action=body.api_key_action,
            supplied=body.api_key,
            existing=existing_key if existing_key is not None else settings.generation.api_key,
        )

    probe_settings = settings.model_copy(deep=True)
    probe_settings.generation.enabled = True
    probe_settings.generation.base_url = normalized
    probe_settings.generation.model = body.model
    probe_settings.generation.timeout_seconds = body.timeout_seconds
    probe_settings.generation.api_key = resolved_key
    probe_settings.generation.approved_endpoints = [normalized]
    probe_settings.generation.approved_models = [body.model]

    generator = OpenAICompatibleGenerator(probe_settings)
    try:
        result = generator.probe()
    finally:
        close = getattr(generator, "close", None)
        if callable(close):
            close()

    reason = result.reason or ("ok" if result.ok else "endpoint_unreachable")
    # Map common probe reasons to closed vocabulary when possible.
    reason_text = str(reason).lower()
    if result.ok:
        closed = "ok"
    elif "not available" in reason_text or "model_not_listed" in reason_text:
        closed = "model_unavailable"
    elif "timed out" in reason_text or reason_text == "timeout":
        closed = "timeout"
    elif "non-json" in reason_text or "invalid" in reason_text:
        closed = "invalid_response"
    elif "http" in reason_text:
        closed = "http_error"
    elif "unauthorized" in reason_text or "not approved" in reason_text:
        closed = "policy_rejected"
    elif reason_text in {
        "policy_rejected",
        "endpoint_unreachable",
        "timeout",
        "http_error",
        "invalid_response",
        "model_unavailable",
    }:
        closed = reason_text
    else:
        closed = "endpoint_unreachable"
    return {
        "ok": bool(result.ok),
        "reason": closed if not result.ok else "ok",
        "available_models": list(result.available_models or []),
    }


@router.put("/v1/settings/generation")
def save_generation_settings(
    request: Request, body: GenerationSaveRequest
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = generation_field_locks(os.environ)
    _assert_unlocked(
        locks,
        {
            "enabled": body.enabled,
            "base_url": body.base_url,
            "model": body.model,
            "timeout_seconds": body.timeout_seconds,
        },
        settings.generation,
    )
    if locks.get("api_key") and body.api_key_action != "keep":
        raise AppError(
            ErrorCode.SETTINGS_LOCKED,
            details=SafeErrorDetails(field="api_key", reason="operator_locked"),
        )

    existing_key = None
    try:
        existing = read_product_generation_settings(settings.paths.product_settings)
        if existing is not None:
            existing_key = existing.generation.api_key
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="malformed_product_settings"),
        ) from exc

    resolved_key = _resolve_api_key_for_write(
        action=body.api_key_action,
        supplied=body.api_key,
        existing=existing_key,
    )

    try:
        record = build_validated_product_record(
            enabled=body.enabled,
            base_url=body.base_url,
            model=body.model,
            timeout_seconds=body.timeout_seconds,
            api_key=resolved_key,
            strict_offline=bool(settings.project.strict_offline),
        )
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason=str(exc)),
        ) from exc

    if body.enabled:
        # Re-probe so product-managed model approval is backed by validation.
        probe_body = GenerationProbeRequest(
            enabled=True,
            base_url=record.generation.base_url,
            model=record.generation.model,
            timeout_seconds=record.generation.timeout_seconds,
            api_key=resolved_key,
            api_key_action="set" if resolved_key else "clear",
        )
        probe = probe_generation_settings(request, probe_body)
        if not probe.get("ok"):
            raise AppError(
                ErrorCode.SETTINGS_PROBE_FAILED,
                details=SafeErrorDetails(reason=str(probe.get("reason") or "probe_failed")),
            )

    write_product_generation_settings(settings.paths.product_settings, record)
    pending = _pending_effective_view(settings, product=record, locks=locks)
    return {
        "saved": True,
        "restart_required": pending is not None,
        "pending": pending,
        "active": _public_generation_view(settings.generation),
    }
