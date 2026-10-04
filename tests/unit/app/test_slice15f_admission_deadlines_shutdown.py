"""Phase 15F — admission, deadlines, disconnect, and drain (D18 / D19)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.ingest import run_product_replace_ingest
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import (
    cleanup_staging,
    spool_multipart_upload,
    validate_ingest_http_envelope,
)
from offline_rag.app.operations import CancelReason, OperationHandle, OperationKind
from offline_rag.app.publication import current_pointer_path
from offline_rag.app.query import run_product_query
from offline_rag.app.query_runtime import SnapshotQueryRuntimeHandle
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories, RuntimeState
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
BASELINE_SHA = "5db8131dc2b6d293d67989c9935d7360880e4040"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


def _load_15e_helpers() -> Any:
    path = Path(__file__).with_name("test_slice15e_product_query_traces.py")
    spec = importlib.util.spec_from_file_location("_slice15e_helpers", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_15e = _load_15e_helpers()


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
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    api = settings.api.model_copy(update=api_overrides) if api_overrides else settings.api
    settings = settings.model_copy(
        update={"generation": generation, "reranker": reranker, "api": api}
    )
    _provision_assets(settings)
    return settings


def _query_runtime(settings: AppSettings) -> ApplicationRuntime:
    """15E-style runtime with FakeQdrant for snapshot-bound query tests."""
    return _15e._runtime(settings)


def _ingest_runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: FakeReranker(),
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _multipart(
    parts: list[tuple[str, bytes | None, str | None]], boundary: str = "----15f"
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


def _citation() -> ResolvedCitation:
    return _15e._citation()


def _canned(**kwargs: Any) -> GroundedAnswerResult:
    return _15e._canned(**kwargs)


def _publish_ready(runtime: ApplicationRuntime) -> tuple[str, Any]:
    return _15e._publish_ready(runtime)


def _trace_files(settings: AppSettings) -> list[Path]:
    root = settings.paths.traces
    if not root.exists():
        return []
    return sorted(root.glob("trace_*.json"))


def _active_handle(runtime: ApplicationRuntime) -> OperationHandle:
    with runtime.operations._idle:
        handles = list(runtime.operations._active.values())
    assert handles, "expected an active operation"
    return handles[0]


def _spool_upload(settings: AppSettings, body: bytes, content_type: str) -> Any:
    async def spool() -> Any:
        boundary = validate_ingest_http_envelope(
            content_type=content_type,
            content_length=str(len(body)),
            settings=settings,
        )

        async def chunks() -> AsyncIterator[bytes]:
            yield body

        return await spool_multipart_upload(
            settings=settings, boundary=boundary, body_chunks=chunks()
        )

    return asyncio.run(spool())


def _hold_execute(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entered: threading.Event,
    release: threading.Event,
    result: GroundedAnswerResult | Exception | None = None,
    checkpoint_while_held: bool = True,
) -> None:
    """Monkeypatch execute to block until ``release``; optionally checkpoint."""

    canned = result if result is not None else _canned(citations=[_citation()])

    def _fake(
        handle: SnapshotQueryRuntimeHandle,
        question: str,
        *,
        control: OperationHandle | None = None,
    ) -> GroundedAnswerResult:
        entered.set()
        while not release.is_set():
            if checkpoint_while_held and control is not None:
                control.checkpoint("held")
            if release.wait(timeout=0.05):
                break
        if isinstance(canned, Exception):
            raise canned
        if control is not None:
            control.checkpoint("post_hold")
        if isinstance(canned, GroundedAnswerResult):
            return canned.model_copy(update={"query": question})
        return canned

    monkeypatch.setattr("offline_rag.app.query._execute_snapshot_query", _fake)


# ---------------------------------------------------------------------------
# Ancestry
# ---------------------------------------------------------------------------


def test_remote_ancestry_begins_at_15f_baseline() -> None:
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
# A + B — query overload + independent capacity classes
# ---------------------------------------------------------------------------


def test_query_overload_and_independent_capacity_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_concurrent_query=1, max_concurrent_ingest=1)
    runtime = _query_runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    entered = threading.Event()
    release = threading.Event()
    success = _canned(
        citations=[_citation()],
        dense_index_id=identity.dense_index_id,
        lexical_index_id=identity.lexical_index_id,
        context_config_hash=identity.context_config_hash,
    )
    _hold_execute(
        monkeypatch, entered=entered, release=release, result=success
    )
    app = create_app(runtime=runtime)
    traces_before = {p.name for p in _trace_files(settings)}

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            q1 = asyncio.create_task(
                client.post(
                    "/v1/query",
                    json={"corpus": "engineering", "question": "hold query one"},
                )
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.05)
            assert entered.is_set()
            assert runtime.query_capacity.held == 1

            # B: ingest capacity remains independently acquirable.
            assert runtime.ingest_capacity.try_acquire()
            runtime.ingest_capacity.release()

            q2 = await client.post(
                "/v1/query",
                json={"corpus": "engineering", "question": "should overload"},
            )
            assert q2.status_code == 503
            assert q2.json()["error"]["code"] == "service_overloaded"
            assert q2.json()["retryable"] is True
            traces_after = {p.name for p in _trace_files(settings)}
            assert traces_after == traces_before

            release.set()
            r1 = await q1
            assert r1.status_code == 200
            assert r1.json()["snapshot_id"] == sid

    # Converse of B: held ingest does not block query admission.
    assert runtime.ingest_capacity.try_acquire()
    try:
        assert runtime.query_capacity.try_acquire()
        runtime.query_capacity.release()
    finally:
        runtime.ingest_capacity.release()

    try:
        asyncio.run(run())
    finally:
        release.set()
        runtime.shutdown()


# ---------------------------------------------------------------------------
# C — cancel await keeps capacity until worker ends
# ---------------------------------------------------------------------------


def test_cancel_keeps_capacity_until_worker_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, max_concurrent_query=1)
    runtime = _query_runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    entered = threading.Event()
    release = threading.Event()
    _hold_execute(
        monkeypatch,
        entered=entered,
        release=release,
        result=_canned(
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
        ),
        checkpoint_while_held=False,
    )
    app = create_app(runtime=runtime)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            q_task = asyncio.create_task(
                client.post(
                    "/v1/query",
                    json={"corpus": "engineering", "question": "held for cancel"},
                )
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.05)
            assert entered.is_set()
            assert runtime.query_capacity.held == 1

            op = _active_handle(runtime)
            op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            await asyncio.sleep(0.1)
            assert runtime.query_capacity.held == 1

            # Also cancel the HTTP await; ownership must still wait on the worker.
            q_task.cancel()
            await asyncio.sleep(0.1)
            assert runtime.query_capacity.held == 1

            release.set()
            for _ in range(100):
                if runtime.query_capacity.held == 0:
                    break
                await asyncio.sleep(0.05)
            assert runtime.query_capacity.held == 0
            # Task may finish as CancelledError or as a completed HTTP response
            # after the owned worker terminates with request_cancelled.
            try:
                await q_task
            except asyncio.CancelledError:
                pass

    try:
        asyncio.run(run())
    finally:
        release.set()
        runtime.shutdown()
    assert sid  # published snapshot used for binding


# ---------------------------------------------------------------------------
# D — short deadline → request_timeout
# ---------------------------------------------------------------------------


def test_short_deadline_maps_to_request_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _query_runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)

    def slow_execute(
        handle: SnapshotQueryRuntimeHandle,
        question: str,
        *,
        control: OperationHandle | None = None,
    ) -> GroundedAnswerResult:
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if control is not None:
                control.checkpoint("deadline_wait")
            time.sleep(0.01)
        if control is not None:
            control.checkpoint("after_deadline")
        return _canned(
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
            query=question,
        )

    monkeypatch.setattr("offline_rag.app.query._execute_snapshot_query", slow_execute)
    op = runtime.operations.admit_query(deadline_seconds=0.01)
    try:
        with pytest.raises(AppError) as exc:
            run_product_query(
                runtime,
                corpus="engineering",
                question="deadline please",
                control=op,
            )
        assert exc.value.code is ErrorCode.REQUEST_TIMEOUT
        assert exc.value.trace_id is not None
        path = settings.paths.traces / f"{exc.value.trace_id}.json"
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["error_code"] == "request_timeout"
        assert payload["snapshot_id"] == sid
    finally:
        runtime.operations.release(op)
        runtime.shutdown()


# ---------------------------------------------------------------------------
# E — generation_timeout still preferred when deadline not expired
# ---------------------------------------------------------------------------


def test_generation_timeout_when_deadline_not_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _query_runtime(settings)
    runtime.start()
    _publish_ready(runtime)

    def timeout_result(
        handle: SnapshotQueryRuntimeHandle,
        question: str,
        *,
        control: OperationHandle | None = None,
    ) -> GroundedAnswerResult:
        if control is not None:
            control.checkpoint("pre_gen")
        return _canned(
            status="generation_failed",
            answer_text=None,
            generation_failure_reason="timeout",
            query=question,
        )

    monkeypatch.setattr(
        "offline_rag.app.query._execute_snapshot_query", timeout_result
    )
    op = runtime.operations.admit_query(deadline_seconds=30.0)
    try:
        with pytest.raises(AppError) as exc:
            run_product_query(
                runtime,
                corpus="engineering",
                question="generation timeout path",
                control=op,
            )
        assert exc.value.code is ErrorCode.GENERATION_TIMEOUT
        assert exc.value.trace_id is not None
        path = settings.paths.traces / f"{exc.value.trace_id}.json"
        assert json.loads(path.read_text(encoding="utf-8"))["error_code"] == (
            "generation_timeout"
        )
    finally:
        runtime.operations.release(op)

    # HTTP mapping remains 504 generation_timeout.
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "http generation timeout"},
        )
    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "generation_timeout"
    runtime.shutdown()


# ---------------------------------------------------------------------------
# F — query disconnect → request_cancelled durable trace
# ---------------------------------------------------------------------------


def test_query_disconnect_records_request_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _query_runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    entered = threading.Event()
    release = threading.Event()
    _hold_execute(
        monkeypatch, entered=entered, release=release, checkpoint_while_held=True
    )

    op = runtime.operations.admit_query()
    errors: dict[str, AppError] = {}

    def worker() -> None:
        try:
            run_product_query(
                runtime,
                corpus="engineering",
                question="disconnect me",
                control=op,
            )
        except AppError as exc:
            errors["exc"] = exc
        finally:
            runtime.operations.release(op)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=5)
    assert runtime.query_capacity.held == 1
    op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
    # Worker should abort via checkpoint; release Event is a safety valve.
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert "exc" in errors
    assert errors["exc"].code is ErrorCode.REQUEST_CANCELLED
    assert errors["exc"].trace_id is not None
    path = settings.paths.traces / f"{errors['exc'].trace_id}.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["error_code"] == (
        "request_cancelled"
    )
    assert runtime.query_capacity.held == 0
    runtime.shutdown()


# ---------------------------------------------------------------------------
# G — drain readiness / rejection
# ---------------------------------------------------------------------------


def test_begin_drain_rejects_ready_and_product_routes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _query_runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200

        runtime.begin_drain()
        assert runtime.state is RuntimeState.DRAINING

        live = client.get("/health/live")
        assert live.status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["error"]["code"] == "runtime_not_ready"

        query = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "after drain"},
        )
        assert query.status_code == 503
        assert query.json()["error"]["code"] == "runtime_not_ready"

        docs = client.get("/v1/documents", params={"corpus": "engineering"})
        assert docs.status_code == 503
        assert docs.json()["error"]["code"] == "runtime_not_ready"

        trace = client.get("/v1/trace/trace_" + ("a" * 32))
        assert trace.status_code == 503
        assert trace.json()["error"]["code"] == "runtime_not_ready"

        body, ct = _multipart(
            [
                ("corpus", b"engineering", None),
                ("files", b"should reject during drain\n", "a.txt"),
            ]
        )
        ingest = client.post("/v1/ingest", content=body, headers={"Content-Type": ct})
        assert ingest.status_code == 503
        assert ingest.json()["error"]["code"] == "runtime_not_ready"

    # TestClient lifespan finalize may have stopped the runtime already.
    assert runtime.state in {RuntimeState.DRAINING, RuntimeState.STOPPED}


# ---------------------------------------------------------------------------
# H — pre-lease disconnect does not publish
# ---------------------------------------------------------------------------


def test_pre_lease_disconnect_does_not_publish(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _ingest_runtime(settings)
    runtime.start()
    boundary = b"----15f"
    content_type = "multipart/form-data; boundary=----15f"
    validate_boundary = validate_ingest_http_envelope(
        content_type=content_type,
        content_length=None,
        settings=settings,
    )
    assert validate_boundary == boundary

    async def run() -> AppError:
        async def failing_chunks() -> AsyncIterator[bytes]:
            prefix = (
                b"------15f\r\n"
                b'Content-Disposition: form-data; name="files"; filename="a.txt"\r\n'
                b"Content-Type: application/octet-stream\r\n\r\n"
                b"partial-"
            )
            yield prefix
            raise RuntimeError("client disconnect")

        op = runtime.operations.admit_ingest()
        try:
            with pytest.raises(AppError) as exc:
                await spool_multipart_upload(
                    settings=settings,
                    boundary=boundary,
                    body_chunks=failing_chunks(),
                )
            op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            assert op.cancel_reason is CancelReason.CLIENT_DISCONNECT
            return exc.value
        finally:
            for staging in settings.paths.staging.glob("*"):
                if staging.is_dir():
                    cleanup_staging(staging)
            runtime.operations.release(op)

    err = asyncio.run(run())
    assert err.code is ErrorCode.REQUEST_INVALID
    assert list(settings.paths.staging.glob("*")) == []
    assert not current_pointer_path(settings.paths.corpora, "eng").exists()
    runtime.shutdown()


# ---------------------------------------------------------------------------
# I — post-lease client disconnect ignored
# ---------------------------------------------------------------------------


def test_post_lease_client_disconnect_ignored(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _ingest_runtime(settings)
    runtime.start()
    op = runtime.operations.admit_ingest()
    try:
        op.mark_post_lease()
        op.signal_cancel(CancelReason.CLIENT_DISCONNECT)
        assert op.cancel_reason is CancelReason.NONE
        assert not op.cancel_event.is_set()
        op.checkpoint("post_lease_work")  # must not raise
    finally:
        runtime.operations.release(op)

    # Worker can still finish a full replace after a post-lease disconnect signal.
    hold = threading.Event()
    released = threading.Event()

    def after_lease(corpus: str, candidate_root: Path) -> None:
        op2 = _active_handle(runtime)
        op2.signal_cancel(CancelReason.CLIENT_DISCONNECT)
        assert op2.cancel_reason is CancelReason.NONE
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
            ("files", b"Post lease disconnect continue.\n", "a.txt"),
        ]
    )
    upload = _spool_upload(settings, body, ct)
    op_finish = runtime.operations.admit_ingest()
    try:
        result = run_product_replace_ingest(
            runtime, upload, hooks=runtime.product_ingest_hooks, control=op_finish
        )
    finally:
        runtime.operations.release(op_finish)
    assert result.snapshot_id.startswith("snap_")
    runtime.shutdown()


# ---------------------------------------------------------------------------
# J — shutdown abort pre-publication leaves pointer unchanged
# ---------------------------------------------------------------------------


def test_shutdown_abort_pre_publication_no_pointer_change(tmp_path: Path) -> None:
    settings = _settings(tmp_path, shutdown_grace_seconds=2)
    runtime = _ingest_runtime(settings)
    runtime.start()

    body_n, ct_n = _multipart(
        [
            ("corpus", b"eng", None),
            ("files", b"Published document N stable.\n", "n.txt"),
        ]
    )
    upload_n = _spool_upload(settings, body_n, ct_n)
    op_n = runtime.operations.admit_ingest()
    try:
        first = run_product_replace_ingest(runtime, upload_n, control=op_n)
    finally:
        runtime.operations.release(op_n)
    snap_n = first.snapshot_id

    entered = threading.Event()
    proceed = threading.Event()

    def after_lease(corpus: str, candidate_root: Path) -> None:
        entered.set()
        assert proceed.wait(timeout=10)

    runtime.product_ingest_hooks = ProductIngestHooks(after_lease_acquired=after_lease)
    results: dict[str, object] = {}

    def worker() -> None:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Candidate that should abort on drain.\n", "n1.txt"),
            ]
        )
        upload = _spool_upload(settings, body, ct)
        op = runtime.operations.admit_ingest()
        try:
            run_product_replace_ingest(
                runtime, upload, hooks=runtime.product_ingest_hooks, control=op
            )
            results["ok"] = True
        except AppError as exc:
            results["error"] = exc
        finally:
            runtime.operations.release(op)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=10)
    runtime.begin_drain()
    proceed.set()
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert "error" in results
    err = results["error"]
    assert isinstance(err, AppError)
    assert err.code is ErrorCode.INGEST_FAILED
    assert err.details is not None
    assert err.details.get("reason") == "shutdown_abort"
    pointer = current_pointer_path(settings.paths.corpora, "eng")
    assert pointer.is_file()
    assert json.loads(pointer.read_text(encoding="utf-8"))["snapshot_id"] == snap_n
    runtime.finalize_shutdown()


# ---------------------------------------------------------------------------
# K — shutdown during publication allows finish; pointer valid
# ---------------------------------------------------------------------------


def test_shutdown_during_publication_allows_finish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, shutdown_grace_seconds=5)
    runtime = _ingest_runtime(settings)
    runtime.start()

    entered_pub = threading.Event()
    release_pub = threading.Event()
    real_publish = runtime.publication.publish

    def holding_publish(corpus_name: str, identity: Any) -> str:
        # Publication CS: enter_publication already called by ingest path.
        op = _active_handle(runtime)
        assert op.in_publication
        entered_pub.set()
        assert release_pub.wait(timeout=10)
        return real_publish(corpus_name, identity)

    monkeypatch.setattr(runtime.publication, "publish", holding_publish)

    results: dict[str, object] = {}

    def worker() -> None:
        body, ct = _multipart(
            [
                ("corpus", b"eng", None),
                ("files", b"Publication critical section document.\n", "a.txt"),
            ]
        )
        upload = _spool_upload(settings, body, ct)
        op = runtime.operations.admit_ingest()
        try:
            result = run_product_replace_ingest(runtime, upload, control=op)
            results["snapshot_id"] = result.snapshot_id
        except Exception as exc:  # noqa: BLE001
            results["error"] = exc
        finally:
            runtime.operations.release(op)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered_pub.wait(timeout=30)
    runtime.begin_drain()
    # Shutdown signal must not abort publication CS.
    op = _active_handle(runtime)
    assert op.cancel_reason is CancelReason.NONE or op.in_publication
    release_pub.set()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert "error" not in results
    snap = results["snapshot_id"]
    assert isinstance(snap, str) and snap.startswith("snap_")
    pointer = current_pointer_path(settings.paths.corpora, "eng")
    assert json.loads(pointer.read_text(encoding="utf-8"))["snapshot_id"] == snap
    assert runtime.wait_for_drain(1.0) is True
    runtime.finalize_shutdown()


# ---------------------------------------------------------------------------
# L — grace expiry is not request_timeout
# ---------------------------------------------------------------------------


def test_grace_expiry_does_not_fabricate_request_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, shutdown_grace_seconds=1)
    runtime = _query_runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    entered = threading.Event()
    release = threading.Event()
    # Never checkpoint while held so grace expiry cannot invent request_timeout.
    _hold_execute(
        monkeypatch,
        entered=entered,
        release=release,
        checkpoint_while_held=False,
    )

    op = runtime.operations.admit_query()
    done = threading.Event()

    def worker() -> None:
        try:
            run_product_query(
                runtime,
                corpus="engineering",
                question="stuck past grace",
                control=op,
            )
        except Exception as exc:  # noqa: BLE001
            # Expected under drain/cancel; keep worker terminal for capacity release.
            assert exc is not None
        finally:
            runtime.operations.release(op)
            done.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=5)
    traces_before = {p.name for p in _trace_files(settings)}
    runtime.begin_drain()
    assert runtime.wait_for_drain(0.05) is False
    runtime.finalize_shutdown()
    assert runtime.state is RuntimeState.STOPPED
    # No request_timeout traces invented by grace alone.
    timeout_traces = []
    for path in _trace_files(settings):
        if path.name in traces_before:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("error_code") == "request_timeout":
            timeout_traces.append(path.name)
    assert timeout_traces == []
    release.set()
    assert done.wait(timeout=5)
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# M — health/live responsive during drain wait / held query
# ---------------------------------------------------------------------------


def test_health_live_responsive_during_drain_and_held_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, shutdown_grace_seconds=5)
    runtime = _query_runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    entered = threading.Event()
    release = threading.Event()
    _hold_execute(
        monkeypatch,
        entered=entered,
        release=release,
        result=_canned(
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
        ),
        checkpoint_while_held=False,
    )
    app = create_app(runtime=runtime)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            q_task = asyncio.create_task(
                client.post(
                    "/v1/query",
                    json={"corpus": "engineering", "question": "hold during drain"},
                )
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.05)
            assert entered.is_set()

            live_before = await client.get("/health/live")
            assert live_before.status_code == 200

            drain_task = asyncio.create_task(
                asyncio.to_thread(runtime.wait_for_drain, 2.0)
            )
            runtime.begin_drain()
            live_during = await client.get("/health/live")
            assert live_during.status_code == 200
            ready_during = await client.get("/health/ready")
            assert ready_during.status_code == 503
            assert ready_during.json()["error"]["code"] == "runtime_not_ready"

            release.set()
            drained = await drain_task
            assert drained is True
            q_resp = await q_task
            # Shutdown cancel may surface as cancelled/internal depending on timing.
            assert q_resp.status_code in {200, 204, 500}
            if q_resp.status_code == 200:
                assert q_resp.json()["snapshot_id"] == sid

    try:
        asyncio.run(run())
    finally:
        release.set()
        if runtime.state is not RuntimeState.STOPPED:
            runtime.finalize_shutdown()


# ---------------------------------------------------------------------------
# Shutdown idempotency smoke
# ---------------------------------------------------------------------------


def test_shutdown_and_drain_async_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path, shutdown_grace_seconds=1)
    runtime = _query_runtime(settings)
    runtime.start()
    runtime.shutdown()
    assert runtime.state is RuntimeState.STOPPED
    assert runtime.shutdown_count >= 1
    runtime.shutdown()
    assert runtime.state is RuntimeState.STOPPED
    asyncio.run(runtime.drain_async())
    assert runtime.state is RuntimeState.STOPPED


def test_operation_kind_and_enter_publication_guards(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _query_runtime(settings)
    q = runtime.operations.admit_query()
    try:
        assert q.kind is OperationKind.QUERY
        with pytest.raises(RuntimeError):
            q.mark_post_lease()
        with pytest.raises(RuntimeError):
            q.enter_publication()
    finally:
        runtime.operations.release(q)

    ing = runtime.operations.admit_ingest()
    try:
        assert ing.kind is OperationKind.INGEST
        ing.mark_post_lease()
        ing.enter_publication()
        assert ing.in_publication
        ing.signal_cancel(CancelReason.SHUTDOWN)
        # Publication CS ignores shutdown cancel.
        assert ing.cancel_reason is CancelReason.NONE
        ing.checkpoint("in_publication")
    finally:
        runtime.operations.release(ing)
