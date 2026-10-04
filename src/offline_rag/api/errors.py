"""FastAPI translation of AppError / validation into the D08 envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.validation import app_error_from_validation_errors


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

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        app_error = app_error_from_validation_errors(exc.errors())
        payload = app_error.to_error_response().model_dump(mode="json")
        return JSONResponse(status_code=422, content=payload)
