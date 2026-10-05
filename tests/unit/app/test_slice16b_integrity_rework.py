"""Slice 16B final integrity rework — F7–F12 + corpus ownership."""

from __future__ import annotations

import json
import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.query import run_workspace_query
from offline_rag.app.query_binding import build_snapshot_query_binding
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import PublishedPointer
from offline_rag.app.workspace.models import ManagedOperationStatus
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.publication_journal import NonEmptyPublicationCoordinator
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.app.workspace.sync_journal import SyncMutationCoordinator
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.lexical.retrieve import LexicalRetriever
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


def _provision(settings: AppSettings) -> None:
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
    _provision(settings)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    presented: list[str] = []

    class _RecordingReranker(FakeReranker):
        def score_pairs(self, pairs):
            for pair in pairs:
                presented.append(getattr(pair, "passage_text", "") or "")
            return super().score_pairs(pairs)

    settings._test_presented = presented  # type: ignore[attr-defined]
    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker = _RecordingReranker()
    generator = FakeGenerator(
        default_response=json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )

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
def _client(tmp_path: Path, **api: object) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    settings = _settings(tmp_path, **api)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app) as client:
        yield client, runtime


def _wait(client: TestClient, op_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/operations/{op_id}").json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"op {op_id} did not terminate")


def _create(client: TestClient, key: str = "c") -> dict:
    r = client.post(
        "/v1/workspaces",
        json={"title": "Desk", "description": "d"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _product_current(settings: AppSettings, corpus: str) -> str | None:
    path = current_pointer_path(settings.paths.corpora, corpus)
    if not path.exists():
        return None
    return PublishedPointer.model_validate_json(path.read_text(encoding="utf-8")).snapshot_id


# ---------------------------------------------------------------------------
# F8 — pre-202 validation
# ---------------------------------------------------------------------------


def test_f8_stale_if_match_rejected_before_202(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f8")["workspace_id"]
        stale = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "stale-add", "If-Match": '"9"'},
            files={"files": ("a.txt", b"stale pumps\n", "text/plain")},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "workspace_conflict"
        ops = ManagedOperationStore(_rt.settings).list_for_workspace(wid)
        assert ops == []


def test_f8_unknown_source_replace_remove(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f8u")["workspace_id"]
        missing = client.put(
            f"/v1/workspaces/{wid}/sources/src_deadbeefdeadbeefdeadbeefdeadbeef",
            headers={"Idempotency-Key": "rep", "If-Match": '"1"'},
            files={"files": ("a.txt", b"x pumps\n", "text/plain")},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "source_unknown"
        missing_del = client.delete(
            f"/v1/workspaces/{wid}/sources/src_deadbeefdeadbeefdeadbeefdeadbeef",
            headers={"Idempotency-Key": "del", "If-Match": '"1"'},
        )
        assert missing_del.status_code == 404


def test_f8_exact_retry_with_historical_revision(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f8r")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "hist", "If-Match": '"1"'},
            files={"files": ("a.txt", b"hist pumps\n", "text/plain")},
        )
        assert add.status_code == 202
        op_id = add.json()["operation_id"]
        assert _wait(client, op_id)["status"] == "succeeded"
        # Workspace advanced; exact retry with historical If-Match still recovers.
        retry = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "hist", "If-Match": '"1"'},
            files={"files": ("a.txt", b"hist pumps\n", "text/plain")},
        )
        assert retry.status_code == 202
        assert retry.json()["operation_id"] == op_id


# ---------------------------------------------------------------------------
# F9 — exact sync replay
# ---------------------------------------------------------------------------


def test_f9_workspace_patch_replay_frozen_source_count(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f9")["workspace_id"]
        first = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p", "If-Match": '"1"'},
        )
        assert first.status_code == 200
        assert first.json()["source_count"] == 0
        assert first.json()["revision"] == 2
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "add", "If-Match": '"2"'},
            files={"files": ("a.txt", b"later pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        live = client.get(f"/v1/workspaces/{wid}").json()
        assert live["source_count"] == 1
        assert live["revision"] >= 3
        retry = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "Renamed"},
            headers={"Idempotency-Key": "p", "If-Match": '"1"'},
        )
        assert retry.status_code == 200
        assert retry.json() == first.json()


def test_f9_failed_sync_replay_not_200(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f9f")["workspace_id"]
        fail = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "X"},
            headers={"Idempotency-Key": "bad", "If-Match": '"9"'},
        )
        assert fail.status_code == 409
        retry = client.patch(
            f"/v1/workspaces/{wid}",
            json={"title": "X"},
            headers={"Idempotency-Key": "bad", "If-Match": '"9"'},
        )
        assert retry.status_code == 409
        assert retry.json()["error"]["code"] == "workspace_conflict"


def test_f9_source_rename_replay_after_replace(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, _rt):
        wid = _create(client, "f9s")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "a", "If-Match": '"1"'},
            files={"files": ("a.txt", b"rename pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        ws = client.get(f"/v1/workspaces/{wid}").json()
        sid = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]["source_id"]
        rename = client.patch(
            f"/v1/workspaces/{wid}/sources/{sid}",
            json={"display_name": "renamed.txt"},
            headers={"Idempotency-Key": "rn", "If-Match": f'"{ws["revision"]}"'},
        )
        assert rename.status_code == 200
        original = rename.json()
        assert original["display_name"] == "renamed.txt"
        assert original["version"] == 1
        ws2 = client.get(f"/v1/workspaces/{wid}").json()
        repl = client.put(
            f"/v1/workspaces/{wid}/sources/{sid}",
            headers={"Idempotency-Key": "rp", "If-Match": f'"{ws2["revision"]}"'},
            files={"files": ("b.txt", b"replaced pumps\n", "text/plain")},
        )
        assert _wait(client, repl.json()["operation_id"])["status"] == "succeeded"
        live = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        assert live["version"] == 2
        retry = client.patch(
            f"/v1/workspaces/{wid}/sources/{sid}",
            json={"display_name": "renamed.txt"},
            headers={"Idempotency-Key": "rn", "If-Match": f'"{ws["revision"]}"'},
        )
        assert retry.status_code == 200
        assert retry.json() == original


# ---------------------------------------------------------------------------
# F10 / F13 — sync mutation three-point crash matrix
# ---------------------------------------------------------------------------


def _f13_prepare_workspace_patch(
    settings: AppSettings, wid: str, *, title: str, idem: str
):
    from offline_rag.app.workspace.leases import WorkspaceMutationLease
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationResult,
        advance_revision,
        utc_now,
    )

    ops = ManagedOperationStore(settings)
    store = WorkspaceStore(settings)
    sync = SyncMutationCoordinator(settings)
    with WorkspaceMutationLease(settings, wid) as lease:
        current = store.get(wid)
        op = ops.begin(
            workspace_id=wid,
            idempotency_key=idem,
            kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
            request_payload={"title": title, "description": ""},
            expected_revision=current.revision,
            lease=lease,
        )
        prepared = current.model_copy(
            update={
                "title": title,
                "description": "",
                "revision": advance_revision(current.revision),
                "updated_at": utc_now(),
            }
        )
        result = ManagedOperationResult(
            workspace_revision=prepared.revision,
            workspace_status=prepared.status,
            snapshot_id=prepared.current_snapshot_id,
            title=prepared.title,
            description=prepared.description,
            source_count=len([s for s in prepared.sources if s.active]),
            created_at=prepared.created_at,
            updated_at=prepared.updated_at,
        )
        sync.begin(
            wid,
            operation_id=op.operation_id,
            kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
            expected_revision=current.revision,
            expected_result=result,
            lease=lease,
        )
        return op, prepared, result, sync, store, ops, current.revision


def _f13_prepare_workspace_delete(settings: AppSettings, wid: str, *, idem: str):
    from offline_rag.app.workspace.leases import WorkspaceMutationLease
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationResult,
        WorkspaceStatus,
        advance_revision,
        utc_now,
    )

    ops = ManagedOperationStore(settings)
    store = WorkspaceStore(settings)
    sync = SyncMutationCoordinator(settings)
    with WorkspaceMutationLease(settings, wid) as lease:
        current = store.get(wid)
        op = ops.begin(
            workspace_id=wid,
            idempotency_key=idem,
            kind=ManagedOperationKind.WORKSPACE_DELETE,
            request_payload={"action": "tombstone"},
            expected_revision=current.revision,
            lease=lease,
        )
        prepared = current.model_copy(
            update={
                "status": WorkspaceStatus.TOMBSTONED,
                "current_snapshot_id": None,
                "revision": advance_revision(current.revision),
                "updated_at": utc_now(),
            }
        )
        result = ManagedOperationResult(
            workspace_revision=prepared.revision,
            workspace_status=prepared.status,
            snapshot_id=None,
            title=prepared.title,
            description=prepared.description,
            source_count=len([s for s in prepared.sources if s.active]),
            created_at=prepared.created_at,
            updated_at=prepared.updated_at,
        )
        sync.begin(
            wid,
            operation_id=op.operation_id,
            kind=ManagedOperationKind.WORKSPACE_DELETE,
            expected_revision=current.revision,
            expected_result=result,
            lease=lease,
        )
        return op, prepared, result, sync, store, ops, current.revision


def _f13_prepare_source_patch(
    settings: AppSettings, wid: str, source_id: str, *, name: str, idem: str
):
    from offline_rag.app.workspace.leases import WorkspaceMutationLease
    from offline_rag.app.workspace.models import (
        ManagedOperationKind,
        ManagedOperationResult,
        advance_revision,
        utc_now,
    )

    ops = ManagedOperationStore(settings)
    store = WorkspaceStore(settings)
    sync = SyncMutationCoordinator(settings)
    with WorkspaceMutationLease(settings, wid) as lease:
        current = store.get(wid)
        op = ops.begin(
            workspace_id=wid,
            idempotency_key=idem,
            kind=ManagedOperationKind.SOURCE_METADATA_PATCH,
            request_payload={"source_id": source_id, "display_name": name},
            expected_revision=current.revision,
            lease=lease,
        )
        updated_source = None
        sources = []
        for item in current.sources:
            if item.active and item.source_id == source_id:
                updated_source = item.model_copy(update={"display_name": name})
                sources.append(updated_source)
            else:
                sources.append(item)
        assert updated_source is not None
        prepared = current.model_copy(
            update={
                "sources": sources,
                "revision": advance_revision(current.revision),
                "updated_at": utc_now(),
            }
        )
        result = ManagedOperationResult(
            workspace_revision=prepared.revision,
            workspace_status=prepared.status,
            snapshot_id=prepared.current_snapshot_id,
            source_id=source_id,
            source_version=updated_source.version,
            display_name=updated_source.display_name,
            content_type=updated_source.content_type,
            byte_size=updated_source.byte_size,
            content_hash=updated_source.content_hash,
            document_id=updated_source.document_id,
            active_from_revision=updated_source.active_from_revision,
            active_from_snapshot_id=updated_source.active_from_snapshot_id,
            created_at=updated_source.created_at,
            updated_at=prepared.updated_at,
            source_count=len([s for s in prepared.sources if s.active]),
            title=prepared.title,
            description=prepared.description,
        )
        sync.begin(
            wid,
            operation_id=op.operation_id,
            kind=ManagedOperationKind.SOURCE_METADATA_PATCH,
            expected_revision=current.revision,
            expected_result=result,
            lease=lease,
        )
        return op, prepared, result, sync, store, ops, current.revision


def test_f13_patch_crash_before_workspace_write(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13a", title="Desk").workspace_id
        op, _prepared, _result, _sync, store, ops, prior_rev = (
            _f13_prepare_workspace_patch(settings, wid, title="Done", idem="p-a")
        )
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "A" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.INTERRUPTED
        assert store.get(wid).revision == prior_rev
        assert store.get(wid).title == "Desk"
    finally:
        runtime.shutdown()


def test_f13_patch_crash_after_workspace_before_journal_committed(tmp_path: Path) -> None:
    """Torn window: workspace.json landed; journal still INTENT (no mark_committed)."""
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13b", title="Desk").workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease

        op, prepared, result, sync, store, ops, _prior = _f13_prepare_workspace_patch(
            settings, wid, title="Done", idem="p-b"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            assert sync.load(wid) is not None
            assert sync.load(wid).phase.value == "intent_recorded"
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.model_dump_json() == result.model_dump_json()
        assert store.get(wid).title == "Done"
    finally:
        runtime.shutdown()


def test_f13_patch_crash_after_journal_committed_before_op_succeeded(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13c", title="Desk").workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease

        op, prepared, result, sync, store, ops, _ = _f13_prepare_workspace_patch(
            settings, wid, title="Done", idem="p-c"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            sync.mark_workspace_committed(wid, result=result, lease=lease)
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.title == "Done"
        assert recovered.result.workspace_revision == 2
    finally:
        runtime.shutdown()


def test_f13_delete_crash_before_workspace_write(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13d", title="Desk").workspace_id
        op, _p, _r, _s, store, ops, prior_rev = _f13_prepare_workspace_delete(
            settings, wid, idem="d-a"
        )
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "A" for item in out["sync_mutations"])
        assert ops.get(wid, op.operation_id).status is ManagedOperationStatus.INTERRUPTED
        assert store.get(wid).revision == prior_rev
        assert store.get(wid).status.value == "empty"
    finally:
        runtime.shutdown()


def test_f13_delete_crash_after_workspace_before_journal_committed(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13e", title="Desk").workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease

        op, prepared, result, sync, store, ops, _ = _f13_prepare_workspace_delete(
            settings, wid, idem="d-b"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            assert sync.load(wid).phase.value == "intent_recorded"
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.model_dump_json() == result.model_dump_json()
        assert store.get(wid, include_tombstoned=True).status.value == "tombstoned"
    finally:
        runtime.shutdown()


def test_f13_delete_crash_after_journal_committed_before_op_succeeded(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f13f", title="Desk").workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease

        op, prepared, result, sync, store, ops, _ = _f13_prepare_workspace_delete(
            settings, wid, idem="d-c"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            sync.mark_workspace_committed(wid, result=result, lease=lease)
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.workspace_status.value == "tombstoned"
    finally:
        runtime.shutdown()


def test_f13_source_patch_three_crash_points(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f13g")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "seed", "If-Match": '"1"'},
            files={"files": ("a.txt", b"src patch pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        sid = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]["source_id"]
        settings = runtime.settings
        from offline_rag.app.workspace.leases import WorkspaceMutationLease
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        op_a, _p, _r, _s, store, ops, prior = _f13_prepare_source_patch(
            settings, wid, sid, name="Renamed-A", idem="s-a"
        )
        out = recover_workspace_transactions(settings)
        assert any(item[1] == "A" for item in out["sync_mutations"])
        assert ops.get(wid, op_a.operation_id).status is ManagedOperationStatus.INTERRUPTED
        assert store.get(wid).revision == prior

        op_b, prepared, result, sync, store, ops, _ = _f13_prepare_source_patch(
            settings, wid, sid, name="Renamed-B", idem="s-b"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            assert sync.load(wid).phase.value == "intent_recorded"
        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op_b.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.display_name == "Renamed-B"
        assert recovered.result.model_dump_json() == result.model_dump_json()

        op_c, prepared, result, sync, store, ops, _ = _f13_prepare_source_patch(
            settings, wid, sid, name="Renamed-C", idem="s-c"
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            store.save(prepared, lease=lease)
            sync.mark_workspace_committed(wid, result=result, lease=lease)
        out = recover_workspace_transactions(settings)
        assert any(item[1] == "B" for item in out["sync_mutations"])
        recovered = ops.get(wid, op_c.operation_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        assert recovered.result is not None
        assert recovered.result.display_name == "Renamed-C"


# ---------------------------------------------------------------------------
# F7 — live failure recovery keeps corpus lease
# ---------------------------------------------------------------------------


def test_f7_failure_recovery_holds_corpus_lease(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f7")["workspace_id"]
        entered = threading.Event()
        release = threading.Event()
        original = NonEmptyPublicationCoordinator.recover

        def gated(self, workspace_id, *, lease=None, corpus_lease=None):
            entered.set()
            assert corpus_lease is not None and corpus_lease.held
            assert release.wait(timeout=10)
            return original(
                self, workspace_id, lease=lease, corpus_lease=corpus_lease
            )

        NonEmptyPublicationCoordinator.recover = gated  # type: ignore[method-assign]
        original_commit = NonEmptyPublicationCoordinator.commit_workspace

        def boom(self, *args, **kwargs):
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                details={"reason": "forced_post_publication_fault"},
            )

        NonEmptyPublicationCoordinator.commit_workspace = boom  # type: ignore[method-assign]
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f7", "If-Match": '"1"'},
                files={"files": ("a.txt", b"f7 pumps\n", "text/plain")},
            )
            assert add.status_code == 202, add.text
            assert entered.wait(timeout=30)
            record = WorkspaceStore(runtime.settings).get(wid, include_tombstoned=True)
            busy = CorpusMutationLease(runtime.settings, record.backing_corpus_name)
            with pytest.raises(AppError) as excinfo:
                busy.acquire()
            assert excinfo.value.code is ErrorCode.CORPUS_BUSY
        finally:
            release.set()
            NonEmptyPublicationCoordinator.recover = original  # type: ignore[method-assign]
            NonEmptyPublicationCoordinator.commit_workspace = original_commit  # type: ignore[method-assign]
        terminal = _wait(client, add.json()["operation_id"])
        assert terminal["status"] in {"failed", "interrupted"}
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert ws.current_snapshot_id is None or _product_current(
            runtime.settings, ws.backing_corpus_name
        ) in {ws.current_snapshot_id, None}


# ---------------------------------------------------------------------------
# F14 — workspace-owned corpus protection (fail closed)
# ---------------------------------------------------------------------------


def _legacy_ingest_body(corpus: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----own"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="corpus"\r\n\r\n{corpus}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, boundary


def test_workspace_owned_corpus_blocks_legacy_ingest(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "own")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "own-add", "If-Match": '"1"'},
            files={"files": ("a.txt", b"owned pumps\n", "text/plain")},
        )
        term = _wait(client, add.json()["operation_id"])
        assert term["status"] == "succeeded"
        ws = WorkspaceStore(runtime.settings).get(wid)
        snap = ws.current_snapshot_id
        corpus = ws.backing_corpus_name
        body, boundary = _legacy_ingest_body(corpus, "x.txt", b"hijack\n")
        legacy = client.post(
            "/v1/ingest",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert legacy.status_code == 409, legacy.text
        assert legacy.json()["error"]["code"] == "workspace_conflict"
        assert _product_current(runtime.settings, corpus) == snap
        ok_body, boundary = _legacy_ingest_body("manuals", "y.txt", b"standalone pumps\n")
        ok = client.post(
            "/v1/ingest",
            content=ok_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert ok.status_code == 200, ok.text


def test_f14_tombstoned_workspace_corpus_blocked(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "tomb")["workspace_id"]
        ws = WorkspaceStore(runtime.settings).get(wid)
        corpus = ws.backing_corpus_name
        deleted = client.delete(
            f"/v1/workspaces/{wid}",
            headers={"Idempotency-Key": "tomb", "If-Match": '"1"'},
        )
        assert deleted.status_code == 200, deleted.text
        body, boundary = _legacy_ingest_body(corpus, "x.txt", b"hijack\n")
        legacy = client.post(
            "/v1/ingest",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert legacy.status_code == 409, legacy.text
        assert legacy.json()["error"]["code"] == "workspace_conflict"


def test_f14_corrupt_and_missing_workspace_json_fail_closed(tmp_path: Path) -> None:
    from offline_rag.app.workspace.models import backing_corpus_name_for

    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "corrupt")["workspace_id"]
        corpus = backing_corpus_name_for(wid)
        path = runtime.settings.paths.workspaces / wid / "workspace.json"
        path.write_text("{not-json", encoding="utf-8")
        body, boundary = _legacy_ingest_body(corpus, "x.txt", b"hijack\n")
        legacy = client.post(
            "/v1/ingest",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert legacy.status_code in {409, 503, 500}, legacy.text
        code = legacy.json()["error"]["code"]
        assert code in {"workspace_state_unavailable", "workspace_conflict"}
        assert _product_current(runtime.settings, corpus) is None

        wid2 = _create(client, "missing")["workspace_id"]
        corpus2 = backing_corpus_name_for(wid2)
        (runtime.settings.paths.workspaces / wid2 / "workspace.json").unlink()
        body2, boundary2 = _legacy_ingest_body(corpus2, "z.txt", b"hijack\n")
        legacy2 = client.post(
            "/v1/ingest",
            content=body2,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary2}"},
        )
        assert legacy2.status_code in {409, 503, 500}, legacy2.text
        assert legacy2.json()["error"]["code"] in {
            "workspace_state_unavailable",
            "workspace_conflict",
        }
        assert _product_current(runtime.settings, corpus2) is None


# ---------------------------------------------------------------------------
# F11 / F15 — recovered scientific result matrix
# ---------------------------------------------------------------------------


def _crash_before_op_succeeded():
    original = ManagedOperationStore.update_status
    crash = {"hit": False}

    def crashing(self, workspace_id, operation_id, status, **kwargs):
        if (
            status is ManagedOperationStatus.SUCCEEDED
            and kwargs.get("result") is not None
            and not crash["hit"]
        ):
            crash["hit"] = True
            raise RuntimeError("crash_before_op_success")
        return original(self, workspace_id, operation_id, status, **kwargs)

    ManagedOperationStore.update_status = crashing  # type: ignore[method-assign]
    return original, crash


def test_f15_recovery_add_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f15a")["workspace_id"]
        original, _crash = _crash_before_op_succeeded()
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f15a", "If-Match": '"1"'},
                files={"files": ("a.txt", b"f15 add pumps\n", "text/plain")},
            )
            assert add.status_code == 202
            _wait(client, add.json()["operation_id"], timeout=20)
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
        succeeded = [o for o in ops if o.status is ManagedOperationStatus.SUCCEEDED]
        assert succeeded
        result = succeeded[0].result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id
        assert result.source_version == 1
        assert result.source_ids == [s.source_id for s in ws.sources if s.active]
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_revision == ws.revision
        assert result.workspace_status.value == "active"


def test_f15_recovery_replace_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f15r")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f15r0", "If-Match": '"1"'},
            files={"files": ("a.txt", b"f15 replace v1 pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        src = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        sid = src["source_id"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        original, _crash = _crash_before_op_succeeded()
        try:
            repl = client.put(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "f15r1", "If-Match": f'"{rev}"'},
                files={"files": ("a2.txt", b"f15 replace v2 pumps\n", "text/plain")},
            )
            assert repl.status_code == 202
            _wait(client, repl.json()["operation_id"], timeout=20)
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
        succeeded = [
            o
            for o in ops
            if o.status is ManagedOperationStatus.SUCCEEDED
            and o.result
            and o.result.source_version == 2
        ]
        assert succeeded, ops
        result = succeeded[0].result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id == sid
        assert result.source_version == 2
        assert result.source_ids == [s.source_id for s in ws.sources if s.active]
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_revision == ws.revision


def test_f15_recovery_nonfinal_remove_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f15n")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f15n0", "If-Match": '"1"'},
            files=[
                ("files", ("one.txt", b"one pumps\n", "text/plain")),
                ("files", ("two.txt", b"two pumps\n", "text/plain")),
            ],
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        remove_id = next(s["source_id"] for s in sources if s["display_name"] == "one.txt")
        removed_version = next(
            s["version"] for s in sources if s["source_id"] == remove_id
        )
        remaining = [s["source_id"] for s in sources if s["source_id"] != remove_id]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        original, _crash = _crash_before_op_succeeded()
        try:
            rem = client.delete(
                f"/v1/workspaces/{wid}/sources/{remove_id}",
                headers={"Idempotency-Key": "f15n1", "If-Match": f'"{rev}"'},
            )
            assert rem.status_code == 202
            _wait(client, rem.json()["operation_id"], timeout=20)
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
        succeeded = [
            o
            for o in ops
            if o.status is ManagedOperationStatus.SUCCEEDED
            and o.result
            and o.result.source_id == remove_id
            and o.kind.value == "source_remove"
        ]
        assert succeeded, [(o.kind, o.status, o.result) for o in ops]
        result = succeeded[0].result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id == remove_id
        assert result.source_version == removed_version
        assert sorted(result.source_ids or []) == sorted(remaining)
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_status.value == "active"


def test_f15_recovery_empty_remove_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f15e")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f15e0", "If-Match": '"1"'},
            files={"files": ("only.txt", b"only pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        src = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        sid = src["source_id"]
        version = src["version"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        original, _crash = _crash_before_op_succeeded()
        try:
            rem = client.delete(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "f15e1", "If-Match": f'"{rev}"'},
            )
            assert rem.status_code == 202
            _wait(client, rem.json()["operation_id"], timeout=20)
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
        succeeded = [
            o
            for o in ops
            if o.status is ManagedOperationStatus.SUCCEEDED
            and o.result
            and o.result.workspace_status.value == "empty"
        ]
        assert succeeded, ops
        result = succeeded[0].result
        assert result is not None
        assert result.source_id == sid
        assert result.source_version == version
        assert result.source_ids == []
        assert result.snapshot_id is None
        assert result.workspace_status.value == "empty"


# ---------------------------------------------------------------------------
# F12 / F16 — full pipeline supersession + assembled context
# ---------------------------------------------------------------------------


def test_f12_pipeline_supersession_isolation(tmp_path: Path) -> None:
    from offline_rag.context.assemble import HybridRerankContextAssembler
    from offline_rag.generation.protocol import GeneratorRequest

    assembled: list = []
    original_assemble = HybridRerankContextAssembler.assemble

    def recording_assemble(self, *args, **kwargs):
        ctx = original_assemble(self, *args, **kwargs)
        assembled.append(ctx)
        return ctx

    HybridRerankContextAssembler.assemble = recording_assemble  # type: ignore[method-assign]
    generator_requests: list[GeneratorRequest] = []

    try:
        settings = _settings(tmp_path)
        presented: list[str] = []

        class _RecordingReranker(FakeReranker):
            def score_pairs(self, pairs):
                for pair in pairs:
                    presented.append(getattr(pair, "passage_text", "") or "")
                return super().score_pairs(pairs)

        settings._test_presented = presented  # type: ignore[attr-defined]

        def _capture(request: GeneratorRequest) -> str:
            generator_requests.append(request)
            return json.dumps({"abstain": True, "answer": None, "citation_ids": []})

        embedder = FakeEmbedder(dimension=8, normalize=True)
        reranker = _RecordingReranker()
        generator = FakeGenerator(response_fn=_capture)

        def _qdrant(s: AppSettings) -> QdrantLocalBackend:
            return QdrantLocalBackend(s.paths.qdrant_storage)

        runtime = ApplicationRuntime(
            settings=settings,
            factories=ResourceFactories(
                embedder=lambda _s: embedder,
                reranker=lambda _s: reranker,
                generator_client=lambda _s: generator,
                qdrant=_qdrant,
            ),
        )
        app = create_app(runtime=runtime)
        with TestClient(app) as client:
            wid = _create(client, "f12")["workspace_id"]
            v05 = f"{OLD_MARKER} valve torque procedure v05.\n".encode()
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f12a", "If-Match": '"1"'},
                files={"files": ("manual_b_v05.txt", v05, "text/plain")},
            )
            t0 = _wait(client, add.json()["operation_id"])
            assert t0["status"] == "succeeded"
            old_doc = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
                "document_id"
            ]
            sid = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
                "source_id"
            ]
            ws = client.get(f"/v1/workspaces/{wid}").json()
            v06 = f"{NEW_MARKER} valve torque procedure v06 revised.\n".encode()
            repl = client.put(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={
                    "Idempotency-Key": "f12r",
                    "If-Match": f'"{ws["revision"]}"',
                },
                files={"files": ("manual_b_v06.txt", v06, "text/plain")},
            )
            t1 = _wait(client, repl.json()["operation_id"])
            assert t1["status"] == "succeeded"
            new_doc = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0][
                "document_id"
            ]
            assert new_doc != old_doc
            record = WorkspaceStore(runtime.settings).get(wid)
            snap = runtime.publication.resolve(record.backing_corpus_name)
            assert snap.snapshot_id == record.current_snapshot_id
            binding = build_snapshot_query_binding(runtime.settings, snap)
            corpus_ids = set(binding.source_name_by_document_id().keys())
            assert old_doc not in corpus_ids
            assert new_doc in corpus_ids

            dense = DenseRetriever(
                runtime.settings,
                embedder=runtime.resources.embedder,
                backend=runtime.resources.qdrant,
            )
            dens = dense.retrieve(
                query=f"{OLD_MARKER} {NEW_MARKER} valve torque",
                corpus_name=record.backing_corpus_name,
                top_k=20,
                index_id=binding.dense_index_id,
                collection_name=binding.dense_collection_name,
                chunk_set_id=binding.chunk_set_id,
            )
            dense_docs = {c.document_id for c in dens.candidates}
            dense_text = " ".join(
                getattr(c, "text", "") or "" for c in dens.candidates
            )
            assert old_doc not in dense_docs
            assert OLD_MARKER not in dense_text

            lexical = LexicalRetriever(runtime.settings)
            lex = lexical.retrieve(
                query=OLD_MARKER,
                corpus_name=record.backing_corpus_name,
                top_k=20,
                index_id=binding.lexical_index_id,
                chunk_set_id=binding.chunk_set_id,
            )
            lex_docs = {c.document_id for c in lex.candidates}
            lex_text = " ".join(getattr(c, "text", "") or "" for c in lex.candidates)
            assert old_doc not in lex_docs
            assert OLD_MARKER not in lex_text

            presented_before = list(presented)
            assembled_before = len(assembled)
            outcome = run_workspace_query(
                runtime,
                workspace_id=wid,
                question=(
                    f"What valve torque procedure does {NEW_MARKER} document? "
                    f"Do not use superseded {OLD_MARKER}."
                ),
            )
            packed = json.dumps(outcome.as_dict())
            assert outcome.snapshot_id == record.current_snapshot_id
            assert OLD_MARKER not in packed or outcome.status != "answered"
            assert old_doc not in packed
            new_presentations = presented[len(presented_before) :]
            assert all(OLD_MARKER not in text for text in new_presentations)

            new_contexts = assembled[assembled_before:]
            assert new_contexts, "bound query must assemble context"
            assert any(ctx.evidence_units for ctx in new_contexts), (
                "assembled context must include evidence units"
            )
            for ctx in new_contexts:
                assert OLD_MARKER not in (ctx.assembled_text or "")
                for unit in ctx.evidence_units:
                    assert OLD_MARKER not in unit.text
                    assert unit.document_id != old_doc
            # F19: generation must actually run (non-vacuous).
            assert generator_requests, "bound query must invoke the recording generator"
            for req in generator_requests:
                blob = "\n".join(m.content for m in req.messages)
                # Adversarial query may mention OLD_MARKER; evidence must not.
                evidence_start = blob.find("EVIDENCE:")
                assert evidence_start >= 0
                evidence_blob = blob[evidence_start:]
                assert OLD_MARKER not in evidence_blob
                assert old_doc not in evidence_blob
    finally:
        HybridRerankContextAssembler.assemble = original_assemble  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# F17 — live AppError after workspace write reconciles (does not drop journal)
# ---------------------------------------------------------------------------


def test_f17_patch_reconciles_after_post_write_apperror(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f17p", title="Desk").workspace_id
        original = type(life.sync_mutations).mark_workspace_committed

        def boom(self, workspace_id, *, result, lease):
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                details={"reason": "forced_post_write_journal_fault"},
            )

        type(life.sync_mutations).mark_workspace_committed = boom  # type: ignore[method-assign]
        try:
            view, op = life.patch_workspace_metadata(
                wid,
                expected_revision=1,
                idempotency_key="f17-patch",
                title="Done",
                description="",
            )
        finally:
            type(life.sync_mutations).mark_workspace_committed = original  # type: ignore[method-assign]

        assert view["title"] == "Done"
        assert view["revision"] == 2
        assert op.status is ManagedOperationStatus.SUCCEEDED
        assert op.result is not None
        assert op.result.title == "Done"
        assert life.sync_mutations.load(wid) is None
        assert WorkspaceStore(settings).get(wid).title == "Done"
    finally:
        runtime.shutdown()


def test_f17_delete_reconciles_after_post_write_apperror(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f17d", title="Desk").workspace_id
        original = type(life.sync_mutations).mark_workspace_committed

        def boom(self, workspace_id, *, result, lease):
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                details={"reason": "forced_post_write_journal_fault"},
            )

        type(life.sync_mutations).mark_workspace_committed = boom  # type: ignore[method-assign]
        try:
            view, op = life.tombstone_workspace(
                wid, expected_revision=1, idempotency_key="f17-del"
            )
        finally:
            type(life.sync_mutations).mark_workspace_committed = original  # type: ignore[method-assign]

        assert view["status"] == "tombstoned"
        assert op.status is ManagedOperationStatus.SUCCEEDED
        assert op.result is not None
        assert op.result.workspace_status.value == "tombstoned"
        assert life.sync_mutations.load(wid) is None
    finally:
        runtime.shutdown()


def test_f17_source_patch_reconciles_after_post_write_apperror(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f17s")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "seed", "If-Match": '"1"'},
            files={"files": ("a.txt", b"f17 src pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        sid = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]["source_id"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        life = runtime.workspace_lifecycle
        original = type(life.sync_mutations).mark_workspace_committed

        def boom(self, workspace_id, *, result, lease):
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                details={"reason": "forced_post_write_journal_fault"},
            )

        type(life.sync_mutations).mark_workspace_committed = boom  # type: ignore[method-assign]
        try:
            view, op = life.patch_source_metadata(
                wid,
                sid,
                expected_revision=rev,
                idempotency_key="f17-src",
                display_name="renamed-f17.txt",
            )
        finally:
            type(life.sync_mutations).mark_workspace_committed = original  # type: ignore[method-assign]

        assert view["display_name"] == "renamed-f17.txt"
        assert op.status is ManagedOperationStatus.SUCCEEDED
        assert op.result is not None
        assert op.result.display_name == "renamed-f17.txt"
        assert life.sync_mutations.load(wid) is None


def test_f17_ambiguous_state_keeps_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        wid = life.create_workspace(idempotency_key="f17a", title="Desk").workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease
        from offline_rag.app.workspace.models import (
            ManagedOperationKind,
            ManagedOperationResult,
            advance_revision,
            utc_now,
        )

        ops = ManagedOperationStore(settings)
        store = WorkspaceStore(settings)
        sync = SyncMutationCoordinator(settings)
        with WorkspaceMutationLease(settings, wid) as lease:
            current = store.get(wid)
            op = ops.begin(
                workspace_id=wid,
                idempotency_key="amb",
                kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                request_payload={"title": "Prepared", "description": ""},
                expected_revision=current.revision,
                lease=lease,
            )
            prepared = current.model_copy(
                update={
                    "title": "Prepared",
                    "description": "",
                    "revision": advance_revision(current.revision),
                    "updated_at": utc_now(),
                }
            )
            result = ManagedOperationResult(
                workspace_revision=prepared.revision,
                workspace_status=prepared.status,
                snapshot_id=None,
                title="Prepared",
                description="",
                source_count=0,
                created_at=prepared.created_at,
                updated_at=prepared.updated_at,
            )
            sync.begin(
                wid,
                operation_id=op.operation_id,
                kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                expected_revision=current.revision,
                expected_result=result,
                lease=lease,
            )
            # Ambiguous: workspace advanced differently from prepared receipt.
            alien = current.model_copy(
                update={
                    "title": "Alien",
                    "revision": advance_revision(current.revision),
                    "updated_at": utc_now(),
                }
            )
            store.save(alien, lease=lease)
            with pytest.raises(AppError) as excinfo:
                sync.reconcile(
                    wid,
                    lease=lease,
                    failure=AppError(
                        ErrorCode.INTERNAL_ERROR,
                        details={"reason": "forced"},
                    ),
                )
            assert excinfo.value.code is ErrorCode.WORKSPACE_STATE_UNAVAILABLE
            assert sync.load(wid) is not None
            still = ops.get(wid, op.operation_id)
            assert still.status is ManagedOperationStatus.PENDING
    finally:
        runtime.shutdown()


# ---------------------------------------------------------------------------
# F18 — explicit startup recovery (live recovery blocked)
# ---------------------------------------------------------------------------


@contextmanager
def _startup_recovery_trap():
    """Leave durable B journal + nonterminal op; block live F7 recovery."""
    from offline_rag.app.workspace.lifecycle import WorkspaceLifecycleService

    original_fail = WorkspaceLifecycleService._fail_operation
    original_update = ManagedOperationStore.update_status
    crash = {"hit": False}

    def noop_fail(self, *args, **kwargs):
        return None

    def crashing(self, workspace_id, operation_id, status, **kwargs):
        if (
            status is ManagedOperationStatus.SUCCEEDED
            and kwargs.get("result") is not None
            and not crash["hit"]
        ):
            crash["hit"] = True
            raise RuntimeError("crash_before_op_success_for_startup")
        return original_update(self, workspace_id, operation_id, status, **kwargs)

    WorkspaceLifecycleService._fail_operation = noop_fail  # type: ignore[method-assign]
    ManagedOperationStore.update_status = crashing  # type: ignore[method-assign]
    try:
        yield crash
    finally:
        WorkspaceLifecycleService._fail_operation = original_fail  # type: ignore[method-assign]
        ManagedOperationStore.update_status = original_update  # type: ignore[method-assign]


def _wait_startup_trap(
    settings: AppSettings,
    workspace_id: str,
    crash: dict[str, bool],
    *,
    journal_name: str,
    timeout: float = 30.0,
) -> Path:
    """Wait until the worker hit the SUCCEEDED crash with journal retained."""
    journal = (
        settings.paths.workspaces / workspace_id / "journal" / journal_name
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        if crash["hit"] and journal.is_file():
            return journal
        time.sleep(0.05)
    raise AssertionError(
        f"startup trap did not leave {journal_name} (crash={crash['hit']})"
    )


def test_f18_startup_recovery_add_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f18a")["workspace_id"]
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        with _startup_recovery_trap() as crash:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f18a", "If-Match": '"1"'},
                files={"files": ("a.txt", b"f18 add pumps\n", "text/plain")},
            )
            assert add.status_code == 202
            journal = _wait_startup_trap(
                runtime.settings,
                wid,
                crash,
                journal_name="publication_transition.json",
            )
            op_id = add.json()["operation_id"]
            ops = ManagedOperationStore(runtime.settings)
            pre = ops.get(wid, op_id)
            assert pre.status in {
                ManagedOperationStatus.PENDING,
                ManagedOperationStatus.RUNNING,
            }
            assert journal.is_file(), "B journal must survive for startup recovery"
            # Recover while live _fail_operation remains suppressed.
            out = recover_workspace_transactions(runtime.settings)
        assert any(item[1] == "B" for item in out["publication_transitions"])
        assert not journal.exists()
        recovered = ops.get(wid, op_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        result = recovered.result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id
        assert result.source_version == 1
        assert result.source_ids == [s.source_id for s in ws.sources if s.active]
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_revision == ws.revision
        assert result.workspace_status.value == "active"


def test_f18_startup_recovery_replace_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f18r")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f18r0", "If-Match": '"1"'},
            files={"files": ("a.txt", b"f18 replace v1 pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        src = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        sid = src["source_id"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        with _startup_recovery_trap() as crash:
            repl = client.put(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "f18r1", "If-Match": f'"{rev}"'},
                files={"files": ("a2.txt", b"f18 replace v2 pumps\n", "text/plain")},
            )
            assert repl.status_code == 202
            journal = _wait_startup_trap(
                runtime.settings,
                wid,
                crash,
                journal_name="publication_transition.json",
            )
            op_id = repl.json()["operation_id"]
            ops = ManagedOperationStore(runtime.settings)
            assert ops.get(wid, op_id).status in {
                ManagedOperationStatus.PENDING,
                ManagedOperationStatus.RUNNING,
            }
            assert journal.is_file()
            out = recover_workspace_transactions(runtime.settings)
        assert any(item[1] == "B" for item in out["publication_transitions"])
        recovered = ops.get(wid, op_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        result = recovered.result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id == sid
        assert result.source_version == 2
        assert result.source_ids == [s.source_id for s in ws.sources if s.active]
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_revision == ws.revision


def test_f18_startup_recovery_nonfinal_remove_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f18n")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f18n0", "If-Match": '"1"'},
            files=[
                ("files", ("one.txt", b"one pumps\n", "text/plain")),
                ("files", ("two.txt", b"two pumps\n", "text/plain")),
            ],
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        remove_id = next(s["source_id"] for s in sources if s["display_name"] == "one.txt")
        removed_version = next(
            s["version"] for s in sources if s["source_id"] == remove_id
        )
        remaining = [s["source_id"] for s in sources if s["source_id"] != remove_id]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        with _startup_recovery_trap() as crash:
            rem = client.delete(
                f"/v1/workspaces/{wid}/sources/{remove_id}",
                headers={"Idempotency-Key": "f18n1", "If-Match": f'"{rev}"'},
            )
            assert rem.status_code == 202
            journal = _wait_startup_trap(
                runtime.settings,
                wid,
                crash,
                journal_name="publication_transition.json",
            )
            op_id = rem.json()["operation_id"]
            assert journal.is_file()
            out = recover_workspace_transactions(runtime.settings)
        assert any(item[1] == "B" for item in out["publication_transitions"])
        recovered = ManagedOperationStore(runtime.settings).get(wid, op_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        result = recovered.result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id == remove_id
        assert result.source_version == removed_version
        assert sorted(result.source_ids or []) == sorted(remaining)
        assert result.snapshot_id == ws.current_snapshot_id
        assert result.workspace_status.value == "active"
        assert result.workspace_revision == ws.revision


def test_f18_startup_recovery_empty_remove_result(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f18e")["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "f18e0", "If-Match": '"1"'},
            files={"files": ("only.txt", b"only pumps\n", "text/plain")},
        )
        assert _wait(client, add.json()["operation_id"])["status"] == "succeeded"
        src = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        sid = src["source_id"]
        version = src["version"]
        rev = client.get(f"/v1/workspaces/{wid}").json()["revision"]
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        with _startup_recovery_trap() as crash:
            rem = client.delete(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "f18e1", "If-Match": f'"{rev}"'},
            )
            assert rem.status_code == 202
            journal = _wait_startup_trap(
                runtime.settings,
                wid,
                crash,
                journal_name="empty_transition.json",
            )
            op_id = rem.json()["operation_id"]
            assert journal.is_file()
            out = recover_workspace_transactions(runtime.settings)
        assert any(item[1] == "B" for item in out["empty_transitions"])
        recovered = ManagedOperationStore(runtime.settings).get(wid, op_id)
        assert recovered.status is ManagedOperationStatus.SUCCEEDED
        result = recovered.result
        assert result is not None
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert result.source_id == sid
        assert result.source_version == version
        assert result.source_ids == []
        assert result.snapshot_id is None
        assert result.workspace_status.value == "empty"
        assert result.workspace_revision == ws.revision
