"""Domain-neutral progress events for long-running pipelines.

Scientific modules may emit these events without importing workspace/UI models.
Application orchestration adapts them into durable ManagedOperationProgress.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgressEvent:
    """One advisory progress observation within a measurable pipeline step."""

    step: str
    current: int
    total: int | None
    unit: str


ProgressReporter = Callable[[ProgressEvent], None]


def report_progress(
    reporter: ProgressReporter | None,
    *,
    step: str,
    current: int,
    total: int | None,
    unit: str,
) -> None:
    """Invoke an optional progress reporter; never raises into the pipeline."""
    if reporter is None:
        return
    reporter(ProgressEvent(step=step, current=current, total=total, unit=unit))


__all__ = [
    "ProgressEvent",
    "ProgressReporter",
    "report_progress",
]
