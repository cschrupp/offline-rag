"""Private operation-bound staging for Gold Lab baseline bootstrap."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from offline_rag.config.models import AppSettings


def bootstrap_staging_root(settings: AppSettings) -> Path:
    return settings.paths.staging / "gold-bootstrap"


def bootstrap_staging_dir(
    settings: AppSettings, *, workspace_id: str, operation_id: str
) -> Path:
    return bootstrap_staging_root(settings) / workspace_id / operation_id


def bootstrap_staging_run_path(
    settings: AppSettings, *, workspace_id: str, operation_id: str
) -> Path:
    return (
        bootstrap_staging_dir(
            settings, workspace_id=workspace_id, operation_id=operation_id
        )
        / "authoring_run.json"
    )


def ensure_bootstrap_staging_dir(
    settings: AppSettings, *, workspace_id: str, operation_id: str
) -> Path:
    path = bootstrap_staging_dir(
        settings, workspace_id=workspace_id, operation_id=operation_id
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_bootstrap_staging(
    settings: AppSettings, *, workspace_id: str, operation_id: str
) -> None:
    path = bootstrap_staging_dir(
        settings, workspace_id=workspace_id, operation_id=operation_id
    )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def scavenge_bootstrap_staging(
    settings: AppSettings, *, retention_hours: int | None = None
) -> list[str]:
    """Delete terminal-age staging trees older than retention TTL.

    Does not inspect ManagedOperation state; deletes by directory mtime only
    when older than TTL. Safe because staging is never scientific authority.
    """
    hours = (
        int(settings.api.gold_bootstrap_staging_retention_hours)
        if retention_hours is None
        else int(retention_hours)
    )
    root = bootstrap_staging_root(settings)
    if not root.is_dir():
        return []
    cutoff = time.time() - (hours * 3600)
    removed: list[str] = []
    for workspace_dir in root.iterdir():
        if not workspace_dir.is_dir():
            continue
        for op_dir in workspace_dir.iterdir():
            if not op_dir.is_dir():
                continue
            try:
                mtime = op_dir.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                shutil.rmtree(op_dir, ignore_errors=True)
                removed.append(str(op_dir))
    return removed


def cleanup_workspace_bootstrap_staging(
    settings: AppSettings, *, workspace_id: str, keep_operation_id: str | None = None
) -> None:
    """Best-effort remove prior staging for a workspace (never reuse)."""
    root = bootstrap_staging_root(settings) / workspace_id
    if not root.is_dir():
        return
    for op_dir in root.iterdir():
        if not op_dir.is_dir():
            continue
        if keep_operation_id is not None and op_dir.name == keep_operation_id:
            continue
        shutil.rmtree(op_dir, ignore_errors=True)
