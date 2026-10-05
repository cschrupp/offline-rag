"""Raw-source vault primitives under /data (Slice 16A)."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.workspace.models import content_sha256_hex, new_vault_object_id
from offline_rag.ingestion.io import atomic_write_bytes, atomic_write_text

VAULT_META_SCHEMA_VERSION = "offline-rag-vault-object-v1"
_OBJECT_ID_RE = re.compile(r"^vobj_[0-9a-f]{32}$")
_SAFE_DISPLAY_NAME_RE = re.compile(r"^[^/\\]{1,512}$")


class VaultObjectMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = VAULT_META_SCHEMA_VERSION
    object_id: str
    workspace_id: str
    display_name: str
    content_type: str | None = None
    byte_size: int = Field(ge=0)
    content_hash: str
    created_at: datetime

    @field_validator("object_id", "workspace_id", "content_hash", mode="before")
    @classmethod
    def _ids(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("identity must be non-empty")
        text = value.strip()
        if "/" in text or "\\" in text or ".." in text:
            raise ValueError("path elements forbidden")
        return text


def _validate_display_name(display_name: str) -> str:
    name = display_name.strip()
    if not name or not _SAFE_DISPLAY_NAME_RE.fullmatch(name):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_display_filename"),
        )
    if name in {".", ".."} or name.startswith(".") and name.count(".") == len(name):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="invalid_display_filename"),
        )
    # Reject absolute / traversal-looking names even if regex passed edge cases.
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="unsafe_display_filename"),
        )
    return name


class RawSourceVault:
    """Workspace-scoped private raw object store.

    Physical object identity is server-generated. Display filenames are metadata
    only and never control filesystem paths.
    """

    def __init__(self, workspaces_root: Path) -> None:
        self._root = workspaces_root

    def _workspace_vault_root(self, workspace_id: str) -> Path:
        if "/" in workspace_id or "\\" in workspace_id or ".." in workspace_id:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_workspace_id"),
            )
        return self._root / workspace_id / "vault"

    def _object_path(self, workspace_id: str, object_id: str) -> Path:
        if not _OBJECT_ID_RE.fullmatch(object_id):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_vault_object_id"),
            )
        return self._workspace_vault_root(workspace_id) / "objects" / object_id

    def _meta_path(self, workspace_id: str, object_id: str) -> Path:
        if not _OBJECT_ID_RE.fullmatch(object_id):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_vault_object_id"),
            )
        return self._workspace_vault_root(workspace_id) / "meta" / f"{object_id}.json"

    def put_bytes(
        self,
        workspace_id: str,
        data: bytes,
        *,
        display_name: str,
        content_type: str | None = None,
        object_id: str | None = None,
    ) -> VaultObjectMeta:
        display = _validate_display_name(display_name)
        oid = object_id or new_vault_object_id()
        if not _OBJECT_ID_RE.fullmatch(oid):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="invalid_vault_object_id"),
            )
        obj_path = self._object_path(workspace_id, oid)
        meta_path = self._meta_path(workspace_id, oid)
        if obj_path.exists() or meta_path.exists():
            raise AppError(
                ErrorCode.WORKSPACE_CONFLICT,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_object_exists"
                ),
            )
        digest = content_sha256_hex(data)
        meta = VaultObjectMeta(
            object_id=oid,
            workspace_id=workspace_id,
            display_name=display,
            content_type=content_type,
            byte_size=len(data),
            content_hash=digest,
            created_at=datetime.now(tz=UTC),
        )
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(obj_path, data)
        # Integrity check before meta commit.
        written = obj_path.read_bytes()
        if hashlib.sha256(written).hexdigest() != digest:
            obj_path.unlink(missing_ok=True)
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_write_corrupt"
                ),
            )
        atomic_write_text(meta_path, meta.model_dump_json())
        return meta

    def get_meta(self, workspace_id: str, object_id: str) -> VaultObjectMeta:
        meta_path = self._meta_path(workspace_id, object_id)
        if not meta_path.exists():
            raise AppError(
                ErrorCode.DOCUMENT_UNKNOWN,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_object_unknown"
                ),
            )
        try:
            return VaultObjectMeta.model_validate_json(
                meta_path.read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_meta_corrupt"
                ),
            ) from exc

    def load_bytes(self, workspace_id: str, object_id: str) -> bytes:
        meta = self.get_meta(workspace_id, object_id)
        obj_path = self._object_path(workspace_id, object_id)
        if not obj_path.exists():
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_object_missing"
                ),
            )
        data = obj_path.read_bytes()
        if content_sha256_hex(data) != meta.content_hash:
            raise AppError(
                ErrorCode.WORKSPACE_STATE_UNAVAILABLE,
                details=SafeErrorDetails(
                    workspace_id=workspace_id, reason="vault_object_hash_mismatch"
                ),
            )
        return data
