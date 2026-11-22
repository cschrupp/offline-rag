"""Registry and terminalization checks for the workspace turn envelope."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.operations import CancelReason
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.config.models import AppSettings


def test_preflight_protects_resources_during_drain():
    runtime = ApplicationRuntime(settings=AppSettings())
    registry = runtime.operations
    binding_started = Barrier(2)
    release_binding = Barrier(2)

    def prepare():
        handle = registry.start_query_preflight()
        try:
            binding_started.wait(timeout=3)
            release_binding.wait(timeout=3)
            with pytest.raises(AppError) as err:
                registry.promote_query_preflight(handle)
            assert err.value.code == ErrorCode.REQUEST_CANCELLED
        finally:
            registry.release(handle)

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(prepare)
        binding_started.wait(timeout=3)
        runtime.begin_drain()
        assert not runtime.wait_for_drain(0)
        assert not runtime.finalize_shutdown()
        with pytest.raises(AppError) as err:
            registry.start_query_preflight()
        assert err.value.code == ErrorCode.RUNTIME_NOT_READY
        release_binding.wait(timeout=3)
        worker.result(timeout=3)
    assert runtime.finalize_shutdown()


def test_promotion_competes_with_managed_query_and_waits_for_release():
    registry = ApplicationRuntime(settings=AppSettings()).operations
    managed = registry.admit_query()
    preparing = registry.start_query_preflight()
    with pytest.raises(AppError) as err:
        registry.promote_query_preflight(preparing)
    assert err.value.code == ErrorCode.SERVICE_OVERLOADED
    assert registry.active_count() == 2
    registry.release(managed)
    registry.promote_query_preflight(preparing)
    assert registry.active_count() == 1
    with pytest.raises(AppError) as err:
        registry.admit_query()
    assert err.value.code == ErrorCode.SERVICE_OVERLOADED
    registry.release(preparing)
    registry.release(preparing)
    assert registry.active_count() == 0
    replacement = registry.admit_query()
    registry.release(replacement)


@pytest.mark.parametrize("cancel_first", [True, False])
def test_terminal_claim_orders_disconnect(cancel_first):
    registry = ApplicationRuntime(settings=AppSettings()).operations
    handle = registry.start_query_preflight()
    registry.promote_query_preflight(handle)
    if cancel_first:
        handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)
        with pytest.raises(AppError) as err:
            registry.claim_query_terminal(handle)
        assert err.value.code == ErrorCode.REQUEST_CANCELLED
    else:
        registry.claim_query_terminal(handle)
        handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)
        assert not handle.cancel_event.is_set()
    assert registry.active_count() == 1
    registry.release(handle)


def test_preflight_limit_is_distinct_from_query_capacity():
    registry = ApplicationRuntime(settings=AppSettings()).operations
    preflight = registry.start_query_preflight()
    try:
        with pytest.raises(AppError) as err:
            registry.start_query_preflight()
        assert err.value.details == {"reason": "query_preflight_capacity_exhausted"}
        query = registry.admit_query()
        registry.release(query)
    finally:
        registry.release(preflight)


def test_admitted_worker_keeps_resources_after_drain_grace():
    runtime = ApplicationRuntime(settings=AppSettings())
    registry = runtime.operations
    handle = registry.start_query_preflight()
    registry.promote_query_preflight(handle)
    runtime.begin_drain()
    assert not runtime.wait_for_drain(0)
    assert not runtime.finalize_shutdown()
    assert registry.grace_exhausted
    assert handle.cancel_reason is CancelReason.SHUTDOWN
    with pytest.raises(AppError):
        registry.claim_query_terminal(handle)
    registry.release(handle)
    assert runtime.finalize_shutdown()


def test_stale_binding_precedes_query_overload(tmp_path, monkeypatch):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)
        handle = runtime.operations.admit_query()

        def stale(*args):
            raise AppError(ErrorCode.SNAPSHOT_UNAVAILABLE)

        monkeypatch.setattr(runtime.publication, "resolve_snapshot", stale)
        try:
            response = client.post(
                f"/v1/workspaces/{workspace}/conversation/turn",
                json={
                    "question": "What is supervised learning?",
                    "source_ids": [source],
                },
            )
            assert response.json()["error"]["code"] == "snapshot_unavailable"
            assert runtime.operations.active_count() == 1
        finally:
            runtime.operations.release(handle)


@pytest.mark.parametrize(
    ("signal", "status", "error"),
    [
        ("disconnect_before", 500, "request_cancelled"),
        ("deadline_before", 504, "request_timeout"),
        ("shutdown_before", 500, "request_cancelled"),
        ("disconnect_after", 200, None),
    ],
)
def test_trace_terminalization_orders_disconnect(
    tmp_path, monkeypatch, signal, status, error
):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)
        claim = runtime.operations.claim_query_terminal

        def disconnect(handle):
            if signal == "disconnect_before":
                handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            if signal == "deadline_before":
                handle.deadline_mono = 0
            if signal == "shutdown_before":
                runtime.begin_drain()
            claim(handle)
            if signal == "disconnect_after":
                handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)

        monkeypatch.setattr(runtime.operations, "claim_query_terminal", disconnect)
        response = client.post(
            f"/v1/workspaces/{workspace}/conversation/turn",
            json={"question": "What is supervised learning?", "source_ids": [source]},
        )
        trace_dir = runtime.settings.paths.traces
        query_paths = list(trace_dir.glob("trace_*.json"))
        conversation_paths = list((trace_dir / "conversation").glob("*.json"))
        assert len(query_paths) == 1
        record = json.loads(query_paths[0].read_text())
        assert response.status_code == status
        if error:
            assert record["error_code"] == error
            assert record["status"] is None
            assert not conversation_paths
        else:
            assert response.status_code == 200
            assert record["status"] == "answered"
            assert len(conversation_paths) == 1
        assert runtime.operations.active_count() == 0


@pytest.mark.parametrize(
    "boundary", ["_enrich_workspace_citations", "_commit_conversation_trace"]
)
def test_post_query_failure_does_not_return_answer_or_duplicate_trace(
    tmp_path, monkeypatch, boundary
):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)

        def fail(*args, **kwargs):
            raise AppError(ErrorCode.INTERNAL_ERROR)

        monkeypatch.setattr(f"offline_rag.app.conversation.turn.{boundary}", fail)
        response = client.post(
            f"/v1/workspaces/{workspace}/conversation/turn",
            json={"question": "What is supervised learning?", "source_ids": [source]},
        )
        assert response.status_code == 500
        trace_dir = runtime.settings.paths.traces
        query_paths = list(trace_dir.glob("trace_*.json"))
        assert len(query_paths) == 1
        assert json.loads(query_paths[0].read_text())["status"] == "answered"
        assert not list((trace_dir / "conversation").glob("*.json"))
        assert runtime.operations.active_count() == 0


def test_disconnect_before_rerank_skips_resolver_and_grounded_trace(
    tmp_path, monkeypatch
):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, captures, _):
        workspace, source, _, _ = _seed_workspace(client)
        promote = runtime.operations.promote_query_preflight

        def disconnect(handle):
            promote(handle)
            handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)

        monkeypatch.setattr(runtime.operations, "promote_query_preflight", disconnect)
        response = client.post(
            f"/v1/workspaces/{workspace}/conversation/turn",
            json={"question": "What is supervised learning?", "source_ids": [source]},
        )
        assert response.status_code == 500
        assert not captures["assemble_queries"]
        assert not captures["generator_requests"]
        assert not list(runtime.settings.paths.traces.rglob("trace_*.json"))
        assert runtime.operations.active_count() == 0


def test_held_preflight_reproduces_validation_precedence_conflict(
    tmp_path, monkeypatch
):
    from threading import Event

    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)
        entered, release = Event(), Event()
        resolve = runtime.publication.resolve_snapshot
        stale = False
        resolutions = 0

        def held(*args, **kwargs):
            nonlocal resolutions
            resolutions += 1
            if resolutions == 1:
                entered.set()
                assert release.wait(8)
            if stale:
                raise AppError(ErrorCode.SNAPSHOT_UNAVAILABLE)
            return resolve(*args, **kwargs)

        monkeypatch.setattr(runtime.publication, "resolve_snapshot", held)

        def send(wid, sid):
            return client.post(
                f"/v1/workspaces/{wid}/conversation/turn",
                json={"question": "What is supervised learning?", "source_ids": [sid]},
            )

        cases = [
            ("invalid_scope", workspace, "src_unknown"),
            ("unknown_workspace", "ws_" + "0" * 32, source),
            ("unavailable_snapshot", workspace, source),
            ("valid", workspace, source),
        ]
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(send, workspace, source)
            try:
                assert entered.wait(4)
                for name, wid, sid in cases:
                    stale = name == "unavailable_snapshot"
                    result = send(wid, sid)
                    assert result.status_code == 503
                    assert result.json()["error"]["code"] == "service_overloaded"
                    assert (
                        result.json()["details"]["reason"]
                        == "query_preflight_capacity_exhausted"
                    )
                    print(
                        name,
                        "held:",
                        result.status_code,
                        result.json()["error"]["code"],
                        result.json()["details"]["reason"],
                    )
                assert resolutions == 1
            finally:
                stale = False
                release.set()
            assert first.result(timeout=8).status_code == 200
        for name, wid, sid in cases:
            stale = name == "unavailable_snapshot"
            result = send(wid, sid)
            code = result.json().get("error", {}).get("code")
            print(name, "idle:", result.status_code, code)
            if name == "valid":
                assert result.status_code == 200
            else:
                assert result.status_code != 503 and result.status_code >= 400
        assert runtime.operations.active_count() == 0


def test_query_trace_write_failure_after_claim_returns_no_answer(tmp_path, monkeypatch):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    from offline_rag.app.traces import ProductTraceStore

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)
        writes = []

        def fail(self, record):
            writes.append(record)
            with pytest.raises(AppError) as err:
                runtime.operations.admit_query()
            assert err.value.code == ErrorCode.SERVICE_OVERLOADED
            raise OSError("fixture I/O failure")

        monkeypatch.setattr(ProductTraceStore, "commit", fail)
        result = client.post(
            f"/v1/workspaces/{workspace}/conversation/turn",
            json={"question": "What is supervised learning?", "source_ids": [source]},
        )
        assert result.status_code == 500
        assert len(writes) == 1
        assert not list(runtime.settings.paths.traces.rglob("trace_*.json"))
        assert runtime.operations.active_count() == 0


def test_repeated_transport_cancel_keeps_capacity_until_worker_returns():
    import asyncio
    from threading import Event

    from offline_rag.api.workers import run_owned_worker

    entered, release = Event(), Event()

    async def scenario():
        registry = ApplicationRuntime(settings=AppSettings()).operations
        handle = registry.start_query_preflight()
        registry.promote_query_preflight(handle)

        def held():
            entered.set()
            assert release.wait(5)

        async def route():
            try:
                await run_owned_worker(
                    request=None,
                    operation=handle,
                    worker=held,
                    watch_disconnect=False,
                    retain_on_repeated_cancel=True,
                )
            finally:
                registry.release(handle)

        task = asyncio.create_task(route())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            for _ in range(3):
                task.cancel()
                await asyncio.sleep(0)
                assert not task.done()
                with pytest.raises(AppError) as err:
                    registry.admit_query()
                assert err.value.code == ErrorCode.SERVICE_OVERLOADED
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
        assert registry.active_count() == 0
        registry.release(registry.admit_query())

    asyncio.run(scenario())
