"""Small cross-platform advisory file-lock operations used by storage leases."""

from __future__ import annotations

import errno
import os
import sys
import time

_WINDOWS_LOCK_LENGTH = 1
_WINDOWS_LOCK_CONTENTION = 33  # ERROR_LOCK_VIOLATION
_WINDOWS_RETRY_SECONDS = 0.05


def acquire_exclusive(fd: int, *, blocking: bool) -> None:
    """Acquire an exclusive OS lock on an already-open lease file.

    Locks are owned by the OS and released when the owning process exits. The
    Windows implementation retries nonblocking byte-range acquisition when
    ``blocking`` is true; it has no timeout and never treats elapsed time as
    permission to steal a live lock.
    """
    if sys.platform == "win32":
        _acquire_windows(fd, blocking=blocking)
        return

    import fcntl

    flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
    fcntl.flock(fd, flags)


def release_exclusive(fd: int) -> None:
    """Release an exclusive OS lock on an already-open lease file."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, _WINDOWS_LOCK_LENGTH)
        return

    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _acquire_windows(fd: int, *, blocking: bool) -> None:
    import msvcrt

    if os.fstat(fd).st_size < _WINDOWS_LOCK_LENGTH:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"\0")

    while True:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, _WINDOWS_LOCK_LENGTH)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) != _WINDOWS_LOCK_CONTENTION:
                raise
            if not blocking:
                raise BlockingIOError(
                    errno.EWOULDBLOCK, "lease is already held"
                ) from exc
            time.sleep(_WINDOWS_RETRY_SECONDS)
