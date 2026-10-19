"""16K-C first-user capacity model — transport vs workspace/search workload.

Transport limits (HTTP upload request envelope) remain on the spool path only.
Workspace/search workload limits are separate, optional, and must not be
conflated with per-request upload bytes.

Unset workspace ceilings mean "no product-supported envelope claimed yet"
(evidence lands in 16K-F); they do not invent a supported numeric claim.
"""

from __future__ import annotations

from collections.abc import Sequence

from offline_rag.app.errors import (
    AppError,
    ErrorCode,
    SafeErrorDetails,
    ValidationFieldDetail,
)
from offline_rag.app.workspace.models import SourceVersionRecord
from offline_rag.app.workspace.publication_journal import PublicationMutationKind
from offline_rag.config.models import AppSettings


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
    Remove is never blocked by this ceiling.
    When ``max_searchable_child_chunks_per_workspace`` is unset, no ceiling
    is enforced (no unmeasured product support claim).
    """
    if mutation_kind is PublicationMutationKind.SOURCE_REMOVE:
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
