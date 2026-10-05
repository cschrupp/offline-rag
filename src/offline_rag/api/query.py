"""POST /v1/query transport adapter (Phase 15E/15F / D21 / D18)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.api.workers import run_owned_worker
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.query import (
    MAX_QUESTION_CHARS,
    ProductQueryResponse,
    run_product_query,
)
from offline_rag.app.runtime import ApplicationRuntime

router = APIRouter(tags=["query"])


class ProductQueryRequest(BaseModel):
    """D21 single-turn server-owned product query contract."""

    model_config = ConfigDict(extra="forbid")

    corpus: str = Field(min_length=1)
    question: str

    @field_validator("question")
    @classmethod
    def _trim_question(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("question must be a string")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("question must be non-empty")
        if len(trimmed) > MAX_QUESTION_CHARS:
            raise ValueError("question exceeds maximum length")
        return trimmed


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


async def _execute_product_query_owned(
    *,
    request: Request,
    runtime: ApplicationRuntime,
    corpus: str,
    question: str,
) -> ProductQueryResponse | Response:
    """Run the canonical product query under request-owned capacity control."""
    runtime.require_ready()
    operation = runtime.operations.admit_query()
    try:

        def worker() -> ProductQueryResponse:
            return run_product_query(
                runtime,
                corpus=corpus,
                question=question,
                control=operation,
            )

        try:
            result = await run_owned_worker(
                request=request,
                operation=operation,
                worker=worker,
                watch_disconnect=True,
            )
        except AppError as exc:
            # request_cancelled has no normative HTTP mapping (D18). When the
            # client is already gone, avoid inventing 408/499; durable trace is
            # the terminal record. Otherwise let the adapter project AppError.
            if (
                exc.code is ErrorCode.REQUEST_CANCELLED
                and await request.is_disconnected()
            ):
                return Response(status_code=204)
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                details=SafeErrorDetails(reason="query_transport_fault"),
            ) from exc
        return result
    finally:
        runtime.operations.release(operation)


@router.post("/v1/query", response_model=None)
async def product_query(
    request: Request, body: ProductQueryRequest
) -> dict[str, Any] | Response:
    """Owned worker: capacity held until the query thread terminates."""
    runtime = _runtime(request)
    result = await _execute_product_query_owned(
        request=request,
        runtime=runtime,
        corpus=body.corpus,
        question=body.question,
    )
    if isinstance(result, Response):
        return result
    return result.as_dict()
