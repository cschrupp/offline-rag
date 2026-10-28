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
DENSE_FAILURE_CUDA_MEMORY_EXHAUSTED: Final = "cuda_memory_exhausted"
DENSE_FAILURE_EMBEDDING_PERSISTENCE: Final = "embedding_artifact_persistence_failed"
DENSE_FAILURE_MATERIALIZATION: Final = "dense_materialization_failed"
DENSE_FAILURE_VALIDATION: Final = "dense_validation_failed"
DENSE_FAILURE_PRECONDITION: Final = "dense_precondition_failed"
DENSE_FAILURE_STAGE: Final = "dense_stage_failed"

DENSE_FAILURE_PUBLIC_REASONS: Final = frozenset(
    {
        DENSE_FAILURE_EMBEDDING_GENERATION,
        DENSE_FAILURE_CUDA_MEMORY_EXHAUSTED,
        DENSE_FAILURE_EMBEDDING_PERSISTENCE,
        DENSE_FAILURE_MATERIALIZATION,
        DENSE_FAILURE_VALIDATION,
        DENSE_FAILURE_PRECONDITION,
        DENSE_FAILURE_STAGE,
    }
)


class CudaMemoryExhaustedError(RuntimeError):
    """Bounded terminal signal after the authorized CUDA batch ladder fails."""

    def __init__(
        self,
        *,
        configured_batch_size: int,
        final_batch_size: int,
    ) -> None:
        super().__init__("CUDA embedding memory exhausted after bounded batch recovery")
        self.configured_batch_size = configured_batch_size
        self.final_batch_size = final_batch_size


def is_cuda_oom_error(exc: BaseException) -> bool:
    """Recognize specific CUDA allocation exhaustion, including wrapped causes."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    markers = (
        "cuda error: out of memory",
        "cuda out of memory",
        "cuda_error_out_of_memory",
        "cudaerrormemoryallocation",
    )
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        current_type = type(current)
        if (
            current_type.__name__ == "OutOfMemoryError"
            and current_type.__module__.startswith("torch")
        ):
            return True
        try:
            message = str(current).lower()
        except Exception:  # noqa: BLE001 — malformed exception text is not evidence
            message = ""
        if any(marker in message for marker in markers):
            return True

        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


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
