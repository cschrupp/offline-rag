"""Authorize carry-forward from the workspace's immutable publication."""

from collections.abc import Sequence

from offline_rag.app.errors import (
    AppError,
    ErrorCode,
    SafeErrorDetails,
    is_safe_identity,
)
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.workspace.models import SourceVersionRecord, WorkspaceRecord
from offline_rag.chunking.persistence import (
    load_chunk_set_manifest,
    try_load_reusable_chunk_artifact,
)
from offline_rag.ingestion.pipeline import PublishedEmptyParse


def published_empty_parses(
    runtime: ApplicationRuntime,
    record: WorkspaceRecord,
    desired: Sequence[SourceVersionRecord],
) -> dict[str, PublishedEmptyParse]:
    """Bind the exception to existing source versions with zero published chunks."""
    if record.current_snapshot_id is None or runtime.settings.parsing.pdf.ocr_enabled:
        return {}
    prior = {
        (item.source_id, item.version): item for item in record.sources if item.active
    }
    unchanged = {}
    for item in desired:
        original = prior.get((item.source_id, item.version))
        if (
            original is not None
            and item.active
            and item.content_type == "application/pdf"
            and item.content_hash
            and item.document_id == f"doc_{item.content_hash}"
            and original.content_hash == item.content_hash
            and original.document_id == item.document_id
            and original.vault_object_id == item.vault_object_id
        ):
            unchanged[item.document_id] = item
    if not unchanged:
        return {}

    try:
        snapshot = runtime.publication.resolve_snapshot(
            record.backing_corpus_name,
            record.current_snapshot_id,
            require_current_config_match=False,
        )
    except AppError:
        # An unverifiable publication grants no exception. Ordinary rebuild
        # still applies its usual parser and rejects OCR-only inputs.
        return {}
    empty_entries = [
        entry
        for entry in snapshot.corpus_manifest.documents
        if entry.document_id in unchanged and entry.block_count == 0
    ]
    if not empty_entries:
        return {}

    settings = runtime.settings
    chunks = load_chunk_set_manifest(
        settings.paths.chunk_manifests / snapshot.identity.chunk_manifest
    )
    proofs = {}
    for entry in empty_entries:
        chunk_rows = [
            row for row in chunks.documents if row.document_id == entry.document_id
        ]
        if (
            entry.source_content_hash != unchanged[entry.document_id].content_hash
            or chunks.corpus_id != snapshot.identity.corpus_id
            or chunks.chunk_set_id != snapshot.identity.chunk_set_id
            or len(chunk_rows) != 1
        ):
            raise _invalid_publication()
        row = chunk_rows[0]
        if (
            row.parsed_artifact_id != entry.parsed_artifact_id
            or row.parent_count != 0
            or row.child_count != 0
            or not is_safe_identity(row.chunk_artifact_id)
        ):
            raise _invalid_publication()
        cached = try_load_reusable_chunk_artifact(
            settings.paths.chunks,
            row.chunk_artifact_id,
            expected_parsed_artifact_id=entry.parsed_artifact_id,
            expected_chunk_config_hash=chunks.chunk_config_hash,
        )
        if cached is None:
            raise _invalid_publication()
        artifact, checksum = cached
        if (
            checksum != row.chunk_artifact_hash
            or artifact.document_id != entry.document_id
            or artifact.parent_count
            or artifact.child_count
            or artifact.parents
            or artifact.children
        ):
            raise _invalid_publication()
        proofs[entry.document_id] = PublishedEmptyParse(
            entry.parsed_artifact_id,
            entry.parse_config_hash,
            entry.processed_artifact_hash,
        )
    return proofs


def _invalid_publication() -> AppError:
    return AppError(
        ErrorCode.SNAPSHOT_UNAVAILABLE,
        details=SafeErrorDetails(reason="published_empty_artifact_unverified"),
    )
