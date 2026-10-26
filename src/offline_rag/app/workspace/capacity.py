"""16K-C first-user capacity model — transport vs workspace/search workload.

Transport limits (HTTP upload request envelope) remain on the spool path only.
Workspace/search workload limits are separate, optional, and must not be
conflated with per-request upload bytes.

Unset workspace ceilings mean "no product-supported envelope claimed yet"
(evidence lands in 16K-F); they do not invent a supported numeric claim.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from offline_rag.app.errors import (
    AppError,
    ErrorCode,
    SafeErrorDetails,
    ValidationFieldDetail,
)
from offline_rag.app.source_limits import PDF_MEDIA_TYPE
from offline_rag.app.workspace.models import SourceVersionRecord
from offline_rag.app.workspace.publication_journal import PublicationMutationKind
from offline_rag.config.models import AppSettings

LARGE_PDF_QUALIFIED_PROFILE_ID = "cpu_onnx_fp32_v1"
LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES = 32_000_000_000
LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES = 19_388_303_360
DISK_RESERVE_BYTES = 1_073_741_824
DISK_AMPLIFICATION_FACTOR = 5


def desired_active_source_bytes(
    desired: Sequence[SourceVersionRecord],
) -> int:
    """Sum raw source bytes in the complete post-mutation desired set."""
    return sum(int(item.byte_size or 0) for item in desired)


def desired_requires_large_pdf(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
) -> bool:
    """Whether the desired set requires the qualified large-PDF runtime."""
    threshold = int(settings.api.max_bytes_per_document)
    return any(
        item.content_type == PDF_MEDIA_TYPE
        and item.byte_size is not None
        and int(item.byte_size) > threshold
        for item in desired
    )


def _memory_telemetry() -> tuple[int, int] | None:
    """Read Linux memory telemetry without making a host claim on failure."""
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            if key in {"MemTotal", "MemAvailable"}:
                values[key] = int(rest.strip().split()[0]) * 1024
        if "MemTotal" not in values or "MemAvailable" not in values:
            return None
        return values["MemTotal"], values["MemAvailable"]
    except (OSError, ValueError, IndexError):
        return None


def large_pdf_runtime_eligibility(
    settings: AppSettings,
    *,
    profile_id: str | None,
    memory: tuple[int, int] | None = None,
) -> tuple[bool, str | None]:
    """Return policy/runtime eligibility for the qualified large-PDF path."""
    if profile_id != LARGE_PDF_QUALIFIED_PROFILE_ID:
        return False, "profile_not_qualified"
    observed = _memory_telemetry() if memory is None else memory
    if observed is None:
        return False, "memory_telemetry_unavailable"
    mem_total, mem_available = observed
    if (
        mem_total < LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES
        or mem_available < LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES
    ):
        return False, "host_memory_insufficient"
    return True, None


def enforce_workspace_active_source_bytes(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
) -> None:
    """Enforce the complete post-mutation raw-byte workspace ceiling."""
    if not desired:
        return
    ceiling = int(settings.api.max_active_source_bytes_per_workspace)
    observed = desired_active_source_bytes(desired)
    if observed > ceiling:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(
                reason="workspace_source_bytes_exceeded",
                fields=[
                    ValidationFieldDetail(
                        loc=["max_active_source_bytes_per_workspace"],
                        msg=f"limit={ceiling} observed={observed}",
                        type="workspace_capacity",
                    )
                ],
            ),
        )


def enforce_large_pdf_runtime(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
    *,
    profile_id: str | None,
    memory: tuple[int, int] | None = None,
) -> None:
    """Fail closed before reconstruction when a large-PDF runtime is unavailable."""
    if not desired_requires_large_pdf(settings, desired):
        return
    eligible, reason = large_pdf_runtime_eligibility(
        settings, profile_id=profile_id, memory=memory
    )
    if eligible:
        return
    if reason == "profile_not_qualified":
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="large_pdf_profile_not_qualified"),
        )
    raise AppError(
        ErrorCode.SERVICE_OVERLOADED,
        details=SafeErrorDetails(reason="large_pdf_host_memory_insufficient"),
    )


def _capacity_paths(settings: AppSettings) -> list[Path]:
    paths = [
        settings.paths.staging,
        settings.paths.workspaces,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
        settings.paths.qdrant_storage,
    ]
    unique: list[Path] = []
    seen: set[tuple[int, int]] = set()
    for path in paths:
        candidate = path
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        try:
            stat = candidate.stat()
        except OSError:
            continue
        key = (stat.st_dev, stat.st_ino)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def enforce_reconstruction_disk_capacity(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
    *,
    known_lower_bound_bytes: int = 0,
    disk_usage: Callable[[str | os.PathLike[str]], Any] = shutil.disk_usage,
) -> None:
    """Reserve bounded temporary/durable disk for a non-empty reconstruction."""
    if not desired:
        return
    active_bytes = desired_active_source_bytes(desired)
    required = max(int(known_lower_bound_bytes), DISK_AMPLIFICATION_FACTOR * active_bytes)
    required += DISK_RESERVE_BYTES
    for path in _capacity_paths(settings):
        try:
            free = int(disk_usage(path).free)
        except OSError as exc:
            raise AppError(
                ErrorCode.SERVICE_OVERLOADED,
                details=SafeErrorDetails(reason="storage_insufficient"),
            ) from exc
        if free < required:
            raise AppError(
                ErrorCode.SERVICE_OVERLOADED,
                details=SafeErrorDetails(reason="storage_insufficient"),
            )


def enforce_workspace_active_source_capacity(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
    *,
    mutation_kind: PublicationMutationKind,
) -> None:
    """Fail closed when desired active-source count exceeds configured ceiling.

    Remove is never blocked by this ceiling (it only reduces workload).
    When ``max_active_sources_per_workspace`` is unset, no ceiling is enforced.
    """
    if mutation_kind is PublicationMutationKind.SOURCE_REMOVE:
        return
    ceiling = settings.api.max_active_sources_per_workspace
    if ceiling is None:
        return
    observed = len(desired)
    if observed > int(ceiling):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(
                reason="workspace_source_capacity_exceeded",
                fields=[
                    ValidationFieldDetail(
                        loc=["max_active_sources_per_workspace"],
                        msg=f"limit={int(ceiling)} observed={observed}",
                        type="workspace_capacity",
                    )
                ],
            ),
        )


def enforce_searchable_workload_capacity(
    settings: AppSettings,
    *,
    searchable_child_count: int,
    mutation_kind: PublicationMutationKind | None,
) -> None:
    """Fail closed after chunking when searchable children exceed the envelope.

    Must run before dense embedding / dense materialization.

    Workspace-only (16K-C F001): applies solely to ``SOURCE_ADD`` /
    ``SOURCE_REPLACE``. ``SOURCE_REMOVE`` is exempt. ``mutation_kind=None``
    (ordinary ``POST /v1/ingest``) must leave legacy ingest semantics unchanged
    and must not be constrained by this per-workspace ceiling.

    When ``max_searchable_child_chunks_per_workspace`` is unset, no ceiling
    is enforced (no unmeasured product support claim).
    """
    if mutation_kind not in {
        PublicationMutationKind.SOURCE_ADD,
        PublicationMutationKind.SOURCE_REPLACE,
    }:
        return
    ceiling = settings.api.max_searchable_child_chunks_per_workspace
    if ceiling is None:
        return
    observed = int(searchable_child_count)
    if observed > int(ceiling):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(
                reason="searchable_workload_capacity_exceeded",
                fields=[
                    ValidationFieldDetail(
                        loc=["max_searchable_child_chunks_per_workspace"],
                        msg=f"limit={int(ceiling)} observed={observed}",
                        type="workspace_capacity",
                    )
                ],
            ),
        )


def validate_desired_set_integrity(
    desired: Sequence[SourceVersionRecord],
) -> None:
    """Vault/desired-set integrity checks that are not HTTP transport policy."""
    if not desired:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="zero_files"),
        )
    for item in desired:
        size = item.byte_size
        if size is None:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    source_id=item.source_id, reason="source_size_unknown"
                ),
            )
        if size <= 0:
            raise AppError(
                ErrorCode.DOCUMENT_INVALID,
                details=SafeErrorDetails(
                    source_id=item.source_id, reason="empty_document"
                ),
            )
