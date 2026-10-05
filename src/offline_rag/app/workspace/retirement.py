"""Application-level publication retirement primitives (Slice 16A).

Does not change Slice-15 ingest. Retires product-visible current publication
while preserving immutable snapshot manifests under product/snapshots/.

Caller serialization contract
-----------------------------
These helpers do **not** acquire ``CorpusMutationLease`` themselves.
Callers that mutate ``current.json`` / ``retired.json`` MUST already hold the
corpus lease (and, for EMPTY transitions, the workspace lease first).

Authority rule (F8)
-------------------
``current.json`` (existence + valid pointer) is the **sole** authority for
whether a corpus currently has a product publication.

``retired.json`` is **audit / recovery metadata only**. Its presence MUST NOT
override an existing valid ``current.json``. Clear it opportunistically on
restore/publish; never treat the two files as a two-bit state machine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.publication import (
    current_pointer_path,
    product_dir,
    snapshot_manifest_path,
)
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.config.models import AppSettings
from offline_rag.ingestion.io import atomic_write_text

RETIREMENT_SCHEMA_VERSION = "offline-rag-publication-retirement-v1"


class PublicationRetirementRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = RETIREMENT_SCHEMA_VERSION
    corpus_name: str
    retired_at: datetime
    last_snapshot_id: str | None = None
    already_retired: bool = False


def retirement_marker_path(corpora_root: Path, corpus_name: str) -> Path:
    return product_dir(corpora_root, corpus_name) / "retired.json"


def retire_current_publication(
    settings: AppSettings, corpus_name: str
) -> PublicationRetirementRecord:
    """Retire current product publication for ``corpus_name``.

    Caller MUST hold ``CorpusMutationLease`` for ``corpus_name``.

    - Writes ``product/retired.json`` audit/recovery metadata (last snapshot id)
    - Removes ``product/current.json`` (authoritative current publication)
    - Leaves ``product/snapshots/*.json`` untouched
    Idempotent when already unpublished / never published.

    Note: a crash between writing ``retired.json`` and unlinking ``current.json``
    may leave both files briefly. ``current.json`` remains authoritative until
    unlinked; recovery/publish clears stale markers.
    """
    name = validate_product_corpus_name(corpus_name)
    pointer_path = current_pointer_path(settings.paths.corpora, name)
    marker_path = retirement_marker_path(settings.paths.corpora, name)
    product_dir(settings.paths.corpora, name).mkdir(parents=True, exist_ok=True)

    last_snapshot_id: str | None = None
    already = False
    if pointer_path.exists():
        try:
            pointer = PublishedPointer.model_validate_json(
                pointer_path.read_text(encoding="utf-8")
            )
            last_snapshot_id = pointer.snapshot_id
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(corpus=name, reason="pointer_unreadable"),
            ) from exc
    else:
        already = True
        if marker_path.exists():
            try:
                existing = PublicationRetirementRecord.model_validate_json(
                    marker_path.read_text(encoding="utf-8")
                )
                return existing.model_copy(update={"already_retired": True})
            except (OSError, ValidationError, ValueError):
                pass

    record = PublicationRetirementRecord(
        corpus_name=name,
        retired_at=datetime.now(tz=UTC),
        last_snapshot_id=last_snapshot_id,
        already_retired=already and last_snapshot_id is None,
    )
    atomic_write_text(marker_path, record.model_dump_json())
    if pointer_path.exists():
        pointer_path.unlink()
    return record


def clear_retirement_marker(settings: AppSettings, corpus_name: str) -> None:
    """Best-effort clear of retirement audit metadata.

    Caller SHOULD hold ``CorpusMutationLease`` when composing with current-pointer
    mutation. Safe if marker absent.
    """
    name = validate_product_corpus_name(corpus_name)
    marker_path = retirement_marker_path(settings.paths.corpora, name)
    marker_path.unlink(missing_ok=True)


def restore_current_publication_pointer(
    settings: AppSettings, corpus_name: str, snapshot_id: str
) -> str:
    """Restore ``current.json`` to an existing immutable snapshot (recovery to A).

    Caller MUST hold ``CorpusMutationLease`` for ``corpus_name``.

    Clears ``retired.json`` after a successful restore (audit cleanup only).
    Snapshot manifests are untouched. ``current.json`` is the publication authority.
    """
    name = validate_product_corpus_name(corpus_name)
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_snapshot_id"),
        )
    snap_path = snapshot_manifest_path(settings.paths.corpora, name, snapshot_id)
    if not snap_path.exists():
        raise AppError(
            ErrorCode.SNAPSHOT_UNAVAILABLE,
            details=SafeErrorDetails(
                corpus=name, snapshot_id=snapshot_id, reason="snapshot_missing"
            ),
        )
    pointer = PublishedPointer(snapshot_id=snapshot_id)
    pointer_path = current_pointer_path(settings.paths.corpora, name)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(pointer_path, pointer.model_dump_json())
    clear_retirement_marker(settings, name)
    return snapshot_id


def list_snapshot_manifests(settings: AppSettings, corpus_name: str) -> list[Path]:
    name = validate_product_corpus_name(corpus_name)
    snap_dir = product_dir(settings.paths.corpora, name) / "snapshots"
    if not snap_dir.exists():
        return []
    return sorted(p for p in snap_dir.glob("*.json") if p.is_file())
