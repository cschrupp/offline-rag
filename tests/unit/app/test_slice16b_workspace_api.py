"""Slice 16B — workspace lifecycle HTTP surface (focused)."""

from __future__ import annotations

import shutil
import time
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
    api = settings.api
    reranker = settings.reranker.model_copy(update={"enabled": False})
    settings = settings.model_copy(
        update={"generation": generation, "api": api, "reranker": reranker}
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


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client


def _wait_operation(client: TestClient, operation_id: str, *, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/v1/operations/{operation_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"operation {operation_id} did not terminate")


def test_workspace_create_idempotent_and_conflict(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = {"Idempotency-Key": "create-1"}
        r1 = client.post(
            "/v1/workspaces",
            json={"title": "Desk", "description": "d"},
            headers=headers,
        )
        assert r1.status_code == 201
        assert r1.headers.get("etag") == '"1"'
        body1 = r1.json()
        assert body1["status"] == "empty"
        assert body1["revision"] == 1
        assert "backing_corpus_name" not in body1

        r2 = client.post(
            "/v1/workspaces",
            json={"title": "Desk", "description": "d"},
            headers=headers,
        )
        assert r2.status_code == 201
        assert r2.json()["workspace_id"] == body1["workspace_id"]

        r3 = client.post(
            "/v1/workspaces",
            json={"title": "Other", "description": "d"},
            headers=headers,
        )
        assert r3.status_code == 409
        assert r3.json()["error"]["code"] == "idempotency_conflict"


def test_etag_if_match_and_metadata_patch(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/v1/workspaces",
            json={"title": "Desk"},
            headers={"Idempotency-Key": "c1"},
        ).json()
        wid = created["workspace_id"]

        missing = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p1"},
        )
        assert missing.status_code == 422

        weak = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p2", "If-Match": 'W/"1"'},
        )
        assert weak.status_code == 422

        stale = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p3", "If-Match": '"9"'},
        )
        assert stale.status_code == 409

        ok = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p4", "If-Match": '"1"'},
        )
        assert ok.status_code == 200
        assert ok.json()["revision"] == 2
        assert ok.json()["title"] == "Renamed"
        assert ok.json()["current_snapshot_id"] is None
        assert ok.headers.get("etag") == '"2"'


def test_tombstone_excludes_from_list_and_query(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        created = client.post(
            "/v1/workspaces",
            json={"title": "Gone"},
            headers={"Idempotency-Key": "t1"},
        ).json()
        wid = created["workspace_id"]
        deleted = client.delete(
            f"/v1/workspaces/{wid}",
            headers={"Idempotency-Key": "td", "If-Match": '"1"'},
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "tombstoned"
        listed = client.get("/v1/workspaces")
        assert all(item["workspace_id"] != wid for item in listed.json())
        get = client.get(f"/v1/workspaces/{wid}")
        assert get.status_code == 404
        query = client.post(
            f"/v1/workspaces/{wid}/query", json={"question": "hello world?"}
        )
        assert query.status_code == 404


def test_empty_workspace_query_not_ready(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        wid = client.post(
            "/v1/workspaces",
            json={"title": "EmptyQ"},
            headers={"Idempotency-Key": "eq"},
        ).json()["workspace_id"]
        response = client.post(
            f"/v1/workspaces/{wid}/query", json={"question": "what is this?"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "workspace_not_ready"


def test_source_add_query_content_and_rename(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        wid = client.post(
            "/v1/workspaces",
            json={"title": "Active"},
            headers={"Idempotency-Key": "a1"},
        ).json()["workspace_id"]
        content = b"OLD_MARKER then text about valves.\n"
        files = {"files": ("manual.txt", content, "text/plain")}
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "add1", "If-Match": '"1"'},
            files=files,
        )
        assert add.status_code == 202, add.text
        op_id = add.json()["operation_id"]
        assert add.headers.get("location") == f"/v1/operations/{op_id}"
        terminal = _wait_operation(client, op_id)
        assert terminal["status"] == "succeeded", terminal
        assert terminal["result"]["workspace_status"] == "active"
        snapshot_id = terminal["result"]["snapshot_id"]
        assert snapshot_id

        ws = client.get(f"/v1/workspaces/{wid}").json()
        assert ws["status"] == "active"
        assert ws["current_snapshot_id"] == snapshot_id
        assert ws["revision"] >= 2
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 1
        source_id = sources[0]["source_id"]
        assert "vault_object_id" not in sources[0]

        renamed = client.patch(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            json={"display_name": "renamed.txt"},
            headers={
                "Idempotency-Key": "rename1",
                "If-Match": f'"{ws["revision"]}"',
            },
        )
        assert renamed.status_code == 200
        assert renamed.json()["display_name"] == "renamed.txt"
        assert renamed.json()["version"] == sources[0]["version"]
        assert renamed.json()["document_id"] == sources[0]["document_id"]
        after = client.get(f"/v1/workspaces/{wid}").json()
        assert after["revision"] == ws["revision"] + 1
        assert after["current_snapshot_id"] == snapshot_id

        raw = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
        assert raw.status_code == 200
        assert raw.content == content
        assert raw.headers.get("x-content-type-options") == "nosniff"
        assert "no-store" in raw.headers.get("cache-control", "")
        assert raw.headers.get("etag") == f'"{sources[0]["content_hash"]}"'

        # Workspace query EMPTY was covered above; ACTIVE binding is covered by
        # test_slice16b_query_binding.py (FakeReranker/generator). HTTP query
        # still rejects EMPTY and tombstone without scientific download.

def test_slice15_health_still_ok(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        health = client.get("/health")
        assert health.status_code == 200
