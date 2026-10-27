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
from dataclasses import dataclass
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
LARGE_PDF_QUALIFIED_PROFILE_IDS = (
    "cpu_onnx_fp32_v1",
    "cuda_fp16_v1",
)
LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES = 32_000_000_000
LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES = 19_388_303_360
CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES = 12_998_318_080
CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES = 8_000_000_000
CUDA_LARGE_PDF_MIN_EFFECTIVE_CAPACITY_BYTES = 7_156_531_200
DISK_RESERVE_BYTES = 1_073_741_824
DISK_AMPLIFICATION_FACTOR = 5

HOST_MEMORY_TELEMETRY_UNAVAILABLE = "HOST_MEMORY_TELEMETRY_UNAVAILABLE"
CUDA_MEMORY_TELEMETRY_UNAVAILABLE = "CUDA_MEMORY_TELEMETRY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CudaMemoryTelemetry:
    """Read-only CUDA resource facts for the active runtime device."""

    total_bytes: int
    free_bytes: int
    current_process_reserved_bytes: int

    @property
    def effective_capacity_bytes(self) -> int:
        """Return free device capacity plus this process's reservation."""
        return self.free_bytes + self.current_process_reserved_bytes


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


def _cuda_memory_telemetry(
    device: str | int | None = None,
) -> CudaMemoryTelemetry | None:
    """Observe CUDA memory without touching the embedding runtime.

    The caller supplies the already-resolved runtime device. This function only
    uses PyTorch device-level counters; it never constructs or loads an
    embedding backend.
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        observed_device: str | int = "cuda" if device is None else device
        free_bytes, total_bytes = torch.cuda.mem_get_info(observed_device)
        reserved_bytes = torch.cuda.memory_reserved(observed_device)
        return CudaMemoryTelemetry(
            total_bytes=int(total_bytes),
            free_bytes=int(free_bytes),
            current_process_reserved_bytes=int(reserved_bytes),
        )
    except Exception:  # noqa: BLE001 — telemetry fails closed
        return None


@dataclass(frozen=True, slots=True)
class _LargePdfEligibility:
    eligible: bool
    reason: str | None
    diagnostic_reason: str | None = None


def _large_pdf_runtime_eligibility(
    settings: AppSettings,
    *,
    profile_id: str | None,
    memory: tuple[int, int] | None = None,
    cuda_memory: CudaMemoryTelemetry | None = None,
    cuda_device: str | int | None = None,
) -> _LargePdfEligibility:
    if profile_id not in LARGE_PDF_QUALIFIED_PROFILE_IDS:
        return _LargePdfEligibility(False, "profile_not_qualified")

    observed = _memory_telemetry() if memory is None else memory
    if observed is None:
        return _LargePdfEligibility(
            False,
            "memory_telemetry_unavailable",
            HOST_MEMORY_TELEMETRY_UNAVAILABLE,
        )
    mem_total, mem_available = observed
    required_available = (
        CUDA_LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES
        if profile_id == "cuda_fp16_v1"
        else LARGE_PDF_REFERENCE_MEM_AVAILABLE_BYTES
    )
    if mem_total < LARGE_PDF_REFERENCE_MEM_TOTAL_BYTES or mem_available < required_available:
        return _LargePdfEligibility(False, "host_memory_insufficient")

    if profile_id == "cuda_fp16_v1":
        cuda_observed = (
            _cuda_memory_telemetry(cuda_device)
            if cuda_memory is None
            else cuda_memory
        )
        if cuda_observed is None:
            return _LargePdfEligibility(
                False,
                "memory_telemetry_unavailable",
                CUDA_MEMORY_TELEMETRY_UNAVAILABLE,
            )
        if (
            cuda_observed.total_bytes < 0
            or cuda_observed.free_bytes < 0
            or cuda_observed.current_process_reserved_bytes < 0
            or cuda_observed.free_bytes > cuda_observed.total_bytes
        ):
            return _LargePdfEligibility(
                False,
                "memory_telemetry_unavailable",
                CUDA_MEMORY_TELEMETRY_UNAVAILABLE,
            )
        if (
            cuda_observed.total_bytes < CUDA_LARGE_PDF_MIN_TOTAL_VRAM_BYTES
            or cuda_observed.effective_capacity_bytes
            < CUDA_LARGE_PDF_MIN_EFFECTIVE_CAPACITY_BYTES
        ):
            return _LargePdfEligibility(False, "large_pdf_gpu_memory_insufficient")

    return _LargePdfEligibility(True, None)


def large_pdf_runtime_eligibility(
    settings: AppSettings,
    *,
    profile_id: str | None,
    memory: tuple[int, int] | None = None,
    cuda_memory: CudaMemoryTelemetry | None = None,
    cuda_device: str | int | None = None,
) -> tuple[bool, str | None]:
    """Return policy/runtime eligibility for the qualified large-PDF path."""
    result = _large_pdf_runtime_eligibility(
        settings,
        profile_id=profile_id,
        memory=memory,
        cuda_memory=cuda_memory,
        cuda_device=cuda_device,
    )
    return result.eligible, result.reason


def enforce_workspace_active_source_bytes(
    settings: AppSettings,
    desired: Sequence[SourceVersionRecord],
    *,
    mutation_kind: PublicationMutationKind = PublicationMutationKind.SOURCE_ADD,
) -> None:
    """Enforce the complete post-mutation raw-byte workspace ceiling."""
    if mutation_kind is PublicationMutationKind.SOURCE_REMOVE or not desired:
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
    cuda_memory: CudaMemoryTelemetry | None = None,
    cuda_device: str | int | None = None,
) -> None:
    """Fail closed before reconstruction when a large-PDF runtime is unavailable."""
    if not desired_requires_large_pdf(settings, desired):
        return
    result = _large_pdf_runtime_eligibility(
        settings,
        profile_id=profile_id,
        memory=memory,
        cuda_memory=cuda_memory,
        cuda_device=cuda_device,
    )
    if result.eligible:
        return
    if result.reason == "profile_not_qualified":
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="large_pdf_profile_not_qualified"),
        )
    if result.reason == "large_pdf_gpu_memory_insufficient":
        raise AppError(
            ErrorCode.SERVICE_OVERLOADED,
            details=SafeErrorDetails(reason="large_pdf_gpu_memory_insufficient"),
        )
    if result.reason == "memory_telemetry_unavailable":
        raise AppError(
            ErrorCode.SERVICE_OVERLOADED,
            details=SafeErrorDetails(reason="memory_telemetry_unavailable"),
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
