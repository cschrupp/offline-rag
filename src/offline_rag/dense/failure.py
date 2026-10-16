"""Bounded dense-stage failure classification (observability only).

Trusted vocabulary for distinguishing embedding generation, artifact
persistence, materialization/backend, and validation failures without
exposing raw exception text through public safe-error DTOs.
"""

from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

DENSE_FAILURE_EMBEDDING_GENERATION: Final = "embedding_generation_failed"
DENSE_FAILURE_EMBEDDING_PERSISTENCE: Final = "embedding_artifact_persistence_failed"
DENSE_FAILURE_MATERIALIZATION: Final = "dense_materialization_failed"
DENSE_FAILURE_VALIDATION: Final = "dense_validation_failed"
DENSE_FAILURE_PRECONDITION: Final = "dense_precondition_failed"
DENSE_FAILURE_STAGE: Final = "dense_stage_failed"

DENSE_FAILURE_PUBLIC_REASONS: Final = frozenset(
    {
        DENSE_FAILURE_EMBEDDING_GENERATION,
        DENSE_FAILURE_EMBEDDING_PERSISTENCE,
        DENSE_FAILURE_MATERIALIZATION,
        DENSE_FAILURE_VALIDATION,
        DENSE_FAILURE_PRECONDITION,
        DENSE_FAILURE_STAGE,
    }
)


class DenseStageError(RuntimeError):
    """Classified dense-stage failure carrying truthful partial counters."""

    def __init__(
        self,
        message: str,
        *,
        classification: str,
        embeddings_generated: int = 0,
        embeddings_reused: int = 0,
        embeddings_failed: int = 0,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.embeddings_generated = int(embeddings_generated)
        self.embeddings_reused = int(embeddings_reused)
        self.embeddings_failed = int(embeddings_failed)


def public_dense_failure_reason(classification: str | None) -> str:
    """Map internal classification to a SafeErrorDetails reason code."""
    if classification is not None and classification in DENSE_FAILURE_PUBLIC_REASONS:
        return classification
    return "stage_failed"


def log_dense_failure(
    *,
    run_id: str,
    corpus_name: str,
    classification: str,
    exc: BaseException,
) -> None:
    """Log full causal exception/traceback for operators (not public DTO)."""
    logger.exception(
        "dense indexing failed run_id=%s corpus=%s classification=%s",
        run_id,
        corpus_name,
        classification,
        exc_info=exc,
    )
