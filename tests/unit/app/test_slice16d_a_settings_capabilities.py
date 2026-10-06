"""Slice 16D-A — capabilities, product settings precedence, endpoint policy."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.endpoint_policy import (
    EndpointPolicyError,
    validate_endpoint_network_policy,
)
from offline_rag.app.product_settings import (
    SenecaGenerationBody,
    SenecaGenerationSettingsFile,
    generation_overlay_from_product_settings,
    read_product_generation_settings,
    write_product_generation_settings,
)
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import ConfigError, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.protocol import GeneratorProbeResult
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_YAML = REPO_ROOT / "config" / "base.yaml"
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


class _Closeable:
    def close(self) -> None:
        return None


def _provision_assets(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    import shutil

    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _settings(
    tmp_path: Path,
    *,
    environ: dict[str, str] | None = None,
    yaml_paths: list[Path] | None = None,
) -> AppSettings:
    env = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        **(environ or {}),
    }
    settings = load_settings(
        yaml_paths=yaml_paths if yaml_paths is not None else [BASE_YAML],
        environ=env,
    )
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    settings = settings.model_copy(
        update={
            "generation": generation,
            "reranker": settings.reranker.model_copy(update={"enabled": False}),
        }
    )
    _provision_assets(settings)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _client(settings: AppSettings) -> TestClient:
    return TestClient(create_app(runtime=_runtime(settings)))


def test_base_yaml_exposes_capacity_defaults() -> None:
    payload = yaml.safe_load(BASE_YAML.read_text(encoding="utf-8"))
    api = payload["api"]
    assert api["max_files_per_ingest"] == 32
    assert api["max_bytes_per_document"] == 26_214_400
    assert api["max_total_upload_bytes"] == 104_857_600
    assert payload["paths"]["product_settings"] == "data/settings"


def test_env_capacity_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_MAX_FILES_PER_INGEST": "7",
            "OFFLINE_RAG_MAX_BYTES_PER_DOCUMENT": "1048576",
            "OFFLINE_RAG_MAX_TOTAL_UPLOAD_BYTES": "2097152",
        },
    )
    assert settings.api.max_files_per_ingest == 7
    assert settings.api.max_bytes_per_document == 1_048_576
    assert settings.api.max_total_upload_bytes == 2_097_152


def test_product_settings_precede_yaml_but_lose_to_env(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    product_dir = data_dir / "settings"
    write_product_generation_settings(
        product_dir,
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                enabled=True,
                base_url="http://10.0.0.5:11434/v1",
                model="product-model",
                timeout_seconds=90,
                api_key="product-secret",
            )
        ),
    )
    # YAML defaults + product overlay, no LLM env.
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
        },
    )
    assert settings.generation.base_url == "http://10.0.0.5:11434/v1"
    assert settings.generation.model == "product-model"
    assert settings.generation.timeout_seconds == 90
    assert settings.generation.api_key == "product-secret"
    assert settings.generation.approved_endpoints == ["http://10.0.0.5:11434/v1"]
    assert settings.generation.approved_models == ["product-model"]

    # Env wins over product; product approvals must not silently approve env endpoint.
    shadowed = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
            "OFFLINE_RAG_LLM_BASE_URL": "http://127.0.0.1:9999/v1",
            "OFFLINE_RAG_LLM_MODEL": "env-model",
        },
    )
    assert shadowed.generation.base_url == "http://127.0.0.1:9999/v1"
    assert shadowed.generation.model == "env-model"
    assert shadowed.generation.approved_endpoints == ["http://10.0.0.5:11434/v1"]
    assert shadowed.generation.approved_models == ["product-model"]


def test_product_overlay_generation_only(tmp_path: Path) -> None:
    root = tmp_path / "settings"
    write_product_generation_settings(
        root,
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://127.0.0.1:11434/v1",
                model="m",
            )
        ),
    )
    overlay = generation_overlay_from_product_settings(root)
    assert set(overlay.keys()) == {"generation"}
    assert set(overlay["generation"].keys()) <= {
        "enabled",
        "base_url",
        "model",
        "timeout_seconds",
        "api_key",
        "approved_endpoints",
        "approved_models",
    }


def test_malformed_product_file_fails_closed(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root = data_dir / "settings"
    root.mkdir(parents=True)
    (root / "seneca-generation.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(
            yaml_paths=[BASE_YAML],
            environ={"OFFLINE_RAG_DATA_DIR": str(data_dir)},
        )


def test_atomic_persistence_and_permissions(tmp_path: Path) -> None:
    root = tmp_path / "settings"
    path = write_product_generation_settings(
        root,
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://127.0.0.1:11434/v1",
                model="m",
                api_key="secret-key",
            )
        ),
    )
    assert path.is_file()
    assert not list(root.glob(".seneca-generation.json.*.tmp"))
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600 or os.name == "nt"
    loaded = read_product_generation_settings(root)
    assert loaded is not None
    assert loaded.generation.api_key == "secret-key"


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("http://127.0.0.1:11434/v1", True),
        ("http://localhost:11434/v1", True),
        ("http://[::1]:11434/v1", True),
        ("http://host.docker.internal:11434/v1", True),
        ("http://10.1.2.3:11434/v1", True),
        ("http://192.168.1.9:11434/v1", True),
        ("http://172.16.5.1:11434/v1", True),
        ("http://8.8.8.8:11434/v1", False),
        ("http://example.com:11434/v1", False),
        ("ftp://127.0.0.1:11434/v1", False),
        ("http://user:pass@127.0.0.1:11434/v1", False),
    ],
)
def test_strict_offline_endpoint_policy(url: str, ok: bool) -> None:
    if ok:
        assert validate_endpoint_network_policy(url, strict_offline=True)
    else:
        with pytest.raises(EndpointPolicyError):
            validate_endpoint_network_policy(url, strict_offline=True)


def test_capabilities_active_only_no_secrets(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.paths.product_settings.mkdir(parents=True, exist_ok=True)
    write_product_generation_settings(
        settings.paths.product_settings,
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://10.0.0.9:11434/v1",
                model="pending-model",
                api_key="should-never-appear",
            )
        ),
    )
    with _client(settings) as client:
        response = client.get("/v1/capabilities")
        assert response.status_code == 200
        body = response.json()
        assert body["product"]["name"] == "Seneca"
        assert body["source_limits"]["max_active_sources"] == 32
        assert body["source_limits"]["max_bytes_per_source"] == 26_214_400
        assert body["source_limits"]["max_active_source_bytes"] == 104_857_600
        assert body["generation"]["model"] == settings.generation.model
        text = json.dumps(body)
        assert "should-never-appear" not in text
        assert "api_key" not in text
        assert "pending-model" not in text


def test_settings_get_never_returns_api_key(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    write_product_generation_settings(
        settings.paths.product_settings,
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://127.0.0.1:11434/v1",
                model="pending-model",
                api_key="super-secret",
            )
        ),
    )
    with _client(settings) as client:
        response = client.get("/v1/settings/generation")
        assert response.status_code == 200
        body = response.json()
        blob = json.dumps(body)
        assert "super-secret" not in blob
        assert "api_key" not in blob or "api_key_configured" in blob
        assert body["active"]["api_key_configured"] is False or isinstance(
            body["active"]["api_key_configured"], bool
        )
        assert body["restart_required"] is True
        assert body["pending"]["model"] == "pending-model"


def test_probe_does_not_persist_or_mutate_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    original_model = settings.generation.model
    product_path = settings.paths.product_settings / "seneca-generation.json"
    assert not product_path.exists()

    with patch(
        "offline_rag.api.settings.OpenAICompatibleGenerator.probe",
        return_value=GeneratorProbeResult(
            ok=True, reason="ok", available_models=(APPROVED_MODEL,)
        ),
    ):
        with _client(settings) as client:
            response = client.post(
                "/v1/settings/generation/probe",
                json={
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": APPROVED_MODEL,
                    "timeout_seconds": 30,
                    "api_key_action": "keep",
                },
            )
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert not product_path.exists()
            assert settings.generation.model == original_model


def test_save_persists_without_mutating_runtime(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    original_model = settings.generation.model
    with patch(
        "offline_rag.api.settings.OpenAICompatibleGenerator.probe",
        return_value=GeneratorProbeResult(
            ok=True, reason="ok", available_models=("saved-model",)
        ),
    ):
        with _client(settings) as client:
            response = client.put(
                "/v1/settings/generation",
                json={
                    "enabled": True,
                    "base_url": "http://127.0.0.1:11434/v1",
                    "model": "saved-model",
                    "timeout_seconds": 45,
                    "api_key_action": "set",
                    "api_key": "new-secret",
                },
            )
            assert response.status_code == 200
            body = response.json()
            assert body["saved"] is True
            assert body["restart_required"] is True
            assert settings.generation.model == original_model
            loaded = read_product_generation_settings(settings.paths.product_settings)
            assert loaded is not None
            assert loaded.generation.model == "saved-model"
            assert loaded.generation.api_key == "new-secret"


def test_operator_locked_field_cannot_be_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFLINE_RAG_LLM_MODEL", "locked-model")
    settings = _settings(
        tmp_path,
        environ={"OFFLINE_RAG_LLM_MODEL": "locked-model"},
    )
    with _client(settings) as client:
        response = client.put(
            "/v1/settings/generation",
            json={
                "enabled": True,
                "base_url": settings.generation.base_url,
                "model": "attempted-override",
                "timeout_seconds": settings.generation.timeout_seconds,
                "api_key_action": "keep",
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "settings_locked"


def test_env_shadowing_active_not_pending_as_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    write_product_generation_settings(
        data_dir / "settings",
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://10.0.0.5:11434/v1",
                model="product-model",
            )
        ),
    )
    monkeypatch.setenv("OFFLINE_RAG_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OFFLINE_RAG_LLM_MODEL", "env-model")
    monkeypatch.setenv("OFFLINE_RAG_APPROVED_LLM_ENDPOINTS", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OFFLINE_RAG_APPROVED_LLM_MODELS", "env-model")
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
            "OFFLINE_RAG_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
            "OFFLINE_RAG_LLM_MODEL": "env-model",
            "OFFLINE_RAG_APPROVED_LLM_ENDPOINTS": "http://127.0.0.1:11434/v1",
            "OFFLINE_RAG_APPROVED_LLM_MODELS": "env-model",
        },
    )
    settings = settings.model_copy(
        update={"reranker": settings.reranker.model_copy(update={"enabled": False})}
    )
    _provision_assets(settings)
    with _client(settings) as client:
        body = client.get("/v1/settings/generation").json()
        assert body["active"]["base_url"] == "http://127.0.0.1:11434/v1"
        assert body["active"]["model"] == "env-model"
        assert body["locks"]["base_url"] is True
        assert body["locks"]["model"] is True
        assert body["restart_required"] is False
        assert body["pending"] is None


def test_fresh_load_applies_product_settings(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    write_product_generation_settings(
        data_dir / "settings",
        SenecaGenerationSettingsFile(
            generation=SenecaGenerationBody(
                base_url="http://192.168.0.10:11434/v1",
                model="restarted-model",
                timeout_seconds=77,
            )
        ),
    )
    reloaded = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
        },
    )
    assert reloaded.generation.model == "restarted-model"
    assert reloaded.generation.timeout_seconds == 77
    assert reloaded.generation.base_url == "http://192.168.0.10:11434/v1"


def test_public_endpoint_rejected_on_probe(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        response = client.post(
            "/v1/settings/generation/probe",
            json={
                "enabled": True,
                "base_url": "http://8.8.8.8:11434/v1",
                "model": "x",
                "timeout_seconds": 30,
                "api_key_action": "keep",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        assert body["reason"] == "policy_rejected"


def test_save_disabled_skips_reachability(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with _client(settings) as client:
        response = client.put(
            "/v1/settings/generation",
            json={
                "enabled": False,
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "offline-model",
                "timeout_seconds": 60,
                "api_key_action": "clear",
            },
        )
        assert response.status_code == 200
        loaded = read_product_generation_settings(settings.paths.product_settings)
        assert loaded is not None
        assert loaded.generation.enabled is False
