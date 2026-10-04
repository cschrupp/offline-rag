"""FastAPI application factory with app-owned lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from offline_rag.api.documents import router as documents_router
from offline_rag.api.errors import register_app_error_handler
from offline_rag.api.health import router as health_router
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ResourceFactories,
    default_resource_factories,
)
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime: ApplicationRuntime = app.state.runtime
    runtime.start()
    try:
        yield
    finally:
        runtime.shutdown()


def create_app(
    *,
    settings: AppSettings | None = None,
    runtime: ApplicationRuntime | None = None,
    factories: ResourceFactories | None = None,
) -> FastAPI:
    """Build the OfflineRAG HTTP application.

    Slice 15C routes: /health* and /v1/documents*.
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
    app.include_router(documents_router)
    return app
