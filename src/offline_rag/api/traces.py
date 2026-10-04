"""GET /v1/trace/{trace_id} transport adapter (Phase 15E / D11)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from offline_rag.app.query import get_product_trace
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["traces"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.get("/v1/trace/{trace_id}")
def read_trace(request: Request, trace_id: str) -> dict[str, Any]:
    """Cheap allowlisted durable trace read."""
    runtime = _runtime(request)
    return get_product_trace(runtime, trace_id)
