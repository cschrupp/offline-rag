"""Workspace / source / workspace-query HTTP adapters (Slice 16B)."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.api.workspace_views import (
    operation_view,
    source_view,
    workspace_view,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest_upload import validate_ingest_http_envelope
from offline_rag.app.operations import OperationHandle
from offline_rag.app.query import MAX_QUESTION_CHARS, run_workspace_query
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.etag import format_etag, parse_if_match
from offline_rag.app.workspace.lifecycle import SourceUpload, WorkspaceLifecycleService
from offline_rag.app.workspace.models import ManagedOperationKind, WorkspaceStatus
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.upload_spool import (
    WorkspaceUploadSpool,
    spool_workspace_multipart,
)
from offline_rag.app.workspace.vault import RawSourceVault

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


def _accepted_operation_response(operation: Any) -> JSONResponse:
    body = operation_view(operation)
    response = JSONResponse(content=body, status_code=202)
    response.headers["Location"] = f"/v1/operations/{operation.operation_id}"
    if operation.expected_revision is not None:
        response.headers["ETag"] = format_etag(operation.expected_revision)
    return response


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


def _uploads_from_spool(spool: WorkspaceUploadSpool) -> list[SourceUpload]:
    return [
        SourceUpload(
            display_name=item.display_name,
            content_type=item.content_type,
            spool_path=item.absolute_path,
            content_sha256=item.content_sha256,
        )
        for item in spool.files
    ]


async def _spool_workspace_files(
    request: Request, *, settings: Any, allow_multiple: bool
) -> WorkspaceUploadSpool:
    """Stream multipart ``files`` parts into durable staging before acceptance."""
    boundary = validate_ingest_http_envelope(
        content_type=request.headers.get("content-type"),
        content_length=request.headers.get("content-length"),
        settings=settings,
    )
    return await spool_workspace_multipart(
        settings=settings,
        boundary=boundary,
        body_chunks=request.stream(),
        allow_multiple=allow_multiple,
    )


async def _launch_scientific_mutation(
    *,
    runtime: ApplicationRuntime,
    lifecycle: WorkspaceLifecycleService,
    workspace_id: str,
    idempotency_key: str,
    kind: ManagedOperationKind,
    expected_revision: int,
    payload: dict[str, Any],
    worker_fn: Any,
    spool: WorkspaceUploadSpool | None = None,
    require_source_id: str | None = None,
) -> JSONResponse:
    """Reserve durable op (and spool) before capacity; return 202 only then."""
    runtime.require_ready()
    try:
        operation, handle = lifecycle.reserve_and_admit_scientific(
            workspace_id,
            kind=kind,
            idempotency_key=idempotency_key,
            expected_revision=expected_revision,
            payload=payload,
            require_source_id=require_source_id,
        )
    except Exception:
        if spool is not None:
            spool.cleanup()
        raise

    if handle is None:
        # Existing matching operation — do not acquire capacity or launch.
        if spool is not None:
            spool.cleanup()
        return _accepted_operation_response(operation)

    loop = asyncio.get_running_loop()

    def _worker() -> None:
        assert handle is not None
        try:
            worker_fn(handle)
        finally:
            runtime.operations.release(handle)
            if spool is not None:
                spool.cleanup()

    # Detached: disconnect must not cancel capacity ownership.
    loop.run_in_executor(None, _worker)
    # Re-read so the 202 body reflects durable state after reservation.
    ops = ManagedOperationStore(runtime.settings)
    fresh = ops.get(workspace_id, operation.operation_id)
    return _accepted_operation_response(fresh)


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
    return _etag_response(
        workspace_view(record), revision=record.revision, status_code=201
    )


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
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    if body.title is None and body.description is None:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="empty_metadata_patch"),
        )
    view, _op = _lifecycle(request).patch_workspace_metadata(
        workspace_id,
        expected_revision=expected,
        idempotency_key=key,
        title=body.title,
        description=body.description,
    )
    return _etag_response(view, revision=int(view["revision"]))


@router.delete("/v1/workspaces/{workspace_id}")
def delete_workspace(
    request: Request,
    workspace_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    runtime = _runtime(request)
    runtime.require_ready()
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    view, _op = _lifecycle(request).tombstone_workspace(
        workspace_id, expected_revision=expected, idempotency_key=key
    )
    return _etag_response(view, revision=int(view["revision"]))


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
    spool = await _spool_workspace_files(
        request, settings=runtime.settings, allow_multiple=True
    )
    uploads = _uploads_from_spool(spool)
    payload = {
        "files": [
            {
                "display_name": u.display_name,
                "content_type": u.content_type,
                "content_sha256": u.digest(),
            }
            for u in uploads
        ]
    }
    lifecycle = _lifecycle(request)

    def worker(handle: OperationHandle) -> None:
        lifecycle.add_sources(
            workspace_id,
            expected_revision=expected,
            idempotency_key=key,
            uploads=uploads,
            control=handle,
        )

    return await _launch_scientific_mutation(
        runtime=runtime,
        lifecycle=lifecycle,
        workspace_id=workspace_id,
        idempotency_key=key,
        kind=ManagedOperationKind.SOURCE_ADD,
        expected_revision=expected,
        payload=payload,
        worker_fn=worker,
        spool=spool,
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
    spool = await _spool_workspace_files(
        request, settings=runtime.settings, allow_multiple=False
    )
    uploads = _uploads_from_spool(spool)
    upload = uploads[0]
    payload = {
        "source_id": source_id,
        "display_name": upload.display_name,
        "content_type": upload.content_type,
        "content_sha256": upload.digest(),
    }
    lifecycle = _lifecycle(request)

    def worker(handle: OperationHandle) -> None:
        lifecycle.replace_source(
            workspace_id,
            source_id=source_id,
            expected_revision=expected,
            idempotency_key=key,
            upload=upload,
            control=handle,
        )

    return await _launch_scientific_mutation(
        runtime=runtime,
        lifecycle=lifecycle,
        workspace_id=workspace_id,
        idempotency_key=key,
        kind=ManagedOperationKind.SOURCE_REPLACE,
        expected_revision=expected,
        payload=payload,
        worker_fn=worker,
        spool=spool,
        require_source_id=source_id,
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
    key = _require_idempotency_key(idempotency_key)
    expected = parse_if_match(if_match)
    view, op = _lifecycle(request).patch_source_metadata(
        workspace_id,
        source_id,
        expected_revision=expected,
        idempotency_key=key,
        display_name=body.display_name,
    )
    revision = (
        op.result.workspace_revision
        if op.result is not None
        else expected
    )
    return _etag_response(view, revision=int(revision))


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
    payload = {"source_id": source_id}

    def worker(handle: OperationHandle) -> None:
        lifecycle.remove_source(
            workspace_id,
            source_id=source_id,
            expected_revision=expected,
            idempotency_key=key,
            control=handle,
        )

    return await _launch_scientific_mutation(
        runtime=runtime,
        lifecycle=lifecycle,
        workspace_id=workspace_id,
        idempotency_key=key,
        kind=ManagedOperationKind.SOURCE_REMOVE,
        expected_revision=expected,
        payload=payload,
        worker_fn=worker,
        spool=None,
        require_source_id=source_id,
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
    safe = quote(filename)
    headers = {
        "Content-Disposition": (
            f'inline; filename="{filename}"; filename*=UTF-8\'\'{safe}'
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "ETag": f'"{source.content_hash}"',
    }
    media = meta.content_type or "application/octet-stream"
    return Response(content=data, media_type=media, headers=headers)


@router.post("/v1/workspaces/{workspace_id}/query")
def workspace_query(
    request: Request, workspace_id: str, body: WorkspaceQueryRequest
) -> dict[str, Any]:
    runtime = _runtime(request)
    runtime.require_ready()
    result = run_workspace_query(
        runtime, workspace_id=workspace_id, question=body.question
    )
    return result.as_dict()
