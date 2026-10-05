"""Ownership guard for workspace-managed backing corpora (S16-D08).

Standalone Slice-15 corpora remain freely mutable via ``POST /v1/ingest``.
A corpus that is the durable backing corpus of any workspace catalog record
must only be mutated through the workspace lifecycle authorization path.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import WorkspaceRecord
from offline_rag.config.models import AppSettings


def find_workspace_id_for_backing_corpus(
    settings: AppSettings, corpus_name: str
) -> str | None:
    """Return the owning workspace id when ``corpus_name`` is workspace-backed."""
    root = settings.paths.workspaces
    if not root.exists():
        return None
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("ws_"):
            continue
        path = child / "workspace.json"
        if not path.is_file():
            continue
        try:
            record = WorkspaceRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError):
            continue
        if record.backing_corpus_name == corpus_name:
            return record.workspace_id
    return None


def assert_legacy_ingest_allowed(settings: AppSettings, corpus_name: str) -> None:
    """Fail closed when a legacy product ingest targets a workspace corpus."""
    owner = find_workspace_id_for_backing_corpus(settings, corpus_name)
    if owner is None:
        return
    raise AppError(
        ErrorCode.WORKSPACE_CONFLICT,
        details=SafeErrorDetails(
            workspace_id=owner,
            corpus=corpus_name,
            reason="workspace_managed_corpus",
        ),
    )


def assert_authorized_workspace_corpus(
    settings: AppSettings,
    corpus_name: str,
    *,
    workspace_id: str,
) -> None:
    """Allow lifecycle ingest only for the caller's own backing corpus."""
    path = Path(settings.paths.workspaces) / workspace_id / "workspace.json"
    if not path.is_file():
        raise AppError(
            ErrorCode.WORKSPACE_UNKNOWN,
            details=SafeErrorDetails(workspace_id=workspace_id),
        )
    try:
        record = WorkspaceRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise AppError(
            ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
            details=SafeErrorDetails(
                workspace_id=workspace_id, reason="workspace_state_unreadable"
            ),
        ) from exc
    if record.backing_corpus_name != corpus_name:
        raise AppError(
            ErrorCode.WORKSPACE_CONFLICT,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                corpus=corpus_name,
                reason="workspace_corpus_mismatch",
            ),
        )
