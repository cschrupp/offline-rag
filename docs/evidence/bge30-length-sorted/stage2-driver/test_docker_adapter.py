import json
from io import StringIO

import docker_adapter as adapter_module
import pytest
import socket_client as socket_client_module
from docker_adapter import (
    project_submission,
    wait_for_event,
    wait_for_worker_release,
)
from driver import Submission


def accepted_events():
    ordinal = 1
    operation = "opq_fixture"
    return [
        {
            "event": "http_received",
            "ordinal": ordinal,
            "method": "POST",
            "path": "/v1/workspaces/ws_fixture/conversation/turn",
        },
        {"event": "preflight_admitted", "ordinal": ordinal, "operation_id": operation},
        {"event": "query_admitted", "ordinal": ordinal, "operation_id": operation},
        {"event": "worker_started", "ordinal": ordinal, "operation_id": operation},
        {
            "event": "worker_returned",
            "ordinal": ordinal,
            "operation_id": operation,
            "result_status": "answered",
            "query_trace_id": "qt_fixture",
            "query_trace_present": True,
            "conversation_trace_present": True,
        },
        {
            "event": "slot_released",
            "ordinal": ordinal,
            "operation_id": operation,
            "worker_returned": True,
            "operation_released": True,
            "global_query_capacity_empty": True,
            "active_count": 0,
            "query_capacity_held": 0,
        },
        {"event": "http_response", "ordinal": ordinal, "status": 200},
    ]


def case():
    return Submission(1, "consecutive", "Recipes", 1, "load")


def transport():
    return {"transport": "response", "http_status": 200, "body": {}}


def test_complete_correlated_http_worker_and_release_passes():
    result = project_submission(
        case(),
        transport(),
        accepted_events(),
        "/v1/workspaces/ws_fixture/conversation/turn",
    )
    assert result["terminal"] == "completed"
    assert result["scientific_trace_ids"] == ["qt_fixture"]
    assert result["slot_released"] is True


def test_disconnected_request_waits_for_worker_release_without_http_response():
    rows = accepted_events()
    rows = [row for row in rows if row["event"] != "http_response"]
    rows = [
        row for row in rows if row["event"] not in {"worker_returned", "slot_released"}
    ]
    rows.append(
        {
            "event": "cancel_signaled",
            "ordinal": 1,
            "operation_id": "opq_fixture",
            "reason": "client_disconnect",
        }
    )
    rows.append(
        {
            "event": "worker_failed",
            "ordinal": 1,
            "operation_id": "opq_fixture",
            "reason": "client_disconnect",
            "error_code": "request_cancelled",
            "trace_id": None,
        }
    )
    rows.append(
        {
            "event": "slot_released",
            "ordinal": 1,
            "operation_id": "opq_fixture",
            "worker_returned": True,
            "operation_released": True,
            "global_query_capacity_empty": True,
            "active_count": 0,
            "query_capacity_held": 0,
        }
    )
    result = project_submission(
        Submission(1, "consecutive", "Recipes", 1, "disconnect_during"),
        {
            "transport": "client_disconnected",
            "http_status": None,
            "body": None,
        },
        rows,
        "/v1/workspaces/ws_fixture/conversation/turn",
    )

    assert result["terminal"] == "cancelled"
    assert result["reason"] == "client_disconnect"
    assert result["server_http_status"] is None
    assert result["worker_returned"] is True
    assert result["slot_released"] is True


def test_wait_for_worker_release_requires_terminal_and_release_events(tmp_path):
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"event": "worker_failed", "ordinal": 16})
        + "\n"
        + json.dumps({"event": "slot_released", "ordinal": 16})
        + "\n",
        encoding="utf-8",
    )

    wait_for_worker_release(tmp_path, 16, 0.1)


def test_wait_for_worker_release_fails_closed_when_capacity_remains_owned(tmp_path):
    (tmp_path / "events.jsonl").write_text(
        json.dumps({"event": "worker_failed", "ordinal": 16}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TimeoutError, match="slot release did not settle"):
        wait_for_worker_release(tmp_path, 16, 0.02)


def test_missing_worker_terminal_fails_closed():
    rows = accepted_events()
    rows = [row for row in rows if row["event"] != "worker_returned"]
    with pytest.raises(RuntimeError, match="worker/release event"):
        project_submission(
            case(), transport(), rows, "/v1/workspaces/ws_fixture/conversation/turn"
        )


def test_duplicate_http_correlation_fails_closed():
    rows = accepted_events()
    rows.append(dict(rows[0]))
    with pytest.raises(RuntimeError, match="duplicate HTTP request correlation"):
        project_submission(
            case(), transport(), rows, "/v1/workspaces/ws_fixture/conversation/turn"
        )


def test_mismatched_operation_correlation_fails_closed():
    rows = accepted_events()
    rows.append({"event": "query_admitted", "ordinal": 1, "operation_id": "opq_other"})
    with pytest.raises(RuntimeError, match="operation correlation mismatch"):
        project_submission(
            case(), transport(), rows, "/v1/workspaces/ws_fixture/conversation/turn"
        )


def test_premature_query_slot_release_fails_closed():
    rows = accepted_events()
    release = next(row for row in rows if row["event"] == "slot_released")
    returned = next(row for row in rows if row["event"] == "worker_returned")
    rows.remove(release)
    rows.insert(rows.index(returned), release)
    with pytest.raises(RuntimeError, match="capacity release preceded"):
        project_submission(
            case(), transport(), rows, "/v1/workspaces/ws_fixture/conversation/turn"
        )


def test_wrong_route_path_fails_closed():
    with pytest.raises(RuntimeError, match="unexpected route"):
        project_submission(
            case(),
            transport(),
            accepted_events(),
            "/v1/workspaces/ws_other/conversation/turn",
        )


def test_event_wait_ignores_prior_arm_lifecycle_events(tmp_path):
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {"event": "drain_grace_exhausted", "ordinal": None, "monotonic_ns": 10}
        )
        + "\n"
        + json.dumps(
            {"event": "drain_grace_exhausted", "ordinal": None, "monotonic_ns": 20}
        )
        + "\n",
        encoding="utf-8",
    )
    assert (
        wait_for_event(
            tmp_path,
            None,
            "drain_grace_exhausted",
            0.1,
            after_monotonic_ns=15,
        )["monotonic_ns"]
        == 20
    )


def test_native_teardown_preserves_thirty_second_application_grace(monkeypatch):
    name = "seneca-stage2-0123456789abcdef"
    session = "0123456789abcdef"
    running = {"Id": "container-id", "State": {"Running": True}}
    stopped = {"Id": "container-id", "State": {"Running": False}}
    owned_rows = iter((running, stopped, None))
    docker_calls = []

    monkeypatch.setattr(
        adapter_module, "owned_container", lambda _name, _session: next(owned_rows)
    )
    monkeypatch.setattr(
        adapter_module,
        "docker",
        lambda *args, **kwargs: docker_calls.append((args, kwargs)) or "",
    )

    adapter_module.terminate(name, session, stop_timeout=30)

    assert docker_calls[0][0] == ("stop", "--timeout", "30", "container-id")
    assert docker_calls[0][1]["timeout"] == 35
    assert docker_calls[1][0] == ("rm", "container-id")


def test_native_readiness_allows_model_startup_beyond_synthetic_window(monkeypatch):
    monotonic_values = iter((0, 0, 31))
    docker_calls = []

    monkeypatch.setattr(adapter_module, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(adapter_module, "sleep", lambda _seconds: None)

    def delayed_ready(*args, **kwargs):
        docker_calls.append((args, kwargs))
        if len(docker_calls) == 1:
            raise adapter_module.subprocess.CalledProcessError(1, args)
        return ""

    monkeypatch.setattr(adapter_module, "docker", delayed_ready)

    assert adapter_module.readiness_timeout("native") == 120
    assert adapter_module.readiness_timeout("synthetic") == 30
    adapter_module.wait_for_http_ready("seneca-stage2-test", 120)

    assert len(docker_calls) == 2


def test_native_readiness_remains_bounded(monkeypatch):
    monotonic_values = iter((0, 0, 120))
    monkeypatch.setattr(adapter_module, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(adapter_module, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        adapter_module,
        "docker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            adapter_module.subprocess.CalledProcessError(1, "docker")
        ),
    )

    with pytest.raises(TimeoutError, match="real app did not become ready"):
        adapter_module.wait_for_http_ready("seneca-stage2-test", 120)


def test_native_forward_entry_wait_matches_query_deadline():
    assert adapter_module.forward_entry_timeout("native") == 180
    assert adapter_module.forward_entry_timeout("synthetic") == 10


def test_disconnect_wait_uses_native_forward_deadline_only_for_held_forward():
    assert adapter_module.disconnect_entry_timeout("disconnect_before", "native") == 10
    assert adapter_module.disconnect_entry_timeout("disconnect_during", "native") == 180
    assert adapter_module.disconnect_entry_timeout("disconnect_during", "synthetic") == 10
    with pytest.raises(ValueError, match="unsupported disconnect case"):
        adapter_module.disconnect_entry_timeout("deadline", "native")


def test_socket_disconnect_barrier_waits_longer_than_default_thirty_seconds(
    monkeypatch,
):
    class Marker:
        def __init__(self, exists_values):
            self.exists_values = exists_values

        def exists(self):
            return next(self.exists_values)

        def touch(self, *, exist_ok=False):
            assert exist_ok is False

    class Journal:
        def __init__(self):
            self.marker_values = iter((False, True))

        def __truediv__(self, _name):
            return Marker(self.marker_values)

    class Connection:
        def __init__(self):
            self.closed = False

        def sendall(self, _payload):
            pass

        def close(self):
            self.closed = True

    connection = Connection()
    observed = {}

    def create_connection(_address, timeout):
        observed["socket_timeout"] = timeout
        return connection

    monkeypatch.setattr(
        socket_client_module.socket,
        "create_connection",
        create_connection,
    )
    monkeypatch.setattr(socket_client_module, "monotonic", iter((0, 45)).__next__)
    monkeypatch.setattr(socket_client_module, "sleep", lambda _seconds: None)

    class SentMarker(Marker):
        def open(self, *_args, **_kwargs):
            return StringIO()

    class JournalWithSent(Journal):
        def __truediv__(self, name):
            if name.endswith(".sent"):
                return SentMarker(iter((True,)))
            return Marker(self.marker_values)

    monkeypatch.setattr(socket_client_module, "Path", lambda _path: JournalWithSent())
    result = socket_client_module.submit(
        {
            "ordinal": 2,
            "path": "/v1/workspaces/ws_fixture/conversation/turn",
            "body": {"question": "test"},
            "timeout": 195,
            "disconnect_at": "forward_entered",
            "barrier_timeout": 180,
        }
    )

    assert result == {"transport": "client_disconnected", "http_status": None}
    assert observed["socket_timeout"] == 195
    assert connection.closed is True
