"""Explicit deployment-profile overlays for operator-owned runtime config."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any

PORTFOLIO_OPENROUTER_PROFILE = "portfolio_openrouter"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

EXTERNAL_MODEL_ENV = "OFFLINE_RAG_EXTERNAL_INFERENCE_MODEL"
EXTERNAL_API_KEY_ENV = "OFFLINE_RAG_EXTERNAL_INFERENCE_API_KEY"
DEPLOYMENT_PROFILE_ENV = "OFFLINE_RAG_DEPLOYMENT_PROFILE"


class DeploymentProfileError(ValueError):
    """Invalid or incomplete explicit deployment-profile configuration."""


def apply_deployment_profile_overlay(
    payload: MutableMapping[str, Any],
    *,
    environ: Mapping[str, str],
) -> None:
    """Apply the final profile-owned OpenRouter settings in place.

    Profile inputs are deliberately kept out of ordinary environment overrides
    and are applied after YAML, product settings, environment, and programmatic
    overlays have been merged.
    """
    deployment = payload.get("deployment")
    profile = deployment.get("profile") if isinstance(deployment, dict) else None
    external_inputs_present = (
        EXTERNAL_MODEL_ENV in environ or EXTERNAL_API_KEY_ENV in environ
    )

    if profile != PORTFOLIO_OPENROUTER_PROFILE:
        if external_inputs_present:
            raise DeploymentProfileError(
                "external inference inputs require "
                "OFFLINE_RAG_DEPLOYMENT_PROFILE=portfolio_openrouter"
            )
        return

    model = environ.get(EXTERNAL_MODEL_ENV, "").strip()
    if not model:
        raise DeploymentProfileError(
            f"{EXTERNAL_MODEL_ENV} is required when "
            "OFFLINE_RAG_DEPLOYMENT_PROFILE=portfolio_openrouter"
        )

    api_key = environ.get(EXTERNAL_API_KEY_ENV, "").strip()
    if not api_key:
        raise DeploymentProfileError(
            f"{EXTERNAL_API_KEY_ENV} is required when "
            "OFFLINE_RAG_DEPLOYMENT_PROFILE=portfolio_openrouter"
        )

    from offline_rag.gold_authoring.contracts import ADAPTER_CONTRACT

    payload.setdefault("project", {})["strict_offline"] = False
    payload.setdefault("generation", {}).update(
        {
            "enabled": True,
            "provider": "openai_compatible",
            "base_url": OPENROUTER_BASE_URL,
            "model": model,
            "api_key": api_key,
            "approved_endpoints": [OPENROUTER_BASE_URL],
            "approved_models": [model],
        }
    )
    payload.setdefault("authoring", {}).update(
        {
            "enabled": True,
            "provider": "openai_compatible",
            "adapter_contract": ADAPTER_CONTRACT,
            "base_url": OPENROUTER_BASE_URL,
            "model": model,
            "api_key": api_key,
            "approved_endpoints": [OPENROUTER_BASE_URL],
            "approved_models": [model],
        }
    )
    payload.setdefault("security", {}).update(
        {
            "reject_unapproved_generation_endpoint": True,
            "reject_unapproved_generation_model": True,
        }
    )


__all__ = [
    "DEPLOYMENT_PROFILE_ENV",
    "EXTERNAL_API_KEY_ENV",
    "EXTERNAL_MODEL_ENV",
    "OPENROUTER_BASE_URL",
    "PORTFOLIO_OPENROUTER_PROFILE",
    "DeploymentProfileError",
    "apply_deployment_profile_overlay",
]
