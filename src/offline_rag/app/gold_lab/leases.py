"""Gold Lab-scoped live-owner leases (fcntl.flock; no PID authority)."""

from __future__ import annotations

import fcntl
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Self

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    validate_campaign_id,
    validate_dataset_id,
    validate_project_id,
)
from offline_rag.config.models import AppSettings


def gold_lab_project_lease_path(locks_root: Path, project_id: str) -> Path:
    pid = validate_project_id(project_id)
    return locks_root / f"goldlab.project.{pid}.lock"


def gold_lab_campaign_lease_path(locks_root: Path, campaign_id: str) -> Path:
    cid = validate_campaign_id(campaign_id)
    return locks_root / f"goldlab.campaign.{cid}.lock"


def gold_lab_dataset_lease_path(locks_root: Path, dataset_id: str) -> Path:
    did = validate_dataset_id(dataset_id)
    return locks_root / f"goldlab.dataset.{did}.lock"


@dataclass
class GoldLabProjectLease:
    """Exclusive live-owner lease for one Gold project."""

    settings: AppSettings
    project_id: str
    _path: Path = field(init=False, repr=False)
    _fd: int | None = field(default=None, init=False, repr=False)
    _held: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        pid = validate_project_id(self.project_id)
        object.__setattr__(self, "project_id", pid)
        self._path = gold_lab_project_lease_path(self.settings.paths.locks, pid)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self, *, blocking: bool = False) -> None:
        if self._held:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            os.close(fd)
            raise GoldLabError(
                "gold_lab_lease_held",
                f"project lease held: {self.project_id}",
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


@dataclass
class GoldLabCampaignLease:
    """Exclusive live-owner lease for one Gold campaign (ledger append)."""

    settings: AppSettings
    campaign_id: str
    _path: Path = field(init=False, repr=False)
    _fd: int | None = field(default=None, init=False, repr=False)
    _held: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        cid = validate_campaign_id(self.campaign_id)
        object.__setattr__(self, "campaign_id", cid)
        self._path = gold_lab_campaign_lease_path(self.settings.paths.locks, cid)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self, *, blocking: bool = False) -> None:
        if self._held:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            os.close(fd)
            raise GoldLabError(
                "gold_lab_lease_held",
                f"campaign lease held: {self.campaign_id}",
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


@dataclass
class GoldLabDatasetLease:
    """Exclusive live-owner lease for one Gold Lab canonical dataset_id."""

    settings: AppSettings
    dataset_id: str
    _path: Path = field(init=False, repr=False)
    _fd: int | None = field(default=None, init=False, repr=False)
    _held: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        did = validate_dataset_id(self.dataset_id)
        object.__setattr__(self, "dataset_id", did)
        self._path = gold_lab_dataset_lease_path(self.settings.paths.locks, did)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self, *, blocking: bool = False) -> None:
        if self._held:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            os.close(fd)
            raise GoldLabError(
                "gold_lab_lease_held",
                f"dataset lease held: {self.dataset_id}",
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
