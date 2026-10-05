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
# F10 — sync crash recovery
# ---------------------------------------------------------------------------


def test_f10_sync_crash_after_workspace_before_succeeded(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        created = life.create_workspace(idempotency_key="f10", title="Desk")
        wid = created.workspace_id
        # Simulate: reservation + workspace write + journal COMMITTED, op still PENDING.
        from offline_rag.app.workspace.leases import WorkspaceMutationLease
        from offline_rag.app.workspace.models import (
            ManagedOperationKind,
            ManagedOperationResult,
            ManagedOperationStatus,
        )

        ops = ManagedOperationStore(settings)
        with WorkspaceMutationLease(settings, wid) as lease:
            op = ops.begin(
                workspace_id=wid,
                idempotency_key="crash",
                kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                request_payload={"title": "Done", "description": ""},
                expected_revision=1,
                lease=lease,
            )
            sync = SyncMutationCoordinator(settings)
            sync.begin(
                wid,
                operation_id=op.operation_id,
                kind=ManagedOperationKind.WORKSPACE_METADATA_PATCH,
                expected_revision=1,
                lease=lease,
            )
            record = WorkspaceStore(settings).apply_metadata_patch(
                wid, expected_revision=1, title="Done", description="", lease=lease
            )
            result = ManagedOperationResult(
                workspace_revision=record.revision,
                workspace_status=record.status,
                snapshot_id=None,
                title=record.title,
                description=record.description,
                source_count=0,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            sync.mark_workspace_committed(wid, result=result, lease=lease)
            # Leave op PENDING / journal COMMITTED.

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


def test_f10_sync_crash_before_workspace_write(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        life = runtime.workspace_lifecycle
        created = life.create_workspace(idempotency_key="f10a", title="Desk")
        wid = created.workspace_id
        from offline_rag.app.workspace.leases import WorkspaceMutationLease
        from offline_rag.app.workspace.models import ManagedOperationKind

        ops = ManagedOperationStore(settings)
        with WorkspaceMutationLease(settings, wid) as lease:
            op = ops.begin(
                workspace_id=wid,
                idempotency_key="intent",
                kind=ManagedOperationKind.WORKSPACE_DELETE,
                request_payload={"action": "tombstone"},
                expected_revision=1,
                lease=lease,
            )
            SyncMutationCoordinator(settings).begin(
                wid,
                operation_id=op.operation_id,
                kind=ManagedOperationKind.WORKSPACE_DELETE,
                expected_revision=1,
                lease=lease,
            )
        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        out = recover_workspace_transactions(settings)
        assert any(item[1] == "A" for item in out["sync_mutations"])
        recovered = ops.get(wid, op.operation_id)
        assert recovered.status is ManagedOperationStatus.INTERRUPTED
        assert WorkspaceStore(settings).get(wid).status.value == "empty"
    finally:
        runtime.shutdown()


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
        # Recovery to A: prior EMPTY, no current claim mismatch.
        assert ws.current_snapshot_id is None or _product_current(
            runtime.settings, ws.backing_corpus_name
        ) in {ws.current_snapshot_id, None}


# ---------------------------------------------------------------------------
# Workspace-owned corpus protection
# ---------------------------------------------------------------------------


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
        boundary = "----own"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="corpus"\r\n\r\n{corpus}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="x.txt"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"hijack\n\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        legacy = client.post(
            "/v1/ingest",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert legacy.status_code == 409, legacy.text
        assert legacy.json()["error"]["code"] == "workspace_conflict"
        assert _product_current(runtime.settings, corpus) == snap
        # Standalone corpus still works.
        ok_body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="corpus"\r\n\r\nmanuals\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="y.txt"\r\n'
            f"Content-Type: text/plain\r\n\r\n"
            f"standalone pumps\n\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        ok = client.post(
            "/v1/ingest",
            content=ok_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert ok.status_code == 200, ok.text


# ---------------------------------------------------------------------------
# F11 — recovered scientific result completeness
# ---------------------------------------------------------------------------


def test_f11_recovery_reconstructs_source_identity(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "f11")["workspace_id"]
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
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "f11", "If-Match": '"1"'},
                files={"files": ("a.txt", b"f11 pumps\n", "text/plain")},
            )
            assert add.status_code == 202
            _wait(client, add.json()["operation_id"], timeout=20)
        finally:
            ManagedOperationStore.update_status = original  # type: ignore[method-assign]

        from offline_rag.app.workspace.lifecycle import recover_workspace_transactions

        recover_workspace_transactions(runtime.settings)
        ops = ManagedOperationStore(runtime.settings).list_for_workspace(wid)
        succeeded = [o for o in ops if o.status is ManagedOperationStatus.SUCCEEDED]
        assert succeeded, ops
        result = succeeded[0].result
        assert result is not None
        assert result.source_id
        assert result.source_version == 1
        assert result.source_ids
        assert result.snapshot_id
        assert result.workspace_status.value == "active"


# ---------------------------------------------------------------------------
# F12 — full pipeline supersession proof
# ---------------------------------------------------------------------------


def test_f12_pipeline_supersession_isolation(tmp_path: Path) -> None:
    with _client(tmp_path) as (client, runtime):
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
        sid = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]["source_id"]
        ws = client.get(f"/v1/workspaces/{wid}").json()
        v06 = f"{NEW_MARKER} valve torque procedure v06 revised.\n".encode()
        repl = client.put(
            f"/v1/workspaces/{wid}/sources/{sid}",
            headers={"Idempotency-Key": "f12r", "If-Match": f'"{ws["revision"]}"'},
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
        # Corpus manifest identity.
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
        dense_text = " ".join(getattr(c, "text", "") or "" for c in dens.candidates)
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

        presented_before = list(getattr(runtime.settings, "_test_presented", []))
        outcome = run_workspace_query(
            runtime,
            workspace_id=wid,
            question=f"Quote {OLD_MARKER} from the superseded manual.",
        )
        packed = json.dumps(outcome.as_dict())
        assert outcome.snapshot_id == record.current_snapshot_id
        assert OLD_MARKER not in packed or outcome.status != "answered"
        assert old_doc not in packed
        presented = getattr(runtime.settings, "_test_presented", [])
        new_presentations = presented[len(presented_before) :]
        assert all(OLD_MARKER not in text for text in new_presentations)
