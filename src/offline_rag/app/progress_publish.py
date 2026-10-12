"""Adapt domain ProgressEvent emissions into durable ManagedOperationProgress."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationProgressStep,
    ManagedOperationProgressUnit,
    OperationProgressStage,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.core.progress import ProgressEvent


@dataclass
class DurableProgressPublisher:
    """Throttle durable progress writes for high-frequency pipeline loops.

    Publishes when step changes, current reaches total, at least one percentage
    point advances, or ~1 second elapsed since the last durable write.
    """

    operations: ManagedOperationStore
    workspace_id: str
    operation_id: str
    lease: WorkspaceMutationLease | None = None
    progress_stage: OperationProgressStage | None = None
    # Injectable clock for deterministic throttling tests (seconds monotonic).
    clock: Callable[[], float] | None = None
    _last_step: str | None = field(default=None, init=False, repr=False)
    _last_current: int | None = field(default=None, init=False, repr=False)
    _last_total: int | None = field(default=None, init=False, repr=False)
    _last_pct: int = field(default=-1, init=False, repr=False)
    _last_mono: float = field(default=0.0, init=False, repr=False)
    write_count: int = field(default=0, init=False)

    def __call__(self, event: ProgressEvent) -> None:
        """Publish fine-grained progress; never raise into scientific/publication paths.

        Coarse ``update_status`` remains authoritative elsewhere and is not
        suppressed here. Only best-effort ``update_progress`` telemetry is
        isolated.
        """
        now = self.clock() if self.clock is not None else time.monotonic()
        pct = -1
        if event.total is not None and event.total > 0:
            pct = min(100, int((event.current * 100) / event.total))

        should = (
            self._last_step != event.step
            or (event.total is not None and event.current >= event.total)
            or self._last_current is None
            or (pct >= 0 and pct > self._last_pct)
            or (now - self._last_mono) >= 1.0
        )
        if not should:
            return

        try:
            self.operations.update_progress(
                self.workspace_id,
                self.operation_id,
                step=ManagedOperationProgressStep(event.step),
                current=event.current,
                total=event.total,
                unit=ManagedOperationProgressUnit(event.unit),
                progress_stage=self.progress_stage,
                lease=self.lease,
            )
        except Exception:  # noqa: BLE001 — fine-grained telemetry must not escape
            return

        self.write_count += 1
        self._last_step = event.step
        self._last_current = event.current
        self._last_total = event.total
        self._last_pct = pct
        self._last_mono = now

    def set_stage(self, stage: OperationProgressStage | None) -> None:
        self.progress_stage = stage


__all__ = ["DurableProgressPublisher"]
