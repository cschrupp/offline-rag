"""FastAPI application factory with app-owned lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from offline_rag.api.authoring_settings import router as authoring_settings_router
from offline_rag.api.bind_policy import is_loopback_bind_host
from offline_rag.api.capabilities import router as capabilities_router
from offline_rag.api.compute_settings import router as compute_settings_router
from offline_rag.api.diag_gpu_probe import (
    DiagGpuSession,
    probe_flag_enabled,
    probe_token,
)
from offline_rag.api.documents import router as documents_router
from offline_rag.api.errors import register_app_error_handler
from offline_rag.api.frontend import mount_frontend
from offline_rag.api.gold_lab import router as gold_lab_router
from offline_rag.api.health import router as health_router
from offline_rag.api.ingest import router as ingest_router
from offline_rag.api.operations import router as operations_router
from offline_rag.api.query import router as query_router
from offline_rag.api.settings import router as settings_router
from offline_rag.api.traces import router as traces_router
from offline_rag.api.workspaces import router as workspaces_router
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ResourceFactories,
    default_resource_factories,
)
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings


class DiagGpuProbeConfigError(RuntimeError):
    """Startup failure when the diagnostic GPU probe is misconfigured."""


def _mount_diag_gpu_probe_if_enabled(app: FastAPI, settings: AppSettings) -> None:
    """Mount env-gated diag routes; fail closed when enabled but unsafe."""
    if not probe_flag_enabled():
        return
    if not probe_token():
        raise DiagGpuProbeConfigError(
            "OFFLINE_RAG_DIAG_GPU_PROBE=1 requires "
            "OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN to be set"
        )
    if not is_loopback_bind_host(str(settings.api.http_host)):
        raise DiagGpuProbeConfigError(
            "OFFLINE_RAG_DIAG_GPU_PROBE=1 requires loopback HTTP bind "
            f"(host={settings.api.http_host!r})"
        )
    from offline_rag.api.diag_gpu import router as diag_gpu_router

    app.state.diag_gpu_session = DiagGpuSession()
    app.include_router(diag_gpu_router)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime: ApplicationRuntime = app.state.runtime
    runtime.start()
    try:
        yield
    finally:
        # D19 drain: readiness false, cooperative cancel, grace wait, then close.
        await runtime.drain_async()


def create_app(
    *,
    settings: AppSettings | None = None,
    runtime: ApplicationRuntime | None = None,
    factories: ResourceFactories | None = None,
) -> FastAPI:
    """Build the OfflineRAG HTTP application.

    Slice 15 routes: /health*, /v1/documents*, /v1/ingest, /v1/query, /v1/trace/{id}.
    Slice 16B routes: /v1/workspaces*, /v1/operations/{id}.
    Slice 16C: same-origin SPA static delivery when OFFLINE_RAG_UI_DIR is present.
    """
    if runtime is not None and factories is not None:
        raise ValueError("pass runtime or factories, not both")

    if runtime is None:
        resolved_settings = settings if settings is not None else load_settings()
        resolved_factories = (
            factories if factories is not None else default_resource_factories()
        )
        runtime = ApplicationRuntime(
            settings=resolved_settings,
            factories=resolved_factories,
        )
    elif settings is not None and runtime.settings is not settings:
        raise ValueError("settings does not match the provided runtime")

    app = FastAPI(
        title="OfflineRAG API",
        version="1.0.0",
        lifespan=_lifespan,
    )
    app.state.runtime = runtime
    register_app_error_handler(app)
    app.include_router(health_router)
    app.include_router(capabilities_router)
    app.include_router(settings_router)
    app.include_router(authoring_settings_router)
    app.include_router(compute_settings_router)
    app.include_router(documents_router)
    app.include_router(ingest_router)
    app.include_router(query_router)
    app.include_router(traces_router)
    app.include_router(workspaces_router)
    app.include_router(operations_router)
    app.include_router(gold_lab_router)
    _mount_diag_gpu_probe_if_enabled(app, runtime.settings)
    # SPA fallback must be registered after API routers so /v1/* and /health*
    # retain backend semantics (including API 404s).
    mount_frontend(app)
    return app
