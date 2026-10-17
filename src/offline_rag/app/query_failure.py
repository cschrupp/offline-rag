"""Bounded grounded-query internal_error classification (observability only)."""

from __future__ import annotations

import logging
import re
import traceback
from typing import Literal

from offline_rag.app.traces import (
    ProductTraceCudaFailureClass,
    ProductTraceFailureClass,
    ProductTraceFailureStage,
    ProductTraceInternalFailure,
)
from offline_rag.context.assemble import HybridRerankContextError
from offline_rag.dense.retrieve import DenseRetrievalError
from offline_rag.generation.executor import GroundedGenerationError
from offline_rag.generation.openai_compatible import OpenAICompatibleGeneratorError
from offline_rag.hybrid.retrieve import HybridRetrievalError
from offline_rag.rerank.cross_encoder import CrossEncoderRerankerError
from offline_rag.rerank.retrieve import HybridRerankRetrievalError

logger = logging.getLogger(__name__)

StageBreadcrumb = Literal["execution", "projection"]

_TYPE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_CHAIN_DEPTH = 16
_MAX_CAUSAL_TYPES = 16

# Deepest matching mapped type in the causal chain wins.
_STAGE_BY_TYPE: dict[type[BaseException], tuple[ProductTraceFailureStage, ProductTraceFailureClass]] = {
    DenseRetrievalError: ("dense_query", "dense_query_failure"),
    HybridRetrievalError: ("hybrid_retrieval", "hybrid_retrieval_failure"),
    HybridRerankRetrievalError: ("rerank", "reranker_failure"),
    CrossEncoderRerankerError: ("rerank", "reranker_failure"),
    HybridRerankContextError: ("context_assembly", "context_assembly_failure"),
    GroundedGenerationError: ("generation", "generation_failure"),
    OpenAICompatibleGeneratorError: ("generation", "generation_failure"),
}
# Message markers inspected only in-process; never persisted as free text.
_CUDA_MESSAGE_MARKERS: tuple[tuple[ProductTraceCudaFailureClass, tuple[str, ...]], ...] = (
    ("out_of_memory", ("out of memory", "cuda out of memory", "cuda oom")),
    ("cublas", ("cublasgemmex", "cublas")),
    ("allocation", ("failed to allocate", "cuda malloc", "allocation failed")),
    ("execution", ("device-side assert", "cuda error", "cuda runtime error")),
)


def sanitize_exception_type_name(name: str) -> str | None:
    """Return a bounded identifier class name, or None if unsafe."""
    if not isinstance(name, str):
        return None
    trimmed = name.strip()
    if not _TYPE_NAME_RE.fullmatch(trimmed):
        return None
    return trimmed


def _iter_exception_chain(exc: BaseException) -> list[BaseException]:
    """Walk __cause__ first; fall back to __context__ only without explicit cause."""
    chain: list[BaseException] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    depth = 0
    while current is not None and depth < _MAX_CHAIN_DEPTH:
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        chain.append(current)
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__context__ is not None:
            current = current.__context__
        else:
            break
        depth += 1
    return chain


def _cuda_failure_from_exception(
    exc: BaseException,
) -> ProductTraceCudaFailureClass | None:
    type_name = type(exc).__name__
    module = (getattr(type(exc), "__module__", "") or "").lower()
    if type_name == "OutOfMemoryError" or "outofmemory" in type_name.lower():
        return "out_of_memory"
    if "cuda" in module and type_name.endswith("Error"):
        return "unknown_cuda"

    # Inspect message only to produce a bounded enum — never persist the text.
    try:
        message = str(exc).lower()
    except Exception:  # noqa: BLE001 - classification must not raise
        return None
    for failure_class, markers in _CUDA_MESSAGE_MARKERS:
        for marker in markers:
            if marker in message:
                return failure_class
    if "cuda" in message:
        return "unknown_cuda"
    return None


def _mapped_stage_for_exception(
    exc: BaseException,
) -> tuple[ProductTraceFailureStage, ProductTraceFailureClass] | None:
    for exc_type, mapping in _STAGE_BY_TYPE.items():
        if isinstance(exc, exc_type):
            return mapping
    return None


def classify_grounded_query_failure(
    exc: BaseException,
    *,
    stage_breadcrumb: StageBreadcrumb,
) -> ProductTraceInternalFailure:
    """Build bounded durable classification for a grounded-query internal_error."""
    chain = _iter_exception_chain(exc)
    outer = chain[0]
    outer_name = sanitize_exception_type_name(type(outer).__name__) or "Exception"

    causal_names: list[str] = []
    for item in chain[1:]:
        name = sanitize_exception_type_name(type(item).__name__)
        if name is None:
            continue
        if name in causal_names:
            continue
        causal_names.append(name)
        if len(causal_names) >= _MAX_CAUSAL_TYPES:
            break

    # Most specific mapped stage: deepest (last) mapped type in the chain.
    mapped_stage: ProductTraceFailureStage | None = None
    mapped_class: ProductTraceFailureClass | None = None
    for item in chain:
        mapped = _mapped_stage_for_exception(item)
        if mapped is not None:
            mapped_stage, mapped_class = mapped

    cuda_failure: ProductTraceCudaFailureClass | None = None
    for item in chain:
        found = _cuda_failure_from_exception(item)
        if found is None:
            continue
        if found == "out_of_memory":
            cuda_failure = "out_of_memory"
            break
        if cuda_failure is None or cuda_failure == "unknown_cuda":
            cuda_failure = found
        elif found == "cublas":
            cuda_failure = "cublas"

    cuda_related = cuda_failure is not None

    if mapped_stage is not None and mapped_class is not None:
        stage = mapped_stage
        failure_class = mapped_class
    elif stage_breadcrumb == "projection":
        stage = "projection"
        failure_class = (
            "cuda_runtime_failure" if cuda_related else "projection_failure"
        )
    else:
        # Breadcrumb "execution" without a mapped subsystem type.
        stage = "unknown"
        failure_class = (
            "cuda_runtime_failure" if cuda_related else "unexpected_internal_failure"
        )

    return ProductTraceInternalFailure(
        stage=stage,
        failure_class=failure_class,
        exception_type=outer_name,
        causal_exception_types=causal_names,
        cuda_related=cuda_related,
        cuda_failure_class=cuda_failure,
    )


def log_grounded_query_failure(
    *,
    trace_id: str,
    classification: ProductTraceInternalFailure,
    exc: BaseException,
) -> None:
    """Emit server-side diagnostic record including full traceback."""
    logger.error(
        "grounded_query_internal_failure trace_id=%s stage=%s failure_class=%s "
        "exception_type=%s causal_exception_types=%s cuda_related=%s "
        "cuda_failure_class=%s\n%s",
        trace_id,
        classification.stage,
        classification.failure_class,
        classification.exception_type,
        classification.causal_exception_types,
        classification.cuda_related,
        classification.cuda_failure_class,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


def log_trace_persistence_failure(
    *,
    trace_id: str,
    exc: BaseException,
    stage_breadcrumb: StageBreadcrumb,
) -> None:
    """Log commit failure; durable trace cannot self-report persistence failure."""
    logger.error(
        "grounded_query_trace_persistence_failure trace_id=%s "
        "stage=trace_persistence failure_class=trace_persistence_failure "
        "stage_breadcrumb=%s exception_type=%s\n%s",
        trace_id,
        stage_breadcrumb,
        sanitize_exception_type_name(type(exc).__name__) or "Exception",
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )
