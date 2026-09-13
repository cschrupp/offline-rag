"""Code-owned gold-authoring contract identifiers (Slice 9A)."""

from __future__ import annotations

ADAPTER_CONTRACT = "openai-compatible-authoring-v1"
QUESTION_PROPOSAL_CONTRACT = "question-proposal-v1"
RELEVANCE_PRELABEL_CONTRACT = "relevance-prelabel-v1"
AUTHORING_ARTIFACT_CONTRACT = "offline-rag-gold-authoring-v1"
SUPPORTED_PROVIDER = "openai_compatible"

SUPPORTED_NETWORK_POLICIES: frozenset[str] = frozenset(
    {"localhost_only", "private_network"}
)
