"""Code-owned gold-authoring contract identifiers (Slices 9A–9D)."""

from __future__ import annotations

ADAPTER_CONTRACT = "openai-compatible-authoring-v1"
QUESTION_PROPOSAL_CONTRACT = "question-proposal-v1"
RELEVANCE_PRELABEL_CONTRACT = "relevance-prelabel-v1"
AUTHORING_ARTIFACT_CONTRACT = "offline-rag-gold-authoring-v1"
SUPPORTED_PROVIDER = "openai_compatible"

SAMPLING_CONTRACT = "source-sampling-random-v1"
CONTEXT_CONTRACT = "proposal-context-seed-provenance-v1"
QUALITY_GATE_CONTRACT = "proposal-quality-gates-v1"
ATTEMPT_CONTRACT = "proposal-attempt-once-v1"

POOLING_CONTRACT = "candidate-pooling-v1"
RETRIEVER_LEXICAL_PLAIN_V1 = "lexical-plain-v1"
RETRIEVER_DENSE_PLAIN_V1 = "dense-plain-v1"
RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1 = "dense-model-query-prompt-v1"
RETRIEVER_DENSE_ARM_H_V1 = "dense-arm-h-v1"
RETRIEVER_HYBRID_RRF_V1 = "hybrid-rrf-v1"
RETRIEVER_HYBRID_RERANK_V1 = "hybrid-rerank-v1"

POOLING_RETRIEVER_IDS: tuple[str, ...] = (
    RETRIEVER_LEXICAL_PLAIN_V1,
    RETRIEVER_DENSE_PLAIN_V1,
    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1,
    RETRIEVER_DENSE_ARM_H_V1,
    RETRIEVER_HYBRID_RRF_V1,
    RETRIEVER_HYBRID_RERANK_V1,
)

POOLING_DEPTHS: dict[str, int] = {
    RETRIEVER_LEXICAL_PLAIN_V1: 50,
    RETRIEVER_DENSE_PLAIN_V1: 50,
    RETRIEVER_DENSE_MODEL_QUERY_PROMPT_V1: 50,
    RETRIEVER_DENSE_ARM_H_V1: 50,
    RETRIEVER_HYBRID_RRF_V1: 50,
    RETRIEVER_HYBRID_RERANK_V1: 20,
}

JUDGE_CONTEXT_CONTRACT = "relevance-judge-context-v1"
BLIND_ORDER_CONTRACT = "blind-order-v1"
PRELABEL_AGREEMENT_CONTRACT = "prelabel-agreement-v1"
PASS_1 = "pass_1"
PASS_2 = "pass_2"
PRELABEL_PASS_IDS: tuple[str, ...] = (PASS_1, PASS_2)
RATIONALE_MAX_CHARS = 500

SUPPORTED_NETWORK_POLICIES: frozenset[str] = frozenset(
    {"localhost_only", "private_network"}
)
