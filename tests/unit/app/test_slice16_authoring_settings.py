"""Slice 16 Gold authoring Settings / capabilities remediation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from offline_rag.api.app import create_app
from offline_rag.api.authoring_settings import (
    AuthoringSaveRequest,
    get_authoring_settings,
    save_authoring_settings,
)
from offline_rag.app.authoring_product_settings import (
    SenecaAuthoringBody,
    SenecaAuthoringSettingsFile,
    authoring_field_locks,
    authoring_overlay_from_product_settings,
    authoring_settings_mode,
    build_validated_authoring_product_record,
    infer_authoring_network_policy,
    read_product_authoring_settings,
    write_product_authoring_settings,
)
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories, RuntimeState
from offline_rag.config import ConfigError, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.gold_authoring.adapter import OpenAICompatibleAuthoringAdapter
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


def _settings_api_request(settings: AppSettings) -> Request:
    """Build a ready fake-runtime request without app startup or model assets."""
    runtime = _runtime(settings)
    runtime.state = RuntimeState.READY
    app = create_app(runtime=runtime)
    return Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/v1/settings/authoring",
            "headers": [],
            "query_string": b"",
        }
    )


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


def test_authoring_settings_mode_defaults_to_operator_and_rejects_unknown() -> None:
    env = {
        "OFFLINE_RAG_AUTHORING_ENABLED": "true",
        "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
        "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": APPROVED_ENDPOINT,
    }
    assert authoring_settings_mode({}) == "operator"
    assert authoring_settings_mode(env) == "operator"
    assert authoring_field_locks(env)["base_url"] is True

    user_env = {**env, "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user"}
    assert authoring_settings_mode(user_env) == "user"
    assert not any(authoring_field_locks(user_env).values())
    user_locks = authoring_field_locks(
        user_env, programmatic_override_fields={"approved_endpoints"}
    )
    assert user_locks["base_url"] is True

    with pytest.raises(ValueError, match="OFFLINE_RAG_AUTHORING_SETTINGS_MODE"):
        authoring_settings_mode({"OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "hybrid"})
    with pytest.raises(ValueError, match="OFFLINE_RAG_AUTHORING_SETTINGS_MODE"):
        authoring_field_locks({"OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "hybrid"})

    with pytest.raises(ConfigError, match="OFFLINE_RAG_AUTHORING_SETTINGS_MODE"):
        load_settings(
            yaml_paths=[BASE_YAML],
            environ={"OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "hybrid"},
        )


def test_authoring_user_mode_bootstrap_save_restart_and_key_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrap_endpoint = "http://127.0.0.1:11434/v1"
    selected_endpoint = "http://127.0.0.1:11436/v1"
    bootstrap_model = "bootstrap-authoring-model"
    selected_model = "user-authoring-model"
    bootstrap_key = "authoring-bootstrap-secret-for-test"
    user_key = "user-owned-authoring-secret-for-test"
    env = {
        "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user",
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        "OFFLINE_RAG_AUTHORING_ENABLED": "true",
        "OFFLINE_RAG_AUTHORING_BASE_URL": bootstrap_endpoint,
        "OFFLINE_RAG_AUTHORING_MODEL": bootstrap_model,
        "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": bootstrap_endpoint,
        "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": bootstrap_model,
        "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "localhost_only",
        "OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS": "240",
        "OFFLINE_RAG_AUTHORING_API_KEY": bootstrap_key,
        # Not exposed by this Settings UI, so these keep their environment
        # ownership even while the editable connection fields use user mode.
        "OFFLINE_RAG_AUTHORING_TEMPERATURE": "0.25",
        "OFFLINE_RAG_AUTHORING_MAX_OUTPUT_TOKENS": "1500",
    }
    for key in (
        "OFFLINE_RAG_AUTHORING_ENABLED",
        "OFFLINE_RAG_AUTHORING_BASE_URL",
        "OFFLINE_RAG_AUTHORING_MODEL",
        "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS",
        "OFFLINE_RAG_AUTHORING_APPROVED_MODELS",
        "OFFLINE_RAG_AUTHORING_NETWORK_POLICY",
        "OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS",
        "OFFLINE_RAG_AUTHORING_API_KEY",
        "OFFLINE_RAG_AUTHORING_TEMPERATURE",
        "OFFLINE_RAG_AUTHORING_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    settings = load_settings(yaml_paths=[BASE_YAML], environ=env)
    assert settings.authoring.enabled is True
    assert settings.authoring.base_url == bootstrap_endpoint
    assert settings.authoring.model == bootstrap_model
    assert settings.authoring.approved_endpoints == [bootstrap_endpoint]
    assert settings.authoring.approved_models == [bootstrap_model]
    assert settings.authoring.timeout_seconds == 240
    assert settings.authoring.api_key == bootstrap_key
    assert settings.authoring.network_policy == "localhost_only"
    assert settings.authoring.temperature == 0.25
    assert settings.authoring.max_output_tokens == 1500
    assert not any(authoring_field_locks(env).values())

    request = _settings_api_request(settings)

    probed_keys: list[str | None] = []

    def successful_probe(**kwargs: object) -> dict[str, object]:
        api_key = kwargs.get("api_key")
        assert api_key is None or isinstance(api_key, str)
        probed_keys.append(api_key)
        return {
            "ok": True,
            "reason": "ok",
            "available_models": [selected_model],
        }

    monkeypatch.setattr(
        "offline_rag.api.authoring_settings._probe_models",
        successful_probe,
    )
    initial = get_authoring_settings(request)
    assert initial["active"]["model"] == bootstrap_model
    assert not any(initial["locks"].values())

    save = save_authoring_settings(
        request,
        AuthoringSaveRequest(
            enabled=True,
            base_url=selected_endpoint,
            model=selected_model,
            timeout_seconds=180,
            api_key_action="keep",
        ),
    )
    assert save["saved"] is True
    assert save["restart_required"] is True
    assert save["pending"]["base_url"] == selected_endpoint
    assert save["pending"]["model"] == selected_model
    assert save["pending"]["api_key_configured"] is True

    settings_path = settings.paths.product_settings / "seneca-authoring.json"
    raw = json.loads(settings_path.read_text(encoding="utf-8"))
    assert raw["authoring"]["base_url"] == selected_endpoint
    assert raw["authoring"]["model"] == selected_model
    assert "api_key" not in raw["authoring"]

    restarted = load_settings(yaml_paths=[BASE_YAML], environ=env)
    assert restarted.authoring.base_url == selected_endpoint
    assert restarted.authoring.model == selected_model
    assert restarted.authoring.approved_endpoints == [selected_endpoint]
    assert restarted.authoring.approved_models == [selected_model]
    assert restarted.authoring.timeout_seconds == 180
    assert restarted.authoring.api_key == bootstrap_key
    assert restarted.authoring.network_policy == "localhost_only"
    readiness = evaluate_authoring_readiness(restarted)
    assert readiness.ready is True
    authoring_client = MagicMock()
    completion_response = MagicMock()
    completion_response.is_redirect = False
    completion_response.status_code = 200
    completion_response.json.return_value = {
        "choices": [{"message": {"content": '{"ok": true}'}}]
    }
    authoring_client.post.return_value = completion_response
    adapter = OpenAICompatibleAuthoringAdapter(restarted, client=authoring_client)
    assert adapter.base_url == selected_endpoint
    proposal = adapter.propose(system_prompt="system", user_content="seed")
    assert proposal == '{"ok": true}'
    call = authoring_client.post.call_args
    assert call.args[0] == f"{selected_endpoint}/chat/completions"
    assert call.kwargs["json"]["model"] == selected_model

    for action, key, expected in (
        ("set", user_key, user_key),
        ("clear", None, None),
    ):
        save_authoring_settings(
            request,
            AuthoringSaveRequest(
                enabled=True,
                base_url=selected_endpoint,
                model=selected_model,
                timeout_seconds=180,
                api_key=key,
                api_key_action=action,
            ),
        )
        restarted = load_settings(yaml_paths=[BASE_YAML], environ=env)
        assert restarted.authoring.api_key == expected
        if key is not None:
            assert key not in json.dumps(get_authoring_settings(request))

    assert probed_keys == [bootstrap_key, user_key, None]


def test_authoring_user_mode_programmatic_overrides_lock_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {
        "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user",
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_AUTHORING_BASE_URL": APPROVED_ENDPOINT,
        "OFFLINE_RAG_AUTHORING_MODEL": "bootstrap-model",
    }
    settings = load_settings(
        yaml_paths=[BASE_YAML],
        environ=env,
        overrides={
            "authoring": {
                "approved_models": ["programmatic-model"],
                "model": "programmatic-model",
            }
        },
    )
    assert settings._explicit_authoring_override_fields == frozenset(
        {"approved_models", "model"}
    )
    assert "_explicit_authoring_override_fields" not in settings.model_dump()
    locks = authoring_field_locks(
        env,
        programmatic_override_fields=settings._explicit_authoring_override_fields,
    )
    assert locks["model"] is True
    assert locks["base_url"] is False
    request = _settings_api_request(settings)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    response = get_authoring_settings(request)
    assert response["locks"]["model"] is True
    assert response["active"]["model"] == "programmatic-model"


def test_authoring_api_key_env_presence_authority(tmp_path: Path) -> None:
    """Absent vs nonempty vs empty AUTHORING_API_KEY ownership."""
    absent = authoring_field_locks({})
    assert absent["api_key"] is False

    nonempty = authoring_field_locks({"OFFLINE_RAG_AUTHORING_API_KEY": "secret"})
    assert nonempty["api_key"] is True

    empty = authoring_field_locks({"OFFLINE_RAG_AUTHORING_API_KEY": ""})
    assert empty["api_key"] is True

    data_dir = tmp_path / "data"
    product_dir = data_dir / "settings"
    write_product_authoring_settings(
        product_dir,
        SenecaAuthoringSettingsFile(
            authoring=SenecaAuthoringBody(
                enabled=True,
                base_url=APPROVED_ENDPOINT,
                model=APPROVED_MODEL,
                timeout_seconds=120,
                api_key="product-secret",
                network_policy="localhost_only",
            )
        ),
        manage_api_key=True,
    )

    # Empty env key wins over product key (explicit operator no-key).
    cleared = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
            "OFFLINE_RAG_AUTHORING_API_KEY": "",
        },
    )
    assert cleared.authoring.api_key is None

    # Nonempty env key wins over product key.
    owned = load_settings(
        yaml_paths=[BASE_YAML],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_dir),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
            "OFFLINE_RAG_AUTHORING_API_KEY": "env-secret",
        },
    )
    assert owned.authoring.api_key == "env-secret"


def test_empty_env_api_key_no_perpetual_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty env API key locks ownership; product cannot invent restart/pending key."""
    monkeypatch.setenv("OFFLINE_RAG_AUTHORING_API_KEY", "")
    settings = _settings(
        tmp_path,
        environ={"OFFLINE_RAG_AUTHORING_API_KEY": ""},
    )
    write_product_authoring_settings(
        settings.paths.product_settings,
        SenecaAuthoringSettingsFile(
            authoring=SenecaAuthoringBody(
                enabled=bool(settings.authoring.enabled),
                base_url=None,
                model=None,
                timeout_seconds=int(settings.authoring.timeout_seconds),
                api_key="should-not-become-pending",
                network_policy=None,
            )
        ),
        manage_api_key=True,
    )
    with _client(settings) as client:
        body = client.get("/v1/settings/authoring").json()
    assert body["locks"]["api_key"] is True
    assert body["active"]["api_key_configured"] is False
    # Locked empty env key means product secret must not appear as pending key.
    if body["pending"] is not None:
        assert body["pending"]["api_key_configured"] is False
    assert "should-not-become-pending" not in json.dumps(body)


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
