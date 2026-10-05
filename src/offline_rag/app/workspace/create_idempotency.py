"""Durable idempotency for workspace creation (S16-D14).

``ManagedOperationStore`` keys idempotency *inside* a workspace, which cannot
work for the request that creates one: the workspace id does not exist yet, so a
retried POST would allocate a second workspace.

This catalog closes that gap by reserving the workspace id under the client's
idempotency key *before* ``workspace.json`` is written. The ordering is what
makes a crash recoverable:

    reservation (id + canonical request)  ->  workspace.json

A retry after a crash in between finds the reservation, reuses the same
workspace id, and finishes the create. A retry with the same key but a different
title/description is a different request and fails closed.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import (
    canonical_request_fingerprint,
    new_workspace_id,
    utc_now,
)
from offline_rag.config.models import AppSettings

CREATE_RESERVATION_SCHEMA_VERSION = "offline-rag-workspace-create-reservation-v1"
CREATE_INDEX_DIRNAME = "_create_index"
MAX_IDEMPOTENCY_KEY_CHARS = 256


class WorkspaceCreateReservation(BaseModel):
    """Durable claim of one workspace id for one create request."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = CREATE_RESERVATION_SCHEMA_VERSION
    idempotency_key: str = Field(min_length=1, max_length=MAX_IDEMPOTENCY_KEY_CHARS)
    request_fingerprint: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4096)
    created_at: datetime


def create_request_fingerprint(*, title: str, description: str) -> str:
    """Canonical identity of a create request (title + description only)."""
    return canonical_request_fingerprint(
        {"kind": "workspace_create", "title": title, "description": description}
    )


def _validate_idempotency_key(idempotency_key: str) -> str:
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_required"),
        )
    text = idempotency_key.strip()
    if len(text) > MAX_IDEMPOTENCY_KEY_CHARS:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="idempotency_key_too_long"),
        )
    return text


class WorkspaceCreateCatalog:
    """Filesystem catalog of create reservations under the workspaces root."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.root = settings.paths.workspaces

    def index_dir(self) -> Path:
        return self.root / CREATE_INDEX_DIRNAME

    def reservation_path(self, idempotency_key: str) -> Path:
        key = _validate_idempotency_key(idempotency_key)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.index_dir() / f"crt_{digest}.json"

    def reserve(
        self, *, idempotency_key: str, title: str, description: str = ""
    ) -> tuple[WorkspaceCreateReservation, bool]:
        """Claim (or recover) a workspace id for this create request.

        Returns the reservation and whether it was newly allocated. Creation of
        the index entry is exclusive (``O_EXCL``), so two concurrent retries of
        the same key converge on one workspace id without a lease.
        """
        key = _validate_idempotency_key(idempotency_key)
        fingerprint = create_request_fingerprint(title=title, description=description)
        path = self.reservation_path(key)

        existing = self._read(path)
        if existing is not None:
            return self._assert_match(existing, fingerprint=fingerprint, key=key), False

        reservation = WorkspaceCreateReservation(
            idempotency_key=key,
            request_fingerprint=fingerprint,
            workspace_id=new_workspace_id(),
            title=title,
            description=description,
            created_at=utc_now(),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = reservation.model_dump_json().encode("utf-8")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            # Lost the race; the winner's reservation is authoritative.
            raced = self._read(path)
            if raced is None:
                raise AppError(
                    ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                    details=SafeErrorDetails(reason="create_index_unreadable"),
                ) from None
            return self._assert_match(raced, fingerprint=fingerprint, key=key), False
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        return reservation, True

    def get(self, idempotency_key: str) -> WorkspaceCreateReservation | None:
        return self._read(self.reservation_path(idempotency_key))

    @staticmethod
    def _assert_match(
        reservation: WorkspaceCreateReservation, *, fingerprint: str, key: str
    ) -> WorkspaceCreateReservation:
        if (
            reservation.request_fingerprint != fingerprint
            or reservation.idempotency_key != key
        ):
            raise AppError(
                ErrorCode.IDEMPOTENCY_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=reservation.workspace_id,
                    reason="create_identity_mismatch",
                ),
            )
        return reservation

    @staticmethod
    def _read(path: Path) -> WorkspaceCreateReservation | None:
        if not path.exists():
            return None
        try:
            return WorkspaceCreateReservation.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(reason="create_index_unreadable"),
            ) from exc
