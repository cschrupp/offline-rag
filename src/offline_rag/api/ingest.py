"""POST /v1/ingest transport adapter (Phase 15D / D20)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_upload import (
    cleanup_staging,
    spool_multipart_upload,
    validate_ingest_http_envelope,
)
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["ingest"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.post("/v1/ingest")
async def ingest_documents(request: Request) -> dict[str, Any]:
    """Synchronous product replace ingest (no 202 / job id)."""
    runtime = _runtime(request)
    runtime.require_ready()

    boundary = validate_ingest_http_envelope(
        content_type=request.headers.get("content-type"),
        content_length=request.headers.get("content-length"),
        settings=runtime.settings,
    )

    gate = runtime.ingest_capacity
    if not gate.try_acquire():
        raise AppError(
            ErrorCode.SERVICE_OVERLOADED,
            details=SafeErrorDetails(reason="ingest_capacity_exhausted"),
        )

    upload = None
    try:
        upload = await spool_multipart_upload(
            settings=runtime.settings,
            boundary=boundary,
            body_chunks=request.stream(),
        )
        hooks = runtime.product_ingest_hooks
        result = await asyncio.to_thread(
            run_product_replace_ingest,
            runtime,
            upload,
            hooks=hooks,
        )
        return {
            "corpus": result.corpus,
            "snapshot_id": result.snapshot_id,
            "document_count": result.document_count,
        }
    except AppError:
        if upload is not None and upload.staging_root.exists():
            cleanup_staging(upload.staging_root)
        raise
    except Exception as exc:
        if upload is not None and upload.staging_root.exists():
            cleanup_staging(upload.staging_root)
        raise AppError(
            ErrorCode.INGEST_FAILED,
            details=SafeErrorDetails(reason="internal_ingest_failure"),
        ) from exc
    finally:
        gate.release()
