"""Deterministic Slice 12C evaluation identity (``receval_``)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from offline_rag.core.ids import recovery_eval_config_hash
from offline_rag.evaluation.generation_semantic.models import GenerationCohortMapV1
from offline_rag.evaluation.recovery_12c.binding import cohort_map_identity_payload
from offline_rag.evaluation.recovery_12c.contracts import (
    RECOVERY_EVAL_CONCLUSION_V1,
    RECOVERY_EVAL_V1,
)
from offline_rag.recovery.contracts import RECOVERY_PROTOCOL_V1
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1, SUFFICIENCY_POLICY_V1


def build_recovery_eval_semantic_payload(
    *,
    gold_dataset_id: str,
    cohort_map: GenerationCohortMapV1 | Mapping[str, Any],
    corpus_id: str,
    chunk_set_id: str,
    dense_index_id: str,
    lexical_index_id: str,
    fusion_config_hash: str,
    reranker_config_hash: str,
    context_config_hash: str,
    rewriter_config_hash: str,
    sufficiency_policy: str = SUFFICIENCY_POLICY_V1,
    sufficiency_gate: str = EMPTY_CONTEXT_GATE_V1,
    recovery_protocol: str = RECOVERY_PROTOCOL_V1,
    conclusion_contract: str = RECOVERY_EVAL_CONCLUSION_V1,
    evaluation_contract: str = RECOVERY_EVAL_V1,
) -> dict[str, Any]:
    """Identity-bearing 12C evaluation payload.

    Excludes timestamps, output paths, API secrets, and wall-clock latency.
    """
    if isinstance(cohort_map, GenerationCohortMapV1):
        cohort_payload = cohort_map_identity_payload(cohort_map)
    else:
        cohort_payload = dict(cohort_map)
    return {
        "evaluation_contract": evaluation_contract,
        "conclusion_contract": conclusion_contract,
        "gold_dataset_id": gold_dataset_id,
        "adjudication_cohort_map": cohort_payload,
        "corpus_id": corpus_id,
        "chunk_set_id": chunk_set_id,
        "dense_index_id": dense_index_id,
        "lexical_index_id": lexical_index_id,
        "fusion_config_hash": fusion_config_hash,
        "reranker_config_hash": reranker_config_hash,
        "context_config_hash": context_config_hash,
        "sufficiency_policy": sufficiency_policy,
        "sufficiency_gate": sufficiency_gate,
        "recovery_protocol": recovery_protocol,
        "rewriter_config_hash": rewriter_config_hash,
    }


def build_recovery_eval_identity_hash(
    *,
    gold_dataset_id: str,
    cohort_map: GenerationCohortMapV1 | Mapping[str, Any],
    corpus_id: str,
    chunk_set_id: str,
    dense_index_id: str,
    lexical_index_id: str,
    fusion_config_hash: str,
    reranker_config_hash: str,
    context_config_hash: str,
    rewriter_config_hash: str,
    **kwargs: Any,
) -> str:
    payload = build_recovery_eval_semantic_payload(
        gold_dataset_id=gold_dataset_id,
        cohort_map=cohort_map,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id=dense_index_id,
        lexical_index_id=lexical_index_id,
        fusion_config_hash=fusion_config_hash,
        reranker_config_hash=reranker_config_hash,
        context_config_hash=context_config_hash,
        rewriter_config_hash=rewriter_config_hash,
        **kwargs,
    )
    return recovery_eval_config_hash(payload)
