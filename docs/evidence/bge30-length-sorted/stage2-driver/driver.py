"""Bounded Stage 2 scheduler. Transport and diagnostic hooks are injected."""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from threading import Barrier, Event, Lock, Thread
from time import monotonic

STRATEGIES = ("consecutive", "length_sorted_8")
WORKLOADS = ("Recipes", "Rich")
LIFECYCLE = ("disconnect_before", "disconnect_during", "deadline", "drain")


@dataclass(frozen=True)
class Submission:
    ordinal: int
    strategy: str
    workload: str
    wave: int
    case: str


def schedule(campaign="full"):
    """Yield the frozen workload waves for one independently owned campaign."""
    if campaign not in {"full", "performance", "lifecycle"}:
        raise ValueError(f"unknown Stage 2 campaign: {campaign}")
    ordinal = 0
    for strategy in STRATEGIES:
        if campaign in {"full", "performance"}:
            for workload in WORKLOADS:
                for size in (1, 2, 4):
                    wave = []
                    for _ in range(size):
                        ordinal += 1
                        wave.append(
                            Submission(ordinal, strategy, workload, size, "load")
                        )
                    yield tuple(wave)
        if campaign in {"full", "lifecycle"}:
            for case in LIFECYCLE:
                ordinal += 1
                yield (Submission(ordinal, strategy, "Recipes", 1, case),)


def validate_outcome(record, case):
    """Validate lifecycle accounting independently of HTTP delivery."""
    if not record.get("settled") or record.get("ordinal") != case.ordinal:
        raise RuntimeError("missing correlated terminal outcome")
    admission = record.get("admission")
    operation = record.get("operation")
    terminal = record.get("terminal")
    status = record.get("http_status")
    if admission == "preflight_rejected":
        if (
            status != 503
            or record.get("reason") != "query_preflight_capacity_exhausted"
            or terminal is not None
            or operation is not None
            or record.get("worker_returned") is not False
            or record.get("scientific_trace_ids") != []
        ):
            raise RuntimeError("ambiguous preflight rejection")
    elif admission == "query_rejected":
        if (
            status != 503
            or record.get("reason") != "query_capacity_exhausted"
            or terminal != "failed"
            or record.get("worker_returned") is not True
            or record.get("scientific_trace_ids") != []
        ):
            raise RuntimeError("ambiguous query-capacity rejection")
    elif admission == "accepted":
        if not operation or terminal not in {
            "completed",
            "cancelled",
            "timed_out",
            "failed",
        }:
            raise RuntimeError("accepted request missing operation or terminal state")
        if record.get("worker_returned") is not True:
            raise RuntimeError("accepted worker still owns capacity")
    else:
        raise RuntimeError("unknown admission outcome")
    if status is not None and not isinstance(status, int):
        raise RuntimeError("invalid HTTP status")
    if case.case == "load":
        if admission == "accepted" and (terminal != "completed" or status != 200):
            raise RuntimeError("accepted load did not complete with HTTP 200")
        return
    if admission != "accepted":
        raise RuntimeError("lifecycle case was rejected before operation ownership")
    if case.case == "disconnect_before":
        if (
            terminal != "cancelled"
            or record.get("reason") != "client_disconnect"
            or record.get("transport") != "client_disconnected"
        ):
            raise RuntimeError("pre-rerank disconnect outcome mismatch")
    elif case.case == "disconnect_during":
        if (
            terminal != "cancelled"
            or record.get("reason") != "client_disconnect"
            or record.get("transport") != "client_disconnected"
        ):
            raise RuntimeError("held-forward disconnect outcome mismatch")
    elif case.case == "deadline":
        if (
            terminal != "timed_out"
            or record.get("reason") != "query_deadline_exceeded"
            or status != 504
        ):
            raise RuntimeError("cooperative deadline outcome mismatch")
    elif case.case == "drain" and (
        terminal != "cancelled" or record.get("reason") != "shutdown"
    ):
        raise RuntimeError("drain cancellation outcome mismatch")


def validate_engineering_smoke(record):
    """Require one complete native request with observer and resource evidence."""
    if (
        record.get("admission") != "accepted"
        or record.get("terminal") != "completed"
        or record.get("http_status") != 200
    ):
        raise RuntimeError("native engineering smoke did not complete with HTTP 200")
    events = record.get("server_events", [])

    def one(name):
        matches = [item for item in events if item.get("event") == name]
        if len(matches) != 1:
            raise RuntimeError(f"native engineering smoke missing {name}")
        return matches[0]

    scores = one("native_scores")
    associations = scores.get("score_associations", [])
    if scores.get("score_count") != 30 or len(associations) != 30:
        raise RuntimeError("native engineering smoke did not score all 30 candidates")
    candidate_ids = []
    for association in associations:
        candidate_id = association.get("candidate_id_sha256")
        pair_id = association.get("pair_input_sha256")
        score = association.get("raw_logit")
        if (
            not isinstance(candidate_id, str)
            or len(candidate_id) != 64
            or not isinstance(pair_id, str)
            or len(pair_id) != 64
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
        ):
            raise RuntimeError("native engineering smoke score association is invalid")
        candidate_ids.append(candidate_id)
    if len(set(candidate_ids)) != 30:
        raise RuntimeError("native engineering smoke candidate IDs are not unique")
    ranking = one("native_ranked_candidates")
    if (
        ranking.get("candidate_count") != 30
        or len(ranking.get("ranked_candidate_order", [])) != 30
        or len(set(ranking["ranked_candidate_order"])) != 30
        or ranking.get("tie_break") != "chunk-id-asc-v1"
    ):
        raise RuntimeError("native engineering smoke ranking evidence is incomplete")
    context = one("native_context")
    latency = context.get("latency_ms", {})
    rerank_latency = latency.get("hybrid_rerank_breakdown", {})
    hybrid_latency = rerank_latency.get("hybrid_breakdown", {})
    required_latency = (
        (latency, ("hybrid_rerank", "context_expand", "total")),
        (rerank_latency, ("hybrid", "pair_build", "rerank_infer", "sort", "total")),
        (hybrid_latency, ("dense", "lexical", "fusion", "total")),
    )
    if any(
        not isinstance(source.get(key), (int, float))
        or not math.isfinite(float(source[key]))
        for source, keys in required_latency
        for key in keys
    ):
        raise RuntimeError("native engineering smoke component timings are incomplete")
    scorer = one("scorer_returned")
    if not all(
        isinstance(scorer.get(key), (int, float)) and math.isfinite(float(scorer[key]))
        for key in ("scorer_wall_ms", "scorer_cpu_ms")
    ):
        raise RuntimeError("native engineering smoke scorer timings are incomplete")
    forward_started = [
        item for item in events if item.get("event") == "forward_started"
    ]
    forward_returned = [
        item for item in events if item.get("event") == "forward_returned"
    ]
    if (
        len(forward_started) != 2
        or len(forward_returned) != 2
        or [item.get("shape", [None])[0] for item in forward_started] != [16, 14]
    ):
        raise RuntimeError(
            "native engineering smoke forward measurements are incomplete"
        )
    for started, returned in zip(forward_started, forward_returned, strict=True):
        shape = started.get("shape")
        logits_shape = returned.get("logits_shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or not 0 < shape[1] <= 1024
            or logits_shape != [shape[0], 1]
            or not all(
                isinstance(returned.get(key), (int, float))
                and math.isfinite(float(returned[key]))
                for key in ("elapsed_ms", "process_cpu_ms")
            )
        ):
            raise RuntimeError(
                "native engineering smoke forward measurements are invalid"
            )
    generator = one("synthetic_generator_returned")
    if not all(
        isinstance(generator.get(key), (int, float))
        and math.isfinite(float(generator[key]))
        for key in ("elapsed_ms", "process_cpu_ms")
    ):
        raise RuntimeError(
            "native engineering smoke generation fixture was not observed"
        )
    citations = one("native_citations")
    if not citations.get("citation_chunk_count") or not citations.get(
        "citation_evidence_unit_count"
    ):
        raise RuntimeError("native engineering smoke citation evidence is empty")
    worker = one("worker_returned")
    if not all(
        isinstance(worker.get(key), (int, float)) and math.isfinite(float(worker[key]))
        for key in ("process_cpu_ms", "process_rss_kib", "process_peak_rss_kib")
    ):
        raise RuntimeError("native engineering smoke process measurements are missing")


class Driver:
    def __init__(self, adapter, host_safe, emit, *, duration=2400, watchdog=0.25):
        self.adapter = adapter
        self.host_safe = host_safe
        self.emit = emit
        self.duration = duration
        self.watchdog = watchdog
        self.stop = Event()
        self.lock = Lock()
        self.sends = set()
        self.submission_budget = 36

    def _send_one(self, case):
        with self.lock:
            if self.stop.is_set() or not self.host_safe():
                self.stop.set()
                raise RuntimeError("submission safety gate closed")
            if case.ordinal in self.sends or len(self.sends) >= self.submission_budget:
                raise RuntimeError("submission budget exceeded")
            self.sends.add(case.ordinal)
            self.emit({"event": "send_attempt", **asdict(case)})
        record = self.adapter.submit(case, timeout=195)
        # Persist the actual terminal observation before any acceptance check
        # can raise and hide a server-side failure from the durable ledger.
        self.emit({"event": "settled", **record})
        validate_outcome(record, case)
        return record

    def _start_monitor(self, deadline):
        def monitor():
            while not self.stop.wait(self.watchdog):
                try:
                    safe = monotonic() < deadline and self.host_safe()
                except (OSError, ValueError):  # fmt: skip
                    safe = False
                if not safe:
                    with self.lock:
                        self.stop.set()
                    self.adapter.abort()
                    return

        monitor_thread = Thread(target=monitor, daemon=True)
        monitor_thread.start()
        return monitor_thread

    def run_engineering_smoke(self):
        """Run one isolated Recipes request as non-scientific harness QA."""
        deadline = monotonic() + self.duration
        monitor_thread = self._start_monitor(deadline)
        case = Submission(1, "consecutive", "Recipes", 1, "load")
        try:
            self.adapter.open(case.strategy)
            record = self._send_one(case)
            validate_engineering_smoke(record)
            self.emit({"event": "engineering_smoke_complete", "attempts": 1})
            return record
        except BaseException:
            self.stop.set()
            self.adapter.abort()
            raise
        finally:
            self.stop.set()
            monitor_thread.join(timeout=2)
            self.adapter.close()

    def run(self, campaign="full"):
        cases = tuple(case for wave in schedule(campaign) for case in wave)
        self.submission_budget = len(cases)
        if not self.submission_budget:
            raise RuntimeError("Stage 2 campaign has no submissions")
        deadline = monotonic() + self.duration
        monitor_thread = self._start_monitor(deadline)

        def send(case, barrier):
            barrier.wait(timeout=5)
            if monotonic() >= deadline:
                self.stop.set()
                raise RuntimeError("submission safety gate closed")
            self._send_one(case)

        active = None
        try:
            for wave in schedule(campaign):
                if self.stop.is_set():
                    raise RuntimeError("campaign aborted")
                strategy = wave[0].strategy
                if strategy != active:
                    if active:
                        self.adapter.close()
                    self.adapter.open(strategy)
                    active = strategy
                barrier = Barrier(len(wave))
                with ThreadPoolExecutor(max_workers=len(wave)) as pool:
                    futures = [pool.submit(send, case, barrier) for case in wave]
                    for future in futures:
                        future.result()
            if self.stop.is_set() or len(self.sends) != self.submission_budget:
                raise RuntimeError("campaign incomplete")
        except BaseException:
            self.stop.set()
            self.adapter.abort()
            raise
        finally:
            self.stop.set()
            monitor_thread.join(timeout=2)
            self.adapter.close()
        self.emit(
            {
                "event": "complete",
                "campaign": campaign,
                "attempts": len(self.sends),
            }
        )
