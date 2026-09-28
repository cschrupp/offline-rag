"""Slice 8 grounded local answer generation."""

from __future__ import annotations

from typing import Any

from offline_rag.generation.config_hash import (
    build_generation_config_hash,
    build_generation_semantic_payload,
)
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.status import (
    describe_generation_status,
    generation_status_for_corpus,
)

__all__ = [
    "FakeGenerator",
    "GroundedAnswerError",
    "GroundedAnswerOrchestrator",
    "QueryEvaluator",
    "build_generation_config_hash",
    "build_generation_semantic_payload",
    "describe_generation_status",
    "generation_status_for_corpus",
]


def __getattr__(name: str) -> Any:
    # Lazy heavy imports avoid recovery↔generation circular package init.
    if name == "QueryEvaluator":
        from offline_rag.generation.evaluate import QueryEvaluator

        return QueryEvaluator
    if name in {"GroundedAnswerError", "GroundedAnswerOrchestrator"}:
        from offline_rag.generation.orchestrate import (
            GroundedAnswerError,
            GroundedAnswerOrchestrator,
        )

        return {
            "GroundedAnswerError": GroundedAnswerError,
            "GroundedAnswerOrchestrator": GroundedAnswerOrchestrator,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
