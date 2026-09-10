"""Configuration loading and precedence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.config import (
    ConfigError,
    experiment_config_from_settings,
    load_settings,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_settings_validate() -> None:
    settings = load_settings(yaml_paths=[], environ={})
    assert settings.project.name == "offline-rag"
    assert settings.project.strict_offline is True


def test_load_base_yaml() -> None:
    settings = load_settings(yaml_paths=[REPO_ROOT / "config" / "base.yaml"], environ={})
    assert settings.paths.raw_data == Path("data/raw")
    assert settings.logging.structured is True
    assert settings.dense.top_k == 10
    assert settings.indexing.embedding.model_id == "Qwen/Qwen3-Embedding-0.6B"
    assert settings.indexing.embedding.revision == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"


def test_load_experiment_overlay() -> None:
    settings = load_settings(
        yaml_paths=[
            REPO_ROOT / "config" / "base.yaml",
            REPO_ROOT / "config" / "experiments" / "dense_baseline.yaml",
        ],
        environ={},
    )
    assert settings.experiment is not None
    assert settings.experiment.name == "dense_baseline"
    assert settings.dense.top_k == 10
    assert settings.sparse.enabled is False
    assert settings.generation.enabled is False
    experiment = experiment_config_from_settings(settings)
    assert experiment is not None
    assert experiment.name == "dense_baseline"
    assert experiment.config_hash.startswith("cfg_")


def test_environment_overrides_yaml(tmp_path: Path) -> None:
    settings = load_settings(
        yaml_paths=[REPO_ROOT / "config" / "base.yaml"],
        environ={
            "OFFLINE_RAG_STRICT_OFFLINE": "false",
            "OFFLINE_RAG_LLM_MODEL": "local-model",
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_APPROVED_LLM_MODELS": "a,b",
        },
    )
    assert settings.project.strict_offline is False
    assert settings.generation.model == "local-model"
    assert settings.paths.raw_data == tmp_path / "data" / "raw"
    assert settings.generation.approved_models == ["a", "b"]


def test_explicit_overrides_win() -> None:
    settings = load_settings(
        yaml_paths=[REPO_ROOT / "config" / "base.yaml"],
        environ={"OFFLINE_RAG_LLM_MODEL": "from-env"},
        overrides={"generation": {"model": "from-override"}},
    )
    assert settings.generation.model == "from-override"


def test_unknown_field_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("project:\n  name: offline-rag\n  unexpected: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid configuration"):
        load_settings(yaml_paths=[bad], environ={})


def test_malformed_yaml_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "broken.yaml"
    bad.write_text("project: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_settings(yaml_paths=[bad], environ={})


def test_missing_yaml_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(yaml_paths=[tmp_path / "missing.yaml"], environ={})
