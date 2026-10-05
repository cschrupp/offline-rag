"""GET /v1/operations/{operation_id} (Slice 16B)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from offline_rag.api.workspace_views import operation_view
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore

router = APIRouter(tags=["operations"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.get("/v1/operations/{operation_id}")
def get_operation(request: Request, operation_id: str) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    record = ManagedOperationStore(runtime.settings).get_by_operation_id(operation_id)
    return operation_view(record)
