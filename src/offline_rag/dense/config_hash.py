"""Deterministic embedding and index configuration hashes."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, IndexingSettings
from offline_rag.core.ids import (
    ALL_CHILDREN_V1,
    DENSE_INDEX_CONTRACT_VERSION,
    DOCUMENT_TITLE_V1,
    EXCLUDE_HEADING_ONLY_V1,
    TITLE_SECTION_TEXT_V1,
    canonical_config_hash,
    embedding_config_hash,
    index_config_hash,
)
from offline_rag.dense.searchable_units import (
    ALL_CHILDREN_STRATEGY,
    EXCLUDE_HEADING_ONLY_STRATEGY,
)
from offline_rag.dense.text import (
    PlainEmbeddingTextBuilder,
    TitleSectionEmbeddingTextBuilder,
)


def build_embedding_config_hash(settings: AppSettings | IndexingSettings) -> str:
    """Hash only vector-affecting embedding semantics (document/passage side).

    Query-side representation (``dense.query_text``) is intentionally excluded so
    query-contract changes do not invalidate immutable document indexes.
    """
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
        # Legacy string fields retained for historical embcfg_ stability.
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
    payload: dict = {
        "embedding_config_hash": emb_cfg,
        "metric": indexing.metric,
        "backend": indexing.backend,
        "backend_contract": indexing.backend_contract,
        "index_contract_version": DENSE_INDEX_CONTRACT_VERSION,
    }
    units = indexing.searchable_units
    # Omit historical all-children-v1 from hash for index-ID stability.
    if (
        units.strategy == EXCLUDE_HEADING_ONLY_STRATEGY
        and units.contract_version == EXCLUDE_HEADING_ONLY_V1
    ):
        payload["searchable_units_strategy"] = units.strategy
        payload["searchable_units_contract"] = units.contract_version
    elif not (
        units.strategy == ALL_CHILDREN_STRATEGY
        and units.contract_version == ALL_CHILDREN_V1
    ):
        payload["searchable_units_strategy"] = units.strategy
        payload["searchable_units_contract"] = units.contract_version
    return index_config_hash(payload)


def build_dense_retrieval_config_hash(settings: AppSettings) -> str:
    """Hash retrieval-facing dense semantics: index identity + query-text contract.

    Distinguishes raw-query-v1 from model-query-prompt-v1 without fabricating a
    new document vector artifact.
    """
    query = settings.dense.query_text
    digest = canonical_config_hash(
        {
            "index_config_hash": build_index_config_hash(settings),
            "query_text_strategy": query.strategy,
            "query_text_contract": query.contract_version,
        }
    )
    return digest.replace("cfg_", "denseretrievecfg_", 1)
