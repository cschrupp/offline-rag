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

    def complete_lease_acquire(self) -> None:
        """Atomic PRE_LEASE → POST_LEASE after lease.acquire().

        If disconnect/shutdown/deadline arrived before the transition completes,
        raise and leave lifecycle at PRE_LEASE so the caller can release the lease
        without establishing candidate mutation.
        """
        with self._lock:
            if self.kind is not OperationKind.INGEST:
                raise RuntimeError("complete_lease_acquire only valid for ingest")
            if self.ingest_lifecycle is IngestLifecycle.TERMINAL:
                return
            if self.ingest_lifecycle is not IngestLifecycle.PRE_LEASE:
                return
            if self.cancel_event.is_set():
                reason = self.cancel_reason
                if reason is CancelReason.CLIENT_DISCONNECT:
                    raise AppError(
                        ErrorCode.REQUEST_CANCELLED,
                        details=SafeErrorDetails(reason="client_disconnect", stage="lease"),
                    )
                if reason is CancelReason.SHUTDOWN:
                    raise AppError(
                        ErrorCode.INGEST_FAILED,
                        details=SafeErrorDetails(reason="shutdown_abort", stage="lease"),
                    )
            if time.monotonic() >= self.deadline_mono:
                raise AppError(
                    ErrorCode.REQUEST_TIMEOUT,
                    details=SafeErrorDetails(
                        reason="ingest_deadline_exceeded", stage="lease"
                    ),
                )
            self.ingest_lifecycle = IngestLifecycle.POST_LEASE

    def mark_post_lease(self) -> None:
        """Backward-compatible alias for complete_lease_acquire()."""
        self.complete_lease_acquire()

    def enter_publication(self) -> None:
        """Atomic gate into the publication critical section.

        Under synchronization: reject pending pre-publication shutdown cancel and
        expired application deadline; only then transition to PUBLICATION. After
        success, shutdown/deadline must not roll publication back.
        """
        with self._lock:
            if self.kind is not OperationKind.INGEST:
                raise RuntimeError("enter_publication only valid for ingest")
            if self.ingest_lifecycle is IngestLifecycle.TERMINAL:
                return
            if self.ingest_lifecycle is IngestLifecycle.PUBLICATION:
                return
            if self.cancel_event.is_set() and self.cancel_reason is CancelReason.SHUTDOWN:
                raise AppError(
                    ErrorCode.INGEST_FAILED,
                    details=SafeErrorDetails(reason="shutdown_abort", stage="publish"),
                )
            if time.monotonic() >= self.deadline_mono:
                raise AppError(
                    ErrorCode.REQUEST_TIMEOUT,
                    details=SafeErrorDetails(
                        reason="ingest_deadline_exceeded", stage="publish"
                    ),
                )
            # Post-lease client disconnect remains ignored (D18).
            self.ingest_lifecycle = IngestLifecycle.PUBLICATION

    def mark_terminal(self) -> None:
        with self._lock:
            if self.kind is OperationKind.INGEST:
                self.ingest_lifecycle = IngestLifecycle.TERMINAL

    def deadline_expired(self) -> bool:
        return time.monotonic() >= self.deadline_mono

    def checkpoint(self, where: str = "") -> None:
        """Raise AppError when cancel/deadline forbids continuing work.

        Grace-period waiting is never converted into request_timeout.
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
                if cancelled and reason is CancelReason.SHUTDOWN:
                    raise AppError(
                        ErrorCode.REQUEST_CANCELLED,
                        details=SafeErrorDetails(reason=str(reason), stage=where or None),
                    )
                raise AppError(
                    ErrorCode.REQUEST_TIMEOUT,
                    details=SafeErrorDetails(
                        reason="query_deadline_exceeded", stage=where or None
                    ),
                )
            return

        # INGEST
        if cancelled and reason is CancelReason.CLIENT_DISCONNECT:
            if lifecycle is IngestLifecycle.PRE_LEASE:
                raise AppError(
                    ErrorCode.REQUEST_CANCELLED,
                    details=SafeErrorDetails(
                        reason="client_disconnect", stage=where or None
                    ),
                )
            # Post-lease / publication: ignore disconnect.
            return
        if cancelled and reason is CancelReason.SHUTDOWN:
            if lifecycle is IngestLifecycle.PUBLICATION:
                return
            raise AppError(
                ErrorCode.INGEST_FAILED,
                details=SafeErrorDetails(reason="shutdown_abort", stage=where or None),
            )
        if self.deadline_expired():
            if lifecycle is IngestLifecycle.PUBLICATION:
                return
            raise AppError(
                ErrorCode.REQUEST_TIMEOUT,
                details=SafeErrorDetails(
                    reason="ingest_deadline_exceeded", stage=where or None
                ),
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
    grace_exhausted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._idle = threading.Condition(self._lock)

    @property
    def draining(self) -> bool:
        with self._lock:
            return self._draining

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def _admit(
        self,
        *,
        kind: OperationKind,
        capacity: CapacityGate,
        deadline_seconds: float | None,
        default_deadline: float,
        exhausted_reason: str,
    ) -> OperationHandle:
        """Admit under the drain lock so drain/admission exclusion is atomic."""
        with self._idle:
            if self._draining:
                raise AppError(ErrorCode.RUNTIME_NOT_READY)
            if not capacity.try_acquire():
                raise AppError(
                    ErrorCode.SERVICE_OVERLOADED,
                    details=SafeErrorDetails(reason=exhausted_reason),
                )
            seconds = (
                float(default_deadline)
                if deadline_seconds is None
                else float(deadline_seconds)
            )
            # Re-check drain after capacity acquire; return slot if drain won the race.
            if self._draining:
                capacity.release()
                raise AppError(ErrorCode.RUNTIME_NOT_READY)
            handle = OperationHandle(
                op_id=f"op{'q' if kind is OperationKind.QUERY else 'i'}_{uuid.uuid4().hex}",
                kind=kind,
                deadline_mono=time.monotonic() + seconds,
                ingest_lifecycle=(
                    IngestLifecycle.PRE_LEASE if kind is OperationKind.INGEST else None
                ),
            )
            self._active[handle.op_id] = handle
            return handle

    def admit_query(self, *, deadline_seconds: float | None = None) -> OperationHandle:
        return self._admit(
            kind=OperationKind.QUERY,
            capacity=self.query_capacity,
            deadline_seconds=deadline_seconds,
            default_deadline=float(self.settings.api.query_deadline_seconds),
            exhausted_reason="query_capacity_exhausted",
        )

    def admit_ingest(self, *, deadline_seconds: float | None = None) -> OperationHandle:
        return self._admit(
            kind=OperationKind.INGEST,
            capacity=self.ingest_capacity,
            deadline_seconds=deadline_seconds,
            default_deadline=float(self.settings.api.ingest_deadline_seconds),
            exhausted_reason="ingest_capacity_exhausted",
        )

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

    def prepare_for_start(self) -> None:
        """Clear drain flags so a restarted runtime can admit again."""
        with self._idle:
            if self._active:
                raise RuntimeError("cannot prepare registry while operations are active")
            self._draining = False
            self.grace_exhausted = False

    def signal_shutdown(self) -> None:
        """Mark draining and cancel active ops. New admits fail closed."""
        with self._idle:
            self._draining = True
            handles = list(self._active.values())
        for handle in handles:
            handle.signal_cancel(CancelReason.SHUTDOWN)

    def wait_until_idle(self, timeout_seconds: float | None) -> bool:
        """Block until no active ops, or timeout. ``None`` waits indefinitely."""
        if timeout_seconds is None:
            with self._idle:
                while self._active:
                    self._idle.wait(timeout=0.05)
                return True
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        with self._idle:
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(timeout=min(0.05, remaining))
            return True
