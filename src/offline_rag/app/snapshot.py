"""D04 CorpusReadSnapshot identity and immutable read binding."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.core.ids import canonical_config_hash
from offline_rag.domain.corpus import CorpusManifest

PRODUCT_MODE_GROUNDED_V1 = "grounded_v1"
SNAPSHOT_SCHEMA_VERSION = "offline-rag-corpus-read-snapshot-v1"


class CanonicalSnapshotManifest(BaseModel):
    """Identity-bearing publication manifest (drives snapshot_id).

    Publication metadata (timestamps, counters) must never appear here.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    product_mode_id: str = PRODUCT_MODE_GROUNDED_V1
    corpus_id: str
    corpus_manifest: str
    chunk_set_id: str
    chunk_manifest: str
    dense_index_id: str
    dense_index_manifest: str
    lexical_index_id: str
    lexical_index_manifest: str
    embedding_config_hash: str
    index_config_hash: str
    lexical_config_hash: str
    fusion_config_hash: str
    reranker_config_hash: str
    context_config_hash: str


def compute_snapshot_id(manifest: CanonicalSnapshotManifest) -> str:
    """Deterministic snapshot identity from canonical constituents only."""
    payload = manifest.model_dump(mode="python")
    cfg = canonical_config_hash(payload)
    return f"snap_{cfg.removeprefix('cfg_')}"


@dataclass(frozen=True)
class CorpusReadSnapshot:
    """Immutable request-bound product snapshot (D04)."""

    corpus_name: str
    snapshot_id: str
    identity: CanonicalSnapshotManifest
    corpus_manifest: CorpusManifest

    def document_summaries(self) -> list[dict[str, object]]:
        docs: list[dict[str, object]] = []
        for entry in self.corpus_manifest.documents:
            docs.append(
                {
                    "document_id": entry.document_id,
                    "source_name": entry.source_name,
                    "content_type": entry.source_media_type,
                    "byte_size": entry.source_size_bytes,
                    "content_hash": entry.source_content_hash,
                }
            )
        return docs

    def get_document_summary(self, document_id: str) -> dict[str, object] | None:
        for entry in self.corpus_manifest.documents:
            if entry.document_id == document_id:
                return {
                    "document_id": entry.document_id,
                    "source_name": entry.source_name,
                    "content_type": entry.source_media_type,
                    "byte_size": entry.source_size_bytes,
                    "content_hash": entry.source_content_hash,
                }
        return None


class PublishedPointer(BaseModel):
    """Mutable product current pointer (not part of snapshot_id)."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
