"""Domain-neutral document-phase events for ingestion observability.

Scientific modules may emit these without importing workspace/UI models.
Application orchestration adapts them into durable managed-operation worklists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentPhaseEvent:
    """One advisory per-document phase observation within a pipeline stage."""

    document_id: str
    source_name: str
    phase: str


ObservabilityReporter = Callable[[DocumentPhaseEvent], None]


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


__all__ = [
    "DocumentPhaseEvent",
    "ObservabilityReporter",
    "report_document_phase",
]
