"""Immutable historical Gold Lab source reader (16F-D; retrieval-independent)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.models import GoldCampaign
from offline_rag.app.snapshot import (
    PRODUCT_MODE_GROUNDED_V1,
    SNAPSHOT_SCHEMA_VERSION,
    CanonicalSnapshotManifest,
    compute_snapshot_id,
)
from offline_rag.chunking.persistence import chunk_artifact_relpath
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    artifact_bytes_hash,
    chunk_artifact_id,
    chunk_set_id_from_entries,
    corpus_id_from_entries,
)
from offline_rag.domain.chunking import (
    ChunkSetDocumentEntry,
    ChunkSetManifest,
    DocumentChunkArtifact,
)
from offline_rag.domain.corpus import CorpusManifest
from offline_rag.domain.documents import Chunk

_SNAPSHOT_ID_RE = re.compile(r"^snap_[0-9a-f]{64}$")
_CHUNK_ARTIFACT_ID_RE = re.compile(r"^chunkartifact_[0-9a-f]{64}$")
_CORPUS_MANIFEST_SCHEMA = "offline-rag-corpus-manifest-v1"
_CHUNKSET_MANIFEST_SCHEMA = "offline-rag-chunkset-manifest-v1"
_CHUNK_ARTIFACT_SCHEMA = "offline-rag-chunk-artifact-v1"


def _state_unavailable(reason: str) -> AppError:
    from offline_rag.app.errors import ErrorCode, SafeErrorDetails

    return AppError(
        ErrorCode.GOLD_STATE_UNAVAILABLE,
        details=SafeErrorDetails(reason=reason),
    )


def _require_filename_only(value: str, *, reason: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise _state_unavailable(reason)
    path = Path(text)
    if path.name != text or path.is_absolute() or "/" in text or "\\" in text or ".." in text:
        raise _state_unavailable(reason)
    return text


def resolve_historical_chunk(
    settings: AppSettings,
    campaign: GoldCampaign,
    *,
    chunk_id: str,
    expected_document_id: str | None = None,
    expected_section_path: list[str] | None = None,
) -> tuple[Chunk, CorpusManifest, str | None]:
    """Load one verified historical chunk for Gold task evidence.

    Returns ``(chunk, corpus_manifest, source_name)``.
    """
    try:
        corpus_name = validate_product_corpus_name(campaign.corpus_name)
    except AppError as exc:
        raise _state_unavailable("historical_chunk_unavailable") from exc

    snapshot_id = str(campaign.snapshot_id or "").strip()
    if _SNAPSHOT_ID_RE.fullmatch(snapshot_id) is None:
        raise _state_unavailable("historical_chunk_unavailable")

    snap_path = (
        settings.paths.corpora
        / corpus_name
        / "product"
        / "snapshots"
        / f"{snapshot_id}.json"
    )
    if not snap_path.is_file():
        raise _state_unavailable("historical_chunk_unavailable")
    try:
        identity = CanonicalSnapshotManifest.model_validate_json(
            snap_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise _state_unavailable("historical_chunk_unavailable") from exc

    if identity.schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise _state_unavailable("historical_chunk_mismatch")
    if identity.product_mode_id != PRODUCT_MODE_GROUNDED_V1:
        raise _state_unavailable("historical_chunk_mismatch")
    if compute_snapshot_id(identity) != campaign.snapshot_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if identity.corpus_id != campaign.corpus_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if identity.chunk_set_id != campaign.chunk_set_id:
        raise _state_unavailable("historical_chunk_mismatch")

    corpus_manifest_name = _require_filename_only(
        identity.corpus_manifest, reason="historical_chunk_unavailable"
    )
    chunk_manifest_name = _require_filename_only(
        identity.chunk_manifest, reason="historical_chunk_unavailable"
    )

    corpus_path = settings.paths.manifests / corpus_manifest_name
    if not corpus_path.is_file():
        raise _state_unavailable("historical_chunk_unavailable")
    try:
        corpus_manifest = CorpusManifest.model_validate_json(
            corpus_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise _state_unavailable("historical_chunk_unavailable") from exc

    if corpus_manifest.schema_version != _CORPUS_MANIFEST_SCHEMA:
        raise _state_unavailable("historical_chunk_mismatch")
    if corpus_manifest.corpus_id != campaign.corpus_id:
        raise _state_unavailable("historical_chunk_mismatch")

    recomputed_corpus_id = corpus_id_from_entries(
        schema_version=corpus_manifest.schema_version,
        parse_cfg_hash=corpus_manifest.config_hash,
        document_identities=[
            {
                "document_id": doc.document_id,
                "source_content_hash": doc.source_content_hash,
                "processed_artifact_hash": doc.processed_artifact_hash,
                "parsed_artifact_id": doc.parsed_artifact_id,
            }
            for doc in corpus_manifest.documents
        ],
    )
    if (
        recomputed_corpus_id != corpus_manifest.corpus_id
        or recomputed_corpus_id != campaign.corpus_id
    ):
        raise _state_unavailable("historical_chunk_mismatch")

    # Canonical writer stores ``{chunk_set_id}.json``; reject filename aliases.
    if chunk_manifest_name != f"{campaign.chunk_set_id}.json":
        raise _state_unavailable("historical_chunk_mismatch")

    chunk_manifest_path = settings.paths.chunk_manifests / chunk_manifest_name
    if not chunk_manifest_path.is_file():
        raise _state_unavailable("historical_chunk_unavailable")
    try:
        chunk_manifest = ChunkSetManifest.model_validate_json(
            chunk_manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise _state_unavailable("historical_chunk_unavailable") from exc

    if chunk_manifest.schema_version != _CHUNKSET_MANIFEST_SCHEMA:
        raise _state_unavailable("historical_chunk_mismatch")
    if chunk_manifest.corpus_id != campaign.corpus_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if chunk_manifest.chunk_set_id != campaign.chunk_set_id:
        raise _state_unavailable("historical_chunk_mismatch")

    recomputed_chunk_set_id = chunk_set_id_from_entries(
        corpus_id=chunk_manifest.corpus_id,
        chunk_cfg_hash=chunk_manifest.chunk_config_hash,
        chunker_version=chunk_manifest.chunker_version,
        document_entries=[
            {
                "document_id": entry.document_id,
                "parsed_artifact_id": entry.parsed_artifact_id,
                "chunk_artifact_id": entry.chunk_artifact_id,
            }
            for entry in chunk_manifest.documents
        ],
    )
    if (
        recomputed_chunk_set_id != chunk_manifest.chunk_set_id
        or recomputed_chunk_set_id != campaign.chunk_set_id
        or recomputed_chunk_set_id != identity.chunk_set_id
    ):
        raise _state_unavailable("historical_chunk_mismatch")

    entry, _artifact, chunk = _resolve_verified_chunk(
        settings, chunk_manifest, chunk_id=chunk_id
    )
    if chunk.document_id != entry.document_id:
        raise _state_unavailable("historical_chunk_mismatch")

    if expected_document_id is not None and expected_document_id != chunk.document_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if (
        expected_section_path is not None
        and list(expected_section_path)
        and list(chunk.section_path) != list(expected_section_path)
    ):
        raise _state_unavailable("historical_chunk_mismatch")

    source_name = _source_name_for_document(corpus_manifest, chunk.document_id)
    return chunk, corpus_manifest, source_name


def _resolve_verified_chunk(
    settings: AppSettings,
    chunk_manifest: ChunkSetManifest,
    *,
    chunk_id: str,
) -> tuple[ChunkSetDocumentEntry, DocumentChunkArtifact, Chunk]:
    # Fail closed on the first artifact-integrity failure encountered while
    # locating the chunk. Never skip a corrupt entry to fall back on another.
    for entry in chunk_manifest.documents:
        artifact = _load_verified_artifact(settings, chunk_manifest, entry)
        for chunk in list(artifact.parents) + list(artifact.children):
            if chunk.chunk_id == chunk_id:
                return entry, artifact, chunk
    raise _state_unavailable("historical_chunk_unavailable")


def _load_verified_artifact(
    settings: AppSettings,
    chunk_manifest: ChunkSetManifest,
    entry: ChunkSetDocumentEntry,
) -> DocumentChunkArtifact:
    artifact_id = str(entry.chunk_artifact_id or "").strip()
    if _CHUNK_ARTIFACT_ID_RE.fullmatch(artifact_id) is None:
        raise _state_unavailable("historical_chunk_unavailable")

    expected_id = chunk_artifact_id(
        entry.parsed_artifact_id,
        chunk_manifest.chunk_config_hash,
        chunker_version=chunk_manifest.chunker_version,
    )
    if expected_id != entry.chunk_artifact_id:
        raise _state_unavailable("historical_chunk_mismatch")

    if entry.chunk_artifact != chunk_artifact_relpath(entry.chunk_artifact_id):
        raise _state_unavailable("historical_chunk_mismatch")

    path = settings.paths.chunks / f"{artifact_id}.json"
    if not path.is_file():
        raise _state_unavailable("historical_chunk_unavailable")
    raw = path.read_bytes()
    if artifact_bytes_hash(raw) != entry.chunk_artifact_hash:
        raise _state_unavailable("historical_chunk_mismatch")

    try:
        artifact = DocumentChunkArtifact.model_validate_json(raw)
    except Exception as exc:
        raise _state_unavailable("historical_chunk_unavailable") from exc

    if artifact.schema_version != _CHUNK_ARTIFACT_SCHEMA:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.chunk_artifact_id != entry.chunk_artifact_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.document_id != entry.document_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.parsed_artifact_id != entry.parsed_artifact_id:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.chunk_config_hash != chunk_manifest.chunk_config_hash:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.chunker_version != chunk_manifest.chunker_version:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.parent_count != entry.parent_count:
        raise _state_unavailable("historical_chunk_mismatch")
    if artifact.child_count != entry.child_count:
        raise _state_unavailable("historical_chunk_mismatch")
    return artifact


def _source_name_for_document(
    corpus_manifest: CorpusManifest, document_id: str
) -> str | None:
    for doc in corpus_manifest.documents:
        if doc.document_id == document_id:
            return doc.source_name
    return None


def gold_source_context(
    *,
    chunk: Chunk,
    document_title: str | None,
    source_name: str | None,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "document_title": document_title,
        "source_name": source_name,
        "section_path": list(chunk.section_path),
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "content_type": chunk.content_type,
        "text": chunk.text,
    }


def raise_as_gold_lab_state(exc: Exception) -> None:
    """Normalize unexpected historical failures (never used for success path)."""
    if isinstance(exc, AppError):
        raise exc
    if isinstance(exc, GoldLabError):
        raise _state_unavailable(exc.reason) from exc
    raise _state_unavailable("historical_chunk_unavailable") from exc
