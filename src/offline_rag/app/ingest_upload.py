"""Streaming multipart spool for product ingest (D20 transport order)."""

from __future__ import annotations

import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from python_multipart.multipart import MultipartParser, parse_options_header

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.base import SUPPORTED_EXTENSIONS, media_type_for_path

_ALLOWED_FIELDS = frozenset({"corpus", "files"})
_MULTIPART_OVERHEAD_BUDGET = 2_097_152  # 2 MiB framing allowance for Content-Length


@dataclass(frozen=True)
class SpooledUploadFile:
    """One bounded-spooled file part under server-generated storage."""

    absolute_path: Path
    client_filename: str
    source_name: str
    size_bytes: int
    media_type: str


@dataclass
class SpooledIngestUpload:
    """Complete validated upload set prior to corpus lease acquisition."""

    upload_id: str
    corpus_name: str
    staging_root: Path
    files_root: Path
    files: list[SpooledUploadFile] = field(default_factory=list)

    @property
    def total_file_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)


def validate_ingest_http_envelope(
    *,
    content_type: str | None,
    content_length: str | None,
    settings: AppSettings,
) -> bytes:
    """Validate request-level envelope before capacity / body consumption.

    Returns the multipart boundary bytes.
    """
    if not content_type:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="missing_content_type"),
        )
    content_type_bytes = content_type.encode("latin-1")
    main_type, options = parse_options_header(content_type_bytes)
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

    if content_length is not None and content_length.strip() != "":
        try:
            length = int(content_length.strip())
        except ValueError as exc:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_content_length"),
            ) from exc
        if length < 0:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_content_length"),
            )
        # Cheap rejection only — never treat Content-Length as the file-byte limit.
        hard_cap = settings.api.max_total_upload_bytes + _MULTIPART_OVERHEAD_BUDGET
        if length > hard_cap:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="content_length_too_large"),
            )
    return boundary


def client_basename(filename: str | None) -> str:
    """Extract a non-traversing basename; path components never reach the FS."""
    if filename is None:
        return ""
    text = str(filename).replace("\\", "/")
    # Drop drive-like prefixes (C:/..., //server/...).
    if len(text) >= 2 and text[1] == ":":
        text = text[2:]
    text = text.replace("\\", "/")
    while text.startswith("//"):
        text = text[1:]
    base = text.rsplit("/", 1)[-1]
    if base in {"", ".", ".."}:
        return ""
    return base


def _safe_extension(basename: str) -> str:
    suffix = Path(basename).suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return suffix
    return ""


def cleanup_staging(staging_root: Path) -> None:
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)


async def spool_multipart_upload(
    *,
    settings: AppSettings,
    boundary: bytes,
    body_chunks: AsyncIterator[bytes],
) -> SpooledIngestUpload:
    """Stream-parse multipart in arbitrary part order into /data/staging."""
    upload_id = uuid.uuid4().hex
    staging_root = settings.paths.staging / upload_id
    files_root = staging_root / "files"
    files_root.mkdir(parents=True, exist_ok=True)

    corpus_chunks: list[bytes] = []
    corpus_seen = 0
    files: list[SpooledUploadFile] = []
    total_file_bytes = 0

    current_field: str | None = None
    current_filename: str | None = None
    current_headers: dict[bytes, bytes] = {}
    header_field = bytearray()
    header_value = bytearray()
    active_file: _ActiveFile | None = None
    parse_error: AppError | None = None

    class _ActiveFile:
        def __init__(self, client_name: str, seq: int) -> None:
            self.client_filename = client_name
            self.source_name = client_name
            ext = _safe_extension(client_name)
            if not ext:
                raise AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="unsupported_source_type"),
                )
            part_dir = files_root / f"{seq:04d}"
            part_dir.mkdir(parents=True, exist_ok=True)
            self.path = part_dir / client_name
            self.handle = self.path.open("wb")
            self.size = 0
            self.media_type = media_type_for_path(self.path) or "application/octet-stream"

        def write(self, data: bytes) -> None:
            nonlocal total_file_bytes
            remaining_doc = settings.api.max_bytes_per_document - self.size
            if remaining_doc <= 0 or len(data) > remaining_doc:
                raise AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="document_too_large"),
                )
            remaining_total = settings.api.max_total_upload_bytes - total_file_bytes
            if len(data) > remaining_total:
                raise AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="upload_too_large"),
                )
            self.handle.write(data)
            self.size += len(data)
            total_file_bytes += len(data)

        def finish(self) -> SpooledUploadFile:
            self.handle.close()
            if self.size == 0:
                raise AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="empty_document"),
                )
            return SpooledUploadFile(
                absolute_path=self.path,
                client_filename=self.client_filename,
                source_name=self.source_name,
                size_bytes=self.size,
                media_type=self.media_type,
            )

        def abort(self) -> None:
            try:
                self.handle.close()
            except OSError:
                pass

    def _fail(exc: AppError) -> None:
        nonlocal parse_error
        if parse_error is None:
            parse_error = exc

    def on_part_begin() -> None:
        nonlocal current_field, current_filename, active_file
        current_field = None
        current_filename = None
        current_headers.clear()
        header_field.clear()
        header_value.clear()
        active_file = None

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
        nonlocal current_field, current_filename, active_file, corpus_seen
        disposition = current_headers.get(b"content-disposition", b"")
        _disp_type, options = parse_options_header(disposition)
        name = options.get(b"name", b"").decode("latin-1", errors="replace")
        raw_filename = options.get(b"filename")
        filename = (
            client_basename(raw_filename.decode("latin-1", errors="replace"))
            if raw_filename is not None
            else ""
        )
        current_field = name
        current_filename = filename or None

        if name not in _ALLOWED_FIELDS:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="unexpected_form_field"),
                )
            )
            return

        if name == "corpus":
            if raw_filename is not None:
                _fail(
                    AppError(
                        ErrorCode.REQUEST_INVALID,
                        details=SafeErrorDetails(reason="invalid_corpus_field"),
                    )
                )
                return
            corpus_seen += 1
            if corpus_seen > 1:
                _fail(
                    AppError(
                        ErrorCode.REQUEST_INVALID,
                        details=SafeErrorDetails(reason="multiple_corpus_fields"),
                    )
                )
            return

        # files part
        if not filename:
            _fail(
                AppError(
                    ErrorCode.DOCUMENT_INVALID,
                    details=SafeErrorDetails(reason="missing_filename"),
                )
            )
            return
        if len(files) >= settings.api.max_files_per_ingest:
            _fail(
                AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="too_many_files"),
                )
            )
            return
        try:
            active_file = _ActiveFile(filename, seq=len(files) + 1)
        except AppError as exc:
            _fail(exc)

    def on_part_data(data: bytes, start: int, end: int) -> None:
        nonlocal active_file
        if parse_error is not None:
            return
        chunk = data[start:end]
        if current_field == "corpus":
            corpus_chunks.append(chunk)
            # Bound corpus field memory (name grammar is tiny).
            if sum(len(c) for c in corpus_chunks) > 512:
                _fail(
                    AppError(
                        ErrorCode.REQUEST_INVALID,
                        details=SafeErrorDetails(reason="invalid_corpus_field"),
                    )
                )
            return
        if current_field == "files" and active_file is not None:
            try:
                active_file.write(chunk)
            except AppError as exc:
                _fail(exc)
                active_file.abort()
                active_file = None

    def on_part_end() -> None:
        nonlocal active_file
        if parse_error is not None:
            if active_file is not None:
                active_file.abort()
                active_file = None
            return
        if current_field == "files" and active_file is not None:
            try:
                files.append(active_file.finish())
            except AppError as exc:
                _fail(exc)
                active_file.abort()
            active_file = None

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

    try:
        async for chunk in body_chunks:
            if parse_error is not None:
                break
            if not chunk:
                continue
            try:
                parser.write(chunk)
            except AppError as exc:
                parse_error = exc
                break
            except Exception as exc:  # noqa: BLE001 — malformed multipart
                parse_error = AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="malformed_multipart"),
                )
                _ = exc
                break
        if parse_error is None:
            try:
                parser.finalize()
            except Exception as exc:  # noqa: BLE001
                parse_error = AppError(
                    ErrorCode.REQUEST_INVALID,
                    details=SafeErrorDetails(reason="malformed_multipart"),
                )
                _ = exc
    except AppError:
        cleanup_staging(staging_root)
        raise
    except Exception as exc:
        cleanup_staging(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="upload_interrupted"),
        ) from exc

    if parse_error is not None:
        if active_file is not None:
            active_file.abort()
        cleanup_staging(staging_root)
        raise parse_error

    if corpus_seen != 1:
        cleanup_staging(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(
                reason="missing_corpus_field" if corpus_seen == 0 else "multiple_corpus_fields"
            ),
        )
    try:
        corpus_raw = b"".join(corpus_chunks).decode("utf-8").strip()
        corpus_name = validate_product_corpus_name(corpus_raw)
    except AppError:
        cleanup_staging(staging_root)
        raise
    except UnicodeDecodeError as exc:
        cleanup_staging(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_corpus_field"),
        ) from exc

    if not files:
        cleanup_staging(staging_root)
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="zero_files"),
        )

    return SpooledIngestUpload(
        upload_id=upload_id,
        corpus_name=corpus_name,
        staging_root=staging_root,
        files_root=files_root,
        files=files,
    )
