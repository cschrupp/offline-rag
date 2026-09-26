"""Frozen retrieval/context lineage comparison across recovery attempts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.sufficiency.contracts import ExactNonBlankStr


class RecoveryLineageV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: ExactNonBlankStr
    chunk_set_id: ExactNonBlankStr
    dense_index_id: ExactNonBlankStr
    lexical_index_id: ExactNonBlankStr
    fusion_config_hash: ExactNonBlankStr
    reranker_config_hash: ExactNonBlankStr
    context_config_hash: ExactNonBlankStr
    query: ExactNonBlankStr


def extract_recovery_lineage(result: HybridRerankContextResult) -> RecoveryLineageV1:
    metadata = dict(result.metadata or {})
    corpus_id = metadata.get("corpus_id")
    chunk_set_id = metadata.get("chunk_set_id")
    if not isinstance(corpus_id, str) or not corpus_id.strip():
        raise ValueError("context metadata.corpus_id is required for recovery lineage")
    if not isinstance(chunk_set_id, str) or not chunk_set_id.strip():
        raise ValueError(
            "context metadata.chunk_set_id is required for recovery lineage"
        )
    return RecoveryLineageV1(
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id=result.dense_index_id,
        lexical_index_id=result.lexical_index_id,
        fusion_config_hash=result.fusion_config_hash,
        reranker_config_hash=result.reranker_config_hash,
        context_config_hash=result.context_config_hash,
        query=result.query,
    )


def lineage_stack_equal(left: RecoveryLineageV1, right: RecoveryLineageV1) -> bool:
    """Compare frozen stack identity fields (query excluded)."""
    return (
        left.corpus_id == right.corpus_id
        and left.chunk_set_id == right.chunk_set_id
        and left.dense_index_id == right.dense_index_id
        and left.lexical_index_id == right.lexical_index_id
        and left.fusion_config_hash == right.fusion_config_hash
        and left.reranker_config_hash == right.reranker_config_hash
        and left.context_config_hash == right.context_config_hash
    )
