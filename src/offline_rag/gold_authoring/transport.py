"""Authorize-then-invoke seam for future authoring transport (no LLM in 9A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.privacy import (
    AuthorizedEndpoint,
    authorize_authoring_endpoint,
    authoring_follow_redirects,
)
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness

T = TypeVar("T")


def invoke_authorized_authoring_transport(
    settings: AppSettings,
    transport: Callable[[AuthorizedEndpoint], T],
) -> T:
    """Run ``transport`` only after readiness + endpoint authorization succeed.

    Slice 9A provides this seam for tests; no production LLM caller uses it yet.
    """
    readiness = evaluate_authoring_readiness(settings)
    if not readiness.ready:
        raise RuntimeError(
            f"authoring is not READY: {', '.join(readiness.reason_codes) or 'unknown'}"
        )
    if authoring_follow_redirects():
        raise RuntimeError("authoring redirects must remain disabled")
    authorized = authorize_authoring_endpoint(settings)
    return transport(authorized)
