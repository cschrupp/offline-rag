"""Code-owned gold-authoring contract identifiers (Slices 9A–9B)."""

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

SUPPORTED_NETWORK_POLICIES: frozenset[str] = frozenset(
    {"localhost_only", "private_network"}
)
