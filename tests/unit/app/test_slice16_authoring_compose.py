"""Docker Compose authoring bootstrap configuration tests."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from offline_rag.app.authoring_product_settings import authoring_field_locks
from offline_rag.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_YAML = REPO_ROOT / "config" / "base.yaml"
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.example.yml"


def _write_env_file(path: Path, *, api_key: str | None) -> dict[str, str]:
    values = {
        "OFFLINE_RAG_GENERATION_SETTINGS_MODE": "user",
        "OFFLINE_RAG_AUTHORING_SETTINGS_MODE": "user",
        "OFFLINE_RAG_LLM_MODEL": "generation-test-model",
        "OFFLINE_RAG_APPROVED_LLM_MODELS": "generation-test-model",
        "OFFLINE_RAG_AUTHORING_ENABLED": "true",
        "OFFLINE_RAG_AUTHORING_BASE_URL": "http://host.docker.internal:11434/v1",
        "OFFLINE_RAG_AUTHORING_MODEL": "authoring-test-model",
        "OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS": (
            "http://host.docker.internal:11434/v1"
        ),
        "OFFLINE_RAG_AUTHORING_APPROVED_MODELS": "authoring-test-model",
        "OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS": "240",
        "OFFLINE_RAG_AUTHORING_NETWORK_POLICY": "localhost_only",
    }
    if api_key is not None:
        values["OFFLINE_RAG_AUTHORING_API_KEY"] = api_key
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()),
        encoding="utf-8",
    )
    return values


@pytest.mark.parametrize("api_key", [None, ""])
def test_compose_forwards_authoring_bootstrap_and_loads_first_start_settings(
    tmp_path: Path, api_key: str | None
) -> None:
    """Only configured authoring variables reach Compose with key presence intact."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose is unavailable")

    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    compose_path = deploy_dir / "docker-compose.yml"
    compose_path.write_bytes(COMPOSE_FILE.read_bytes())
    env_file = tmp_path / ".env"
    source_env = _write_env_file(env_file, api_key=api_key)

    process_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_path),
            "config",
            "--format",
            "json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=process_env,
    )
    service_environment = json.loads(result.stdout)["services"]["offline-rag"]
    container_env = service_environment["environment"]

    assert container_env["OFFLINE_RAG_AUTHORING_SETTINGS_MODE"] == "user"
    assert container_env["OFFLINE_RAG_AUTHORING_ENABLED"] == "true"
    assert (
        container_env["OFFLINE_RAG_AUTHORING_BASE_URL"]
        == source_env["OFFLINE_RAG_AUTHORING_BASE_URL"]
    )
    assert (
        container_env["OFFLINE_RAG_AUTHORING_MODEL"]
        == source_env["OFFLINE_RAG_AUTHORING_MODEL"]
    )
    assert (
        container_env["OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS"]
        == source_env["OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS"]
    )
    assert (
        container_env["OFFLINE_RAG_AUTHORING_APPROVED_MODELS"]
        == source_env["OFFLINE_RAG_AUTHORING_APPROVED_MODELS"]
    )
    assert container_env["OFFLINE_RAG_AUTHORING_TIMEOUT_SECONDS"] == "240"
    assert container_env["OFFLINE_RAG_AUTHORING_NETWORK_POLICY"] == "localhost_only"
    assert container_env["HF_TOKEN"] == ""
    assert container_env.get("OFFLINE_RAG_AUTHORING_API_KEY") == api_key

    loaded_env = {
        name: value for name, value in container_env.items() if value is not None
    }
    loaded_env["OFFLINE_RAG_DATA_DIR"] = str(tmp_path / "data")
    settings = load_settings(yaml_paths=[BASE_YAML], environ=loaded_env)

    assert settings.authoring.enabled is True
    assert (
        str(settings.authoring.base_url) == source_env["OFFLINE_RAG_AUTHORING_BASE_URL"]
    )
    assert settings.authoring.model == source_env["OFFLINE_RAG_AUTHORING_MODEL"]
    assert settings.authoring.approved_endpoints == [
        source_env["OFFLINE_RAG_AUTHORING_APPROVED_ENDPOINTS"]
    ]
    assert settings.authoring.approved_models == [
        source_env["OFFLINE_RAG_AUTHORING_APPROVED_MODELS"]
    ]
    assert settings.authoring.timeout_seconds == 240
    assert settings.authoring.network_policy == "localhost_only"
    assert settings.authoring.api_key == (api_key or None)

    operator_env = dict(loaded_env)
    operator_env["OFFLINE_RAG_AUTHORING_SETTINGS_MODE"] = "operator"
    assert authoring_field_locks(operator_env)["api_key"] is (api_key is not None)
