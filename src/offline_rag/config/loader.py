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
    "LLM_TIMEOUT_SECONDS": ("generation", "timeout_seconds"),
    "LLM_API_KEY": ("generation", "api_key"),
    "APPROVED_LLM_MODELS": ("generation", "approved_models"),
    "APPROVED_LLM_ENDPOINTS": ("generation", "approved_endpoints"),
    "AUTHORING_ENABLED": ("authoring", "enabled"),
    "AUTHORING_PROVIDER": ("authoring", "provider"),
    "AUTHORING_ADAPTER_CONTRACT": ("authoring", "adapter_contract"),
    "AUTHORING_BASE_URL": ("authoring", "base_url"),
    "AUTHORING_MODEL": ("authoring", "model"),
    "AUTHORING_API_KEY": ("authoring", "api_key"),
    "AUTHORING_NETWORK_POLICY": ("authoring", "network_policy"),
    "AUTHORING_TEMPERATURE": ("authoring", "temperature"),
    "AUTHORING_MAX_OUTPUT_TOKENS": ("authoring", "max_output_tokens"),
    "AUTHORING_TIMEOUT_SECONDS": ("authoring", "timeout_seconds"),
    "AUTHORING_APPROVED_ENDPOINTS": ("authoring", "approved_endpoints"),
    "AUTHORING_APPROVED_MODELS": ("authoring", "approved_models"),
    "RAW_DATA": ("paths", "raw_data"),
    "MANIFESTS": ("paths", "manifests"),
    "PROCESSED": ("paths", "processed"),
    "CORPORA": ("paths", "corpora"),
    "CHUNKS": ("paths", "chunks"),
    "CHUNK_MANIFESTS": ("paths", "chunk_manifests"),
    "EMBEDDINGS": ("paths", "embeddings"),
    "INDEX_MANIFESTS": ("paths", "index_manifests"),
    "LEXICAL_INDEXES": ("paths", "lexical_indexes"),
    "LEXICAL_INDEX_MANIFESTS": ("paths", "lexical_index_manifests"),
    "QDRANT_DIR": ("paths", "qdrant_storage"),
    "MODELS_DIR": ("paths", "retrieval_models"),
    "DOCLING_ARTIFACTS_PATH": ("paths", "docling_artifacts"),
    "TOKENIZER_ARTIFACTS_PATH": ("paths", "tokenizer_artifacts"),
    "EMBEDDING_ARTIFACTS_PATH": ("paths", "embedding_artifacts"),
    "RERANKER_ARTIFACTS_PATH": ("paths", "reranker_artifacts"),
    "EVAL_RESULTS": ("paths", "eval_results"),
    "LOG_LEVEL": ("logging", "level"),
    "LOG_STRUCTURED": ("logging", "structured"),
    "PDF_OCR_ENABLED": ("parsing", "pdf", "ocr_enabled"),
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


def _coerce_list_env_fields(overrides: MutableMapping[str, Any]) -> None:
    """Ensure comma-oriented env list fields remain lists for single values."""
    for section_name in ("generation", "authoring"):
        section = overrides.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in ("approved_models", "approved_endpoints"):
            value = section.get(key)
            if isinstance(value, str):
                section[key] = [value]


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
    paths["corpora"] = str(root / "corpora")
    paths["chunks"] = str(root / "chunks")
    paths["chunk_manifests"] = str(root / "chunk-manifests")
    paths["embeddings"] = str(root / "embeddings")
    paths["index_manifests"] = str(root / "index-manifests")
    paths["lexical_indexes"] = str(root / "lexical-indexes")
    paths["lexical_index_manifests"] = str(root / "lexical-index-manifests")
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


def _reject_legacy_sparse_config(payload: Mapping[str, Any]) -> None:
    """Fail closed on renamed sparse: config (no silent alias)."""
    if "sparse" not in payload:
        return
    if "lexical" in payload:
        raise ConfigError(
            'Configuration keys "sparse" and "lexical" must not both be present. '
            'Remove "sparse:" and keep only "lexical:".'
        )
    raise ConfigError(
        'Configuration key "sparse" has been renamed to "lexical".\n'
        "Replace:\n\n"
        "  sparse:\n\n"
        "with:\n\n"
        "  lexical:"
    )


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
        overlay = _load_yaml_file(Path(yaml_path))
        _reject_legacy_sparse_config(overlay)
        payload = _deep_merge(payload, overlay)

    env_payload = env_overrides(env)
    _coerce_list_env_fields(env_payload)
    _reject_legacy_sparse_config(env_payload)
    payload = _deep_merge(payload, env_payload)
    if overrides:
        override_payload = dict(overrides)
        _reject_legacy_sparse_config(override_payload)
        payload = _deep_merge(payload, override_payload)

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
            "lexical": canonical["lexical"],
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


def load_dotenv(path: Path | None = None, *, environ: MutableMapping[str, str] | None = None) -> Path | None:
    """Load KEY=VALUE pairs from a local ``.env`` into the process environment.

    Existing environment variables win (are not overwritten). Returns the path
    loaded, or ``None`` when the file is absent.
    """
    env_path = Path(path) if path is not None else Path.cwd() / ".env"
    if not env_path.is_file():
        return None
    target: MutableMapping[str, str] = environ if environ is not None else os.environ
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in target:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target[key] = value
    return env_path


__all__ = [
    "ConfigError",
    "env_overrides",
    "experiment_config_from_settings",
    "load_dotenv",
    "load_settings",
]
