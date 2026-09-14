"""Atomic filesystem helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes via temp file + rename into ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_publish_directory(destination: Path, files: dict[str, str]) -> None:
    """Publish a directory of text files as one logical artifact.

    Writes into a temporary sibling directory, then replaces ``destination``
    via ``os.replace``. On failure the previous destination (if any) is left
    intact.
    """
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
    )
    try:
        for name, text in files.items():
            if "/" in name or "\\" in name or name in {".", ".."}:
                raise ValueError(f"invalid publish filename: {name!r}")
            target = tmp_dir / name
            target.write_text(text, encoding="utf-8")
            with target.open("rb") as handle:
                os.fsync(handle.fileno())
        if destination.exists():
            backup = Path(
                tempfile.mkdtemp(
                    prefix=f".{destination.name}.bak.",
                    suffix=".tmp",
                    dir=destination.parent,
                )
            )
            # Move existing aside, then promote tmp, then remove backup.
            os.replace(destination, backup)
            try:
                os.replace(tmp_dir, destination)
            except Exception:
                os.replace(backup, destination)
                raise
            _rmtree(backup)
        else:
            os.replace(tmp_dir, destination)
    except Exception:
        _rmtree(tmp_dir)
        raise


def _rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
