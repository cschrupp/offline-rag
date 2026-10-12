"""Read-only product capabilities (Slice 16D-A)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness

router = APIRouter(tags=["capabilities"])


def _runtime(request: Request) -> ApplicationRuntime:
    return request.app.state.runtime


@router.get("/v1/capabilities")
def get_capabilities(request: Request) -> dict[str, Any]:
    """Return ACTIVE/effective runtime capabilities (no secrets, no pending)."""
    runtime = _runtime(request)
    runtime.require_ready()
    settings = runtime.settings
    gen = settings.generation
    auth = settings.authoring
    api = settings.api
    readiness = evaluate_authoring_readiness(settings)
    return {
        "product": {
            "name": "Seneca",
            "descriptor": "Grounded knowledge workspace",
        },
        "source_limits": {
            "max_active_sources": int(api.max_files_per_ingest),
            "max_bytes_per_source": int(api.max_bytes_per_document),
            "max_active_source_bytes": int(api.max_total_upload_bytes),
        },
        "generation": {
            "enabled": bool(gen.enabled),
            "provider": str(gen.provider),
            "base_url": str(gen.base_url),
            "model": str(gen.model),
            "timeout_seconds": int(gen.timeout_seconds),
        },
        "authoring": {
            "enabled": bool(auth.enabled),
            "provider": str(auth.provider),
            "base_url": str(auth.base_url),
            "model": auth.model,
            "timeout_seconds": int(auth.timeout_seconds),
            "ready": bool(readiness.ready),
            "reason_codes": list(readiness.reason_codes),
            "api_key_configured": bool(auth.api_key),
        },
    }
