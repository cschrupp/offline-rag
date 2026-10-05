"""Workspace / source / workspace-query HTTP adapters (Slice 16B)."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from python_multipart.multipart import MultipartParser, parse_options_header

from offline_rag.api.workers import run_owned_worker
from offline_rag.api.workspace_views import (
    operation_view,
    source_view,
    workspace_view,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.query import MAX_QUESTION_CHARS, run_workspace_query
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.etag import format_etag, parse_if_match
from offline_rag.app.workspace.lifecycle import SourceUpload, WorkspaceLifecycleService
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.ingestion.base import SUPPORTED_EXTENSIONS

router = APIRouter(tags=["workspaces"])

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _runtime(request: Request) -> ApplicationRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, ApplicationRuntime):
        raise TypeError("application runtime is not configured")
    return runtime


def _lifecycle(request: Request) -> WorkspaceLifecycleService:
    return _runtime(request).workspace_lifecycle


def _require_idempotency_key(raw: str | None) -> str:
    if raw is None or not str(raw).strip():
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_required"),
        )
    key = str(raw).strip()
    if len(key) > 256:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_invalid"),
        )
    return key


def _etag_response(
    body: dict[str, Any], *, revision: int, status_code: int = 200
) -> JSONResponse:
    response = JSONResponse(content=body, status_code=status_code)
    response.headers["ETag"] = format_etag(revision)
    return response


def _safe_content_filename(display_name: str) -> str:
    base = display_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].strip() or "source.bin"
    cleaned = _SAFE_FILENAME_RE.sub("_", base).strip("._") or "source.bin"
    return cleaned[:180]


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)


class WorkspacePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = Field(default=None, max_length=4096)


class SourcePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=512)


class WorkspaceQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


async def _spool_workspace_files(
    request: Request, *, settings: Any, allow_multiple: bool
) -> list[SourceUpload]:
    """Stream multipart ``files`` parts into bounded SourceUpload list."""
    from offline_rag.app.ingest_upload import client_basename

    content_type = request.headers.get("content-type")
    if not content_type:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="missing_content_type"),
        )
    main_type, options = parse_options_header(content_type.encode("latin-1"))
    if main_type.lower() != b"multipart/form-data":
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="not_multipart"),
        )
    boundary = options.get(b"boundary")
    if not boundary:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="missing_boundary"),
        )

    max_files = int(settings.api.max_files_per_ingest)
    max_doc = int(settings.api.max_bytes_per_document)
    max_total = int(settings.api.max_total_upload_bytes)

    uploads: list[SourceUpload] = []
    total = 0
    parse_error: AppError | None = None
    current_headers: dict[bytes, bytes] = {}
    header_field = bytearray()
    header_value = bytearray()
    current_field: str | None = None
    current_filename: str | None = None
    current_type: str | None = None
    chunks: list[bytes] = []
    size = 0

    def _fail(exc: AppError) -> None:
        nonlocal parse_error
        if parse_error is None:
            parse_error = exc

    def on_part_begin() -> None:
        nonlocal current_field, current_filename, current_type, size
        current_headers.clear()
        header_field.clear()
        header_value.clear()
        current_field = None
        current_filename = None
        current_type = None
        chunks.clear()
        size = 0

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_field.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        key = bytes(header_field).lower().strip()
        value = bytes(header_value).strip()
        current_headers[key] = value
        header_field.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        nonlocal current_field, current_filename, current_type
        if parse_error is not None:
            return
        disposition = current_headers.get(b"content-disposition", b"")
        _disp, opts = parse_options_header(disposition)
        name = opts.get(b"name", b"").decode("latin-1", errors="replace")
        current_field = name
        if name != "files":
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="unexpected_form_field"),
                )
            )
            return
        raw_filename = opts.get(b"filename")
        filename = (
            client_basename(raw_filename.decode("latin-1", errors="replace"))
            if raw_filename is not None
            else ""
        )
        if not filename:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="missing_filename"),
                )
            )
            return
        current_filename = filename
        ctype = current_headers.get(b"content-type")
        current_type = (
            ctype.decode("latin-1", errors="replace").strip() if ctype else None
        )

    def on_part_data(data: bytes, start: int, end: int) -> None:
        nonlocal size, total
        if parse_error is not None or current_field != "files":
            return
        chunk = data[start:end]
        size += len(chunk)
        if size > max_doc:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="document_too_large"),
                )
            )
            return
        if total + size > max_total:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="upload_too_large"),
                )
            )
            return
        chunks.append(chunk)

    def on_part_end() -> None:
        nonlocal total
        if parse_error is not None or current_field != "files":
            return
        raw = b"".join(chunks)
        if not raw:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="empty_document"),
                )
            )
            return
        filename = current_filename or "upload.bin"
        suffix = filename[filename.rfind(".") :].lower() if "." in filename else ""
        if suffix not in SUPPORTED_EXTENSIONS:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="unsupported_source_type"),
                )
            )
            return
        if len(uploads) >= max_files:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="too_many_files"),
                )
            )
            return
        if not allow_multiple and uploads:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="exactly_one_file_required"),
                )
            )
            return
        total += len(raw)
        uploads.append(
            SourceUpload(
                display_name=filename,
                content=raw,
                content_type=current_type or SUPPORTED_EXTENSIONS.get(suffix),
            )
        )

    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
        },
    )
    async for chunk in request.stream():
        if parse_error is not None:
            break
        parser.write(chunk)
    if parse_error is None:
        parser.finalize()
    if parse_error is not None:
        raise parse_error
    if not uploads:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="zero_files"),
        )
    if not allow_multiple and len(uploads) != 1:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="exactly_one_file_required"),
        )
    return uploads


async def _launch_scientific_mutation(
    *,
    request: Request,
    runtime: ApplicationRuntime,
    workspace_id: str,
    idempotency_key: str,
    worker_fn: Any,
) -> JSONResponse:
    """Admit ingest capacity, start worker, return 202 once durable op exists."""
    runtime.require_ready()
    handle = runtime.operations.admit_ingest()
    ops = ManagedOperationStore(runtime.settings)
    loop = asyncio.get_running_loop()
    error_box: list[BaseException] = []

    def _worker() -> None:
        try:
            worker_fn(handle)
        except BaseException as exc:  # noqa: BLE001 — capture for polling path
            error_box.append(exc)
        finally:
            runtime.operations.release(handle)

    future = loop.run_in_executor(None, _worker)
    operation = None
    for _ in range(400):
        operation = ops.find_by_idempotency(workspace_id, idempotency_key)
        if operation is not None:
            break
        if future.done():
            break
        await asyncio.sleep(0.025)

    if operation is None:
        # Worker failed before durable begin; surface the error.
        try:
            await asyncio.wrap_future(future)
        except AppError:
            raise
        except Exception as exc:
            if error_box:
                boxed = error_box[0]
                if isinstance(boxed, AppError):
                    raise boxed from exc
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="workspace_mutation_fault"),
            ) from exc
        if error_box:
            boxed = error_box[0]
            if isinstance(boxed, AppError):
                raise boxed
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="workspace_mutation_fault"),
            ) from boxed
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=workspace_id, reason="operation_not_visible"
            ),
        )

    # Detached: do not await completion; disconnect must not cancel capacity.
    body = operation_view(operation)
    response = JSONResponse(content=body, status_code=202)
    response.headers["Location"] = f"/v1/operations/{operation.operation_id}"
    if operation.expected_revision is not None:
        # ETag reflects the revision the mutation was admitted against until
        # success advances workspace revision (client re-GETs workspace).
        response.headers["ETag"] = format_etag(operation.expected_revision)
    _ = request  # retained for future disconnect telemetry
    return response


@router.get("/v1/workspaces")
def list_workspaces(request: Request) -> list[dict[str, Any]]:
    runtime = _runtime(request)
    runtime.require_ready()
    store = WorkspaceStore(runtime.settings)
    return [workspace_view(item) for item in store.list_active()]


@router.post("/v1/workspaces")
def create_workspace(
    request: Request,
    body: WorkspaceCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    key = _require_idempotency_key(idempotency_key)
    record = _lifecycle(request).create_workspace(
        idempotency_key=key, title=body.title, description=body.description
    )
    return _etag_response(workspace_view(record), revision=record.revision, status_code=201)


@router.get("/v1/workspaces/{workspace_id}")
def get_workspace(request: Request, workspace_id: str) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    record = WorkspaceStore(runtime.settings).get(workspace_id)
    return _etag_response(workspace_view(record), revision=record.revision)


@router.patch("/v1/workspaces/{workspace_id}")
def patch_workspace(
    request: Request,
    workspace_id: str,
    body: WorkspacePatchRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    if body.title is None and body.description is None:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="empty_metadata_patch"),
        )
    record = _lifecycle(request).patch_workspace_metadata(
        workspace_id,
        expected_revision=expected,
        title=body.title,
        description=body.description,
    )
    return _etag_response(workspace_view(record), revision=record.revision)


@router.delete("/v1/workspaces/{workspace_id}")
def delete_workspace(
    request: Request,
    workspace_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    record = _lifecycle(request).tombstone_workspace(
        workspace_id, expected_revision=expected
    )
    return _etag_response(workspace_view(record), revision=record.revision)


@router.get("/v1/workspaces/{workspace_id}/sources")
def list_sources(request: Request, workspace_id: str) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    record = WorkspaceStore(runtime.settings).get(workspace_id)
    body = {
        "workspace_id": workspace_id,
        "revision": record.revision,
        "sources": [source_view(s) for s in record.sources if s.active],
    }
    return _etag_response(body, revision=record.revision)


@router.post("/v1/workspaces/{workspace_id}/sources")
async def add_sources(
    request: Request,
    workspace_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    uploads = await _spool_workspace_files(
        request, settings=runtime.settings, allow_multiple=True
    )
    lifecycle = _lifecycle(request)

    def worker(handle: Any) -> None:
        lifecycle.add_sources(
            workspace_id,
            expected_revision=expected,
            idempotency_key=key,
            uploads=uploads,
            control=handle,
        )

    return await _launch_scientific_mutation(
        request=request,
        runtime=runtime,
        workspace_id=workspace_id,
        idempotency_key=key,
        worker_fn=worker,
    )


@router.get("/v1/workspaces/{workspace_id}/sources/{source_id}")
def get_source(request: Request, workspace_id: str, source_id: str) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    record = WorkspaceStore(runtime.settings).get(workspace_id)
    for item in record.sources:
        if item.active and item.source_id == source_id:
            return _etag_response(source_view(item), revision=record.revision)
    raise AppError(
        ErrorCode.SOURCE_UNKNOWN,
        details=SafeErrorDetails(workspace_id=workspace_id, source_id=source_id),
    )


@router.put("/v1/workspaces/{workspace_id}/sources/{source_id}")
async def replace_source(
    request: Request,
    workspace_id: str,
    source_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    uploads = await _spool_workspace_files(
        request, settings=runtime.settings, allow_multiple=False
    )
    lifecycle = _lifecycle(request)

    def worker(handle: Any) -> None:
        lifecycle.replace_source(
            workspace_id,
            source_id=source_id,
            expected_revision=expected,
            idempotency_key=key,
            upload=uploads[0],
            control=handle,
        )

    return await _launch_scientific_mutation(
        request=request,
        runtime=runtime,
        workspace_id=workspace_id,
        idempotency_key=key,
        worker_fn=worker,
    )


@router.patch("/v1/workspaces/{workspace_id}/sources/{source_id}")
def patch_source(
    request: Request,
    workspace_id: str,
    source_id: str,
    body: SourcePatchRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    record = _lifecycle(request).patch_source_metadata(
        workspace_id,
        source_id,
        expected_revision=expected,
        display_name=body.display_name,
    )
    active = next(s for s in record.sources if s.active and s.source_id == source_id)
    return _etag_response(source_view(active), revision=record.revision)


@router.delete("/v1/workspaces/{workspace_id}/sources/{source_id}")
async def delete_source(
    request: Request,
    workspace_id: str,
    source_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    lifecycle = _lifecycle(request)

    def worker(handle: Any) -> None:
        lifecycle.remove_source(
            workspace_id,
            source_id=source_id,
            expected_revision=expected,
            idempotency_key=key,
            control=handle,
        )

    return await _launch_scientific_mutation(
        request=request,
        runtime=runtime,
        workspace_id=workspace_id,
        idempotency_key=key,
        worker_fn=worker,
    )


@router.get("/v1/workspaces/{workspace_id}/sources/{source_id}/content")
def get_source_content(
    request: Request, workspace_id: str, source_id: str
) -> Response:
    runtime = _runtime(request)
    runtime.require_ready()
    record = WorkspaceStore(runtime.settings).get(workspace_id)
    if record.status is WorkspaceStatus.TOMBSTONED:
        raise AppError(
            ErrorCode.WORKSPACE_UNKNOWN,
            details=SafeErrorDetails(workspace_id=workspace_id),
        )
    source = None
    for item in record.sources:
        if item.active and item.source_id == source_id:
            source = item
            break
    if source is None:
        raise AppError(
            ErrorCode.SOURCE_UNKNOWN,
            details=SafeErrorDetails(workspace_id=workspace_id, source_id=source_id),
        )
    vault = RawSourceVault(runtime.settings.paths.workspaces)
    data = vault.load_bytes(workspace_id, source.vault_object_id)
    meta = vault.get_meta(workspace_id, source.vault_object_id)
    filename = _safe_content_filename(source.display_name)
    media = meta.content_type or "application/octet-stream"
    headers = {
        "Content-Type": media,
        "Content-Disposition": f"inline; filename=\"{filename}\"; "
        f"filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "ETag": f'"{meta.content_hash}"',
    }
    return Response(content=data, media_type=media, headers=headers)


@router.post("/v1/workspaces/{workspace_id}/query", response_model=None)
async def workspace_query(
    request: Request, workspace_id: str, body: WorkspaceQueryRequest
) -> dict[str, Any] | Response:
    runtime = _runtime(request)
    runtime.require_ready()
    operation = runtime.operations.admit_query()
    try:

        def worker() -> Any:
            return run_workspace_query(
                runtime,
                workspace_id=workspace_id,
                question=body.question,
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
            if (
                exc.code is ErrorCode.REQUEST_CANCELLED
                and await request.is_disconnected()
            ):
                return Response(status_code=204)
            raise
        return result.as_dict()
    finally:
        runtime.operations.release(operation)
