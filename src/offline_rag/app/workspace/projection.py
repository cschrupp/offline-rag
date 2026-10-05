"""Project a desired active source set onto the Slice-15 ingest path (S16-D11).

Add / remove / replace never incrementally mutates live scientific state. Each
accepted mutation computes the *whole* desired active source set, rehydrates it
from the raw-source vault, and feeds it through the existing full-replace ingest.
That is what makes supersession isolation (S16-D12) structural rather than a
cleanup step: a removed or replaced version is simply absent from the candidate.

Upload limits are enforced against the desired set, not the request delta. A
single added file can push the workspace past the aggregate bound, and ingest
would then fail after the user already paid for the upload.
"""

from __future__ import annotations

import shutil
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import SourceVersionRecord
from offline_rag.app.workspace.vault import RawSourceVault, VaultObjectMeta
from offline_rag.config.models import AppSettings


@dataclass(frozen=True)
class MaterializedSource:
    """One rehydrated desired source ready for spooling."""

    source_id: str
    version: int
    path: Path
    source_name: str
    byte_size: int


@dataclass(frozen=True)
class DesiredSetMaterialization:
    """Rehydrated desired active set plus the scratch directory owning it."""

    work_dir: Path
    sources: list[MaterializedSource]

    @property
    def total_bytes(self) -> int:
        return sum(item.byte_size for item in self.sources)

    def spool_inputs(self) -> list[tuple[Path, str]]:
        """Argument shape accepted by ``spool_local_files``."""
        return [(item.path, item.source_name) for item in self.sources]

    def cleanup(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)


def upload_source_name(meta: VaultObjectMeta) -> str:
    """Immutable scientific source name for a vault object.

    Deliberately the basename captured at vault put time, *not*
    ``SourceVersionRecord.display_name``. Display labels are user-renameable
    presentation metadata (S16-D11); letting a rename flow into
    ``CorpusDocumentEntry.source_name`` would make a display-only edit change
    scientific provenance.
    """
    return meta.display_name


def enforce_desired_set_limits(
    settings: AppSettings, desired: Sequence[SourceVersionRecord]
) -> None:
    """Apply ``settings.api`` upload bounds to the whole desired active set."""
    if not desired:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="zero_files"),
        )
    if len(desired) > settings.api.max_files_per_ingest:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="too_many_files"),
        )
    total = 0
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
        if size > settings.api.max_bytes_per_document:
            raise AppError(
                ErrorCode.DOCUMENT_INVALID,
                details=SafeErrorDetails(
                    source_id=item.source_id, reason="document_too_large"
                ),
            )
        total += size
    if total > settings.api.max_total_upload_bytes:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="upload_too_large"),
        )


def materialize_desired_sources(
    settings: AppSettings,
    *,
    workspace_id: str,
    desired: Sequence[SourceVersionRecord],
    vault: RawSourceVault | None = None,
    work_dir: Path | None = None,
) -> DesiredSetMaterialization:
    """Rehydrate every desired active source from the vault into scratch files.

    Unchanged sources are read back from local storage, so adding or removing one
    source never requires the browser to re-upload the others (S16-D10).
    """
    enforce_desired_set_limits(settings, desired)
    store = vault or RawSourceVault(settings.paths.workspaces)
    root = work_dir or (settings.paths.staging / f"wsproj_{uuid.uuid4().hex}")
    root.mkdir(parents=True, exist_ok=True)

    materialized: list[MaterializedSource] = []
    try:
        for item in desired:
            meta = store.get_meta(workspace_id, item.vault_object_id)
            data = store.load_bytes(workspace_id, item.vault_object_id)
            if item.content_hash is not None and item.content_hash != meta.content_hash:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(
                        workspace_id=workspace_id,
                        source_id=item.source_id,
                        reason="source_content_hash_mismatch",
                    ),
                )
            source_name = upload_source_name(meta)
            # Physical scratch name is server-generated; the display/upload name
            # is carried separately as metadata only.
            path = root / f"{item.source_id}_v{item.version}{Path(source_name).suffix}"
            path.write_bytes(data)
            materialized.append(
                MaterializedSource(
                    source_id=item.source_id,
                    version=item.version,
                    path=path,
                    source_name=source_name,
                    byte_size=len(data),
                )
            )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise

    return DesiredSetMaterialization(work_dir=root, sources=materialized)
