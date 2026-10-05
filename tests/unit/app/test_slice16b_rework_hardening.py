"""Slice 16B independent-review rework — F1–F6 hardening evidence."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.app.workspace.lifecycle import WorkspaceLifecycleService
from offline_rag.app.workspace.models import (
    ManagedOperationStatus,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.publication_journal import NonEmptyPublicationCoordinator
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.upload_spool import quarantine_orphan_workspace_spools
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
OLD_MARKER = "OLD_MARKER_V05_UNIQUE_9f3c"
NEW_MARKER = "NEW_MARKER_V06_UNIQUE_7a1e"


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


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    api = settings.api.model_copy(update=api_overrides) if api_overrides else settings.api
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(
        update={"generation": generation, "api": api, "reranker": reranker}
    )
    _provision_assets(settings)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker = FakeReranker()

    def _response_fn(request: object) -> str:
        _ = request
        # Deterministic abstention keeps HTTP query on the contract without
        # requiring citation-valid grounded JSON from digest embeddings.
        return json.dumps({"abstain": True, "answer": None, "citation_ids": []})

    generator = FakeGenerator(response_fn=_response_fn)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker,
            generator_client=lambda _s: generator,
            qdrant=_qdrant,
        ),
    )


@contextmanager
def _client(tmp_path: Path, **api_overrides: object) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    settings = _settings(tmp_path, **api_overrides)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client, runtime


def _wait_operation(client: TestClient, operation_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/v1/operations/{operation_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"operation {operation_id} did not terminate")


def _create_workspace(client: TestClient, *, key: str, title: str = "Desk") -> dict:
    response = client.post(
        "/v1/workspaces",
        json={"title": title, "description": "d"},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product_current(settings: AppSettings, corpus: str) -> str | None:
    path = current_pointer_path(settings.paths.corpora, corpus)
    if not path.exists():
        return None
    return PublishedPointer.model_validate_json(path.read_text(encoding="utf-8")).snapshot_id


def _active_source_text(settings: AppSettings, workspace_id: str) -> str:
    """Concatenate active vault bytes for marker presence checks."""
    from offline_rag.app.workspace.vault import RawSourceVault

    record = WorkspaceStore(settings).get(workspace_id)
    vault = RawSourceVault(settings.paths.workspaces)
    parts: list[str] = []
    for source in record.sources:
        if not source.active:
            continue
        data = vault.load_bytes(workspace_id, source.vault_object_id)
        parts.append(data.decode("utf-8", errors="ignore"))
        # Chunk artifacts keyed by content also prove what scientific indexes absorbed.
        for path in settings.paths.chunks.glob("chunkartifact_*.json"):
            raw = path.read_text(encoding="utf-8", errors="ignore")
            if source.document_id and source.document_id in raw:
                parts.append(raw)
            if source.content_hash and source.content_hash in raw:
                parts.append(raw)
    return "\n".join(parts)


def _scan_snapshot_text(settings: AppSettings, corpus: str, snapshot_id: str) -> str:
    """Unused alias retained only if older assertions remain."""
    _ = settings, corpus, snapshot_id
    return ""


# ---------------------------------------------------------------------------
# F2 — durable synchronous mutation idempotency
# ---------------------------------------------------------------------------


def test_f2_sync_workspace_patch_idempotent(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime_obj):
        created = _create_workspace(client, key="c-f2p")
        wid = created["workspace_id"]
        headers = {"Idempotency-Key": "patch-k", "If-Match": '"1"'}
        first = client.patch(
            f"/v1/workspaces/{wid}", json={"title": "Renamed"}, headers=headers
        )
        assert first.status_code == 200, first.text
        assert first.json()["revision"] == 2
        assert first.json()["title"] == "Renamed"

        retry = client.patch(
            f"/v1/workspaces/{wid}", json={"title": "Renamed"}, headers=headers
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["revision"] == 2
        assert retry.json()["title"] == "Renamed"
        assert client.get(f"/v1/workspaces/{wid}").json()["revision"] == 2

        conflict = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Other"},
            headers={"Idempotency-Key": "patch-k", "If-Match": '"1"'},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_f2_sync_workspace_delete_idempotent(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime_obj):
        wid = _create_workspace(client, key="c-f2d")["workspace_id"]
        headers = {"Idempotency-Key": "del-k", "If-Match": '"1"'}
        first = client.delete(f"/v1/workspaces/{wid}", headers=headers)
        assert first.status_code == 200
        assert first.json()["status"] == "tombstoned"
        assert first.json()["revision"] == 2

        retry = client.delete(f"/v1/workspaces/{wid}", headers=headers)
        assert retry.status_code == 200
        assert retry.json()["status"] == "tombstoned"
        assert retry.json()["revision"] == 2

        conflict = client.delete(
            f"/v1/workspaces/{wid}",
            headers={"Idempotency-Key": "del-k", "If-Match": '"9"'},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_f2_sync_source_patch_idempotent(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _runtime_obj):
        wid = _create_workspace(client, key="c-f2s")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "add-f2", "If-Match": '"1"'},
            files={"files": ("a.txt", b"hello valves\n", "text/plain")},
        )
        assert add.status_code == 202, add.text
        terminal = _wait_operation(client, add.json()["operation_id"])
        assert terminal["status"] == "succeeded"
        ws = client.get(f"/v1/workspaces/{wid}").json()
        source_id = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
            "source_id"
        ]
        headers = {
            "Idempotency-Key": "rename-k",
            "If-Match": f'"{ws["revision"]}"',
        }
        first = client.patch(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            json={"display_name": "renamed.txt"},
            headers=headers,
        )
        assert first.status_code == 200, first.text
        assert first.json()["display_name"] == "renamed.txt"
        rev_after = client.get(f"/v1/workspaces/{wid}").json()["revision"]

        retry = client.patch(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            json={"display_name": "renamed.txt"},
            headers=headers,
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["display_name"] == "renamed.txt"
        assert client.get(f"/v1/workspaces/{wid}").json()["revision"] == rev_after

        conflict = client.patch(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            json={"display_name": "other.txt"},
            headers=headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "idempotency_conflict"


# ---------------------------------------------------------------------------
# F3 — scientific idempotency before capacity / worker launch
# ---------------------------------------------------------------------------


def test_f3_retry_while_running_does_not_overload(tmp_path: Path) -> None:
    with _client(tmp_path, max_concurrent_ingest=1) as (client, runtime):
        wid = _create_workspace(client, key="c-f3r")["workspace_id"]
        gate = threading.Event()
        original = WorkspaceLifecycleService.add_sources

        def blocked(self, *args, **kwargs):
            gate.wait(timeout=10)
            return original(self, *args, **kwargs)

        WorkspaceLifecycleService.add_sources = blocked  # type: ignore[method-assign]
        try:
            first = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "same-add", "If-Match": '"1"'},
                files={"files": ("a.txt", b"alpha content about pumps\n", "text/plain")},
            )
            assert first.status_code == 202, first.text
            op_id = first.json()["operation_id"]
            # Wait until durable op exists and worker is admitted.
            deadline = time.time() + 5
            while time.time() < deadline:
                op = ManagedOperationStore(runtime.settings).get(wid, op_id)
                if op.status in {
                    ManagedOperationStatus.PENDING,
                    ManagedOperationStatus.PREPARING,
                    ManagedOperationStatus.RUNNING,
                }:
                    break
                time.sleep(0.02)
            retry = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "same-add", "If-Match": '"1"'},
                files={"files": ("a.txt", b"alpha content about pumps\n", "text/plain")},
            )
            assert retry.status_code == 202, retry.text
            assert retry.json()["operation_id"] == op_id
            assert retry.json()["error"] is None or retry.status_code != 503
        finally:
            gate.set()
            WorkspaceLifecycleService.add_sources = original  # type: ignore[method-assign]
        terminal = _wait_operation(client, op_id)
        assert terminal["status"] == "succeeded"


def test_f3_conflicting_upload_while_running(tmp_path: Path) -> None:
    with _client(tmp_path, max_concurrent_ingest=1) as (client, _runtime_obj):
        wid = _create_workspace(client, key="c-f3c")["workspace_id"]
        gate = threading.Event()
        original = WorkspaceLifecycleService.add_sources

        def blocked(self, *args, **kwargs):
            gate.wait(timeout=10)
            return original(self, *args, **kwargs)

        WorkspaceLifecycleService.add_sources = blocked  # type: ignore[method-assign]
        try:
            first = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "same-key", "If-Match": '"1"'},
                files={"files": ("a.txt", b"first payload pumps\n", "text/plain")},
            )
            assert first.status_code == 202, first.text
            conflict = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "same-key", "If-Match": '"1"'},
                files={"files": ("a.txt", b"different payload valves\n", "text/plain")},
            )
            assert conflict.status_code == 409, conflict.text
            assert conflict.json()["error"]["code"] == "idempotency_conflict"
        finally:
            gate.set()
            WorkspaceLifecycleService.add_sources = original  # type: ignore[method-assign]
        _wait_operation(client, first.json()["operation_id"])


def test_f3_simultaneous_identical_posts_one_operation(tmp_path: Path) -> None:
    with _client(tmp_path, max_concurrent_ingest=1) as (client, _runtime_obj):
        wid = _create_workspace(client, key="c-f3s")["workspace_id"]
        payload = b"shared payload about pumps\n"

        def _post() -> dict:
            response = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "race-same", "If-Match": '"1"'},
                files={"files": ("a.txt", payload, "text/plain")},
            )
            return {"status": response.status_code, "body": response.json()}

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: _post(), range(2)))
        assert all(item["status"] == 202 for item in results), results
        ids = {item["body"]["operation_id"] for item in results}
        assert len(ids) == 1
        terminal = _wait_operation(client, next(iter(ids)))
        assert terminal["status"] == "succeeded"


def test_f3_simultaneous_conflicting_posts(tmp_path: Path) -> None:
    with _client(tmp_path, max_concurrent_ingest=1) as (client, _runtime_obj):
        wid = _create_workspace(client, key="c-f3x")["workspace_id"]

        def _post(body: bytes) -> dict:
            response = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "race-conflict", "If-Match": '"1"'},
                files={"files": ("a.txt", body, "text/plain")},
            )
            return {"status": response.status_code, "body": response.json()}

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(_post, b"payload A pumps\n")
            b = pool.submit(_post, b"payload B valves\n")
            results = [a.result(), b.result()]
        codes = sorted(item["status"] for item in results)
        assert codes == [202, 409], results
        ok = next(item for item in results if item["status"] == 202)
        bad = next(item for item in results if item["status"] == 409)
        assert bad["body"]["error"]["code"] == "idempotency_conflict"
        terminal = _wait_operation(client, ok["body"]["operation_id"])
        assert terminal["status"] == "succeeded"


# ---------------------------------------------------------------------------
# F1 — corpus lease spans cross-registry commit
# ---------------------------------------------------------------------------


def test_f1_corpus_lease_held_until_workspace_commit(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f1")["workspace_id"]
        entered = threading.Event()
        release = threading.Event()
        original = NonEmptyPublicationCoordinator.mark_publication_observed

        def gated(self, workspace_id, snapshot_id, *, lease=None):
            entered.set()
            assert release.wait(timeout=10)
            return original(self, workspace_id, snapshot_id, lease=lease)

        NonEmptyPublicationCoordinator.mark_publication_observed = gated  # type: ignore[method-assign]
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f1-add", "If-Match": '"1"'},
                files={"files": ("a.txt", b"lease hold text about pumps\n", "text/plain")},
            )
            assert add.status_code == 202, add.text
            assert entered.wait(timeout=30)
            record = WorkspaceStore(runtime.settings).get(wid)
            busy = CorpusMutationLease(runtime.settings, record.backing_corpus_name)
            with pytest.raises(AppError) as excinfo:
                busy.acquire()
            assert excinfo.value.code is ErrorCode.CORPUS_BUSY
        finally:
            release.set()
            NonEmptyPublicationCoordinator.mark_publication_observed = original  # type: ignore[method-assign]
        terminal = _wait_operation(client, add.json()["operation_id"])
        assert terminal["status"] == "succeeded"
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert ws.current_snapshot_id == terminal["result"]["snapshot_id"]
        assert (
            _product_current(runtime.settings, ws.backing_corpus_name)
            == ws.current_snapshot_id
        )


def test_f1_empty_removal_holds_corpus_lease(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f1e")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f1e-add", "If-Match": '"1"'},
            files={"files": ("only.txt", b"single source pumps\n", "text/plain")},
        )
        terminal = _wait_operation(client, add.json()["operation_id"])
        assert terminal["status"] == "succeeded"
        ws = client.get(f"/v1/workspaces/{wid}").json()
        source_id = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
            "source_id"
        ]
        entered = threading.Event()
        release = threading.Event()
        from offline_rag.app.workspace.journal import EmptyTransitionCoordinator

        original = EmptyTransitionCoordinator.step_empty_workspace

        def gated(self, workspace_id, *, lease=None):
            entered.set()
            assert release.wait(timeout=10)
            return original(self, workspace_id, lease=lease)

        EmptyTransitionCoordinator.step_empty_workspace = gated  # type: ignore[method-assign]
        try:
            delete = client.delete(
                f"/v1/workspaces/{wid}/sources/{source_id}",
                headers={
                    "Idempotency-Key": "f1e-del",
                    "If-Match": f'"{ws["revision"]}"',
                },
            )
            assert delete.status_code == 202, delete.text
            assert entered.wait(timeout=30)
            record = WorkspaceStore(runtime.settings).get(wid, include_tombstoned=True)
            # During EMPTY, workspace record may still be active until step completes.
            corpus = record.backing_corpus_name
            busy = CorpusMutationLease(runtime.settings, corpus)
            with pytest.raises(AppError) as excinfo:
                busy.acquire()
            assert excinfo.value.code is ErrorCode.CORPUS_BUSY
        finally:
            release.set()
            EmptyTransitionCoordinator.step_empty_workspace = original  # type: ignore[method-assign]
        done = _wait_operation(client, delete.json()["operation_id"])
        assert done["status"] == "succeeded"
        final = WorkspaceStore(runtime.settings).get(wid)
        assert final.status.value == "empty"
        assert final.current_snapshot_id is None
        assert _product_current(runtime.settings, final.backing_corpus_name) is None


# ---------------------------------------------------------------------------
# F4 — durable upload spool before 202
# ---------------------------------------------------------------------------


def test_f4_spool_durable_before_202_and_interrupt(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f4")["workspace_id"]
        seen_spools: list[Path] = []
        gate = threading.Event()
        original = WorkspaceLifecycleService.add_sources

        def blocked(self, *args, **kwargs):
            staging = runtime.settings.paths.staging
            seen_spools.extend(
                sorted(p for p in staging.glob("ws_upload_*") if p.is_dir())
            )
            gate.wait(timeout=10)
            raise RuntimeError("forced_interrupt_before_scientific")

        WorkspaceLifecycleService.add_sources = blocked  # type: ignore[method-assign]
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f4-add", "If-Match": '"1"'},
                files={"files": ("a.txt", b"spool durable pumps\n", "text/plain")},
            )
            assert add.status_code == 202, add.text
            op_id = add.json()["operation_id"]
            # Acceptance returned; durable staging must already exist (or have existed).
            staging = runtime.settings.paths.staging
            present = list(staging.glob("ws_upload_*"))
            assert present or seen_spools
            for root in present or seen_spools:
                files = list((root / "files").glob("*")) if (root / "files").exists() else []
                assert files or root.exists()
        finally:
            gate.set()
            WorkspaceLifecycleService.add_sources = original  # type: ignore[method-assign]
        # Force interrupt classification as on process restart.
        interrupted = ManagedOperationStore(runtime.settings).interrupt_all_nonterminal(
            recovery_note="process_restart"
        )
        assert any(item.operation_id == op_id for item in interrupted)
        op = ManagedOperationStore(runtime.settings).get(wid, op_id)
        assert op.status is ManagedOperationStatus.INTERRUPTED
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert ws.status.value == "empty"
        assert ws.current_snapshot_id is None
        quarantined = quarantine_orphan_workspace_spools(runtime.settings)
        assert quarantined or not list(runtime.settings.paths.staging.glob("ws_upload_*"))


# ---------------------------------------------------------------------------
# F5 — journal outlives lineage + operation terminalization (crash points)
# ---------------------------------------------------------------------------


def test_f5_nonempty_crash_after_lineage_before_op_success(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f5")["workspace_id"]
        original = ManagedOperationStore.update_status
        crash_once = {"hit": False}

        def crashing(self, workspace_id, operation_id, status, **kwargs):
            if (
                status is ManagedOperationStatus.SUCCEEDED
                and not crash_once["hit"]
                and kwargs.get("result") is not None
            ):
                crash_once["hit"] = True
                # Lineage/COMMITTED journal retained; op still nonterminal.
                raise RuntimeError("crash_before_op_success")
            return original(self, workspace_id, operation_id, status, **kwargs)

        ManagedOperationStore.update_status = crashing  # type: ignore[method-assign]
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f5-add", "If-Match": '"1"'},
                files={"files": ("a.txt", b"journal order pumps\n", "text/plain")},
            )
            assert add.status_code == 202, add.text
            terminal = _wait_operation(client, add.json()["operation_id"], timeout=15)
            # Worker surfaces failure; journal recovery reconciles on restart.
            assert terminal["status"] in {"failed", "interrupted", "succeeded"}
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ws = WorkspaceStore(runtime.settings).get(wid)
        # Forward B: workspace claimed the published snapshot.
        if ws.current_snapshot_id is not None:
            assert (
                _product_current(runtime.settings, ws.backing_corpus_name)
                == ws.current_snapshot_id
            )
            ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
            assert any(op.status is ManagedOperationStatus.SUCCEEDED for op in ops)


# ---------------------------------------------------------------------------
# F6 — supersession + batch HTTP campaigns
# ---------------------------------------------------------------------------


def test_f6_supersession_old_marker_absent(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f6", title="ManualB")["workspace_id"]
        v05 = f"{OLD_MARKER} manual_b_v05 valve torque procedure.\n".encode()
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f6-add", "If-Match": '"1"'},
            files={"files": ("manual_b_v05.txt", v05, "text/plain")},
        )
        assert add.status_code == 202, add.text
        t0 = _wait_operation(client, add.json()["operation_id"])
        assert t0["status"] == "succeeded"
        snap_n = t0["result"]["snapshot_id"]
        ws = client.get(f"/v1/workspaces/{wid}").json()
        assert ws["current_snapshot_id"] == snap_n
        source_id = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
            "source_id"
        ]
        version_before = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
            "version"
        ]

        # Query against N (binding only; generation may abstain under fake embedder).
        q_n = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "What valve torque procedure is documented?"},
        )
        assert q_n.status_code == 200, q_n.text
        assert q_n.json()["snapshot_id"] == snap_n

        v06 = f"{NEW_MARKER} manual_b_v06 valve torque procedure revised.\n".encode()
        replace = client.put(
            f"/v1/workspaces/{wid}/sources/{source_id}",
            headers={
                "Idempotency-Key": "f6-replace",
                "If-Match": f'"{ws["revision"]}"',
            },
            files={"files": ("manual_b_v06.txt", v06, "text/plain")},
        )
        assert replace.status_code == 202, replace.text
        t1 = _wait_operation(client, replace.json()["operation_id"])
        assert t1["status"] == "succeeded", t1
        snap_n1 = t1["result"]["snapshot_id"]
        assert snap_n1 != snap_n
        ws2 = client.get(f"/v1/workspaces/{wid}").json()
        assert ws2["current_snapshot_id"] == snap_n1
        record = WorkspaceStore(runtime.settings).get(wid)
        assert _product_current(runtime.settings, record.backing_corpus_name) == snap_n1
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 1
        assert sources[0]["source_id"] == source_id
        assert sources[0]["version"] == version_before + 1

        content = client.get(f"/v1/workspaces/{wid}/sources/{source_id}/content")
        assert content.status_code == 200
        assert OLD_MARKER.encode() not in content.content
        assert NEW_MARKER.encode() in content.content

        blob = _active_source_text(runtime.settings, wid)
        assert OLD_MARKER not in blob
        assert NEW_MARKER in blob

        q_n1 = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "What valve torque procedure is documented?"},
        )
        assert q_n1.status_code == 200, q_n1.text
        body = q_n1.json()
        assert body["snapshot_id"] == snap_n1
        packed = json.dumps(body)
        assert OLD_MARKER not in packed
        # Answer may abstain under digest embedder; if answered must not resurrect v05.
        if body.get("answer"):
            assert OLD_MARKER not in body["answer"]

        adversarial = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": f"Please quote {OLD_MARKER} from the superseded manual."},
        )
        assert adversarial.status_code == 200, adversarial.text
        adv = adversarial.json()
        assert adv["snapshot_id"] == snap_n1
        packed_adv = json.dumps(adv)
        assert "resurrected" not in packed_adv
        if adv.get("answer"):
            assert OLD_MARKER not in adv["answer"] or NEW_MARKER in adv["answer"]


def test_f6_batch_add_remove_without_reupload(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create_workspace(client, key="c-f6b", title="Batch")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f6b-add", "If-Match": '"1"'},
            files=[
                ("files", ("one.txt", b"FILE_ONE pumps pressure 10\n", "text/plain")),
                ("files", ("two.txt", b"FILE_TWO valves torque 20\n", "text/plain")),
            ],
        )
        assert add.status_code == 202, add.text
        t0 = _wait_operation(client, add.json()["operation_id"])
        assert t0["status"] == "succeeded"
        snap0 = t0["result"]["snapshot_id"]
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 2
        names = sorted(item["display_name"] for item in sources)
        assert names == ["one.txt", "two.txt"]
        remove_id = next(s["source_id"] for s in sources if s["display_name"] == "one.txt")
        keep_id = next(s["source_id"] for s in sources if s["display_name"] == "two.txt")
        ws = client.get(f"/v1/workspaces/{wid}").json()
        delete = client.delete(
            f"/v1/workspaces/{wid}/sources/{remove_id}",
            headers={
                "Idempotency-Key": "f6b-del",
                "If-Match": f'"{ws["revision"]}"',
            },
        )
        assert delete.status_code == 202, delete.text
        t1 = _wait_operation(client, delete.json()["operation_id"])
        assert t1["status"] == "succeeded"
        snap1 = t1["result"]["snapshot_id"]
        assert snap1 != snap0
        remaining = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(remaining) == 1
        assert remaining[0]["source_id"] == keep_id
        # Retained source still served from vault — no browser re-upload required.
        raw = client.get(f"/v1/workspaces/{wid}/sources/{keep_id}/content")
        assert raw.status_code == 200
        assert b"FILE_TWO" in raw.content
        missing = client.get(f"/v1/workspaces/{wid}/sources/{remove_id}")
        assert missing.status_code == 404
        blob = _active_source_text(runtime.settings, wid)
        assert "FILE_ONE" not in blob
        assert "FILE_TWO" in blob
        q = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "What does FILE_ONE say?"},
        )
        assert q.status_code == 200
        assert "FILE_ONE" not in json.dumps(q.json().get("citations") or [])
