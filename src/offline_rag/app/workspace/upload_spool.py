"""Durable multipart upload spool for workspace source mutations (Slice 16B).

Uploaded bytes are streamed to ``/data/staging`` before HTTP acceptance so a
process crash after 202 cannot lose the only copy of accepted request bytes.
Orphan staging is never auto-resumed into ingest; startup may quarantine it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from python_multipart.multipart import MultipartParser, parse_options_header

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest_upload import client_basename
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.base import SUPPORTED_EXTENSIONS
from offline_rag.ingestion.io import atomic_write_text


@dataclass(frozen=True)
class SpooledWorkspaceFile:
    """One file streamed to durable staging with digest computed on write."""

    absolute_path: Path
    display_name: str
    content_type: str | None
    size_bytes: int
    content_sha256: str


@dataclass
class WorkspaceUploadSpool:
    """Durable staging set for one accepted workspace multipart upload."""

    spool_id: str
    staging_root: Path
    files_root: Path
    files: list[SpooledWorkspaceFile] = field(default_factory=list)

    def cleanup(self) -> None:
        if self.staging_root.exists():
            shutil.rmtree(self.staging_root, ignore_errors=True)


def cleanup_workspace_upload_spool(staging_root: Path) -> None:
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)


def quarantine_orphan_workspace_spools(settings: AppSettings) -> list[Path]:
    """Move abandoned ``ws_upload_*`` staging dirs aside; never resume ingest."""
    staging = settings.paths.staging
    if not staging.exists():
        return []
    quarantine_root = staging / "_quarantine_workspace_uploads"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for child in sorted(staging.iterdir()):
        if not child.is_dir() or not child.name.startswith("ws_upload_"):
            continue
        target = quarantine_root / child.name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(child), str(target))
        moved.append(target)
    return moved


async def spool_workspace_multipart(
    *,
    settings: AppSettings,
    boundary: bytes,
    body_chunks: AsyncIterator[bytes],
    allow_multiple: bool,
) -> WorkspaceUploadSpool:
    """Stream-parse multipart ``files`` parts into durable local staging."""
    spool_id = uuid.uuid4().hex
    staging_root = settings.paths.staging / f"ws_upload_{spool_id}"
    files_root = staging_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    max_files = int(settings.api.max_files_per_ingest)
    max_doc = int(settings.api.max_bytes_per_document)
    max_total = int(settings.api.max_total_upload_bytes)

    files: list[SpooledWorkspaceFile] = []
    total_file_bytes = 0
    parse_error: AppError | None = None
    current_headers: dict[bytes, bytes] = {}
    header_field = bytearray()
    header_value = bytearray()
    current_field: str | None = None
    current_filename: str | None = None
    current_type: str | None = None
    active: _ActiveSpoolFile | None = None

    class _ActiveSpoolFile:
        def __init__(self, display_name: str, media_type: str | None) -> None:
            suffix = Path(display_name).suffix.lower()
            self.display_name = display_name
            self.media_type = media_type
            self.path = files_root / f"{uuid.uuid4().hex}{suffix}"
            self.handle = self.path.open("wb")
            self.size = 0
            self.digest = hashlib.sha256()

        def write(self, data: bytes) -> None:
            nonlocal total_file_bytes
            remaining_doc = max_doc - self.size
            if remaining_doc <= 0 or len(data) > remaining_doc:
                raise AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="document_too_large"),
                )
            remaining_total = max_total - total_file_bytes
            if len(data) > remaining_total:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="upload_too_large"),
                )
            self.handle.write(data)
            self.digest.update(data)
            self.size += len(data)
            total_file_bytes += len(data)

        def finish(self) -> SpooledWorkspaceFile:
            self.handle.close()
            return SpooledWorkspaceFile(
                absolute_path=self.path,
                display_name=self.display_name,
                content_type=self.media_type,
                size_bytes=self.size,
                content_sha256=self.digest.hexdigest(),
            )

        def abort(self) -> None:
            try:
                self.handle.close()
            except OSError:
                pass
            self.path.unlink(missing_ok=True)

    def _fail(exc: AppError) -> None:
        nonlocal parse_error
        if parse_error is None:
            parse_error = exc

    def on_part_begin() -> None:
        nonlocal current_field, current_filename, current_type, active
        current_headers.clear()
        header_field.clear()
        header_value.clear()
        current_field = None
        current_filename = None
        current_type = None
        active = None

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
        nonlocal current_field, current_filename, current_type, active
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
            raw_filename.decode("latin-1", errors="replace")
            if raw_filename is not None
            else None
        )
        basename = client_basename(filename)
        if not basename:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="missing_filename"),
                )
            )
            return
        suffix = Path(basename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="unsupported_source_type"),
                )
            )
            return
        ctype = current_headers.get(b"content-type")
        current_filename = basename
        current_type = (
            ctype.decode("latin-1", errors="replace") if ctype is not None else None
        )
        if len(files) >= max_files:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="too_many_files"),
                )
            )
            return
        try:
            active = _ActiveSpoolFile(basename, current_type)
        except OSError as exc:
            _fail(
                AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(reason="upload_spool_unwritable"),
                )
            )
            _ = exc

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if parse_error is not None or active is None:
            return
        try:
            active.write(data[start:end])
        except AppError as exc:
            active.abort()
            _fail(exc)

    def on_part_end() -> None:
        nonlocal active
        if parse_error is not None:
            if active is not None:
                active.abort()
                active = None
            return
        if active is None:
            return
        try:
            finished = active.finish()
        except OSError as exc:
            active.abort()
            _fail(
                AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(reason="upload_spool_write_failed"),
                )
            )
            _ = exc
            active = None
            return
        if finished.size_bytes <= 0:
            finished.absolute_path.unlink(missing_ok=True)
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="empty_file"),
                )
            )
            active = None
            return
        files.append(finished)
        active = None
        _ = current_field, current_filename

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
        },
    )
    try:
        async for chunk in body_chunks:
            if parse_error is not None:
                break
            parser.write(chunk)
        if parse_error is None:
            parser.finalize()
    except Exception:
        for item in files:
            item.absolute_path.unlink(missing_ok=True)
        if active is not None:
            active.abort()
        cleanup_workspace_upload_spool(staging_root)
        raise

    if parse_error is not None:
        for item in files:
            item.absolute_path.unlink(missing_ok=True)
        if active is not None:
            active.abort()
        cleanup_workspace_upload_spool(staging_root)
        raise parse_error

    if not files:
        cleanup_workspace_upload_spool(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="zero_files"),
        )
    if not allow_multiple and len(files) != 1:
        cleanup_workspace_upload_spool(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="exactly_one_file_required"),
        )

    spool = WorkspaceUploadSpool(
        spool_id=spool_id,
        staging_root=staging_root,
        files_root=files_root,
        files=files,
    )
    # Manifest makes orphan inspection deterministic without scanning opaque blobs.
    atomic_write_text(
        staging_root / "manifest.json",
        json.dumps(
            {
                "spool_id": spool_id,
                "files": [
                    {
                        "display_name": item.display_name,
                        "content_sha256": item.content_sha256,
                        "size_bytes": item.size_bytes,
                    }
                    for item in files
                ],
            },
            separators=(",", ":"),
        ),
    )
    return spool
