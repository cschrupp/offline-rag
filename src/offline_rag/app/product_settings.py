"""Seneca product-managed generation settings store (Slice 16D-A).

Allowlisted generation-only overlay persisted under ``paths.product_settings``.
Not a generic AppSettings JSON injector.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.generation.openai_compatible import normalize_endpoint

SCHEMA_VERSION = "seneca-generation-settings-v1"
SETTINGS_FILENAME = "seneca-generation.json"

ApiKeyAction = Literal["keep", "set", "clear"]


class SenecaGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str
    model: str
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    api_key: str | None = None

    @field_validator("base_url", "model")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("must be non-empty")
        return text

    @field_validator("api_key")
    @classmethod
    def _normalize_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class SenecaGenerationSettingsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["seneca-generation-settings-v1"] = SCHEMA_VERSION
    generation: SenecaGenerationBody


def resolve_product_settings_dir(
    payload: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the durable product-settings directory from a partial payload."""
    del environ  # reserved; path already rebases via DATA_DIR in loader
    paths = payload.get("paths")
    if isinstance(paths, dict) and paths.get("product_settings"):
        return Path(str(paths["product_settings"]))
    return Path("data/settings")


def product_settings_path(root: Path) -> Path:
    return Path(root) / SETTINGS_FILENAME


def read_product_generation_settings(
    root: Path,
) -> SenecaGenerationSettingsFile | None:
    path = product_settings_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")
    return SenecaGenerationSettingsFile.model_validate(raw)


def generation_overlay_from_product_settings(root: Path) -> dict[str, Any]:
    """Return a deep-mergeable generation overlay, or ``{}`` when absent/invalid.

    Malformed files fail closed by raising; callers in ``load_settings`` treat
    that as ``ConfigError``.
    """
    try:
        record = read_product_generation_settings(root)
    except ValueError:
        raise
    if record is None:
        return {}
    body = record.generation
    try:
        normalized = normalize_endpoint(body.base_url)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("malformed_product_settings: invalid base_url") from exc
    overlay_generation: dict[str, Any] = {
        "enabled": body.enabled,
        "base_url": normalized,
        "model": body.model,
        "timeout_seconds": body.timeout_seconds,
        "approved_endpoints": [normalized],
        "approved_models": [body.model],
    }
    if body.api_key is not None:
        overlay_generation["api_key"] = body.api_key
    return {"generation": overlay_generation}


def _chmod_owner_only(path: Path, *, is_dir: bool) -> None:
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        # Best-effort on platforms that do not support POSIX modes.
        pass


def write_product_generation_settings(
    root: Path,
    record: SenecaGenerationSettingsFile,
) -> Path:
    """Atomically persist allowlisted generation settings with restrictive perms."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(root, is_dir=True)
    path = product_settings_path(root)
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


def build_validated_product_record(
    *,
    enabled: bool,
    base_url: str,
    model: str,
    timeout_seconds: int,
    api_key: str | None,
    strict_offline: bool,
) -> SenecaGenerationSettingsFile:
    """Validate candidate values and return a persistable record."""
    try:
        normalized = validate_endpoint_network_policy(
            base_url, strict_offline=strict_offline
        )
    except EndpointPolicyError as exc:
        raise ValueError(exc.reason) from exc
    body = SenecaGenerationBody(
        enabled=enabled,
        base_url=normalized,
        model=model.strip(),
        timeout_seconds=timeout_seconds,
        api_key=api_key,
    )
    return SenecaGenerationSettingsFile(generation=body)


# Environment keys that lock corresponding generation fields when set.
GENERATION_ENV_LOCKS: dict[str, str] = {
    "enabled": "",  # no dedicated env; never env-locked via this map alone
    "base_url": "OFFLINE_RAG_LLM_BASE_URL",
    "model": "OFFLINE_RAG_LLM_MODEL",
    "timeout_seconds": "OFFLINE_RAG_LLM_TIMEOUT_SECONDS",
    "api_key": "OFFLINE_RAG_LLM_API_KEY",
}


def generation_field_locks(
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """Return which generation Settings fields are operator-locked by env."""
    env = environ if environ is not None else os.environ
    locks = {
        "enabled": False,
        "base_url": bool(env.get("OFFLINE_RAG_LLM_BASE_URL")),
        "model": bool(env.get("OFFLINE_RAG_LLM_MODEL")),
        "timeout_seconds": bool(env.get("OFFLINE_RAG_LLM_TIMEOUT_SECONDS")),
        "api_key": bool(env.get("OFFLINE_RAG_LLM_API_KEY")),
    }
    # Approval-list env locks imply product cannot rewrite approvals via save.
    if env.get("OFFLINE_RAG_APPROVED_LLM_ENDPOINTS"):
        locks["base_url"] = True
    if env.get("OFFLINE_RAG_APPROVED_LLM_MODELS"):
        locks["model"] = True
    return locks


__all__ = [
    "SCHEMA_VERSION",
    "SETTINGS_FILENAME",
    "ApiKeyAction",
    "SenecaGenerationBody",
    "SenecaGenerationSettingsFile",
    "build_validated_product_record",
    "generation_field_locks",
    "generation_overlay_from_product_settings",
    "product_settings_path",
    "read_product_generation_settings",
    "resolve_product_settings_dir",
    "write_product_generation_settings",
]
