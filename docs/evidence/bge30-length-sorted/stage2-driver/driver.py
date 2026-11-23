"""Bounded Stage 2 scheduler. Transport and diagnostic hooks are injected."""

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


def schedule():
    ordinal = 0
    for strategy in STRATEGIES:
        for workload in WORKLOADS:
            for size in (1, 2, 4):
                wave = []
                for _ in range(size):
                    ordinal += 1
                    wave.append(Submission(ordinal, strategy, workload, size, "load"))
                yield tuple(wave)
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

    def run(self):
        deadline = monotonic() + self.duration

        # Adapter abort must be idempotent and target only the isolated session.
        def monitor():
            while not self.stop.wait(self.watchdog):
                try:
                    safe = monotonic() < deadline and self.host_safe()
                except (OSError, ValueError):
                    safe = False
                if not safe:
                    with self.lock:
                        self.stop.set()
                    self.adapter.abort()
                    return

        monitor_thread = Thread(target=monitor, daemon=True)
        monitor_thread.start()

        def send(case, barrier):
            barrier.wait(timeout=5)
            with self.lock:
                if (
                    self.stop.is_set()
                    or monotonic() >= deadline
                    or not self.host_safe()
                ):
                    self.stop.set()
                    raise RuntimeError("submission safety gate closed")
                if case.ordinal in self.sends or len(self.sends) >= 36:
                    raise RuntimeError("submission budget exceeded")
                self.sends.add(case.ordinal)
                self.emit({"event": "send_attempt", **asdict(case)})
            # Every adapter call makes at most one send and never retries.
            record = self.adapter.submit(case, timeout=195)
            validate_outcome(record, case)
            self.emit({"event": "settled", **record})

        active = None
        try:
            for wave in schedule():
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
            if self.stop.is_set() or len(self.sends) != 36:
                raise RuntimeError("campaign incomplete")
        except BaseException:
            self.stop.set()
            self.adapter.abort()
            raise
        finally:
            self.stop.set()
            monitor_thread.join(timeout=2)
            self.adapter.close()
        self.emit({"event": "complete", "attempts": len(self.sends)})
