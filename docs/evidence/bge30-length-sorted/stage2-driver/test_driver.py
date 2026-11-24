from collections import Counter
from threading import Event, Lock

import pytest
from driver import Driver, schedule


class Fixture:
    def __init__(self, *, incomplete=False, held=False):
        self.lock = Lock()
        self.started = Event()
        self.released = Event()
        self.closed = 0
        self.incomplete = incomplete
        self.held = held
        self.submitted = []

    def open(self, strategy):
        self.strategy = strategy

    def submit(self, case, *, timeout):
        assert case.strategy == self.strategy
        assert timeout == 195
        with self.lock:
            self.submitted.append(case)
        self.started.set()
        if self.held:
            assert self.released.wait(4)
        lifecycle = {
            "disconnect_before": (
                "cancelled",
                "client_disconnect",
                None,
                "client_disconnected",
            ),
            "disconnect_during": (
                "cancelled",
                "client_disconnect",
                None,
                "client_disconnected",
            ),
            "deadline": ("timed_out", "query_deadline_exceeded", 504, "response"),
            "drain": ("cancelled", "shutdown", 500, "response"),
        }
        terminal, reason, status, transport = lifecycle.get(
            case.case, ("completed", None, 200, "response")
        )
        return {
            "ordinal": case.ordinal,
            "settled": not self.incomplete,
            "admission": "accepted",
            "operation": f"synthetic-{case.ordinal}",
            "terminal": terminal,
            "reason": reason,
            "worker_returned": True,
            "http_status": status,
            "transport": transport,
        }

    def abort(self):
        self.released.set()

    def close(self):
        self.closed += 1


def test_exact_full_schedule():
    events = []
    fixture = Fixture()
    Driver(fixture, lambda: True, events.append).run()
    assert len(fixture.submitted) == 36
    assert Counter(c.case == "load" for c in fixture.submitted) == {True: 28, False: 8}
    assert sorted(fixture.submitted, key=lambda c: c.ordinal) == [
        case for wave in schedule() for case in wave
    ]
    assert [len(wave) for wave in schedule()] == [1, 2, 4, 1, 2, 4, 1, 1, 1, 1] * 2
    assert events[-1] == {
        "event": "complete",
        "campaign": "full",
        "attempts": 36,
    }
    assert fixture.closed == 2


def test_performance_campaign_preserves_all_load_waves_and_only_loads():
    events = []
    fixture = Fixture()
    Driver(fixture, lambda: True, events.append).run(campaign="performance")

    scheduled = [case for wave in schedule("performance") for case in wave]
    assert len(scheduled) == 28
    assert [len(wave) for wave in schedule("performance")] == [1, 2, 4] * 4
    assert sorted(fixture.submitted, key=lambda case: case.ordinal) == scheduled
    assert all(case.case == "load" for case in fixture.submitted)
    assert events[-1] == {
        "event": "complete",
        "campaign": "performance",
        "attempts": 28,
    }
    assert fixture.closed == 2


def test_lifecycle_campaign_contains_all_cases_for_both_strategies():
    events = []
    fixture = Fixture()
    Driver(fixture, lambda: True, events.append).run(campaign="lifecycle")

    scheduled = [case for wave in schedule("lifecycle") for case in wave]
    assert len(scheduled) == 8
    assert [len(wave) for wave in schedule("lifecycle")] == [1] * 8
    assert sorted(fixture.submitted, key=lambda case: case.ordinal) == scheduled
    assert {(case.strategy, case.case) for case in fixture.submitted} == {
        (strategy, lifecycle)
        for strategy in ("consecutive", "length_sorted_8")
        for lifecycle in (
            "disconnect_before",
            "disconnect_during",
            "deadline",
            "drain",
        )
    }
    assert events[-1] == {
        "event": "complete",
        "campaign": "lifecycle",
        "attempts": 8,
    }
    assert fixture.closed == 2


def test_unknown_campaign_fails_before_opening_adapter():
    fixture = Fixture()
    with pytest.raises(ValueError, match="unknown Stage 2 campaign"):
        list(schedule("unexpected"))
    with pytest.raises(ValueError, match="unknown Stage 2 campaign"):
        Driver(fixture, lambda: True, lambda _: None).run(campaign="unexpected")
    assert fixture.closed == 0


def test_missing_terminal_aborts_without_retry():
    events = []
    fixture = Fixture(incomplete=True)
    with pytest.raises(RuntimeError, match="missing correlated"):
        Driver(fixture, lambda: True, events.append).run()
    assert len(fixture.submitted) == 1
    assert not any(e["event"] == "complete" for e in events)
    assert fixture.closed == 1


def test_failed_load_settlement_is_emitted_before_outcome_validation():
    class FailedFixture(Fixture):
        def submit(self, case, *, timeout):
            assert case.ordinal == 1
            assert timeout == 195
            return {
                "ordinal": case.ordinal,
                "settled": True,
                "admission": "accepted",
                "operation": "failed-operation",
                "terminal": "failed",
                "worker_returned": True,
                "http_status": 500,
                "server_events": [{"event": "worker_failed", "exception": "AppError"}],
            }

    events = []
    fixture = FailedFixture()
    with pytest.raises(RuntimeError, match="accepted load did not complete"):
        Driver(fixture, lambda: True, events.append).run()

    assert [event["event"] for event in events] == ["send_attempt", "settled"]
    assert events[-1]["http_status"] == 500
    assert fixture.closed == 1


def test_engineering_smoke_sends_one_request_and_requires_complete_observation():
    class SmokeFixture(Fixture):
        def submit(self, case, *, timeout):
            record = super().submit(case, timeout=timeout)
            latency = {
                "hybrid_rerank": 12,
                "context_expand": 3,
                "total": 15,
                "hybrid_rerank_breakdown": {
                    "hybrid": 8,
                    "pair_build": 1,
                    "rerank_infer": 5,
                    "sort": 1,
                    "total": 10,
                    "hybrid_breakdown": {
                        "dense": 2,
                        "lexical": 3,
                        "fusion": 1,
                        "total": 6,
                    },
                },
            }
            record["server_events"] = [
                {
                    "event": "native_scores",
                    "score_count": 30,
                    "score_associations": [
                        {
                            "candidate_id_sha256": f"{index:064x}",
                            "pair_input_sha256": f"{index + 100:064x}",
                            "raw_logit": index / 10,
                        }
                        for index in range(30)
                    ],
                },
                {
                    "event": "native_ranked_candidates",
                    "candidate_count": 30,
                    "ranked_candidate_order": [
                        f"{index + 200:064x}" for index in range(30)
                    ],
                    "tie_break": "chunk-id-asc-v1",
                },
                {"event": "native_context", "latency_ms": latency},
                {"event": "scorer_returned", "scorer_wall_ms": 11, "scorer_cpu_ms": 9},
                {
                    "event": "forward_started",
                    "shape": [16, 128],
                },
                {
                    "event": "forward_returned",
                    "elapsed_ms": 5,
                    "process_cpu_ms": 4,
                    "logits_shape": [16, 1],
                },
                {
                    "event": "forward_started",
                    "shape": [14, 128],
                },
                {
                    "event": "forward_returned",
                    "elapsed_ms": 6,
                    "process_cpu_ms": 5,
                    "logits_shape": [14, 1],
                },
                {
                    "event": "synthetic_generator_returned",
                    "elapsed_ms": 1,
                    "process_cpu_ms": 1,
                },
                {
                    "event": "native_citations",
                    "citation_chunk_count": 1,
                    "citation_evidence_unit_count": 1,
                },
                {
                    "event": "worker_returned",
                    "process_cpu_ms": 100,
                    "process_rss_kib": 2000,
                    "process_peak_rss_kib": 2500,
                },
            ]
            return record

    events = []
    fixture = SmokeFixture()
    result = Driver(fixture, lambda: True, events.append).run_engineering_smoke()

    assert result["http_status"] == 200
    assert len(fixture.submitted) == 1
    assert fixture.submitted[0].workload == "Recipes"
    assert fixture.submitted[0].strategy == "consecutive"
    assert [event["event"] for event in events] == [
        "send_attempt",
        "settled",
        "engineering_smoke_complete",
    ]
    assert fixture.closed == 1


def test_watchdog_stops_new_submissions_and_releases_fixture():
    fixture = Fixture(held=True)
    events = []
    with pytest.raises(RuntimeError, match="aborted"):
        Driver(
            fixture, lambda: not fixture.started.is_set(), events.append, watchdog=0.01
        ).run()
    assert len(fixture.submitted) == 1
    assert fixture.released.is_set()
    assert not any(e["event"] == "complete" for e in events)


def test_independent_process_deadline_terminates_held_process(tmp_path):
    import sys

    from host_watchdog import run

    path = tmp_path / "late"
    child = [
        sys.executable,
        "-c",
        "import time,pathlib,sys; time.sleep(2); pathlib.Path(sys.argv[1]).touch()",
        str(path),
    ]
    assert run(child, ceiling=0.1, memory_floor=0, grace=0.5) == 124
    assert not path.exists()


def test_resource_floor_aborts_independent_process():
    import sys

    from host_watchdog import run

    assert (
        run(
            [sys.executable, "-c", "import time; time.sleep(3)"],
            ceiling=2,
            memory_floor=2**60,
            grace=0.5,
        )
        == 124
    )


def test_forward_hooks_preserve_native_result_and_are_removed():
    torch = pytest.importorskip("torch")
    from forward_observer import observe_forward

    class Native(torch.nn.Module):
        def forward(self, *, input_ids):
            return input_ids.float().sum(dim=1)

    model = Native()
    ids = torch.tensor([[1, 2], [3, 4]])
    expected = model(input_ids=ids)
    events = []
    with observe_forward(model, lambda: "fixture", events.append):
        assert torch.equal(model(input_ids=ids), expected)
    assert torch.equal(model(input_ids=ids), expected)
    assert [e["event"] for e in events] == ["forward_enter", "forward_exit"]


@pytest.mark.parametrize(
    "admission,reason",
    [
        ("preflight_rejected", "query_preflight_capacity_exhausted"),
        ("query_rejected", "query_capacity_exhausted"),
    ],
)
def test_rejection_uses_exact_reason(admission, reason):
    from driver import validate_outcome

    case = next(schedule())[0]
    record = {
        "ordinal": case.ordinal,
        "settled": True,
        "admission": admission,
        "reason": reason,
        "http_status": 503,
        "terminal": None if admission == "preflight_rejected" else "failed",
        "operation": None if admission == "preflight_rejected" else "opq_fixture",
        "worker_returned": admission == "query_rejected",
        "scientific_trace_ids": [],
    }
    validate_outcome(record, case)
    with pytest.raises(RuntimeError, match="ambiguous"):
        validate_outcome(record | {"reason": "other"}, case)


def test_client_disconnect_alone_cannot_settle_worker():
    from driver import validate_outcome

    case = next(wave[0] for wave in schedule() if wave[0].case == "disconnect_before")
    record = {
        "ordinal": case.ordinal,
        "settled": True,
        "admission": "accepted",
        "operation": "fixture",
        "terminal": "cancelled",
        "reason": "client_disconnect",
        "http_status": None,
        "transport": "client_disconnected",
        "worker_returned": False,
    }
    with pytest.raises(RuntimeError, match="still owns capacity"):
        validate_outcome(record, case)
    validate_outcome(record | {"worker_returned": True}, case)


def test_multi_client_wave_reaches_adapter_concurrently():
    from threading import Barrier

    class Synchronized(Fixture):
        def open(self, strategy):
            super().open(strategy)
            self.arrivals = {}

        def submit(self, case, *, timeout):
            if case.case == "load" and case.wave > 1:
                with self.lock:
                    barrier = self.arrivals.setdefault(
                        (case.workload, case.wave), Barrier(case.wave)
                    )
                barrier.wait(timeout=3)
            return super().submit(case, timeout=timeout)

    fixture = Synchronized()
    Driver(fixture, lambda: True, lambda _: None).run()
    assert len(fixture.submitted) == 36
