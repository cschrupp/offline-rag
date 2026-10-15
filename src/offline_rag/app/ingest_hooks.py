"""Optional product-ingest test hooks (Phase 15D) + 16I/16K-B telemetry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from offline_rag.core.observability import ObservabilityReporter
from offline_rag.core.progress import ProgressReporter


@dataclass
class ProductIngestHooks:
    """Optional test hooks — production leaves these unset."""

    after_lease_acquired: Callable[[str, Path], None] | None = None
    before_stage: Callable[[str], None] | None = None
    after_stage: Callable[[str], None] | None = None
    # 16I: optional fine-grained progress reporter for pipeline loops.
    on_progress: ProgressReporter | None = None
    # 16K-B: optional stage-report + per-document phase observability.
    after_stage_report: Callable[[str, object], None] | None = None
    on_document_phase: ObservabilityReporter | None = None
