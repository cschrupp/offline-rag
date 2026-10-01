"""Monotonic high-resolution timing substrate for Slice 14A.

Durations MUST use ``time.perf_counter`` (or equivalent monotonic clock).
Wall-clock timestamps are provenance only and must never compute durations.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from offline_rag.evaluation.performance_14.contracts import (
    SEMANTIC_STAGE_ENVELOPES_V1,
    SEMANTIC_STAGE_IDS_V1,
    Performance14Error,
)


def validate_stage_id(stage_id: str) -> str:
    if stage_id not in SEMANTIC_STAGE_IDS_V1:
        raise Performance14Error(
            f"unknown semantic stage_id {stage_id!r}; "
            f"allowed={list(SEMANTIC_STAGE_IDS_V1)}"
        )
    return stage_id


def stage_envelope(stage_id: str) -> str:
    """Return the normative start→end envelope for a locked stage id."""
    validate_stage_id(stage_id)
    return SEMANTIC_STAGE_ENVELOPES_V1[stage_id]


@dataclass(frozen=True, slots=True)
class TimingSample:
    """One monotonic duration sample (seconds)."""

    stage_id: str
    duration_seconds: float
    envelope: str


@contextmanager
def measure_stage(stage_id: str) -> Iterator[dict[str, float]]:
    """Context manager measuring a semantic stage with perf_counter.

    Yields a mutable dict that receives ``duration_seconds`` on exit even if
    the body raises (exception is re-raised after recording).
    """
    validate_stage_id(stage_id)
    result: dict[str, float] = {}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["duration_seconds"] = time.perf_counter() - start


def timed_call[T](stage_id: str, fn: Callable[[], T]) -> tuple[T, TimingSample]:
    """Run ``fn`` under a semantic stage timer; preserve return value.

    Exceptions propagate unchanged after the duration is measured. Callers that
    need a sample on failure should use :func:`measure_stage`.
    """
    validate_stage_id(stage_id)
    start = time.perf_counter()
    value = fn()
    duration = time.perf_counter() - start
    sample = TimingSample(
        stage_id=stage_id,
        duration_seconds=duration,
        envelope=stage_envelope(stage_id),
    )
    return value, sample


def monotonic_now() -> float:
    """Return monotonic clock seconds (not wall-clock)."""
    return time.perf_counter()
