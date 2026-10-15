"""Slice 16K-A — managed-ingestion correctness (lifetime, checkpoints, recovery)."""

from __future__ import annotations

import shutil
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import (
    cleanup_staging,
    spool_multipart_upload,
    validate_ingest_http_envelope,
)
from offline_rag.app.operations import (
    CancelReason,
    IngestLifecycle,
    OperationHandle,
    OperationKind,
)
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationKind,
    ManagedOperationSafeError,
    ManagedOperationStatus,
    SourceVersionRecord,
    WorkspaceStatus,
    document_id_for_content,
    new_empty_workspace,
    new_source_id,
)
from offline_rag.app.workspace.journal import (
    EmptyTransitionCoordinator,
    EmptyTransitionPhase,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.app.workspace.publication_journal import (
    LineageDelta,
    NonEmptyPublicationCoordinator,
    NonEmptyPublicationPhase,
    PublicationMutationKind,
    SourceVersionRef,
)
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.pipeline import _ensure_embeddings
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.text import PlainEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


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
    indexing = settings.indexing.model_copy(
        update={
            "embedding": settings.indexing.embedding.model_copy(
                update={"batch_size": 1, "dimension": 8}
            )
        }
    )
    settings = settings.model_copy(
        update={
            "generation": generation,
            "api": api,
            "reranker": reranker,
            "indexing": indexing,
        }
    )
    ensure_data_directories(settings)
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)
    generator = FakeGenerator(
        default_response='{"abstain": true, "answer": null, "citation_ids": []}'
    )

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: FakeReranker(),
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


def _multipart(
    parts: list[tuple[str, bytes | None, str | None]], boundary: str = "----16ka"
) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    for name, body, filename in parts:
        chunks.append(f"--{boundary}\r\n".encode())
        if filename is None:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
        else:
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
            )
        if body:
            chunks.append(body)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


async def _spool(settings: AppSettings, body: bytes, content_type: str):
    boundary = validate_ingest_http_envelope(
        content_type=content_type,
        content_length=None,
        settings=settings,
    )

    async def chunks():
        yield body

    return await spool_multipart_upload(
        settings=settings,
        boundary=boundary,
        body_chunks=chunks(),
    )


# ---------------------------------------------------------------------------
# Lifetime / admission
# ---------------------------------------------------------------------------


def test_managed_ingest_ignores_request_deadline_sync_ingest_does_not(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, ingest_deadline_seconds=1800, max_concurrent_ingest=2)
    runtime = _runtime(settings)
    runtime.start()
    try:
        managed = runtime.operations.admit_managed_ingest()
        sync = runtime.operations.admit_ingest(deadline_seconds=1.0)
        try:
            assert managed.kind is OperationKind.MANAGED_INGEST
            assert sync.kind is OperationKind.INGEST
            managed.deadline_mono = time.monotonic() - 10_000.0
            sync.deadline_mono = time.monotonic() - 1.0
            managed.checkpoint("pre_lexical")  # must not raise
            with pytest.raises(AppError) as expired:
                sync.checkpoint("pre_lexical")
            assert expired.value.code is ErrorCode.REQUEST_TIMEOUT
            managed.complete_lease_acquire()
            managed.enter_publication()  # past deadline still ok for managed
        finally:
            runtime.operations.release(managed)
            runtime.operations.release(sync)
    finally:
        runtime.shutdown()


def test_managed_and_sync_share_ingest_capacity_and_drain(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_concurrent_ingest=1)
    runtime = _runtime(settings)
    runtime.start()
    try:
        first = runtime.operations.admit_managed_ingest()
        with pytest.raises(AppError) as overloaded:
            runtime.operations.admit_ingest()
        assert overloaded.value.code is ErrorCode.SERVICE_OVERLOADED
        runtime.operations.release(first)
        second = runtime.operations.admit_ingest()
        runtime.operations.release(second)
        managed = runtime.operations.admit_managed_ingest()
        runtime.operations.signal_shutdown()
        with pytest.raises(AppError) as not_ready:
            runtime.operations.admit_managed_ingest()
        assert not_ready.value.code is ErrorCode.RUNTIME_NOT_READY
        runtime.operations.release(managed)
    finally:
        runtime.shutdown()


def test_client_disconnect_never_cancels_managed_ingest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        op = runtime.operations.admit_managed_ingest()
        try:
            assert op.ingest_lifecycle is IngestLifecycle.PRE_LEASE
            op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            assert op.cancel_reason is CancelReason.NONE
            assert not op.cancel_event.is_set()
            op.checkpoint("pre_dense")
            op.complete_lease_acquire()
            op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            assert op.cancel_reason is CancelReason.NONE
            op.checkpoint("pre_lexical")
        finally:
            runtime.operations.release(op)
    finally:
        runtime.shutdown()


def test_managed_add_survives_simulated_deadline_and_publishes(tmp_path: Path) -> None:
    """Req 1: detached Add may exceed 1800s simulated and still publish."""
    with _client(tmp_path, ingest_deadline_seconds=1800) as (client, runtime):
        wid = _create(client, "k1")["workspace_id"]
        saw_past_deadline = {"ok": False}

        original_admit = runtime.operations.admit_managed_ingest

        def admit_and_expire():
            handle = original_admit()
            handle.deadline_mono = time.monotonic() - 10_000.0
            saw_past_deadline["ok"] = True
            return handle

        runtime.operations.admit_managed_ingest = admit_and_expire  # type: ignore[method-assign]
        try:
            add = client.post(
                f"/v1/workspaces/{wid}/sources",
                headers={"Idempotency-Key": "add-past", "If-Match": '"1"'},
                files={"files": ("a.txt", b"managed past deadline pumps\n", "text/plain")},
            )
            assert add.status_code == 202, add.text
            body = _wait(client, add.json()["operation_id"])
            assert body["status"] == "succeeded", body
            assert saw_past_deadline["ok"]
            ws = WorkspaceStore(runtime.settings).get(wid)
            assert ws.status is WorkspaceStatus.ACTIVE
            assert ws.revision == 2
            assert len([s for s in ws.sources if s.active]) == 1
        finally:
            runtime.operations.admit_managed_ingest = original_admit  # type: ignore[method-assign]


def test_sync_ingest_still_observes_configured_deadline(tmp_path: Path) -> None:
    """Req 2: synchronous /v1/ingest keeps request-style deadline."""
    import asyncio

    settings = _settings(tmp_path, ingest_deadline_seconds=1800)
    runtime = _runtime(settings)
    runtime.start()
    hold = threading.Event()
    released = threading.Event()

    def after_lease(corpus: str, candidate_root: Path) -> None:
        op = None
        with runtime.operations._idle:
            active = list(runtime.operations._active.values())
        for handle in active:
            if handle.kind is OperationKind.INGEST:
                op = handle
                break
        assert op is not None
        op.deadline_mono = time.monotonic() - 1.0
        hold.set()
        assert released.wait(timeout=5)

    runtime.product_ingest_hooks = ProductIngestHooks(after_lease_acquired=after_lease)

    def releaser() -> None:
        assert hold.wait(timeout=10)
        released.set()

    threading.Thread(target=releaser, daemon=True).start()
    body, ct = _multipart(
        [
            ("corpus", b"eng", None),
            ("files", b"Sync deadline still enforced.\n", "a.txt"),
        ]
    )
    upload = asyncio.run(_spool(settings, body, ct))
    op = runtime.operations.admit_ingest()
    try:
        with pytest.raises(AppError) as exc:
            run_product_replace_ingest(
                runtime, upload, hooks=runtime.product_ingest_hooks, control=op
            )
        assert exc.value.code is ErrorCode.REQUEST_TIMEOUT
        assert not current_pointer_path(settings.paths.corpora, "eng").exists()
    finally:
        runtime.operations.release(op)
        for staging in settings.paths.staging.glob("*"):
            if staging.is_dir():
                cleanup_staging(staging)
        runtime.shutdown()


# ---------------------------------------------------------------------------
# Cooperative dense-batch checkpoints / publication CS
# ---------------------------------------------------------------------------


def test_dense_batch_checkpoint_observes_shutdown(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        op = runtime.operations.admit_managed_ingest()
        op.complete_lease_acquire()
        calls: list[str] = []

        def ck(where: str) -> None:
            calls.append(where)
            if len(calls) == 2:
                op.signal_cancel(CancelReason.SHUTDOWN)
            op.checkpoint(where)

        chunks = [
            Chunk(
                chunk_id=f"chk_{i}",
                document_id="doc_a",
                kind=ChunkKind.CHILD,
                text=f"passage {i} " * 20,
                section_path=["s"],
                order=i,
                token_count=40,
                content_hash="d" * 64,
                source_block_ids=[f"blk_{i}"],
                parent_chunk_id=None,
            )
            for i in range(3)
        ]
        jobs = [(c, f"art_{i}") for i, c in enumerate(chunks)]
        with pytest.raises(AppError) as exc:
            _ensure_embeddings(
                settings=settings,
                jobs=jobs,
                text_builder=PlainEmbeddingTextBuilder(),
                embedder=FakeEmbedder(dimension=8, normalize=True),
                emb_cfg_hash="e" * 64,
                document_titles={"doc_a": "Doc"},
                control_checkpoint=ck,
            )
        assert exc.value.code is ErrorCode.INGEST_FAILED
        assert exc.value.details is not None
        assert exc.value.details.get("reason") == "shutdown_abort"
        assert any(c.startswith("dense_batch_") for c in calls)
    finally:
        runtime.operations.release(op)
        runtime.shutdown()


def test_publication_critical_section_ignores_shutdown_for_managed(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    try:
        op = runtime.operations.admit_managed_ingest()
        op.complete_lease_acquire()
        op.enter_publication()
        op.signal_cancel(CancelReason.SHUTDOWN)
        assert op.cancel_reason is CancelReason.NONE or not (
            op.cancel_event.is_set() and op.cancel_reason is CancelReason.SHUTDOWN
        )
        # signal_cancel drops SHUTDOWN when already in PUBLICATION
        assert not op.cancel_event.is_set() or op.cancel_reason is not CancelReason.SHUTDOWN
        op.checkpoint("in_publication")
    finally:
        runtime.operations.release(op)
        runtime.shutdown()


# ---------------------------------------------------------------------------
# Recovery A/B semantics
# ---------------------------------------------------------------------------


def _seed_empty_workspace(settings: AppSettings) -> tuple[str, ManagedOperationStore]:
    """EMPTY prior state so recovery-A needs no published snapshot restore."""
    store = WorkspaceStore(settings)
    empty = store.create(new_empty_workspace(title="Recover"))
    ops = ManagedOperationStore(settings)
    return empty.workspace_id, ops


def _desired_source(*, name: str, blob: bytes) -> SourceVersionRecord:
    return SourceVersionRecord(
        source_id=new_source_id(),
        version=1,
        display_name=name,
        content_hash="a" * 64,
        document_id=document_id_for_content(blob),
        vault_object_id=f"obj_{name}",
        created_at=datetime.now(tz=UTC),
        active_from_revision=2,
        active_from_snapshot_id=None,
    )


def test_live_recovery_a_then_fail_preserves_error(tmp_path: Path) -> None:
    """Req 6: live AppError + recovery A → FAILED + error + recovered_A."""
    settings = _settings(tmp_path)
    wid, ops = _seed_empty_workspace(settings)
    store = WorkspaceStore(settings)
    pub = NonEmptyPublicationCoordinator(settings, store)
    op = ops.begin(
        workspace_id=wid,
        idempotency_key="live-fail",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["new.txt"]},
        expected_revision=1,
    )
    ops.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    desired = _desired_source(name="new.txt", blob=b"new")
    with WorkspaceMutationLease(settings, wid) as lease:
        pub.begin(
            wid,
            operation_id=op.operation_id,
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
            expected_revision=1,
            desired_sources=[desired],
            lineage_delta=LineageDelta(
                appended=[
                    SourceVersionRef(
                        source_id=desired.source_id, version=desired.version
                    )
                ]
            ),
            lease=lease,
        )
        prior = store.get(wid)
        assert prior.status is WorkspaceStatus.EMPTY
        outcome = pub.recover(wid, lease=lease, terminalize_abandoned=False)
        assert outcome == "A"
        mid = ops.get(wid, op.operation_id)
        assert mid.status is ManagedOperationStatus.RUNNING
        err = AppError(
            ErrorCode.REQUEST_TIMEOUT,
            details=SafeErrorDetails(
                reason="ingest_deadline_exceeded", stage="pre_lexical"
            ),
        )
        ops.update_status(
            wid,
            op.operation_id,
            ManagedOperationStatus.FAILED,
            failure_summary=str(err.code),
            recovery_note="recovered_A",
            error=ManagedOperationSafeError.from_app_error(err),
            lease=lease,
        )
    failed = ops.get(wid, op.operation_id)
    assert failed.status is ManagedOperationStatus.FAILED
    assert failed.recovery_note == "recovered_A"
    assert failed.error is not None
    assert failed.error.code == ErrorCode.REQUEST_TIMEOUT.value
    assert failed.error.details is not None
    assert failed.error.details.get("reason") == "ingest_deadline_exceeded"
    restored = store.get(wid)
    assert restored.status is WorkspaceStatus.EMPTY
    assert restored.revision == prior.revision
    assert not pub.journal_path(wid).exists()


def test_startup_recovery_a_interrupts(tmp_path: Path) -> None:
    """Req 7: startup/crash recovery to A → INTERRUPTED / recovered_A."""
    settings = _settings(tmp_path)
    wid, ops = _seed_empty_workspace(settings)
    store = WorkspaceStore(settings)
    pub = NonEmptyPublicationCoordinator(settings, store)
    op = ops.begin(
        workspace_id=wid,
        idempotency_key="startup-a",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["x.txt"]},
        expected_revision=1,
    )
    ops.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    desired = _desired_source(name="x.txt", blob=b"x")
    with WorkspaceMutationLease(settings, wid) as lease:
        pub.begin(
            wid,
            operation_id=op.operation_id,
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
            expected_revision=1,
            desired_sources=[desired],
            lineage_delta=LineageDelta(
                appended=[
                    SourceVersionRef(
                        source_id=desired.source_id, version=desired.version
                    )
                ]
            ),
            lease=lease,
        )
        outcome = pub.recover(wid, lease=lease, terminalize_abandoned=True)
        assert outcome == "A"
    interrupted = ops.get(wid, op.operation_id)
    assert interrupted.status is ManagedOperationStatus.INTERRUPTED
    assert interrupted.recovery_note == "recovered_A"
    assert interrupted.error is None
    restored = store.get(wid)
    assert restored.status is WorkspaceStatus.EMPTY


def test_recovery_b_succeeds(tmp_path: Path) -> None:
    """Req 8: recovery to committed B → SUCCEEDED / recovered_B."""
    settings = _settings(tmp_path)
    wid, ops = _seed_empty_workspace(settings)
    store = WorkspaceStore(settings)
    pub = NonEmptyPublicationCoordinator(settings, store)
    op = ops.begin(
        workspace_id=wid,
        idempotency_key="rec-b",
        kind=ManagedOperationKind.SOURCE_ADD,
        request_payload={"files": ["b.txt"]},
        expected_revision=1,
    )
    ops.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
    desired = _desired_source(name="b.txt", blob=b"b").model_copy(
        update={"active_from_snapshot_id": "snap_test_b"}
    )
    with WorkspaceMutationLease(settings, wid) as lease:
        pub.begin(
            wid,
            operation_id=op.operation_id,
            mutation_kind=PublicationMutationKind.SOURCE_ADD,
            expected_revision=1,
            desired_sources=[desired],
            lineage_delta=LineageDelta(
                appended=[
                    SourceVersionRef(
                        source_id=desired.source_id, version=desired.version
                    )
                ]
            ),
            lease=lease,
        )
        committed = store.get(wid).model_copy(
            update={
                "revision": 2,
                "status": WorkspaceStatus.ACTIVE,
                "current_snapshot_id": "snap_test_b",
                "sources": [desired],
                "updated_at": datetime.now(tz=UTC),
            }
        )
        store.save(committed, lease=lease, allow_during_journal=True)
        journal = pub.load_journal(wid)
        assert journal is not None
        # Forward phase alone is enough for B; avoid fake snapshot pointer restore.
        pub._save_journal(  # noqa: SLF001 — test forces committed phase
            journal.model_copy(
                update={
                    "phase": NonEmptyPublicationPhase.WORKSPACE_COMMITTED,
                    "new_snapshot_id": None,
                }
            )
        )
        outcome = pub.recover(wid, lease=lease, terminalize_abandoned=True)
        assert outcome == "B"
    succeeded = ops.get(wid, op.operation_id)
    assert succeeded.status is ManagedOperationStatus.SUCCEEDED
    assert succeeded.recovery_note == "recovered_B"


def test_idempotent_replay_and_no_partial_on_live_fail(tmp_path: Path) -> None:
    """Req 10–11: idempotent replay; failed A leaves prior set authoritative."""
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "idem")["workspace_id"]
        first = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "same", "If-Match": '"1"'},
            files={"files": ("a.txt", b"idempotent pumps\n", "text/plain")},
        )
        assert first.status_code == 202, first.text
        body1 = _wait(client, first.json()["operation_id"])
        assert body1["status"] == "succeeded"
        second = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "same", "If-Match": '"1"'},
            files={"files": ("a.txt", b"idempotent pumps\n", "text/plain")},
        )
        assert second.status_code == 202, second.text
        assert second.json()["operation_id"] == first.json()["operation_id"]
        body2 = _wait(client, second.json()["operation_id"])
        assert body2["status"] == "succeeded"
        ws = WorkspaceStore(runtime.settings).get(wid)
        assert ws.revision == 2
        assert len([s for s in ws.sources if s.active]) == 1


# ---------------------------------------------------------------------------
# R1 — Final-source Remove cooperative control / EMPTY publication CS
# ---------------------------------------------------------------------------


def _add_one_source(client: TestClient, wid: str, *, key: str) -> tuple[str, int]:
    add = client.post(
        f"/v1/workspaces/{wid}/sources",
        headers={"Idempotency-Key": key, "If-Match": '"1"'},
        files={"files": ("only.txt", b"sole source for empty remove\n", "text/plain")},
    )
    assert add.status_code == 202, add.text
    body = _wait(client, add.json()["operation_id"])
    assert body["status"] == "succeeded", body
    sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
    sid = sources[0]["source_id"]
    rev = int(client.get(f"/v1/workspaces/{wid}").json()["revision"])
    return sid, rev


def test_final_remove_shutdown_before_empty_publication_cs(tmp_path: Path) -> None:
    """R1: shutdown before EMPTY CS aborts; prior workspace remains authoritative."""
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "rm-pre")["workspace_id"]
        sid, rev = _add_one_source(client, wid, key="add-pre")
        prior = WorkspaceStore(runtime.settings).get(wid)
        assert prior.status is WorkspaceStatus.ACTIVE

        original = OperationHandle.checkpoint

        def checkpoint_inject_shutdown(self: OperationHandle, where: str = "") -> None:
            if where == "pre_empty_publish":
                self.signal_cancel(CancelReason.SHUTDOWN)
            return original(self, where)

        OperationHandle.checkpoint = checkpoint_inject_shutdown  # type: ignore[method-assign]
        try:
            remove = client.delete(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "rm-pre", "If-Match": f'"{rev}"'},
            )
            assert remove.status_code == 202, remove.text
            op_id = remove.json()["operation_id"]
            body = _wait(client, op_id)
            assert body["status"] == "failed", body
            assert body["error"]["code"] == "ingest_failed"
            failed = ManagedOperationStore(runtime.settings).get(wid, op_id)
            assert failed.recovery_note == "recovered_A"
        finally:
            OperationHandle.checkpoint = original  # type: ignore[method-assign]

        restored = WorkspaceStore(runtime.settings).get(wid)
        assert restored.status is WorkspaceStatus.ACTIVE
        assert restored.revision == prior.revision
        assert restored.current_snapshot_id == prior.current_snapshot_id
        assert any(s.active and s.source_id == sid for s in restored.sources)
        assert current_pointer_path(
            runtime.settings.paths.corpora, restored.backing_corpus_name
        ).exists()


def test_final_remove_shutdown_after_empty_publication_cs_completes(
    tmp_path: Path,
) -> None:
    """R1: shutdown after EMPTY CS entry does not tear the transition in half."""
    with _client(tmp_path) as (client, runtime):
        wid = _create(client, "rm-post")["workspace_id"]
        sid, rev = _add_one_source(client, wid, key="add-post")

        original = OperationHandle.enter_publication

        def enter_then_shutdown(self: OperationHandle) -> None:
            original(self)
            self.signal_cancel(CancelReason.SHUTDOWN)

        OperationHandle.enter_publication = enter_then_shutdown  # type: ignore[method-assign]
        try:
            remove = client.delete(
                f"/v1/workspaces/{wid}/sources/{sid}",
                headers={"Idempotency-Key": "rm-post", "If-Match": f'"{rev}"'},
            )
            assert remove.status_code == 202, remove.text
            body = _wait(client, remove.json()["operation_id"])
            assert body["status"] == "succeeded", body
        finally:
            OperationHandle.enter_publication = original  # type: ignore[method-assign]

        emptied = WorkspaceStore(runtime.settings).get(wid)
        assert emptied.status is WorkspaceStatus.EMPTY
        assert emptied.current_snapshot_id is None
        assert [s for s in emptied.sources if s.active] == []


# ---------------------------------------------------------------------------
# R2 — EMPTY recovery-A terminal semantics on every A exit
# ---------------------------------------------------------------------------


def _seed_active_one_source_via_api(
    client: TestClient, runtime: ApplicationRuntime, *, prefix: str
) -> tuple[str, str, int]:
    wid = _create(client, f"{prefix}-ws")["workspace_id"]
    sid, rev = _add_one_source(client, wid, key=f"{prefix}-add")
    return wid, sid, rev


def _begin_empty_journal(
    settings: AppSettings,
    wid: str,
    *,
    op_id: str,
    removed_source_json: str | None,
) -> EmptyTransitionCoordinator:
    store = WorkspaceStore(settings)
    coord = EmptyTransitionCoordinator(settings, store)
    record = store.get(wid)
    with WorkspaceMutationLease(settings, wid) as lease:
        coord.begin(
            wid,
            expected_revision=record.revision,
            lease=lease,
            operation_id=op_id,
            removed_source_json=removed_source_json,
        )
    return coord


def test_empty_recovery_a_missing_workspace_startup_and_live(tmp_path: Path) -> None:
    """R2: missing workspace.json A exit honors terminalize_abandoned."""
    with _client(tmp_path) as (client, runtime):
        wid, sid, _rev = _seed_active_one_source_via_api(client, runtime, prefix="miss")
        settings = runtime.settings
        store = WorkspaceStore(settings)
        ops = ManagedOperationStore(settings)
        record = store.get(wid)
        removed = next(s for s in record.sources if s.source_id == sid)
        op = ops.begin(
            workspace_id=wid,
            idempotency_key="miss-op",
            kind=ManagedOperationKind.SOURCE_REMOVE,
            request_payload={"source_id": sid},
            expected_revision=record.revision,
        )
        ops.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
        coord = _begin_empty_journal(
            settings,
            wid,
            op_id=op.operation_id,
            removed_source_json=removed.model_dump_json(),
        )
        # Exceptional A branch: workspace.json unreadable/missing.
        store.workspace_path(wid).unlink()
        with WorkspaceMutationLease(settings, wid) as lease:
            assert (
                coord.recover(wid, lease=lease, terminalize_abandoned=True) == "A"
            )
        interrupted = ops.get(wid, op.operation_id)
        assert interrupted.status is ManagedOperationStatus.INTERRUPTED
        assert interrupted.recovery_note == "recovered_A"
        restored = store.get(wid)
        assert restored.status is WorkspaceStatus.ACTIVE
        assert any(s.active and s.source_id == sid for s in restored.sources)

        # Live-failure mode on a fresh op/journal: leave nonterminal.
        op2 = ops.begin(
            workspace_id=wid,
            idempotency_key="miss-live",
            kind=ManagedOperationKind.SOURCE_REMOVE,
            request_payload={"source_id": sid},
            expected_revision=restored.revision,
        )
        ops.update_status(wid, op2.operation_id, ManagedOperationStatus.RUNNING)
        coord2 = _begin_empty_journal(
            settings,
            wid,
            op_id=op2.operation_id,
            removed_source_json=removed.model_dump_json(),
        )
        store.workspace_path(wid).unlink()
        with WorkspaceMutationLease(settings, wid) as lease:
            assert (
                coord2.recover(wid, lease=lease, terminalize_abandoned=False) == "A"
            )
        mid = ops.get(wid, op2.operation_id)
        assert mid.status is ManagedOperationStatus.RUNNING
        err = AppError(
            ErrorCode.INGEST_FAILED,
            details=SafeErrorDetails(reason="shutdown_abort", stage="pre_empty_publish"),
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            ops.update_status(
                wid,
                op2.operation_id,
                ManagedOperationStatus.FAILED,
                failure_summary=str(err.code),
                recovery_note="recovered_A",
                error=ManagedOperationSafeError.from_app_error(err),
                lease=lease,
            )
        failed = ops.get(wid, op2.operation_id)
        assert failed.status is ManagedOperationStatus.FAILED
        assert failed.recovery_note == "recovered_A"
        assert failed.error is not None
        assert failed.error.code == ErrorCode.INGEST_FAILED.value


def test_empty_recovery_a_intent_and_committed_inconsistent(tmp_path: Path) -> None:
    """R2: INTENT_RECORDED and inconsistent COMMITTED A exits terminalize correctly."""
    with _client(tmp_path) as (client, runtime):
        wid, sid, _rev = _seed_active_one_source_via_api(client, runtime, prefix="ph")
        settings = runtime.settings
        store = WorkspaceStore(settings)
        ops = ManagedOperationStore(settings)
        record = store.get(wid)
        removed = next(s for s in record.sources if s.source_id == sid)

        # INTENT_RECORDED → startup A
        op = ops.begin(
            workspace_id=wid,
            idempotency_key="intent-a",
            kind=ManagedOperationKind.SOURCE_REMOVE,
            request_payload={"source_id": sid},
            expected_revision=record.revision,
        )
        ops.update_status(wid, op.operation_id, ManagedOperationStatus.RUNNING)
        coord = _begin_empty_journal(
            settings,
            wid,
            op_id=op.operation_id,
            removed_source_json=removed.model_dump_json(),
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            assert (
                coord.recover(wid, lease=lease, terminalize_abandoned=True) == "A"
            )
        assert ops.get(wid, op.operation_id).status is ManagedOperationStatus.INTERRUPTED
        assert ops.get(wid, op.operation_id).recovery_note == "recovered_A"
        assert store.get(wid).status is WorkspaceStatus.ACTIVE

        # PUBLICATION_RETIRED → live A leaves nonterminal
        record = store.get(wid)
        op2 = ops.begin(
            workspace_id=wid,
            idempotency_key="retired-live",
            kind=ManagedOperationKind.SOURCE_REMOVE,
            request_payload={"source_id": sid},
            expected_revision=record.revision,
        )
        ops.update_status(wid, op2.operation_id, ManagedOperationStatus.RUNNING)
        coord2 = _begin_empty_journal(
            settings,
            wid,
            op_id=op2.operation_id,
            removed_source_json=removed.model_dump_json(),
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            coord2.step_retire_publication(wid, lease=lease)
            assert (
                coord2.recover(wid, lease=lease, terminalize_abandoned=False) == "A"
            )
        assert ops.get(wid, op2.operation_id).status is ManagedOperationStatus.RUNNING
        assert store.get(wid).status is WorkspaceStatus.ACTIVE
        assert current_pointer_path(
            settings.paths.corpora, store.get(wid).backing_corpus_name
        ).exists()

        # COMMITTED + non-EMPTY workspace → startup A
        record = store.get(wid)
        op3 = ops.begin(
            workspace_id=wid,
            idempotency_key="committed-a",
            kind=ManagedOperationKind.SOURCE_REMOVE,
            request_payload={"source_id": sid},
            expected_revision=record.revision,
        )
        ops.update_status(wid, op3.operation_id, ManagedOperationStatus.RUNNING)
        coord3 = _begin_empty_journal(
            settings,
            wid,
            op_id=op3.operation_id,
            removed_source_json=removed.model_dump_json(),
        )
        journal = coord3.load_journal(wid)
        assert journal is not None
        coord3._save_journal(  # noqa: SLF001
            journal.model_copy(update={"phase": EmptyTransitionPhase.COMMITTED})
        )
        with WorkspaceMutationLease(settings, wid) as lease:
            assert (
                coord3.recover(wid, lease=lease, terminalize_abandoned=True) == "A"
            )
        assert ops.get(wid, op3.operation_id).status is ManagedOperationStatus.INTERRUPTED
        assert ops.get(wid, op3.operation_id).recovery_note == "recovered_A"
        assert store.get(wid).status is WorkspaceStatus.ACTIVE
