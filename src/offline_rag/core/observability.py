"""Domain-neutral document-phase and activity events for ingestion observability.

Scientific modules may emit these without importing workspace/UI models.
Application orchestration adapts them into durable managed-operation worklists.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentPhaseEvent:
    """One advisory per-document phase observation within a pipeline stage."""

    document_id: str
    source_name: str
    phase: str


@dataclass(frozen=True)
class DocumentActivityEvent:
    """Bounded current-activity set for an interruptible execution unit.

    ``document_ids`` is the truthful 0..N set contributing work right now
    (for example the documents present in the current dense embedding batch).
    An empty tuple clears current activity between units/stages.
    """

    document_ids: tuple[str, ...]
    stage: str


ObservabilityReporter = Callable[[DocumentPhaseEvent], None]
ActivityReporter = Callable[[DocumentActivityEvent], None]


def report_document_phase(
    reporter: ObservabilityReporter | None,
    *,
    document_id: str,
    source_name: str,
    phase: str,
) -> None:
    """Invoke an optional document-phase reporter; never raises into the pipeline."""
    if reporter is None:
        return
    try:
        reporter(
            DocumentPhaseEvent(
                document_id=document_id,
                source_name=source_name,
                phase=phase,
            )
        )
    except Exception:  # noqa: BLE001 — telemetry must not escape into science
        return


def report_document_activity(
    reporter: ActivityReporter | None,
    *,
    document_ids: Sequence[str],
    stage: str,
) -> None:
    """Invoke an optional activity reporter; never raises into the pipeline."""
    if reporter is None:
        return
    try:
        reporter(
            DocumentActivityEvent(
                document_ids=tuple(document_ids),
                stage=stage,
            )
        )
    except Exception:  # noqa: BLE001 — telemetry must not escape into science
        return


__all__ = [
    "ActivityReporter",
    "DocumentActivityEvent",
    "DocumentPhaseEvent",
    "ObservabilityReporter",
    "report_document_activity",
    "report_document_phase",
]
