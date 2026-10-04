"""FastAPI translation of AppError into the D08 envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from offline_rag.app.errors import AppError


def register_app_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        status = exc.http_status if exc.http_status is not None else 500
        payload = exc.to_error_response().model_dump(mode="json")
        return JSONResponse(status_code=status, content=payload)
