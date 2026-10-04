"""POST /v1/query transport adapter (Phase 15E / D21)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.query import MAX_QUESTION_CHARS, run_product_query
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


@router.post("/v1/query")
async def product_query(
    request: Request, body: ProductQueryRequest
) -> dict[str, Any]:
    """Offload blocking grounded query so the ASGI loop stays responsive."""
    runtime = _runtime(request)
    try:
        result = await asyncio.to_thread(
            run_product_query,
            runtime,
            corpus=body.corpus,
            question=body.question,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            details=SafeErrorDetails(reason="query_transport_fault"),
        ) from exc
    return result.as_dict()
