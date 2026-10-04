"""Storage-backed per-corpus mutation leases with live-owner semantics (D03/D15).

Mechanism: OS advisory exclusive ``fcntl.flock`` on a lock file under
``/data/locks``. Process death releases the flock automatically, so a
persistent lock *filename* does not mean busy. No PID records, no timeout
theft, and no global corpus mutation lock.
"""

from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Self

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.config.models import AppSettings


def corpus_lease_path(locks_root: Path, corpus_name: str) -> Path:
    """Return the coordination path for a validated logical corpus name."""
    name = validate_product_corpus_name(corpus_name)
    return locks_root / f"corpus.{name}.lock"


@dataclass
class CorpusMutationLease:
    """Exclusive live-owner mutation lease for one logical corpus."""

    settings: AppSettings
    corpus_name: str
    _path: Path = field(init=False, repr=False)
    _fd: int | None = field(default=None, init=False, repr=False)
    _held: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        name = validate_product_corpus_name(self.corpus_name)
        object.__setattr__(self, "corpus_name", name)
        self._path = corpus_lease_path(self.settings.paths.locks, name)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self) -> None:
        if self._held:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise AppError(
                ErrorCode.CORPUS_BUSY,
                details=SafeErrorDetails(corpus=self.corpus_name, reason="lease_held"),
            ) from exc
        self._fd = fd
        self._held = True

    def release(self) -> None:
        if not self._held or self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
            self._held = False

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
