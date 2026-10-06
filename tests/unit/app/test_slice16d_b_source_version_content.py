"""Slice 16D-B — exact-version source content evidence reads."""

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
from offline_rag.app.workspace.history import SourceHistoryStore
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.vault import RawSourceVault
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
V1_MARKER = "VERSION_ONE_BYTES_16DB_a91f"
V2_MARKER = "VERSION_TWO_BYTES_16DB_b72e"


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


@contextmanager
def _client(tmp_path: Path) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client, runtime


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


def _create_workspace(client: TestClient, *, key: str = "16db") -> dict:
    response = client.post(
        "/v1/workspaces",
        json={"title": "Evidence Desk", "description": ""},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_text(
    client: TestClient,
    wid: str,
    *,
    revision: int,
    name: str,
    content: bytes,
    key: str,
) -> dict:
    response = client.post(
        f"/v1/workspaces/{wid}/sources",
        headers={"Idempotency-Key": key, "If-Match": f'"{revision}"'},
        files={"files": (name, content, "text/plain")},
    )
    assert response.status_code == 202, response.text
    terminal = _wait_operation(client, response.json()["operation_id"])
    assert terminal["status"] == "succeeded", terminal
    return terminal


def _version_url(wid: str, source_id: str, version: int, revision: int) -> str:
    return (
        f"/v1/workspaces/{wid}/sources/{source_id}/versions/{version}/content"
        f"?workspace_revision={revision}"
    )


def test_exact_version_content_after_replace(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime):
        ws = _create_workspace(client)
        wid = ws["workspace_id"]
        v1 = f"{V1_MARKER} original manual text.\n".encode()
        _add_text(client, wid, revision=1, name="manual.txt", content=v1, key="add-v1")
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 1
        source_id = sources[0]["source_id"]
        assert sources[0]["version"] == 1
        rev_v1 = client.get(f"/v1/workspaces/{wid}").json()["revision"]

        current = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
        assert current.status_code == 200
        assert current.content == v1
        assert current.headers.get("x-content-type-options") == "nosniff"
        assert "no-store" in current.headers.get("cache-control", "")
        assert current.headers.get("etag") == f'"{sources[0]["content_hash"]}"'
        assert "inline" in current.headers.get("content-disposition", "")
        packed = current.content + current.headers.get("content-disposition", "").encode()
        assert b"vault" not in packed.lower()
        assert b"/" not in current.headers.get("etag", "").encode()

        hist = client.get(_version_url(wid, source_id, 1, rev_v1))
        assert hist.status_code == 200
        assert hist.content == v1

        v2 = f"{V2_MARKER} replaced manual text.\n".encode()
        replace = client.put(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            headers={"Idempotency-Key": "replace-v2", "If-Match": f'"{rev_v1}"'},
            files={"files": ("manual.txt", v2, "text/plain")},
        )
        assert replace.status_code == 202, replace.text
        terminal = _wait_operation(client, replace.json()["operation_id"])
        assert terminal["status"] == "succeeded", terminal
        rev_v2 = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        sources2 = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert sources2[0]["version"] == 2

        current2 = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
        assert current2.status_code == 200
        assert current2.content == v2
        assert V1_MARKER.encode() not in current2.content

        hist_v1 = client.get(_version_url(wid, source_id, 1, rev_v1))
        assert hist_v1.status_code == 200
        assert hist_v1.content == v1
        assert V2_MARKER.encode() not in hist_v1.content

        hist_v2 = client.get(_version_url(wid, source_id, 2, rev_v2))
        assert hist_v2.status_code == 200
        assert hist_v2.content == v2


def test_historical_content_after_remove_and_empty(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        ws = _create_workspace(client, key="16db-rm")
        wid = ws["workspace_id"]
        a = b"FILE_A keep lineage\n"
        b = b"FILE_B remaining\n"
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "add-ab", "If-Match": '"1"'},
            files=[
                ("files", ("a.txt", a, "text/plain")),
                ("files", ("b.txt", b, "text/plain")),
            ],
        )
        assert add.status_code == 202, add.text
        assert _wait_operation(client, add.json()["operation_id"])["status"] == "succeeded"
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 2
        remove_id = next(s["source_id"] for s in sources if s["display_name"] == "a.txt")
        keep_id = next(s["source_id"] for s in sources if s["display_name"] == "b.txt")
        rev_before = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        removed_version = next(s["version"] for s in sources if s["source_id"] == remove_id)

        delete = client.delete(
            f"/v1/workspaces/{wid}/sources/{remove_id}",
            headers={
                "Idempotency-Key": "del-a",
                "If-Match": f'"{rev_before}"',
            },
        )
        assert delete.status_code == 202, delete.text
        terminal = _wait_operation(client, delete.json()["operation_id"])
        assert terminal["status"] == "succeeded", terminal

        hist = client.get(_version_url(wid, remove_id, removed_version, rev_before))
        assert hist.status_code == 200
        assert hist.content == a

        # Remove last source → EMPTY; lineage still readable for prior revision.
        rev2 = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        keep_version = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
            "version"
        ]
        delete2 = client.delete(
            f"/v1/workspaces/{wid}/sources/{keep_id}",
            headers={"Idempotency-Key": "del-b", "If-Match": f'"{rev2}"'},
        )
        assert delete2.status_code == 202, delete2.text
        t2 = _wait_operation(client, delete2.json()["operation_id"])
        assert t2["status"] == "succeeded", t2
        empty = client.get(f"/v1/workspaces/{wid}").json()
        assert empty["status"] == "empty"
        assert empty["current_snapshot_id"] is None

        hist_empty = client.get(_version_url(wid, keep_id, keep_version, rev2))
        assert hist_empty.status_code == 200
        assert hist_empty.content == b
        assert SourceHistoryStore(runtime.settings).get(wid, keep_id, keep_version)


def test_version_content_fail_closed_and_tombstone(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        ws = _create_workspace(client, key="16db-fc")
        wid = ws["workspace_id"]
        content = b"fail closed bytes\n"
        _add_text(client, wid, revision=1, name="x.txt", content=content, key="add-x")
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        source_id = sources[0]["source_id"]
        version = sources[0]["version"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]

        # Requesting revision before active_from must fail closed.
        history = SourceHistoryStore(runtime.settings).get(wid, source_id, version)
        early_rev = max(1, history.active_from_revision - 1)
        if early_rev < history.active_from_revision:
            early = client.get(_version_url(wid, source_id, version, early_rev))
            assert early.status_code == 404
            assert early.json()["error"]["code"] == "source_unknown"

        # After supersede via replace, prior revision still works; after through fails.
        replace = client.put(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            headers={"Idempotency-Key": "repl-fc", "If-Match": f'"{rev}"'},
            files={"files": ("x.txt", b"second\n", "text/plain")},
        )
        assert replace.status_code == 202
        assert _wait_operation(client, replace.json()["operation_id"])["status"] == "succeeded"
        closed = SourceHistoryStore(runtime.settings).get(wid, source_id, version)
        assert closed.active_through_revision is not None
        after_through = closed.active_through_revision + 1
        late = client.get(_version_url(wid, source_id, version, after_through))
        assert late.status_code == 404
        assert late.json()["error"]["code"] == "source_unknown"

        unknown = client.get(_version_url(wid, source_id, 99, rev))
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "source_unknown"

        bad_rev = client.get(
            f"/v1/workspaces/{wid}/sources/{source_id}/versions/{version}/content"
            "?workspace_revision=0"
        )
        assert bad_rev.status_code == 422

        # Corrupt vault hash → state unavailable; no path leakage.
        v2 = SourceHistoryStore(runtime.settings).get(wid, source_id, 2)
        vault = RawSourceVault(runtime.settings.paths.workspaces)
        obj = (
            runtime.settings.paths.workspaces
            / wid
            / "vault"
            / "objects"
            / v2.vault_object_id
        )
        assert obj.exists()
        obj.write_bytes(b"tampered-bytes-not-matching-hash")
        del vault
        corrupt = client.get(
            _version_url(
                wid,
                source_id,
                2,
                client.get(f"/v1/workspaces/{wid}").json()["revision"],
            )
        )
        assert corrupt.status_code == 409
        assert corrupt.json()["error"]["code"] == "workspace_state_unavailable"
        assert "vault_object_id" not in corrupt.text
        assert str(obj) not in corrupt.text

        # Tombstone denies.
        ws_live = client.get(f"/v1/workspaces/{wid}").json()
        deleted = client.delete(
            f"/v1/workspaces/{wid}",
            headers={
                "Idempotency-Key": "tombstone",
                "If-Match": f'"{ws_live["revision"]}"',
            },
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "tombstoned"
        tomb = client.get(_version_url(wid, source_id, 1, rev))
        assert tomb.status_code == 404
        assert tomb.json()["error"]["code"] == "workspace_unknown"
        assert (
            WorkspaceStore(runtime.settings)
            .get(wid, include_tombstoned=True)
            .status.value
            == "tombstoned"
        )
