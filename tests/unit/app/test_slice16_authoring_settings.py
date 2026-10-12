"""Slice 16 Gold authoring Settings / capabilities remediation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.authoring_product_settings import (
    SenecaAuthoringBody,
    SenecaAuthoringSettingsFile,
    authoring_field_locks,
    authoring_overlay_from_product_settings,
    build_validated_authoring_product_record,
    infer_authoring_network_policy,
    read_product_authoring_settings,
    write_product_authoring_settings,
)
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.gold_authoring.readiness import evaluate_authoring_readiness
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_YAML = REPO_ROOT / "config" / "base.yaml"
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
LAN_ENDPOINT = "http://10.0.0.5:8888/v1"


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
) -> AppSettings:
    env = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        **(environ or {}),
    }
    settings = load_settings(yaml_paths=[BASE_YAML], environ=env)
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


def test_infer_network_policy() -> None:
    assert infer_authoring_network_policy("http://127.0.0.1:11434/v1") == "localhost_only"
    assert (
        infer_authoring_network_policy("http://host.docker.internal:11434/v1")
        == "localhost_only"
    )
    assert infer_authoring_network_policy(LAN_ENDPOINT) == "private_network"
    with pytest.raises(ValueError, match="public"):
        infer_authoring_network_policy("https://api.openai.com/v1")


def test_authoring_product_persistence_atomic(tmp_path: Path) -> None:
    root = tmp_path / "settings"
    record = build_validated_authoring_product_record(
        enabled=True,
        base_url=APPROVED_ENDPOINT,
        model=APPROVED_MODEL,
        timeout_seconds=180,
        api_key="secret-key",
        network_policy=None,
        strict_offline=True,
    )
    path = write_product_authoring_settings(root, record, manage_api_key=True)
    assert path.name == "seneca-authoring.json"
    loaded = read_product_authoring_settings(root)
    assert loaded is not None
    assert loaded.schema_version == "seneca-authoring-settings-v1"
    assert loaded.authoring.enabled is True
    assert loaded.authoring.model == APPROVED_MODEL
    assert loaded.authoring.network_policy == "localhost_only"
    assert loaded.authoring.api_key == "secret-key"
    assert not list(root.glob(".seneca-authoring.json.*.tmp"))


def test_yaml_product_env_precedence(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    product_dir = data_dir / "settings"
    write_product_authoring_settings(
        product_dir,
        SenecaAuthoringSettingsFile(
            authoring=SenecaAuthoringBody(
                enabled=True,
                base_url=LAN_ENDPOINT,
                model="product-authoring-model",
                timeout_seconds=90,
                api_key="product-secret",
                network_policy="private_network",
            )
        ),
        manage_api_key=True,
    )
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
        },
    )
    assert settings.authoring.enabled is True
    assert settings.authoring.base_url == LAN_ENDPOINT
    assert settings.authoring.model == "product-authoring-model"
    assert settings.authoring.api_key == "product-secret"
    assert settings.authoring.approved_endpoints == [LAN_ENDPOINT]
    assert settings.authoring.approved_models == ["product-authoring-model"]

    env_wins = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
            "OFFLINE_RAG_AUTHORING_ENABLED": "false",
            "OFFLINE_RAG_AUTHORING_MODEL": "env-model",
            "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
            "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": APPROVED_ENDPOINT,
            "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": "env-model",
            "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "localhost_only",
        },
    )
    assert env_wins.authoring.enabled is False
    assert env_wins.authoring.model == "env-model"
    assert env_wins.authoring.base_url == APPROVED_ENDPOINT


def test_authoring_field_locks() -> None:
    locks = authoring_field_locks(
        {
            "OFFLINE_RAG_AUTHORING_ENABLED": "true",
            "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
            "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": "m",
            "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "private_network",
            "OFFLINE_RAG_AUTHORING_API_KEY": "x",
            "OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS": "300",
        }
    )
    assert locks["enabled"] is True
    assert locks["base_url"] is True
    assert locks["model"] is True
    assert locks["network_policy"] is True
    assert locks["api_key"] is True
    assert locks["timeout_seconds"] is True


def test_public_endpoint_rejected_under_strict_offline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="public_endpoint_forbidden"):
        build_validated_authoring_product_record(
            enabled=True,
            base_url="https://api.openai.com/v1",
            model="x",
            timeout_seconds=60,
            api_key=None,
            network_policy=None,
            strict_offline=True,
        )
    root = tmp_path / "settings"
    root.mkdir(parents=True)
    (root / "seneca-authoring.json").write_text(
        json.dumps(
            {
                "schema_version": "seneca-authoring-settings-v1",
                "authoring": {
                    "enabled": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "x",
                    "timeout_seconds": 60,
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="endpoint_policy"):
        authoring_overlay_from_product_settings(root, strict_offline=True)


def test_api_get_never_returns_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in {
        "OFFLINE_RAG_AUTHORING_ENABLED": "true",
        "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
        "OFFLINE_RAG_AUTHORING_MODEL": APPROVED_MODEL,
        "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": APPROVED_ENDPOINT,
        "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": APPROVED_MODEL,
        "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "localhost_only",
        "OFFLINE_RAG_AUTHORING_API_KEY": "super-secret",
    }.items():
        monkeypatch.setenv(key, value)
    settings = _settings(
        tmp_path,
        environ={
            "OFFLINE_RAG_AUTHORING_ENABLED": "true",
            "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
            "OFFLINE_RAG_AUTHORING_MODEL": APPROVED_MODEL,
            "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": APPROVED_ENDPOINT,
            "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": APPROVED_MODEL,
            "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "localhost_only",
            "OFFLINE_RAG_AUTHORING_API_KEY": "super-secret",
        },
    )
    with _client(settings) as client:
        body = client.get("/v1/settings/authoring").json()
    blob = json.dumps(body)
    assert "super-secret" not in blob
    assert body["active"]["api_key_configured"] is True
    assert body["locks"]["api_key"] is True
    assert body["readiness"]["ready"] is True
    # Never surface a secret-bearing field value under active/pending.
    assert "api_key" not in body["active"]
    assert body.get("pending") is None or "api_key" not in body["pending"]


def test_capabilities_authoring_active_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert evaluate_authoring_readiness(settings).ready is False
    with _client(settings) as client:
        caps = client.get("/v1/capabilities").json()
    assert "authoring" in caps
    assert caps["authoring"]["ready"] is False
    assert "disabled" in caps["authoring"]["reason_codes"]
    assert '"api_key":' not in json.dumps(caps)
    assert caps["authoring"]["api_key_configured"] is False


def test_probe_prospective_no_persist(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    product_path = settings.paths.product_settings / "seneca-authoring.json"
    assert not product_path.exists()

    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {"data": [{"id": APPROVED_MODEL}]}

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.return_value = _Resp()

    with (
        patch("offline_rag.api.authoring_settings.httpx.Client", return_value=mock_client),
        _client(settings) as client,
    ):
        result = client.post(
            "/v1/settings/authoring/probe",
            json={
                "enabled": True,
                "base_url": APPROVED_ENDPOINT,
                "model": APPROVED_MODEL,
                "timeout_seconds": 60,
                "api_key_action": "clear",
            },
        )
    assert result.status_code == 200
    assert result.json()["ok"] is True
    assert not product_path.exists()
    mock_client.get.assert_called()
    # follow_redirects=False is required on Client construction
    assert mock_client.get.call_args is not None


def test_save_sets_pending_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {"data": [{"id": "pending-model"}]}

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.return_value = _Resp()

    with (
        patch("offline_rag.api.authoring_settings.httpx.Client", return_value=mock_client),
        _client(settings) as client,
    ):
        saved = client.put(
            "/v1/settings/authoring",
            json={
                "enabled": True,
                "base_url": APPROVED_ENDPOINT,
                "model": "pending-model",
                "timeout_seconds": 200,
                "api_key_action": "clear",
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["saved"] is True
        assert body["restart_required"] is True
        get_body = client.get("/v1/settings/authoring").json()
        assert get_body["restart_required"] is True
        assert get_body["pending"]["model"] == "pending-model"
        # ACTIVE remains YAML defaults (not yet restarted)
        assert get_body["active"]["enabled"] is False


def test_operator_lock_blocks_api_key_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFLINE_RAG_AUTHORING_API_KEY", "locked-secret")
    settings = _settings(
        tmp_path,
        environ={
            "OFFLINE_RAG_AUTHORING_API_KEY": "locked-secret",
        },
    )
    with _client(settings) as client:
        resp = client.put(
            "/v1/settings/authoring",
            json={
                "enabled": False,
                "base_url": str(settings.authoring.base_url),
                "model": settings.authoring.model or APPROVED_MODEL,
                "timeout_seconds": int(settings.authoring.timeout_seconds),
                "api_key_action": "clear",
            },
        )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "settings_locked"
