"""Derived hybrid-rerank readiness (no persisted HybridRerankState)."""

from __future__ import annotations

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    CHUNK_ID_ASC_TIE_BREAK,
    PLAIN_PAIR_INPUT_CONTRACT,
    RAW_LOGIT_SCORE_CONTRACT,
    SEQ_TRUNC_1024_PASSAGE_RIGHT,
)
from offline_rag.hybrid.status import describe_hybrid_status, hybrid_status_for_corpus
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.rerank.provision import (
    RerankerReadiness,
    resolve_reranker_model_dir,
    validate_reranker_artifacts,
)


def reranker_artifact_status(settings: AppSettings) -> str:
    """Return READY | ABSENT | INVALID for the configured local reranker artifact."""
    model_dir = resolve_reranker_model_dir(
        reranker_artifacts_root=settings.paths.reranker_artifacts,
        model_path=settings.reranker.model.model_path,
    )
    status = validate_reranker_artifacts(
        model_dir,
        expected_model_id=settings.reranker.model.model_id,
        expected_revision=settings.reranker.model.revision,
        expected_adapter_contract=settings.reranker.model.adapter_contract,
    )
    if status.readiness == RerankerReadiness.READY:
        return "READY"
    if status.readiness == RerankerReadiness.ABSENT:
        return "ABSENT"
    return "INVALID"


def _reranker_config_ok(settings: AppSettings) -> bool:
    rrk = settings.reranker
    if rrk.input_construction != PLAIN_PAIR_INPUT_CONTRACT:
        return False
    if rrk.sequence_contract == SEQ_TRUNC_1024_PASSAGE_RIGHT and rrk.max_length != 1024:
        return False
    if rrk.score_transform != RAW_LOGIT_SCORE_CONTRACT:
        return False
    if rrk.tie_break != CHUNK_ID_ASC_TIE_BREAK:
        return False
    if not rrk.model.local_files_only or rrk.model.trust_remote_code:
        return False
    return rrk.input_k >= 1 and rrk.output_k >= 1


def hybrid_rerank_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return READY or NOT_READY for hybrid-rerank (derived)."""
    name = validate_corpus_name(corpus_name)
    if hybrid_status_for_corpus(settings, name) != "READY":
        return "NOT_READY"
    if not settings.reranker.enabled:
        return "NOT_READY"
    if not _reranker_config_ok(settings):
        return "NOT_READY"

    # Fake implementation is for CI; skip production artifact gate.
    if settings.reranker.implementation == "fake":
        return "READY"

    if reranker_artifact_status(settings) != "READY":
        return "NOT_READY"
    return "READY"


def describe_hybrid_rerank_status(
    settings: AppSettings, corpus_name: str
) -> dict[str, str | None]:
    name = validate_corpus_name(corpus_name)
    hybrid_details = describe_hybrid_status(settings, name)
    return {
        "status": hybrid_rerank_status_for_corpus(settings, name),
        "corpus_name": name,
        "hybrid_status": hybrid_details.get("status"),
        "reranker_artifacts": reranker_artifact_status(settings),
        "reranker_enabled": "true" if settings.reranker.enabled else "false",
        "reranker_implementation": settings.reranker.implementation,
        "dense_index_id": hybrid_details.get("dense_index_id"),
        "lexical_index_id": hybrid_details.get("lexical_index_id"),
        "active_chunk_set_id": hybrid_details.get("active_chunk_set_id"),
    }
