"""Gold-Lab-local nested staged-directory publication (not a global helper)."""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from offline_rag.app.gold_lab.errors import GoldLabError


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _fsync_file(path)
    fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def stage_nested_directory(
    destination: Path,
    populate: Callable[[Path], None],
) -> Path:
    """Populate a temporary sibling directory for later atomic promotion."""
    destination = Path(destination)
    if destination.exists():
        raise GoldLabError(
            "campaign_already_exists",
            f"destination already exists: {destination}",
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            suffix=f".{uuid.uuid4().hex}.tmp",
            dir=destination.parent,
        )
    )
    try:
        populate(tmp_dir)
        _fsync_tree(tmp_dir)
        return tmp_dir
    except Exception:
        _rmtree(tmp_dir)
        raise


def promote_staged_directory(tmp_dir: Path, destination: Path) -> None:
    """Atomically rename staged directory into a previously absent destination."""
    destination = Path(destination)
    tmp_dir = Path(tmp_dir)
    if destination.exists():
        raise GoldLabError(
            "campaign_already_exists",
            f"destination already exists: {destination}",
        )
    if not tmp_dir.is_dir():
        raise GoldLabError(
            "campaign_staging_missing",
            f"staged directory missing: {tmp_dir}",
        )
    os.replace(tmp_dir, destination)


def cleanup_staged_directory(tmp_dir: Path | None) -> None:
    if tmp_dir is not None:
        _rmtree(tmp_dir)


def atomic_publish_nested_directory(
    destination: Path,
    populate: Callable[[Path], None],
    *,
    preflight: Callable[[], None] | None = None,
) -> None:
    """Stage, optionally preflight, then promote (legacy helper).

    Prefer explicit stage + promote under held leases for campaign publication.
    """
    tmp_dir: Path | None = None
    try:
        tmp_dir = stage_nested_directory(destination, populate)
        if preflight is not None:
            preflight()
        promote_staged_directory(tmp_dir, destination)
        tmp_dir = None
    except Exception:
        cleanup_staged_directory(tmp_dir)
        raise
