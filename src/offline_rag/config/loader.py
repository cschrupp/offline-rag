"""Configuration loading with explicit precedence and no network access.

Precedence (later wins):
  built-in defaults < YAML < environment variables < explicit overrides
"""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import canonical_config_hash
from offline_rag.domain.evaluation import ExperimentConfig

ENV_PREFIX = "OFFLINE_RAG_"

# Nested field paths for direct environment overrides.
_ENV_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "STRICT_OFFLINE": ("project", "strict_offline"),
    "LLM_BASE_URL": ("generation", "base_url"),
    "LLM_MODEL": ("generation", "model"),
    "APPROVED_LLM_MODELS": ("generation", "approved_models"),
    "RAW_DATA": ("paths", "raw_data"),
    "MANIFESTS": ("paths", "manifests"),
    "PROCESSED": ("paths", "processed"),
    "QDRANT_DIR": ("paths", "qdrant_storage"),
    "MODELS_DIR": ("paths", "retrieval_models"),
    "EVAL_RESULTS": ("paths", "eval_results"),
    "LOG_LEVEL": ("logging", "level"),
    "LOG_STRUCTURED": ("logging", "structured"),
}


class ConfigError(ValueError):
    """Raised when configuration cannot be loaded or validated."""


def _deep_merge(base: MutableMapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _set_path(data: MutableMapping[str, Any], path: Sequence[str], value: Any) -> None:
    cursor: MutableMapping[str, Any] = data
    for part in path[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[path[-1]] = value


def _parse_env_value(raw: str) -> Any:
    lowered = raw.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    if "," in raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    try:
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return int(raw)
        return float(raw)
    except ValueError:
        return raw


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"configuration file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ConfigError(f"configuration root must be a mapping in {path}")
    return payload


def _apply_data_dir(data: MutableMapping[str, Any], data_dir: str) -> None:
    root = Path(data_dir)
    paths = data.setdefault("paths", {})
    if not isinstance(paths, dict):
        raise ConfigError("paths must be a mapping when applying OFFLINE_RAG_DATA_DIR")
    paths["raw_data"] = str(root / "raw")
    paths["manifests"] = str(root / "manifests")
    paths["processed"] = str(root / "processed")
    paths["qdrant_storage"] = str(root / "qdrant")
    paths["eval_results"] = str(root / "eval" / "results")


def env_overrides(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Translate OFFLINE_RAG_* environment variables into nested overrides."""
    env = environ if environ is not None else os.environ
    overrides: dict[str, Any] = {}

    data_dir = env.get(f"{ENV_PREFIX}DATA_DIR")
    if data_dir:
        _apply_data_dir(overrides, data_dir)

    for suffix, path in _ENV_FIELD_MAP.items():
        key = f"{ENV_PREFIX}{suffix}"
        if key not in env:
            continue
        _set_path(overrides, path, _parse_env_value(env[key]))
    return overrides


def load_settings(
    *,
    yaml_paths: Sequence[Path | str] | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> AppSettings:
    """Load and validate settings using documented precedence."""
    env = environ if environ is not None else os.environ
    payload: dict[str, Any] = AppSettings().model_dump(mode="python")

    if yaml_paths is None:
        configured = env.get(f"{ENV_PREFIX}CONFIG")
        paths: list[Path | str] = [Path(configured)] if configured else []
    else:
        paths = list(yaml_paths)

    for yaml_path in paths:
        payload = _deep_merge(payload, _load_yaml_file(Path(yaml_path)))

    payload = _deep_merge(payload, env_overrides(env))
    if overrides:
        payload = _deep_merge(payload, dict(overrides))

    try:
        return AppSettings.model_validate(payload)
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration: {exc}") from exc


def experiment_config_from_settings(settings: AppSettings) -> ExperimentConfig | None:
    """Build a domain ExperimentConfig when an experiment section is present."""
    if settings.experiment is None:
        return None
    canonical = settings.to_canonical_dict()
    config_hash = canonical_config_hash(canonical)
    return ExperimentConfig(
        experiment_id=config_hash,
        name=settings.experiment.name,
        config_hash=config_hash,
        parameters={
            "dense": canonical["dense"],
            "sparse": canonical["sparse"],
            "fusion": canonical["fusion"],
            "reranker": canonical["reranker"],
            "context": canonical["context"],
            "retrieval_recovery": canonical["retrieval_recovery"],
            "abstention": canonical["abstention"],
            "generation": {
                "enabled": canonical["generation"]["enabled"],
                "model": canonical["generation"]["model"],
                "temperature": canonical["generation"]["temperature"],
            },
        },
    )


__all__ = [
    "ConfigError",
    "env_overrides",
    "experiment_config_from_settings",
    "load_settings",
]
