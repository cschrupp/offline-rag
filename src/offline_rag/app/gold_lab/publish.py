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
    # Best-effort directory fsync after file contents.
    fd = os.open(root, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def atomic_publish_nested_directory(
    destination: Path,
    populate: Callable[[Path], None],
    *,
    preflight: Callable[[], None] | None = None,
) -> None:
    """Publish a nested directory tree into a previously absent destination.

    Writes into a temporary sibling, optionally runs ``preflight`` immediately
    before promotion, then ``os.replace`` into ``destination``. Existing
    destinations are never overwritten. Crash/failure before promotion leaves
    no committed destination.
    """
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
        if preflight is not None:
            preflight()
        if destination.exists():
            raise GoldLabError(
                "campaign_already_exists",
                f"destination already exists: {destination}",
            )
        os.replace(tmp_dir, destination)
    except Exception:
        _rmtree(tmp_dir)
        raise
