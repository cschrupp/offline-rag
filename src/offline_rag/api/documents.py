"""Product document inventory endpoints (D10) — Slice 15C."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["documents"])


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


@router.get("/v1/documents")
def list_documents(
    request: Request,
    corpus: str = Query(..., min_length=1),
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    snapshot = runtime.publication.resolve(corpus)
    return {
        "corpus": snapshot.corpus_name,
        "snapshot_id": snapshot.snapshot_id,
        "documents": snapshot.document_summaries(),
    }


@router.get("/v1/documents/{document_id}")
def get_document(
    request: Request,
    document_id: str,
    corpus: str = Query(..., min_length=1),
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    snapshot = runtime.publication.resolve(corpus)
    summary = snapshot.get_document_summary(document_id)
    if summary is None:
        # Do not echo arbitrary path values into trusted identity fields —
        # unsafe IDs must still map to document_unknown 404 (D10).
        raise AppError(
            ErrorCode.DOCUMENT_UNKNOWN,
            details=SafeErrorDetails(
                corpus=snapshot.corpus_name,
                snapshot_id=snapshot.snapshot_id,
                reason="document_not_in_snapshot",
            ),
        )
    return {
        "corpus": snapshot.corpus_name,
        "snapshot_id": snapshot.snapshot_id,
        "document": summary,
    }
