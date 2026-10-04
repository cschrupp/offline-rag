"""App-owned operation registry for admission, deadlines, and drain (15F)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from offline_rag.app.capacity import CapacityGate
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.config.models import AppSettings


class OperationKind(StrEnum):
    QUERY = "query"
    INGEST = "ingest"


class IngestLifecycle(StrEnum):
    PRE_LEASE = "pre_lease"
    POST_LEASE = "post_lease"
    PUBLICATION = "publication"
    TERMINAL = "terminal"


class CancelReason(StrEnum):
    NONE = "none"
    CLIENT_DISCONNECT = "client_disconnect"
    SHUTDOWN = "shutdown"


@dataclass
class OperationHandle:
    """Per-invocation control: monotonic deadline + cooperative cancel."""

    op_id: str
    kind: OperationKind
    deadline_mono: float
    cancel_event: threading.Event = field(default_factory=threading.Event)
    cancel_reason: CancelReason = CancelReason.NONE
    ingest_lifecycle: IngestLifecycle | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _released: bool = field(default=False, repr=False)

    @property
    def in_publication(self) -> bool:
        return self.ingest_lifecycle is IngestLifecycle.PUBLICATION

    def signal_cancel(self, reason: CancelReason) -> None:
        """Request cooperative cancellation. Idempotent; first reason wins."""
        if reason is CancelReason.NONE:
            return
        with self._lock:
            if self.kind is OperationKind.INGEST:
                # D18: post-lease client disconnect is not a cancel signal.
                if reason is CancelReason.CLIENT_DISCONNECT and self.ingest_lifecycle in {
                    IngestLifecycle.POST_LEASE,
                    IngestLifecycle.PUBLICATION,
                    IngestLifecycle.TERMINAL,
                }:
                    return
                # Shutdown cannot abort an ingest already in publication CS.
                if (
                    reason is CancelReason.SHUTDOWN
                    and self.ingest_lifecycle is IngestLifecycle.PUBLICATION
                ):
                    return
            if self.cancel_reason is CancelReason.NONE:
                self.cancel_reason = reason
            self.cancel_event.set()

    def mark_post_lease(self) -> None:
        with self._lock:
            if self.kind is not OperationKind.INGEST:
                raise RuntimeError("mark_post_lease only valid for ingest")
            if self.ingest_lifecycle is IngestLifecycle.TERMINAL:
                return
            self.ingest_lifecycle = IngestLifecycle.POST_LEASE

    def enter_publication(self) -> None:
        with self._lock:
            if self.kind is not OperationKind.INGEST:
                raise RuntimeError("enter_publication only valid for ingest")
            if self.ingest_lifecycle is IngestLifecycle.TERMINAL:
                return
            self.ingest_lifecycle = IngestLifecycle.PUBLICATION

    def mark_terminal(self) -> None:
        with self._lock:
            if self.kind is OperationKind.INGEST:
                self.ingest_lifecycle = IngestLifecycle.TERMINAL

    def deadline_expired(self) -> bool:
        return time.monotonic() >= self.deadline_mono

    def checkpoint(self, where: str = "") -> None:
        """Raise AppError when cancel/deadline forbids continuing work.

        Grace-period shutdown waiting is never converted into request_timeout.
        Queries cancelled by disconnect/shutdown raise request_cancelled.
        Ingest shutdown abort (pre-publication) raises request_cancelled as an
        application abort signal; transports map as needed. Deadline → request_timeout.
        """
        with self._lock:
            reason = self.cancel_reason
            lifecycle = self.ingest_lifecycle
            cancelled = self.cancel_event.is_set()

        if self.kind is OperationKind.QUERY:
            if cancelled and reason in {
                CancelReason.CLIENT_DISCONNECT,
                CancelReason.SHUTDOWN,
            }:
                raise AppError(
                    ErrorCode.REQUEST_CANCELLED,
                    details=SafeErrorDetails(reason=str(reason), stage=where or None),
                )
            if self.deadline_expired():
                # Prefer explicit cancel classification when already signalled.
                if cancelled and reason is CancelReason.SHUTDOWN:
                    raise AppError(
                        ErrorCode.REQUEST_CANCELLED,
                        details=SafeErrorDetails(reason=str(reason), stage=where or None),
                    )
                raise AppError(
                    ErrorCode.REQUEST_TIMEOUT,
                    details=SafeErrorDetails(reason="query_deadline_exceeded", stage=where or None),
                )
            return

        # INGEST
        if cancelled and reason is CancelReason.SHUTDOWN:
            if lifecycle is IngestLifecycle.PUBLICATION:
                return
            # Application abort — not request_timeout / not a query cancel mapping.
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="shutdown_abort", stage=where or None),
            )
        # Client disconnect never cancels post-lease ingest via checkpoint.
        if self.deadline_expired():
            if lifecycle is IngestLifecycle.PUBLICATION:
                # Finish publication; do not convert to request_timeout.
                return
            raise AppError(
                ErrorCode.REQUEST_TIMEOUT,
                details=SafeErrorDetails(reason="ingest_deadline_exceeded", stage=where or None),
            )


@dataclass
class OperationRegistry:
    """Process-local registry of admitted product operations."""

    settings: AppSettings
    query_capacity: CapacityGate
    ingest_capacity: CapacityGate
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _active: dict[str, OperationHandle] = field(default_factory=dict, init=False)
    _idle: threading.Condition = field(init=False)
    _draining: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._idle = threading.Condition(self._lock)

    @property
    def draining(self) -> bool:
        with self._lock:
            return self._draining

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def admit_query(self, *, deadline_seconds: float | None = None) -> OperationHandle:
        if not self.query_capacity.try_acquire():
            raise AppError(
                ErrorCode.SERVICE_OVERLOADED,
                details=SafeErrorDetails(reason="query_capacity_exhausted"),
            )
        seconds = (
            float(self.settings.api.query_deadline_seconds)
            if deadline_seconds is None
            else float(deadline_seconds)
        )
        handle = OperationHandle(
            op_id=f"opq_{uuid.uuid4().hex}",
            kind=OperationKind.QUERY,
            deadline_mono=time.monotonic() + seconds,
        )
        with self._idle:
            self._active[handle.op_id] = handle
        return handle

    def admit_ingest(self, *, deadline_seconds: float | None = None) -> OperationHandle:
        if not self.ingest_capacity.try_acquire():
            raise AppError(
                ErrorCode.SERVICE_OVERLOADED,
                details=SafeErrorDetails(reason="ingest_capacity_exhausted"),
            )
        seconds = (
            float(self.settings.api.ingest_deadline_seconds)
            if deadline_seconds is None
            else float(deadline_seconds)
        )
        handle = OperationHandle(
            op_id=f"opi_{uuid.uuid4().hex}",
            kind=OperationKind.INGEST,
            deadline_mono=time.monotonic() + seconds,
            ingest_lifecycle=IngestLifecycle.PRE_LEASE,
        )
        with self._idle:
            self._active[handle.op_id] = handle
        return handle

    def release(self, handle: OperationHandle) -> None:
        with self._idle:
            if handle._released:
                return
            handle._released = True
            handle.mark_terminal()
            self._active.pop(handle.op_id, None)
            if handle.kind is OperationKind.QUERY:
                self.query_capacity.release()
            else:
                self.ingest_capacity.release()
            self._idle.notify_all()

    def signal_shutdown(self) -> None:
        with self._idle:
            self._draining = True
            handles = list(self._active.values())
        for handle in handles:
            handle.signal_cancel(CancelReason.SHUTDOWN)

    def wait_until_idle(self, timeout_seconds: float) -> bool:
        """Block until no active ops or timeout. Uses monotonic deadline."""
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        with self._idle:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(timeout=min(0.05, remaining))
            return True
