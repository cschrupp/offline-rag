"""Process-scoped ingest-class capacity gate (Phase 15D / D18)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class IngestCapacityGate:
    """Fail-fast ingest admission: wait=0, no backlog.

    Process-scoped only. Query admission remains Phase 15F.
    """

    max_concurrent: int
    _semaphore: threading.BoundedSemaphore = field(init=False, repr=False)
    _held: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)

    @property
    def held(self) -> int:
        with self._lock:
            return self._held

    def try_acquire(self) -> bool:
        """Non-blocking acquire. False means service_overloaded."""
        acquired = self._semaphore.acquire(blocking=False)
        if acquired:
            with self._lock:
                self._held += 1
        return acquired

    def release(self) -> None:
        with self._lock:
            if self._held <= 0:
                raise RuntimeError("ingest capacity release without acquire")
            self._held -= 1
        self._semaphore.release()
