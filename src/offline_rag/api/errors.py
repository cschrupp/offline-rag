"""FastAPI translation of AppError into the D08 envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from offline_rag.app.errors import AppError, ErrorCode


def register_app_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        # Non-HTTP application-terminal codes (e.g. request_cancelled) must not
        # invent a transport mapping. Surface canonical internal_error instead.
        if exc.http_status is None:
            internal = AppError(ErrorCode.INTERNAL_ERROR)
            payload = internal.to_error_response().model_dump(mode="json")
            return JSONResponse(status_code=500, content=payload)
        payload = exc.to_error_response().model_dump(mode="json")
        return JSONResponse(status_code=exc.http_status, content=payload)
