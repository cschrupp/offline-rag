"""Seneca product-managed Gold authoring settings store.

Independent of generation product settings. Allowlisted authoring-only overlay
persisted under ``paths.product_settings`` as ``seneca-authoring.json``.
Not a generic AppSettings JSON injector.
"""

from __future__ import annotations

import ipaddress
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.app.product_settings import resolve_product_settings_dir
from offline_rag.generation.openai_compatible import normalize_endpoint

SCHEMA_VERSION = "seneca-authoring-settings-v1"
SETTINGS_FILENAME = "seneca-authoring.json"

ApiKeyAction = Literal["keep", "set", "clear"]
NetworkPolicy = Literal["localhost_only", "private_network"]

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "host.docker.internal"})


class SenecaAuthoringBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    base_url: str | None = None
    model: str | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    api_key: str | None = None
    network_policy: NetworkPolicy | None = None

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


class SenecaAuthoringSettingsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["seneca-authoring-settings-v1"] = SCHEMA_VERSION
    authoring: SenecaAuthoringBody


def authoring_product_settings_path(root: Path) -> Path:
    return Path(root) / SETTINGS_FILENAME


def infer_authoring_network_policy(base_url: str) -> NetworkPolicy:
    """Derive product network_policy from a candidate endpoint host."""
    try:
        normalized = normalize_endpoint(base_url)
    except Exception as exc:
        raise ValueError("malformed_endpoint") from exc
    host = (urlparse(normalized).hostname or "").strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host in _LOOPBACK_HOSTS:
        return "localhost_only"
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        # Arbitrary DNS hostnames are not product-managed private endpoints.
        raise ValueError("public_endpoint_forbidden") from exc
    if addr.is_loopback:
        return "localhost_only"
    if addr.is_private or addr.is_link_local:
        return "private_network"
    raise ValueError("public_endpoint_forbidden")


def read_product_authoring_settings(
    root: Path,
) -> SenecaAuthoringSettingsFile | None:
    path = authoring_product_settings_path(root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    return SenecaAuthoringSettingsFile.model_validate(raw)


def authoring_overlay_from_product_settings(
    root: Path,
    *,
    strict_offline: bool,
) -> dict[str, Any]:
    """Return a deep-mergeable authoring overlay, or ``{}`` when absent."""
    path = authoring_product_settings_path(root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed_product_settings: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("malformed_product_settings: root must be object")  # noqa: TRY004
    record = SenecaAuthoringSettingsFile.model_validate(raw)
    body = record.authoring
    overlay_authoring: dict[str, Any] = {
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
        overlay_authoring["base_url"] = normalized
        overlay_authoring["approved_endpoints"] = [normalized]
        if body.network_policy is not None:
            overlay_authoring["network_policy"] = body.network_policy
        else:
            try:
                overlay_authoring["network_policy"] = infer_authoring_network_policy(
                    normalized
                )
            except ValueError as exc:
                raise ValueError(
                    f"malformed_product_settings: network_policy:{exc}"
                ) from exc
    elif body.network_policy is not None:
        overlay_authoring["network_policy"] = body.network_policy
    if body.model is not None:
        overlay_authoring["model"] = body.model
        overlay_authoring["approved_models"] = [body.model]
    raw_authoring = raw.get("authoring")
    if isinstance(raw_authoring, dict) and "api_key" in raw_authoring:
        overlay_authoring["api_key"] = body.api_key
    return {"authoring": overlay_authoring}


def _chmod_owner_only(path: Path, *, is_dir: bool) -> None:
    try:
        path.chmod(0o700 if is_dir else 0o600)
    except OSError:
        pass


def authoring_api_key_is_managed(root: Path) -> bool:
    path = authoring_product_settings_path(root)
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return False
    if not isinstance(raw, dict):
        return False
    authoring = raw.get("authoring")
    return isinstance(authoring, dict) and "api_key" in authoring


def write_product_authoring_settings(
    root: Path,
    record: SenecaAuthoringSettingsFile,
    *,
    manage_api_key: bool = False,
) -> Path:
    """Atomically persist allowlisted authoring settings with restrictive perms."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _chmod_owner_only(root, is_dir=True)
    path = authoring_product_settings_path(root)
    payload = record.model_dump(mode="json")
    authoring = payload.get("authoring")
    if isinstance(authoring, dict):
        if authoring.get("base_url") is None:
            authoring.pop("base_url", None)
        if authoring.get("model") is None:
            authoring.pop("model", None)
        if authoring.get("network_policy") is None:
            authoring.pop("network_policy", None)
        if not manage_api_key:
            authoring.pop("api_key", None)
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


def build_validated_authoring_product_record(
    *,
    enabled: bool,
    base_url: str | None,
    model: str | None,
    timeout_seconds: int,
    api_key: str | None,
    network_policy: NetworkPolicy | None,
    strict_offline: bool,
) -> SenecaAuthoringSettingsFile:
    """Validate candidate values and return a persistable authoring record."""
    normalized: str | None = None
    resolved_policy = network_policy
    if base_url is not None:
        try:
            normalized = validate_endpoint_network_policy(
                base_url, strict_offline=strict_offline
            )
        except EndpointPolicyError as exc:
            raise ValueError(exc.reason) from exc
        if resolved_policy is None:
            try:
                resolved_policy = infer_authoring_network_policy(normalized)
            except ValueError as exc:
                raise ValueError(str(exc)) from exc
    body = SenecaAuthoringBody(
        enabled=enabled,
        base_url=normalized,
        model=None if model is None else model.strip(),
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        network_policy=resolved_policy,
    )
    return SenecaAuthoringSettingsFile(authoring=body)


def authoring_field_locks(
    environ: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """Return which authoring Settings fields are operator-locked by env."""
    env = environ if environ is not None else os.environ
    locks = {
        "enabled": bool(env.get("OFFLINE_RAG_AUTHORING_ENABLED")),
        "base_url": bool(env.get("OFFLINE_RAG_AUTHORING_BASE_URL")),
        "model": bool(env.get("OFFLINE_RAG_AUTHORING_MODEL")),
        "timeout_seconds": bool(env.get("OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS")),
        "api_key": bool(env.get("OFFLINE_RAG_AUTHORING_API_KEY")),
        "network_policy": bool(env.get("OFFLINE_RAG_AUTHORING_NETWORK_POLICY")),
    }
    if env.get("OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS"):
        locks["base_url"] = True
    if env.get("OFFLINE_RAG_AUTHORING_APPROVED_MODELS"):
        locks["model"] = True
    return locks


__all__ = [
    "SCHEMA_VERSION",
    "SETTINGS_FILENAME",
    "ApiKeyAction",
    "NetworkPolicy",
    "SenecaAuthoringBody",
    "SenecaAuthoringSettingsFile",
    "authoring_api_key_is_managed",
    "authoring_field_locks",
    "authoring_overlay_from_product_settings",
    "authoring_product_settings_path",
    "build_validated_authoring_product_record",
    "infer_authoring_network_policy",
    "read_product_authoring_settings",
    "resolve_product_settings_dir",
    "write_product_authoring_settings",
]
