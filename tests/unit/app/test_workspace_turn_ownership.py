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


@pytest.mark.parametrize("before_claim", [True, False])
def test_trace_terminalization_orders_disconnect(tmp_path, monkeypatch, before_claim):
    from test_slice16d_b3_conversation import _conversation_client, _seed_workspace

    with _conversation_client(tmp_path) as (client, runtime, _, _):
        workspace, source, _, _ = _seed_workspace(client)
        claim = runtime.operations.claim_query_terminal

        def disconnect(handle):
            if before_claim:
                handle.signal_cancel(CancelReason.CLIENT_DISCONNECT)
            claim(handle)
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
        if before_claim:
            assert response.status_code == 500
            assert record["error_code"] == "request_cancelled"
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
