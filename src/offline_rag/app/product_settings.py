"""Seneca product-managed generation settings store (Slice 16D-A).

Allowlisted generation-only overlay persisted under ``paths.product_settings``.
Not a generic AppSettings JSON injector.

Selection fields (``base_url``, ``model``) are independently optional so the
product layer can own one without inventing approval for an operator-locked
counterpart.
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

SCHEMA_VERSION = "seneca-generation-settings-v1"
SETTINGS_FILENAME = "seneca-generation.json"

ApiKeyAction = Literal["keep", "set", "clear"]


class SenecaGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    api_key: str | None = None

    @field_validator("base_url", "model", mode="before")
    @classmethod
    def _optional_non_empty(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("must be a string or null")
        text = value.strip()
        if not text:
            raise ValueError("must be non-empty when present")
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
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    return SenecaGenerationSettingsFile.model_validate(raw)


def generation_overlay_from_product_settings(
    root: Path,
    *,
    strict_offline: bool,
) -> dict[str, Any]:
    """Return a deep-mergeable generation overlay, or ``{}`` when absent.

    Malformed files and strict-offline policy violations fail closed by raising;
    callers in ``load_settings`` treat that as ``ConfigError``.

    Field ownership:
    - omitted ``base_url`` / ``model`` → product does not own that selection
      (and does not inject the matching approval list)
    - present ``base_url`` / ``model`` → product owns selection + matching approval
    - omitted ``api_key`` → do not override lower-priority YAML
    - present ``api_key`` (including JSON null) → product owns the key
    """
    path = product_settings_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    record = SenecaGenerationSettingsFile.model_validate(raw)
    body = record.generation
    overlay_generation: dict[str, Any] = {
        "enabled": body.enabled,
        "timeout_seconds": body.timeout_seconds,
    }
    if body.base_url is not None:
        try:
            normalized = validate_endpoint_network_policy(
                body.base_url, strict_offline=strict_offline
            )
        except EndpointPolicyError as exc:
            raise ValueError(
                f"malformed_product_settings: endpoint_policy:{exc.reason}"
            ) from exc
        overlay_generation["base_url"] = normalized
        overlay_generation["approved_endpoints"] = [normalized]
    if body.model is not None:
        overlay_generation["model"] = body.model
        overlay_generation["approved_models"] = [body.model]
    raw_generation = raw.get("generation")
    if isinstance(raw_generation, dict) and "api_key" in raw_generation:
        overlay_generation["api_key"] = body.api_key
    return {"generation": overlay_generation}


def _chmod_owner_only(path: Path, *, is_dir: bool) -> None:
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        # Best-effort on platforms that do not support POSIX modes.
        pass


def product_api_key_is_managed(root: Path) -> bool:
    """Return whether the product file explicitly owns the API-key field."""
    path = product_settings_path(root)
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    generation = raw.get("generation")
    return isinstance(generation, dict) and "api_key" in generation


def write_product_generation_settings(
    root: Path,
    record: SenecaGenerationSettingsFile,
    *,
    manage_api_key: bool = False,
) -> Path:
    """Atomically persist allowlisted generation settings with restrictive perms.

    When ``manage_api_key`` is False, omit ``api_key`` from the durable file so
    lower-priority YAML keys remain effective. When True, persist the key
    (including JSON null for an explicit clear).

    ``base_url`` / ``model`` are omitted from the durable file when null so the
    product layer does not claim selection/approval for operator-owned fields.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(root, is_dir=True)
    path = product_settings_path(root)
    payload = record.model_dump(mode="json")
    generation = payload.get("generation")
    if isinstance(generation, dict):
        if generation.get("base_url") is None:
            generation.pop("base_url", None)
        if generation.get("model") is None:
            generation.pop("model", None)
        if not manage_api_key:
            generation.pop("api_key", None)
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
    base_url: str | None,
    model: str | None,
    timeout_seconds: int,
    api_key: str | None,
    strict_offline: bool,
) -> SenecaGenerationSettingsFile:
    """Validate candidate values and return a persistable record.

    ``base_url`` / ``model`` may be None when the product layer does not own
    that selection (operator lock). Present endpoint values are still checked
    against the network policy.
    """
    normalized: str | None = None
    if base_url is not None:
        try:
            normalized = validate_endpoint_network_policy(
                base_url, strict_offline=strict_offline
            )
        except EndpointPolicyError as exc:
            raise ValueError(exc.reason) from exc
    body = SenecaGenerationBody(
        enabled=enabled,
        base_url=normalized,
        model=None if model is None else model.strip(),
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
    "product_api_key_is_managed",
    "product_settings_path",
    "read_product_generation_settings",
    "resolve_product_settings_dir",
    "write_product_generation_settings",
]
