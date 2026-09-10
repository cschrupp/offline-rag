"""Deterministic embedding and index configuration hashes."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, IndexingSettings
from offline_rag.core.ids import (
    DENSE_INDEX_CONTRACT_VERSION,
    embedding_config_hash,
    index_config_hash,
)


def build_embedding_config_hash(settings: AppSettings | IndexingSettings) -> str:
    """Hash only vector-affecting embedding semantics."""
    indexing = settings.indexing if isinstance(settings, AppSettings) else settings
    text = indexing.embedding_text
    emb = indexing.embedding
    return embedding_config_hash(
        {
            "embedding_text_strategy": text.strategy,
            "embedding_text_contract": text.contract_version,
            "implementation": emb.implementation,
            "model_id": emb.model_id,
            "model_revision": emb.revision,
            "adapter_contract": emb.adapter_contract,
            "dimension": emb.dimension,
            "normalize": emb.normalize,
            "query_instruction": emb.query_instruction,
            "document_instruction": emb.document_instruction,
        }
    )


def build_index_config_hash(settings: AppSettings | IndexingSettings) -> str:
    """Hash embedding identity plus dense index/search semantics."""
    indexing = settings.indexing if isinstance(settings, AppSettings) else settings
    emb_cfg = build_embedding_config_hash(indexing)
    return index_config_hash(
        {
            "embedding_config_hash": emb_cfg,
            "metric": indexing.metric,
            "backend": indexing.backend,
            "backend_contract": indexing.backend_contract,
            "index_contract_version": DENSE_INDEX_CONTRACT_VERSION,
        }
    )
