"""Dense searchable-unit eligibility contracts."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, IndexingSettings
from offline_rag.core.ids import ALL_CHILDREN_V1, EXCLUDE_HEADING_ONLY_V1
from offline_rag.domain.documents import Chunk, ChunkKind

ALL_CHILDREN_STRATEGY = "all_children"
EXCLUDE_HEADING_ONLY_STRATEGY = "exclude_heading_only"

# Authoritative Slice 2 signal: child composed of exactly one heading block.
HEADING_ONLY_CONTENT_TYPE = "heading"


class DenseSearchableUnitsError(ValueError):
    """Fail-closed searchable-unit classification/eligibility error."""


def is_heading_only_v1(chunk: Chunk) -> bool:
    """Return True iff ``chunk`` is a structural heading-only child.

    Authoritative rule (exclude-heading-only-v1):

    ``chunk.content_type == "heading"``

    The structure-aware chunker sets this when a child unit contains exactly one
    ``ContentBlock`` with ``ContentType.HEADING``. Mixed heading+prose children
    receive ``content_type="mixed"`` and are not heading-only.

    Does not use token-length thresholds.
    """
    if chunk.kind != ChunkKind.CHILD:
        raise DenseSearchableUnitsError(
            f"is_heading_only_v1 requires a child chunk; got kind={chunk.kind!r} "
            f"chunk_id={chunk.chunk_id}"
        )
    content_type = chunk.content_type
    if not isinstance(content_type, str) or not content_type.strip():
        raise DenseSearchableUnitsError(
            f"child {chunk.chunk_id} lacks deterministic content_type for "
            "searchable-unit classification"
        )
    return content_type == HEADING_ONLY_CONTENT_TYPE


def resolve_searchable_units_contract(*, strategy: str, contract_version: str) -> str:
    if strategy == ALL_CHILDREN_STRATEGY and contract_version == ALL_CHILDREN_V1:
        return ALL_CHILDREN_V1
    if (
        strategy == EXCLUDE_HEADING_ONLY_STRATEGY
        and contract_version == EXCLUDE_HEADING_ONLY_V1
    ):
        return EXCLUDE_HEADING_ONLY_V1
    raise DenseSearchableUnitsError(
        f"unsupported searchable_units pair: {strategy}/{contract_version}"
    )


def filter_dense_searchable_children(
    jobs: list[tuple[Chunk, str]],
    settings: AppSettings | IndexingSettings,
) -> tuple[list[tuple[Chunk, str]], list[tuple[Chunk, str]]]:
    """Split child jobs into (eligible, excluded) under the configured policy.

    ``all-children-v1``: all children eligible; excluded empty.
    ``exclude-heading-only-v1``: heading-only children excluded from dense vectors.
    """
    indexing = settings.indexing if isinstance(settings, AppSettings) else settings
    contract = resolve_searchable_units_contract(
        strategy=indexing.searchable_units.strategy,
        contract_version=indexing.searchable_units.contract_version,
    )
    if contract == ALL_CHILDREN_V1:
        return list(jobs), []

    eligible: list[tuple[Chunk, str]] = []
    excluded: list[tuple[Chunk, str]] = []
    for chunk, artifact_id in jobs:
        if is_heading_only_v1(chunk):
            excluded.append((chunk, artifact_id))
        else:
            eligible.append((chunk, artifact_id))
    return eligible, excluded
