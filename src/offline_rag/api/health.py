"""Liveness / readiness probes (D09)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["health"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.get("/health")
@router.get("/health/live")
def health_live(request: Request) -> dict[str, str]:
    """Cheap process liveness — no model/generator/storage work."""
    _ = _runtime(request)  # ensure runtime object exists; do not touch resources
    return {"status": "live"}


@router.get("/health/ready")
def health_ready(request: Request) -> dict[str, str]:
    """Cached runtime readiness — no model load or generator probe."""
    runtime = _runtime(request)
    runtime.require_ready()
    return {"status": "ready"}
