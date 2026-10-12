"""Seneca Gold Lab authoring Settings API (Slice 16 closure remediation)."""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.authoring_product_settings import (
    ApiKeyAction,
    SenecaAuthoringSettingsFile,
    authoring_api_key_is_managed,
    authoring_field_locks,
    build_validated_authoring_product_record,
    infer_authoring_network_policy,
    read_product_authoring_settings,
    write_product_authoring_settings,
)
from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.config.models import AppSettings, AuthoringSettings
from offline_rag.generation.openai_compatible import normalize_endpoint
from offline_rag.gold_authoring.privacy import (
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness

router = APIRouter(tags=["settings"])

ApiKeyActionLiteral = Literal["keep", "set", "clear"]


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


def _public_authoring_view(auth: AuthoringSettings) -> dict[str, Any]:
    return {
        "enabled": bool(auth.enabled),
        "provider": str(auth.provider),
        "base_url": str(auth.base_url),
        "model": auth.model,
        "timeout_seconds": int(auth.timeout_seconds),
        "network_policy": str(auth.network_policy),
        "api_key_configured": bool(auth.api_key),
    }


def _readiness_view(settings: AppSettings) -> dict[str, Any]:
    ready = evaluate_authoring_readiness(settings)
    return {
        "ready": bool(ready.ready),
        "reason_codes": list(ready.reason_codes),
        "enabled": bool(ready.enabled),
        "endpoint_configured": bool(ready.endpoint_configured),
        "endpoint_approved": bool(ready.endpoint_approved),
        "model_configured": bool(ready.model_configured),
        "model_approved": bool(ready.model_approved),
        "network_policy_satisfied": bool(ready.network_policy_satisfied),
        "api_key_configured": bool(ready.api_key_configured),
    }


def _pending_effective_view(
    settings: AppSettings,
    *,
    product: SenecaAuthoringSettingsFile | None,
    locks: dict[str, bool],
    api_key_managed: bool,
) -> dict[str, Any] | None:
    if product is None:
        return None
    active = settings.authoring
    body = product.authoring

    if locks.get("base_url") or body.base_url is None:
        pending_base_url = str(active.base_url)
    else:
        try:
            pending_base_url = str(normalize_endpoint(body.base_url))
        except Exception:  # noqa: BLE001
            pending_base_url = str(body.base_url)

    if locks.get("model") or body.model is None:
        pending_model = active.model
    else:
        pending_model = str(body.model)

    if locks.get("network_policy") or body.network_policy is None:
        pending_policy = str(active.network_policy)
    else:
        pending_policy = str(body.network_policy)

    if locks.get("api_key"):
        future_key_configured = bool(active.api_key)
    elif api_key_managed:
        future_key_configured = bool(body.api_key)
    else:
        future_key_configured = bool(active.api_key)

    pending = {
        "enabled": bool(active.enabled) if locks.get("enabled") else bool(body.enabled),
        "provider": "openai_compatible",
        "base_url": pending_base_url,
        "model": pending_model,
        "timeout_seconds": (
            int(active.timeout_seconds)
            if locks.get("timeout_seconds")
            else int(body.timeout_seconds)
        ),
        "network_policy": pending_policy,
        "api_key_configured": future_key_configured,
    }
    active_view = _public_authoring_view(active)
    if (
        pending["enabled"] == active_view["enabled"]
        and pending["base_url"] == active_view["base_url"]
        and pending["model"] == active_view["model"]
        and pending["timeout_seconds"] == active_view["timeout_seconds"]
        and pending["network_policy"] == active_view["network_policy"]
        and pending["api_key_configured"] == active_view["api_key_configured"]
    ):
        return None
    return pending


@router.get("/v1/settings/authoring")
def get_authoring_settings(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = authoring_field_locks(os.environ)
    try:
        product = read_product_authoring_settings(settings.paths.product_settings)
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="malformed_product_settings"),
        ) from exc
    pending = _pending_effective_view(
        settings,
        product=product,
        locks=locks,
        api_key_managed=authoring_api_key_is_managed(settings.paths.product_settings),
    )
    return {
        "active": _public_authoring_view(settings.authoring),
        "pending": pending,
        "restart_required": pending is not None,
        "locks": locks,
        "strict_offline": bool(settings.project.strict_offline),
        "readiness": _readiness_view(settings),
    }


class AuthoringProbeRequest(BaseModel):
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


class AuthoringSaveRequest(BaseModel):
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


def _assert_unlocked(
    locks: dict[str, bool], fields: dict[str, Any], active: AuthoringSettings
) -> None:
    comparisons = {
        "enabled": bool(active.enabled),
        "base_url": str(active.base_url),
        "model": active.model,
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


def _extract_model_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item["id"])
    return models


def _probe_models(
    *,
    base_url: str,
    model: str,
    api_key: str | None,
    timeout_seconds: int,
    network_policy: str,
    approved_endpoints: list[str],
    approved_models: list[str],
) -> dict[str, Any]:
    """Prospective /models probe with follow_redirects=False; no persistence."""
    prospective = AuthoringSettings(
        enabled=True,
        base_url=base_url,
        model=model,
        api_key=api_key,
        network_policy=network_policy,  # type: ignore[arg-type]
        approved_endpoints=approved_endpoints,
        approved_models=approved_models,
        timeout_seconds=timeout_seconds,
    )
    try:
        authorize_authoring_endpoint(prospective)
    except AuthoringPrivacyError as exc:
        return {
            "ok": False,
            "reason": "policy_rejected",
            "available_models": [],
            "details": {"policy_reason": str(exc.reason)},
        }

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    models_url = f"{normalize_endpoint(base_url)}/models"
    try:
        with httpx.Client(
            timeout=float(min(timeout_seconds, 30)),
            follow_redirects=False,
            headers=headers or None,
        ) as client:
            response = client.get(models_url)
    except httpx.TimeoutException:
        return {"ok": False, "reason": "timeout", "available_models": []}
    except httpx.HTTPError:
        return {"ok": False, "reason": "endpoint_unreachable", "available_models": []}

    if response.status_code >= 400:
        return {"ok": False, "reason": "http_error", "available_models": []}
    try:
        payload = response.json()
    except ValueError:
        return {"ok": False, "reason": "invalid_response", "available_models": []}
    models = _extract_model_ids(payload)
    if model not in models:
        return {
            "ok": False,
            "reason": "model_unavailable",
            "available_models": models,
        }
    return {"ok": True, "reason": "ok", "available_models": models}


@router.post("/v1/settings/authoring/probe")
def probe_authoring_settings(
    request: Request, body: AuthoringProbeRequest
) -> dict[str, Any]:
    """Probe a PROSPECTIVE authoring candidate without activating or persisting."""
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = authoring_field_locks(os.environ)
    _assert_unlocked(
        locks,
        {
            "enabled": body.enabled,
            "base_url": body.base_url,
            "model": body.model,
            "timeout_seconds": body.timeout_seconds,
        },
        settings.authoring,
    )
    try:
        normalized = validate_endpoint_network_policy(
            body.base_url, strict_offline=bool(settings.project.strict_offline)
        )
    except EndpointPolicyError:
        return {
            "ok": False,
            "reason": "policy_rejected",
            "available_models": [],
        }

    if locks.get("network_policy"):
        network_policy = str(settings.authoring.network_policy)
    else:
        try:
            network_policy = infer_authoring_network_policy(normalized)
        except ValueError:
            return {
                "ok": False,
                "reason": "policy_rejected",
                "available_models": [],
            }

    existing_key = None
    product_key_managed = False
    try:
        product = read_product_authoring_settings(settings.paths.product_settings)
        product_key_managed = authoring_api_key_is_managed(
            settings.paths.product_settings
        )
        if product is not None:
            existing_key = product.authoring.api_key
    except ValueError:
        existing_key = settings.authoring.api_key
        product_key_managed = False

    if locks.get("api_key"):
        resolved_key = settings.authoring.api_key
    elif body.api_key_action == "keep":
        if product_key_managed:
            resolved_key = existing_key
        else:
            resolved_key = settings.authoring.api_key
    else:
        resolved_key = _resolve_api_key_for_write(
            action=body.api_key_action,
            supplied=body.api_key,
            existing=existing_key if product_key_managed else settings.authoring.api_key,
        )

    approved_endpoints = (
        list(settings.authoring.approved_endpoints)
        if locks.get("base_url")
        else [normalized]
    )
    approved_models = (
        list(settings.authoring.approved_models)
        if locks.get("model")
        else [body.model]
    )

    return _probe_models(
        base_url=normalized,
        model=body.model,
        api_key=resolved_key,
        timeout_seconds=body.timeout_seconds,
        network_policy=network_policy,
        approved_endpoints=approved_endpoints,
        approved_models=approved_models,
    )


@router.put("/v1/settings/authoring")
def save_authoring_settings(
    request: Request, body: AuthoringSaveRequest
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    locks = authoring_field_locks(os.environ)
    _assert_unlocked(
        locks,
        {
            "enabled": body.enabled,
            "base_url": body.base_url,
            "model": body.model,
            "timeout_seconds": body.timeout_seconds,
        },
        settings.authoring,
    )
    if locks.get("api_key") and body.api_key_action != "keep":
        raise AppError(
            ErrorCode.SETTINGS_LOCKED,
            details=SafeErrorDetails(field="api_key", reason="operator_locked"),
        )

    existing: SenecaAuthoringSettingsFile | None = None
    existing_key = None
    try:
        existing = read_product_authoring_settings(settings.paths.product_settings)
        if existing is not None:
            existing_key = existing.authoring.api_key
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason="malformed_product_settings"),
        ) from exc

    persist_base_url: str | None = None if locks.get("base_url") else body.base_url
    persist_model: str | None = None if locks.get("model") else body.model

    if locks.get("network_policy"):
        persist_policy = None  # product must not rewrite operator policy
    elif persist_base_url is not None:
        try:
            persist_policy = infer_authoring_network_policy(persist_base_url)
        except ValueError as exc:
            raise AppError(
                ErrorCode.SETTINGS_INVALID,
                details=SafeErrorDetails(reason=str(exc)),
            ) from exc
    else:
        persist_policy = None

    manage_api_key = False
    if locks.get("api_key"):
        resolved_key = existing_key
        manage_api_key = authoring_api_key_is_managed(settings.paths.product_settings)
    elif body.api_key_action == "keep":
        if authoring_api_key_is_managed(settings.paths.product_settings):
            resolved_key = existing_key
            manage_api_key = True
        else:
            resolved_key = None
            manage_api_key = False
    else:
        resolved_key = _resolve_api_key_for_write(
            action=body.api_key_action,
            supplied=body.api_key,
            existing=existing_key,
        )
        manage_api_key = True

    try:
        record = build_validated_authoring_product_record(
            enabled=(
                body.enabled
                if not locks.get("enabled")
                else bool(settings.authoring.enabled)
            ),
            base_url=persist_base_url,
            model=persist_model,
            timeout_seconds=(
                body.timeout_seconds
                if not locks.get("timeout_seconds")
                else int(settings.authoring.timeout_seconds)
            ),
            api_key=resolved_key,
            network_policy=persist_policy,
            strict_offline=bool(settings.project.strict_offline),
        )
    except ValueError as exc:
        raise AppError(
            ErrorCode.SETTINGS_INVALID,
            details=SafeErrorDetails(reason=str(exc)),
        ) from exc

    if body.enabled and (persist_base_url is not None or persist_model is not None):
        probe_body = AuthoringProbeRequest(
            enabled=True,
            base_url=persist_base_url or str(settings.authoring.base_url),
            model=persist_model or str(settings.authoring.model or ""),
            timeout_seconds=record.authoring.timeout_seconds,
            api_key=resolved_key,
            api_key_action="set" if resolved_key else "clear",
        )
        probe = probe_authoring_settings(request, probe_body)
        if not probe.get("ok"):
            raise AppError(
                ErrorCode.SETTINGS_PROBE_FAILED,
                details=SafeErrorDetails(
                    reason=str(probe.get("reason") or "probe_failed")
                ),
            )

    write_product_authoring_settings(
        settings.paths.product_settings,
        record,
        manage_api_key=manage_api_key,
    )
    pending = _pending_effective_view(
        settings,
        product=record,
        locks=locks,
        api_key_managed=manage_api_key,
    )
    return {
        "saved": True,
        "restart_required": pending is not None,
        "pending": pending,
        "active": _public_authoring_view(settings.authoring),
    }
