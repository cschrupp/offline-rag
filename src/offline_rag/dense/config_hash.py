"""Deterministic embedding and index configuration hashes."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, IndexingSettings
from offline_rag.core.ids import (
    DENSE_INDEX_CONTRACT_VERSION,
    DOCUMENT_TITLE_V1,
    TITLE_SECTION_TEXT_V1,
    embedding_config_hash,
    index_config_hash,
)
from offline_rag.dense.text import (
    PlainEmbeddingTextBuilder,
    TitleSectionEmbeddingTextBuilder,
)


def build_embedding_config_hash(settings: AppSettings | IndexingSettings) -> str:
    """Hash only vector-affecting embedding semantics."""
    indexing = settings.indexing if isinstance(settings, AppSettings) else settings
    text = indexing.embedding_text
    emb = indexing.embedding
    payload: dict = {
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
    # Metadata-aware representation identity (omit for historical plain-v1 stability).
    if (
        text.strategy == TitleSectionEmbeddingTextBuilder.strategy
        and text.contract_version == TitleSectionEmbeddingTextBuilder.contract_version
    ):
        payload["document_title_contract"] = DOCUMENT_TITLE_V1
        payload["ranking_text_contract"] = TITLE_SECTION_TEXT_V1
    elif not (
        text.strategy == PlainEmbeddingTextBuilder.strategy
        and text.contract_version == PlainEmbeddingTextBuilder.contract_version
    ):
        # Unsupported combinations still hash their declared contracts if present.
        pass
    return embedding_config_hash(payload)


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
