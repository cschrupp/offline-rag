"""HTTP routes for the env-gated GPU diagnostic probe."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from offline_rag.api.diag_gpu_probe import (
    DIAG_GPU_PROBE_HEADER,
    DiagGpuSession,
    build_state,
    probe_token,
    run_action,
)
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(include_in_schema=False)

DiagOp = Literal[
    "load_embedder",
    "load_reranker",
    "touch_embedder",
    "touch_reranker",
    "h2_reserve_gap",
    "h2_fragment",
    "release_h2",
]


class DiagGpuActionBody(BaseModel):
    op: DiagOp = Field(..., description="Diagnostic conditioning operation")


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise HTTPException(status_code=503, detail="runtime unavailable")
    return runtime


def _session(request: Request) -> DiagGpuSession:
    session = getattr(request.app.state, "diag_gpu_session", None)
    if not isinstance(session, DiagGpuSession):
        raise HTTPException(status_code=503, detail="diag session unavailable")
    return session


def _authorize(token_header: str | None) -> None:
    expected = probe_token()
    # Token is never logged. Compare in constant-ish fashion for small secrets.
    if not expected or token_header is None or token_header != expected:
        raise HTTPException(status_code=401, detail="diagnostic token required")


@router.get("/v1/_diag/gpu/state", include_in_schema=False)
def diag_gpu_state(
    request: Request,
    x_seneca_diag_token: str | None = Header(default=None, alias=DIAG_GPU_PROBE_HEADER),
) -> dict[str, Any]:
    _authorize(x_seneca_diag_token)
    return build_state(_runtime(request), _session(request))


@router.post("/v1/_diag/gpu/action", include_in_schema=False)
def diag_gpu_action(
    body: DiagGpuActionBody,
    request: Request,
    x_seneca_diag_token: str | None = Header(default=None, alias=DIAG_GPU_PROBE_HEADER),
) -> dict[str, Any]:
    _authorize(x_seneca_diag_token)
    try:
        return run_action(_runtime(request), _session(request), body.op)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
