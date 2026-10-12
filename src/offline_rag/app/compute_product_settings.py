"""Seneca product-managed compute settings store (Slice 16L).

Narrow allowlist: only ``embedding_device``. Not a generic indexing injector.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "seneca-compute-settings-v1"
SETTINGS_FILENAME = "seneca-compute.json"

EmbeddingDevicePolicy = Literal["auto", "cpu", "cuda"]


class SenecaComputeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_device: EmbeddingDevicePolicy = "auto"


class SenecaComputeSettingsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["seneca-compute-settings-v1"] = SCHEMA_VERSION
    compute: SenecaComputeBody


def compute_product_settings_path(root: Path) -> Path:
    return Path(root) / SETTINGS_FILENAME


def read_product_compute_settings(root: Path) -> SenecaComputeSettingsFile | None:
    path = compute_product_settings_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    return SenecaComputeSettingsFile.model_validate(raw)


def compute_overlay_from_product_settings(root: Path) -> dict[str, Any]:
    """Return a deep-mergeable indexing.embedding.device overlay, or ``{}``."""
    path = compute_product_settings_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    record = SenecaComputeSettingsFile.model_validate(raw)
    return {
        "indexing": {
            "embedding": {
                "device": record.compute.embedding_device,
            }
        }
    }


def _chmod_owner_only(path: Path, *, is_dir: bool) -> None:
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        pass


def write_product_compute_settings(
    root: Path, record: SenecaComputeSettingsFile
) -> Path:
    """Atomically persist allowlisted compute settings with restrictive perms."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(root, is_dir=True)
    path = compute_product_settings_path(root)
    payload = record.model_dump(mode="json")
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=root,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_owner_only(tmp_path, is_dir=False)
        tmp_path.replace(path)
        _chmod_owner_only(path, is_dir=False)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def compute_field_locks(
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """Return which Compute Settings fields are operator-locked by env."""
    env = environ if environ is not None else os.environ
    # Presence locks ownership even when empty — same pattern as authoring API key.
    return {"embedding_device": "OFFLINE_RAG_EMBEDDING_DEVICE" in env}


__all__ = [
    "SCHEMA_VERSION",
    "SETTINGS_FILENAME",
    "EmbeddingDevicePolicy",
    "SenecaComputeBody",
    "SenecaComputeSettingsFile",
    "compute_field_locks",
    "compute_overlay_from_product_settings",
    "compute_product_settings_path",
    "read_product_compute_settings",
    "write_product_compute_settings",
]
