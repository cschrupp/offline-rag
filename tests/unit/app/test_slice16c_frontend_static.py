"""Slice 16C — same-origin SPA static delivery contracts."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
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
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _settings(tmp_path: Path) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    reranker = settings.reranker.model_copy(update={"enabled": False})
    settings = settings.model_copy(update={"generation": generation, "reranker": reranker})
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


def _write_ui(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(
        "<!doctype html><html><body>OfflineRAG UI</body></html>\n",
        encoding="utf-8",
    )
    assets = root / "assets"
    assets.mkdir()
    (assets / "app-abc123.js").write_text(
        "window.__OFFLINE_RAG__=1;\n", encoding="utf-8"
    )
    (root / "favicon.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'></svg>\n", encoding="utf-8"
    )
    return root


@contextmanager
def _ui_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, with_ui: bool = True
) -> Iterator[TestClient]:
    if with_ui:
        ui_dir = _write_ui(tmp_path / "ui")
        monkeypatch.setenv("OFFLINE_RAG_UI_DIR", str(ui_dir))
    else:
        monkeypatch.setenv("OFFLINE_RAG_UI_DIR", str(tmp_path / "missing-ui"))
    settings = _settings(tmp_path / "rt")
    app = create_app(runtime=_runtime(settings))
    with TestClient(app) as client:
        yield client


def test_root_serves_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "OfflineRAG UI" in response.text
        assert "text/html" in response.headers.get("content-type", "")


def test_spa_deep_link_serves_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/workspaces/ws_example")
        assert response.status_code == 200
        assert "OfflineRAG UI" in response.text


def test_assets_serve_exact_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/assets/app-abc123.js")
        assert response.status_code == 200
        assert "window.__OFFLINE_RAG__=1" in response.text


def test_health_remains_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        live = client.get("/health")
        assert live.status_code == 200
        assert live.json() == {"status": "live"}


def test_health_ready_remains_backend_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}


def test_workspaces_api_remains_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/v1/workspaces")
        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("application/json")
        assert response.json() == []


def test_unknown_v1_route_is_not_spa_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/v1/not-a-route")
        assert response.status_code == 404
        assert "OfflineRAG UI" not in response.text


def test_openapi_remains_openapi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        payload = response.json()
        assert payload["info"]["title"] == "OfflineRAG API"


def test_docs_route_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()


def test_path_traversal_does_not_escape_static_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret\n", encoding="utf-8")
    with _ui_client(tmp_path, monkeypatch) as client:
        response = client.get("/../secret.txt")
        assert "top-secret" not in response.text
        assert response.status_code in {200, 404}
        if response.status_code == 200:
            assert "OfflineRAG UI" in response.text


def test_api_usable_when_frontend_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _ui_client(tmp_path, monkeypatch, with_ui=False) as client:
        assert client.get("/health").json() == {"status": "live"}
        assert client.get("/v1/workspaces").json() == []
        root = client.get("/")
        assert root.status_code == 404
        assert "OfflineRAG UI" not in root.text
