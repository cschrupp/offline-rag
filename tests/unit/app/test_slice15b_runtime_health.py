"""Phase 15B — runtime lifecycle, health endpoints, non-mutating doctor."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import ErrorCode
from offline_rag.app.paths import ensure_data_directories, required_data_directories
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ResourceFactories,
    RuntimeState,
)
from offline_rag.cli import main
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings

REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakeCloseable:
    def __init__(self, name: str, counter: dict[str, int]) -> None:
        self.name = name
        self._counter = counter
        self.closed = False
        self.load_calls = 0

    def touch(self) -> None:
        self.load_calls += 1

    def close(self) -> None:
        self.closed = True
        self._counter["close"] = self._counter.get("close", 0) + 1


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    if api_overrides:
        settings = settings.model_copy(
            update={"api": settings.api.model_copy(update=api_overrides)}
        )
    return settings


def _counting_factories() -> tuple[ResourceFactories, dict[str, int], dict[str, _FakeCloseable]]:
    counts = {"embedder": 0, "reranker": 0, "generator_client": 0, "close": 0}
    objects: dict[str, _FakeCloseable] = {}

    def embedder(_settings: AppSettings) -> _FakeCloseable:
        counts["embedder"] += 1
        obj = _FakeCloseable("embedder", counts)
        objects["embedder"] = obj
        return obj

    def reranker(_settings: AppSettings) -> _FakeCloseable:
        counts["reranker"] += 1
        obj = _FakeCloseable("reranker", counts)
        objects["reranker"] = obj
        return obj

    def generator_client(_settings: AppSettings) -> _FakeCloseable:
        counts["generator_client"] += 1
        obj = _FakeCloseable("generator", counts)
        objects["generator_client"] = obj
        return obj

    return (
        ResourceFactories(
            embedder=embedder,
            reranker=reranker,
            generator_client=generator_client,
        ),
        counts,
        objects,
    )


def test_runtime_starts_not_ready_then_ready_once(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, counts, _objs = _counting_factories()
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    assert runtime.state is RuntimeState.NOT_STARTED
    assert runtime.is_ready is False

    runtime.start()
    assert runtime.state is RuntimeState.READY
    assert runtime.is_ready is True
    assert counts == {"embedder": 1, "reranker": 1, "generator_client": 1, "close": 0}

    runtime.start()  # idempotent — no second construction
    assert counts["embedder"] == 1
    assert counts["reranker"] == 1
    assert counts["generator_client"] == 1


def test_runtime_failed_init_stays_not_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, counts, _objs = _counting_factories()

    def boom(_settings: AppSettings) -> object:
        counts["embedder"] += 1
        raise RuntimeError("embedder unavailable")

    factories = ResourceFactories(
        embedder=boom,
        reranker=factories.reranker,
        generator_client=factories.generator_client,
    )
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    runtime.start()
    assert runtime.state is RuntimeState.NOT_READY
    assert runtime.is_ready is False
    assert runtime.failure_reason == "startup_failed"
    assert counts["embedder"] == 1
    assert counts["reranker"] == 0


def test_startup_creates_required_data_directories(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    for path in required_data_directories(settings):
        assert not path.exists()
    factories, _counts, _objs = _counting_factories()
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    runtime.start()
    assert runtime.is_ready
    for path in required_data_directories(settings):
        assert path.is_dir()


def test_require_ready_before_startup_is_not_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, _counts, _objs = _counting_factories()
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    assert runtime.state is RuntimeState.NOT_STARTED
    with pytest.raises(Exception) as exc_info:
        runtime.require_ready()
    assert exc_info.value.code is ErrorCode.RUNTIME_NOT_READY  # type: ignore[attr-defined]


def test_health_endpoints_and_no_resource_touch_on_probe(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, counts, objs = _counting_factories()
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    app = create_app(runtime=runtime)

    with TestClient(app) as client:
        # Lifespan started runtime once.
        assert counts["embedder"] == 1
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "live"}
        alias = client.get("/health")
        assert alias.status_code == 200
        assert alias.json() == {"status": "live"}

        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}

        for _ in range(5):
            assert client.get("/health/ready").status_code == 200
            assert client.get("/health/live").status_code == 200

        # Health must not re-construct or "load" resources.
        assert counts["embedder"] == 1
        assert counts["reranker"] == 1
        assert counts["generator_client"] == 1
        assert objs["embedder"].load_calls == 0
        assert objs["generator_client"].load_calls == 0

    assert runtime.shutdown_count == 1
    assert runtime.state is RuntimeState.STOPPED
    assert objs["embedder"].closed is True


def test_health_ready_503_when_startup_fails(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, _counts, _objs = _counting_factories()

    def boom(_settings: AppSettings) -> object:
        raise RuntimeError("no models")

    factories = ResourceFactories(
        embedder=boom,
        reranker=factories.reranker,
        generator_client=factories.generator_client,
    )
    app = create_app(
        runtime=ApplicationRuntime(settings=settings, factories=factories)
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        live = client.get("/health/live")
        assert live.status_code == 200
        assert live.json() == {"status": "live"}
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        body = ready.json()
        assert body["error"]["code"] == "runtime_not_ready"
        assert body["retryable"] is True


def test_readiness_independent_of_corpus_existence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factories, _counts, _objs = _counting_factories()
    app = create_app(
        runtime=ApplicationRuntime(settings=settings, factories=factories)
    )
    with TestClient(app) as client:
        assert not any(settings.paths.corpora.iterdir()) if settings.paths.corpora.exists() else True
        assert client.get("/health/ready").status_code == 200


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int]]:
    """Map relative path -> (mode, size) for files/dirs under root."""
    snapshot: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        st = path.stat()
        snapshot[rel] = (st.st_mode, st.st_size if path.is_file() else -1)
    # Include root marker
    st = root.stat()
    snapshot["."] = (st.st_mode, -1)
    return snapshot


def test_doctor_non_mutating_on_missing_required_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    models = tmp_path / "models"
    data.mkdir()
    models.mkdir()
    # Intentionally omit required durable roots.
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "project:\n  name: offline-rag\n  strict_offline: false\n"
        "paths:\n"
        f"  raw_data: {data / 'raw'}\n"
        f"  manifests: {data / 'manifests'}\n"
        f"  processed: {data / 'processed'}\n"
        f"  corpora: {data / 'corpora'}\n"
        f"  chunks: {data / 'chunks'}\n"
        f"  chunk_manifests: {data / 'chunk-manifests'}\n"
        f"  embeddings: {data / 'embeddings'}\n"
        f"  index_manifests: {data / 'index-manifests'}\n"
        f"  lexical_indexes: {data / 'lexical-indexes'}\n"
        f"  lexical_index_manifests: {data / 'lexical-index-manifests'}\n"
        f"  qdrant_storage: {data / 'qdrant'}\n"
        f"  traces: {data / 'traces'}\n"
        f"  staging: {data / 'staging'}\n"
        f"  locks: {data / 'locks'}\n"
        f"  logs: {data / 'logs'}\n"
        f"  retrieval_models: {models}\n"
        f"  docling_artifacts: {models / 'docling'}\n"
        f"  tokenizer_artifacts: {models / 'tokenizers' / 'tiktoken'}\n"
        f"  embedding_artifacts: {models / 'embeddings'}\n"
        f"  reranker_artifacts: {models / 'rerankers'}\n"
        f"  eval_results: {tmp_path / 'eval' / 'results'}\n",
        encoding="utf-8",
    )
    before = _snapshot_tree(tmp_path)
    code = main(["doctor", "--config", str(cfg), "--corpus", "default"])
    after = _snapshot_tree(tmp_path)
    captured = capsys.readouterr()
    assert code == 1
    assert "ABSENT" in captured.err or "ABSENT" in captured.out or "doctor: FAIL" in captured.err
    assert before == after
    assert not (data / "raw").exists()
    assert not list(tmp_path.rglob(".offline_rag_write_probe"))


def test_doctor_reports_missing_model_assets_without_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = _settings(tmp_path)
    ensure_data_directories(settings)
    # Create empty required path tree + models root, but no provisioned weights.
    (tmp_path / "models").mkdir(exist_ok=True)
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "project:\n  name: offline-rag\n  strict_offline: true\n"
        "security:\n  reject_unapproved_generation_endpoint: false\n"
        "  reject_unapproved_generation_model: false\n"
        "  allow_network_tools: false\n"
        "paths:\n"
        f"  raw_data: {settings.paths.raw_data}\n"
        f"  manifests: {settings.paths.manifests}\n"
        f"  processed: {settings.paths.processed}\n"
        f"  corpora: {settings.paths.corpora}\n"
        f"  chunks: {settings.paths.chunks}\n"
        f"  chunk_manifests: {settings.paths.chunk_manifests}\n"
        f"  embeddings: {settings.paths.embeddings}\n"
        f"  index_manifests: {settings.paths.index_manifests}\n"
        f"  lexical_indexes: {settings.paths.lexical_indexes}\n"
        f"  lexical_index_manifests: {settings.paths.lexical_index_manifests}\n"
        f"  qdrant_storage: {settings.paths.qdrant_storage}\n"
        f"  traces: {settings.paths.traces}\n"
        f"  staging: {settings.paths.staging}\n"
        f"  locks: {settings.paths.locks}\n"
        f"  logs: {settings.paths.logs}\n"
        f"  retrieval_models: {settings.paths.retrieval_models}\n"
        f"  docling_artifacts: {settings.paths.docling_artifacts}\n"
        f"  tokenizer_artifacts: {settings.paths.tokenizer_artifacts}\n"
        f"  embedding_artifacts: {settings.paths.embedding_artifacts}\n"
        f"  reranker_artifacts: {settings.paths.reranker_artifacts}\n"
        f"  eval_results: {settings.paths.eval_results}\n",
        encoding="utf-8",
    )
    before = _snapshot_tree(tmp_path)
    code = main(["doctor", "--config", str(cfg)])
    after = _snapshot_tree(tmp_path)
    captured = capsys.readouterr()
    assert code == 1
    assert before == after
    assert "Embedding model artifacts" in captured.out or "doctor: FAIL" in captured.err
    # No provisioning side effects under models/.
    assert list((tmp_path / "models").rglob("*")) == [] or all(
        p.is_dir() for p in (tmp_path / "models").rglob("*")
    )
