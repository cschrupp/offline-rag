"""Ownership guard for workspace-managed backing corpora (S16-D08).

Standalone Slice-15 corpora remain freely mutable via ``POST /v1/ingest``.
A corpus whose name is the deterministic backing corpus of any ``ws_*`` catalog
directory must only be mutated through the workspace lifecycle authorization
path.

Directory identity alone reserves the ``wsc_*`` namespace: a missing or corrupt
``workspace.json`` fails closed rather than silently forgetting ownership.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import WorkspaceRecord, backing_corpus_name_for
from offline_rag.config.models import AppSettings


def find_workspace_id_for_backing_corpus(
    settings: AppSettings, corpus_name: str
) -> str | None:
    """Return the owning workspace id when ``corpus_name`` is workspace-backed.

    Raises ``WORKSPACE_STATE_UNAVAILABLE`` when a matching ``ws_*`` directory
    exists but its catalog record is missing, corrupt, or inconsistent — never
    treats that as "unowned".
    """
    root = settings.paths.workspaces
    if not root.exists():
        return None
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("ws_"):
            continue
        try:
            expected_corpus = backing_corpus_name_for(child.name)
        except AppError:
            continue
        if expected_corpus != corpus_name:
            continue
        # Directory identity reserves this backing corpus namespace.
        path = child / "workspace.json"
        if not path.is_file():
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=child.name,
                    corpus=corpus_name,
                    reason="workspace_ownership_record_missing",
                ),
            )
        try:
            record = WorkspaceRecord.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=child.name,
                    corpus=corpus_name,
                    reason="workspace_ownership_record_unreadable",
                ),
            ) from exc
        if (
            record.workspace_id != child.name
            or record.backing_corpus_name != expected_corpus
        ):
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=child.name,
                    corpus=corpus_name,
                    reason="workspace_ownership_record_inconsistent",
                ),
            )
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
    expected = backing_corpus_name_for(workspace_id)
    if corpus_name != expected:
        raise AppError(
            ErrorCode.WORKSPACE_CONFLICT,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                corpus=corpus_name,
                reason="workspace_corpus_mismatch",
            ),
        )
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
    if record.backing_corpus_name != corpus_name or record.workspace_id != workspace_id:
        raise AppError(
            ErrorCode.WORKSPACE_CONFLICT,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                corpus=corpus_name,
                reason="workspace_corpus_mismatch",
            ),
        )
