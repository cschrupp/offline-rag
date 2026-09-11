"""Slice 7 structural context expansion / evidence assembly."""

from __future__ import annotations

from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.context.config_hash import (
    build_context_config_hash,
    build_context_semantic_payload,
)
from offline_rag.context.evaluate import HybridRerankContextEvaluator
from offline_rag.context.expand import ContextExpander, ExpandedContext
from offline_rag.context.status import (
    context_status_for_corpus,
    describe_context_status,
)

__all__ = [
    "ContextExpander",
    "ExpandedContext",
    "HybridRerankContextAssembler",
    "HybridRerankContextError",
    "HybridRerankContextEvaluator",
    "build_context_config_hash",
    "build_context_semantic_payload",
    "context_status_for_corpus",
    "describe_context_status",
]
