"""Phase 15G — container packaging, bind policy, and deploy contracts."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from offline_rag.api import server as server_mod
from offline_rag.api.bind_policy import (
    BindPolicyError,
    enforce_bind_policy,
    is_loopback_bind_host,
)
from offline_rag.config import load_settings

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE_SHA = "c767b31df23df3943214a2f99387b542de875bf8"
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile"
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.example.yml"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


# ---------------------------------------------------------------------------
# Ancestry
# ---------------------------------------------------------------------------


def test_remote_ancestry_begins_at_15g_baseline() -> None:
    merge_base = subprocess.check_output(
        ["git", "merge-base", "HEAD", BASELINE_SHA],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    assert merge_base == BASELINE_SHA
    contained = subprocess.call(
        ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        cwd=REPO_ROOT,
    )
    assert contained == 0


# ---------------------------------------------------------------------------
# A — bind policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "::1", "localhost", "LOCALHOST", "[::1]"],
)
def test_loopback_hosts_allowed_without_opt_in(host: str) -> None:
    assert is_loopback_bind_host(host) is True
    enforce_bind_policy(host, allow_non_loopback=False)


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "example.local"],
)
def test_non_loopback_hosts_rejected_without_opt_in(host: str) -> None:
    assert is_loopback_bind_host(host) is False
    with pytest.raises(BindPolicyError):
        enforce_bind_policy(host, allow_non_loopback=False)


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "192.168.1.10"],
)
def test_non_loopback_hosts_accepted_with_opt_in(host: str) -> None:
    enforce_bind_policy(host, allow_non_loopback=True)


# ---------------------------------------------------------------------------
# B — server launch
# ---------------------------------------------------------------------------


def test_server_main_enforces_bind_before_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {"enforce": 0, "run": 0}

    def fake_enforce(host: str, *, allow_non_loopback: bool) -> None:
        calls["enforce"] += 1
        calls["host"] = host
        calls["allow"] = allow_non_loopback
        assert calls["run"] == 0

    def fake_run(*_args: Any, **kwargs: Any) -> None:
        calls["run"] += 1
        calls["uvicorn"] = kwargs

    monkeypatch.setattr(server_mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        server_mod,
        "load_settings",
        lambda: load_settings(
            yaml_paths=[],
            environ={
                "OFFLINE_RAG_HTTP_HOST": "127.0.0.1",
                "OFFLINE_RAG_HTTP_PORT": "8080",
                "OFFLINE_RAG_ALLOW_NON_LOOPBACK": "false",
            },
        ),
    )
    monkeypatch.setattr(server_mod, "enforce_bind_policy", fake_enforce)
    monkeypatch.setattr(server_mod, "create_app", lambda **_kw: MagicMock(name="app"))
    monkeypatch.setattr(server_mod.uvicorn, "run", fake_run)

    assert server_mod.main() == 0
    assert calls["enforce"] == 1
    assert calls["run"] == 1
    assert calls["host"] == "127.0.0.1"
    assert calls["allow"] is False
    assert calls["uvicorn"]["host"] == "127.0.0.1"
    assert calls["uvicorn"]["port"] == 8080
    assert calls["uvicorn"]["workers"] == 1
    assert calls["uvicorn"]["reload"] is False


def test_server_main_refuses_non_loopback_before_listen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = {"uvicorn": False}

    monkeypatch.setattr(server_mod, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        server_mod,
        "load_settings",
        lambda: load_settings(
            yaml_paths=[],
            environ={
                "OFFLINE_RAG_HTTP_HOST": "0.0.0.0",
                "OFFLINE_RAG_HTTP_PORT": "8080",
                "OFFLINE_RAG_ALLOW_NON_LOOPBACK": "false",
            },
        ),
    )
    monkeypatch.setattr(
        server_mod.uvicorn,
        "run",
        lambda *_a, **_k: ran.__setitem__("uvicorn", True),
    )

    assert server_mod.main() == 2
    assert ran["uvicorn"] is False


# ---------------------------------------------------------------------------
# C — configuration projection
# ---------------------------------------------------------------------------


def test_container_env_projects_data_models_and_http() -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_DATA_DIR": "/data",
            "OFFLINE_RAG_MODELS_DIR": "/models",
            "OFFLINE_RAG_HTTP_HOST": "0.0.0.0",
            "OFFLINE_RAG_HTTP_PORT": "8080",
            "OFFLINE_RAG_ALLOW_NON_LOOPBACK": "true",
        },
    )
    root = Path("/data")
    assert settings.paths.raw_data == root / "raw"
    assert settings.paths.manifests == root / "manifests"
    assert settings.paths.processed == root / "processed"
    assert settings.paths.corpora == root / "corpora"
    assert settings.paths.chunks == root / "chunks"
    assert settings.paths.chunk_manifests == root / "chunk-manifests"
    assert settings.paths.embeddings == root / "embeddings"
    assert settings.paths.index_manifests == root / "index-manifests"
    assert settings.paths.lexical_indexes == root / "lexical-indexes"
    assert settings.paths.lexical_index_manifests == root / "lexical-index-manifests"
    assert settings.paths.qdrant_storage == root / "qdrant"
    assert settings.paths.traces == root / "traces"
    assert settings.paths.staging == root / "staging"
    assert settings.paths.locks == root / "locks"
    assert settings.paths.logs == root / "logs"
    assert settings.paths.eval_results == root / "eval" / "results"

    models = Path("/models")
    assert settings.paths.retrieval_models == models
    assert settings.paths.docling_artifacts == models / "docling"
    assert settings.paths.tokenizer_artifacts == models / "tokenizers" / "tiktoken"
    assert settings.paths.embedding_artifacts == models / "embeddings"
    assert settings.paths.reranker_artifacts == models / "rerankers"

    assert settings.api.http_host == "0.0.0.0"
    assert settings.api.http_port == 8080
    assert settings.api.allow_non_loopback is True
    enforce_bind_policy(
        settings.api.http_host,
        allow_non_loopback=settings.api.allow_non_loopback,
    )


def test_container_http_without_allow_flag_fails_policy() -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_HTTP_HOST": "0.0.0.0",
            "OFFLINE_RAG_HTTP_PORT": "8080",
        },
    )
    assert settings.api.allow_non_loopback is False
    with pytest.raises(BindPolicyError):
        enforce_bind_policy(
            settings.api.http_host,
            allow_non_loopback=settings.api.allow_non_loopback,
        )


# ---------------------------------------------------------------------------
# D — Dockerfile static contract
# ---------------------------------------------------------------------------


def test_dockerfile_static_contract() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.14-slim" in text
    assert "10001" in text
    assert re.search(r"^\s*USER\s+10001:10001\s*$", text, re.MULTILINE)
    assert "OFFLINE_RAG_DATA_DIR=/data" in text
    assert "OFFLINE_RAG_MODELS_DIR=/models" in text
    assert "OFFLINE_RAG_ALLOW_NON_LOOPBACK=true" in text
    assert "OFFLINE_RAG_HTTP_HOST=0.0.0.0" in text
    assert "HF_HUB_OFFLINE=1" in text
    assert "TRANSFORMERS_OFFLINE=1" in text
    assert "ollama" not in text.lower() or "NOT" in text
    assert "generator" not in text.lower() or "NOT" in text
    assert 'CMD ["python", "-m", "offline_rag.api.server"]' in text
    assert "--workers" not in text
    assert "gunicorn" not in text.lower()
    assert "COPY . " not in text
    assert "COPY src /app/src" in text
    assert "COPY config /app/config" in text
    assert not (REPO_ROOT / "deploy" / "Dockerfile.template").exists()


# ---------------------------------------------------------------------------
# E — Compose static contract
# ---------------------------------------------------------------------------


def test_compose_static_contract() -> None:
    payload = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = payload["services"]
    assert set(services) == {"offline-rag"}
    svc = services["offline-rag"]
    assert svc["build"]["context"] == ".."
    assert svc["build"]["dockerfile"] == "deploy/Dockerfile"
    assert svc["ports"] == ["127.0.0.1:8080:8080"]
    assert "host.docker.internal:host-gateway" in svc["extra_hosts"]
    assert svc["stop_grace_period"] == "45s"
    env = svc["environment"]
    assert env["OFFLINE_RAG_HTTP_HOST"] == "0.0.0.0"
    assert env["OFFLINE_RAG_HTTP_PORT"] == "8080"
    assert env["OFFLINE_RAG_ALLOW_NON_LOOPBACK"] == "true"
    assert env["OFFLINE_RAG_DATA_DIR"] == "/data"
    assert env["OFFLINE_RAG_MODELS_DIR"] == "/models"
    assert env["OFFLINE_RAG_CONFIG"] == "/app/config/base.yaml"
    assert env["OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS"] == "30"
    assert env["OFFLINE_RAG_LLM_BASE_URL"] == "http://host.docker.internal:11434/v1"
    assert (
        env["OFFLINE_RAG_APPROVED_LLM_ENDPOINTS"]
        == "http://host.docker.internal:11434/v1"
    )
    assert "OFFLINE_RAG_LLM_MODEL" in env
    assert "OFFLINE_RAG_APPROVED_LLM_MODELS" in env
    assert set(svc["volumes"]) == {"../data:/data", "../models:/models:ro"}
    assert "qdrant" not in services
    assert "ollama" not in services
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    assert re.search(r"^\s*replicas\s*:", text, re.MULTILINE) is None
    assert "workers" not in text.lower()


# ---------------------------------------------------------------------------
# F — .dockerignore
# ---------------------------------------------------------------------------


def test_dockerignore_excludes_sensitive_and_local_trees() -> None:
    text = DOCKERIGNORE.read_text(encoding="utf-8")
    for pattern in (".git", ".env", "data/", "models/", ".venv/", "__pycache__"):
        assert pattern in text


def test_pyproject_declares_uvicorn_runtime_dependency() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "uvicorn" in text
    # Ensure the server module is importable as a package entry.
    source = (REPO_ROOT / "src" / "offline_rag" / "api" / "server.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert "main" in names
