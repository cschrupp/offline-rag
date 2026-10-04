"""POST /v1/ingest transport adapter (Phase 15D/15F / D20 / D18)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from offline_rag.api.workers import run_owned_worker
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_upload import (
    cleanup_staging,
    spool_multipart_upload,
    validate_ingest_http_envelope,
)
from offline_rag.app.operations import CancelReason
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["ingest"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.post("/v1/ingest", response_model=None)
async def ingest_documents(request: Request) -> dict[str, Any] | Response:
    """Owned worker: capacity held until the ingest thread terminates."""
    runtime = _runtime(request)
    runtime.require_ready()

    boundary = validate_ingest_http_envelope(
        content_type=request.headers.get("content-type"),
        content_length=request.headers.get("content-length"),
        settings=runtime.settings,
    )

    # Admit before body spool so saturated capacity can reject early (15D).
    operation = runtime.operations.admit_ingest()
    upload = None
    try:
        try:
            upload = await spool_multipart_upload(
                settings=runtime.settings,
                boundary=boundary,
                body_chunks=request.stream(),
            )
        except AppError:
            if upload is not None and upload.staging_root.exists():
                cleanup_staging(upload.staging_root)
            raise
        except Exception:
            # Pre-lease disconnect/failure: cleanup only; no mutation.
            if await request.is_disconnected():
                operation.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            if upload is not None and upload.staging_root.exists():
                cleanup_staging(upload.staging_root)
            raise

        if await request.is_disconnected():
            # Still pre-lease: disconnect means cleanup, no mutation.
            operation.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            if upload.staging_root.exists():
                cleanup_staging(upload.staging_root)
            return Response(status_code=204)

        hooks = runtime.product_ingest_hooks

        def worker() -> Any:
            return run_product_replace_ingest(
                runtime,
                upload,
                hooks=hooks,
                control=operation,
            )

        # Post-lease client disconnect is ignored by OperationHandle; watching
        # remains best-effort. Capacity is released only after the worker ends.
        try:
            result = await run_owned_worker(
                request=request,
                operation=operation,
                worker=worker,
                watch_disconnect=True,
            )
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

        return {
            "corpus": result.corpus,
            "snapshot_id": result.snapshot_id,
            "document_count": result.document_count,
        }
    finally:
        runtime.operations.release(operation)
