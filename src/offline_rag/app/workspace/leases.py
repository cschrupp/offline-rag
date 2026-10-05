"""Workspace-scoped live-owner mutation leases (Slice 16A).

Mechanism mirrors ``CorpusMutationLease``: OS advisory exclusive ``fcntl.flock``
on ``/data/locks/workspace.<workspace_id>.lock``. Process death releases the
flock automatically. A persistent lock *filename* alone does not imply busy.
No PID records, no timeout theft.

Global acquisition order (frozen for 16B when both are required):

    workspace lease → corpus lease

Never acquire in the opposite order (avoids cross-resource deadlocks).
"""

from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Self

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.config.models import AppSettings


def workspace_lease_path(locks_root: Path, workspace_id: str) -> Path:
    if (
        not workspace_id
        or "/" in workspace_id
        or "\\" in workspace_id
        or ".." in workspace_id
        or not workspace_id.startswith("ws_")
    ):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_workspace_id"),
        )
    return locks_root / f"workspace.{workspace_id}.lock"


@dataclass
class WorkspaceMutationLease:
    """Exclusive live-owner mutation lease for one workspace."""

    settings: AppSettings
    workspace_id: str
    _path: Path = field(init=False, repr=False)
    _fd: int | None = field(default=None, init=False, repr=False)
    _held: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._path = workspace_lease_path(self.settings.paths.locks, self.workspace_id)

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
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=self.workspace_id, reason="lease_held"
                ),
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
