"""Snapshot-bound query identities for product read paths (15E)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from offline_rag.app.snapshot import CorpusReadSnapshot
from offline_rag.config.models import AppSettings
from offline_rag.dense.persistence import load_index_manifest
from offline_rag.domain.corpus import CorpusManifest
from offline_rag.lexical.persistence import load_lexical_index_manifest


@dataclass(frozen=True)
class SnapshotQueryBinding:
    """Immutable dense/lexical/context identities resolved from a publication snapshot."""

    corpus_name: str
    snapshot_id: str
    product_mode_id: str
    corpus_id: str
    corpus_manifest: CorpusManifest
    chunk_set_id: str
    chunk_manifest_name: str
    dense_index_id: str
    dense_index_manifest_name: str
    dense_collection_name: str
    lexical_index_id: str
    lexical_index_manifest_name: str
    fusion_config_hash: str
    reranker_config_hash: str
    context_config_hash: str
    embedding_config_hash: str
    index_config_hash: str
    lexical_config_hash: str

    def source_name_by_document_id(self) -> dict[str, str]:
        return {
            entry.document_id: entry.source_name
            for entry in self.corpus_manifest.documents
        }


def build_snapshot_query_binding(
    settings: AppSettings,
    snapshot: CorpusReadSnapshot,
) -> SnapshotQueryBinding:
    """Build query binding from a resolved snapshot + dense/lexical manifests.

    Loads index manifests under ``settings.paths.*`` for ``collection_name``.
    Does not read ``corpora/*/state.json`` or ``product/current.json``.
    """
    identity = snapshot.identity
    dense_manifest = load_index_manifest(
        settings.paths.index_manifests / Path(identity.dense_index_manifest).name
    )
    load_lexical_index_manifest(
        settings.paths.lexical_index_manifests
        / Path(identity.lexical_index_manifest).name
    )
    return SnapshotQueryBinding(
        corpus_name=snapshot.corpus_name,
        snapshot_id=snapshot.snapshot_id,
        product_mode_id=identity.product_mode_id,
        corpus_id=identity.corpus_id,
        corpus_manifest=snapshot.corpus_manifest,
        chunk_set_id=identity.chunk_set_id,
        chunk_manifest_name=Path(identity.chunk_manifest).name,
        dense_index_id=identity.dense_index_id,
        dense_index_manifest_name=Path(identity.dense_index_manifest).name,
        dense_collection_name=dense_manifest.collection_name,
        lexical_index_id=identity.lexical_index_id,
        lexical_index_manifest_name=Path(identity.lexical_index_manifest).name,
        fusion_config_hash=identity.fusion_config_hash,
        reranker_config_hash=identity.reranker_config_hash,
        context_config_hash=identity.context_config_hash,
        embedding_config_hash=identity.embedding_config_hash,
        index_config_hash=identity.index_config_hash,
        lexical_config_hash=identity.lexical_config_hash,
    )
