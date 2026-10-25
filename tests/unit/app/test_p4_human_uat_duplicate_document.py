"""P4 human-UAT — duplicate document identity classification."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import DOCUMENT_ALREADY_PRESENT_MESSAGE
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


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    settings = _settings(tmp_path)
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )
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


def _create_workspace(client: TestClient, *, key: str = "ws1") -> tuple[str, int]:
    body = client.post(
        "/v1/workspaces",
        json={"title": "DupUAT"},
        headers={"Idempotency-Key": key},
    ).json()
    return body["workspace_id"], int(body["revision"])


def _add_and_wait(
    client: TestClient,
    wid: str,
    rev: int,
    *,
    files: list[tuple[str, bytes, str]],
    key: str,
) -> dict:
    response = client.post(
        f"/v1/workspaces/{wid}/sources",
        headers={"Idempotency-Key": key, "If-Match": f'"{rev}"'},
        files=[("files", item) for item in files],
    )
    assert response.status_code == 202, response.text
    return _wait_operation(client, response.json()["operation_id"])


def test_duplicate_active_file_rejects_with_identity_message(tmp_path: Path) -> None:
    content = b"canonical duplicate body for UAT\n"
    with _client(tmp_path) as client:
        wid, rev = _create_workspace(client)
        first = _add_and_wait(
            client,
            wid,
            rev,
            files=[("manual.txt", content, "text/plain")],
            key="add-first",
        )
        assert first["status"] == "succeeded", first
        ws = client.get(f"/v1/workspaces/{wid}").json()
        sources_before = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources_before) == 1

        dup = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={
                "Idempotency-Key": "add-dup",
                "If-Match": f'"{ws["revision"]}"',
            },
            files={"files": ("manual.txt", content, "text/plain")},
        )
        assert dup.status_code == 202, dup.text
        terminal = _wait_operation(client, dup.json()["operation_id"])
        assert terminal["status"] == "failed", terminal
        err = terminal["error"]
        assert err["code"] == "document_invalid"
        assert err["details"]["reason"] == "document_identity_conflict"
        assert err["message"] == DOCUMENT_ALREADY_PRESENT_MESSAGE

        after = client.get(f"/v1/workspaces/{wid}").json()
        sources_after = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert after["revision"] == ws["revision"]
        assert len(sources_after) == 1


def test_duplicate_same_bytes_different_filename(tmp_path: Path) -> None:
    content = b"same-bytes-different-name\n"
    with _client(tmp_path) as client:
        wid, rev = _create_workspace(client)
        first = _add_and_wait(
            client,
            wid,
            rev,
            files=[("A.txt", content, "text/plain")],
            key="add-a",
        )
        assert first["status"] == "succeeded", first
        ws = client.get(f"/v1/workspaces/{wid}").json()
        dup = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={
                "Idempotency-Key": "add-renamed",
                "If-Match": f'"{ws["revision"]}"',
            },
            files={"files": ("renamed-copy.txt", content, "text/plain")},
        )
        assert dup.status_code == 202, dup.text
        terminal = _wait_operation(client, dup.json()["operation_id"])
        assert terminal["status"] == "failed", terminal
        assert terminal["error"]["details"]["reason"] == "document_identity_conflict"
        assert terminal["error"]["message"] == DOCUMENT_ALREADY_PRESENT_MESSAGE
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 1


def test_duplicate_within_same_add_sources_request(tmp_path: Path) -> None:
    content = b"batch-internal-duplicate\n"
    with _client(tmp_path) as client:
        wid, rev = _create_workspace(client)
        response = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "batch-dup", "If-Match": f'"{rev}"'},
            files=[
                ("files", ("A.txt", content, "text/plain")),
                ("files", ("A-copy.txt", content, "text/plain")),
            ],
        )
        # Immediate spool conflict or async plan conflict — either is fail-closed.
        if response.status_code == 422:
            body = response.json()
            assert body["error"]["code"] == "document_invalid"
            assert body["details"]["reason"] == "document_identity_conflict"
            assert body["error"]["message"] == DOCUMENT_ALREADY_PRESENT_MESSAGE
        else:
            assert response.status_code == 202, response.text
            terminal = _wait_operation(client, response.json()["operation_id"])
            assert terminal["status"] == "failed", terminal
            assert terminal["error"]["details"]["reason"] == "document_identity_conflict"
            assert terminal["error"]["message"] == DOCUMENT_ALREADY_PRESENT_MESSAGE
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert sources == []


def test_distinct_files_still_ingest(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        wid, rev = _create_workspace(client)
        first = _add_and_wait(
            client,
            wid,
            rev,
            files=[("a.txt", b"document-a\n", "text/plain")],
            key="add-a",
        )
        assert first["status"] == "succeeded", first
        ws = client.get(f"/v1/workspaces/{wid}").json()
        second = _add_and_wait(
            client,
            wid,
            int(ws["revision"]),
            files=[("b.txt", b"document-b\n", "text/plain")],
            key="add-b",
        )
        assert second["status"] == "succeeded", second
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 2


def test_empty_document_keeps_generic_invalid_message(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        wid, rev = _create_workspace(client)
        response = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "empty", "If-Match": f'"{rev}"'},
            files={"files": ("empty.txt", b"", "text/plain")},
        )
        assert response.status_code == 422, response.text
        body = response.json()
        # Empty upload is rejected as invalid input — not as a duplicate.
        assert body["error"]["code"] in {"document_invalid", "request_invalid"}
        reason = (body.get("details") or {}).get("reason")
        assert reason != "document_identity_conflict"
        assert body["error"]["message"] != DOCUMENT_ALREADY_PRESENT_MESSAGE
        if body["error"]["code"] == "document_invalid" and reason == "empty_document":
            assert body["error"]["message"] == "Submitted document is invalid"
