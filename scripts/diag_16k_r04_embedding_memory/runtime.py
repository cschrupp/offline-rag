"""Lazy diagnostic-only runtime instrumentation for authorized R04 cells.

Importing this module does not import PyTorch/Transformers or initialize CUDA.
All runtime access is deferred until a separately authorized cell is launched.
"""

from __future__ import annotations

import fcntl
import functools
import hashlib
import inspect
import json
import math
import os
import re
import resource
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__:
    from .contract import (
        ACCEPTED_DESIGN_SUBJECT,
        MAX_CAMPAIGN_SECONDS,
        MAX_CELL_SECONDS,
        enforce_cell_budget,
    )
else:
    from contract import (
        ACCEPTED_DESIGN_SUBJECT,
        MAX_CAMPAIGN_SECONDS,
        MAX_CELL_SECONDS,
        enforce_cell_budget,
    )

_OOM_ALLOCATION_RE = re.compile(
    r"(?:Tried to allocate|request(?:ed)? allocation of)\s+([0-9.]+)\s*(B|KB|MB|GB|KiB|MiB|GiB)",
    re.IGNORECASE,
)
_SIZE_BYTES = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
}
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CellClaim:
    """Single-use claim plus the strictest remaining process deadline."""

    path: Path
    deadline_seconds: float
    claimed_monotonic: float


def effective_cell_deadline_seconds(
    *, remaining_campaign_wall_seconds: float, remaining_cumulative_seconds: float
) -> float:
    """Return the strictest cell, campaign-wall, and cumulative deadline."""
    return min(
        MAX_CELL_SECONDS,
        remaining_campaign_wall_seconds,
        remaining_cumulative_seconds,
    )


def verify_execution_authority(
    authority_path: Path,
    *,
    current_commit: str,
    cell_id: str,
    replicate: int,
    cell_spec_sha256: str,
) -> dict[str, Any]:
    """Require a separate future execution record before importing any runtime."""
    try:
        payload = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PermissionError("execution authority is unreadable") from exc
    if payload.get("execution_authorized") is not True:
        raise PermissionError("scientific execution is not authorized")
    if payload.get("authority") != (
        "S16-K-R04-EMBEDDING-MEMORY-SCIENTIFIC-EXECUTION-AUTH-001"
    ):
        raise PermissionError("unexpected scientific execution authority")
    if payload.get("allow_model_execution") is not True:
        raise PermissionError("model execution is not explicitly authorized")
    if payload.get("accepted_design_subject") != ACCEPTED_DESIGN_SUBJECT:
        raise PermissionError("execution authority names a different design")
    if payload.get("implementation_subject") != current_commit:
        raise PermissionError("execution authority does not bind this implementation")
    cells = payload.get("allowed_cells")
    if not isinstance(cells, list) or cell_id not in cells:
        raise PermissionError("requested cell is not in the execution authority")
    spec_hashes = payload.get("cell_spec_sha256")
    cell_hashes = spec_hashes.get(cell_id) if isinstance(spec_hashes, dict) else None
    expected_hash = (
        cell_hashes.get(str(replicate)) if isinstance(cell_hashes, dict) else None
    )
    if not isinstance(expected_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_hash
    ):
        raise PermissionError("authority lacks the exact cell/replicate spec hash")
    if cell_spec_sha256 != expected_hash:
        raise PermissionError("cell spec hash does not match exact replicate authority")
    if payload.get("human_authorization") != "ACCEPTED":
        raise PermissionError("Human execution authorization is absent")
    return payload


def require_local_untracked_path(path: Path, *, repo_root: Path) -> Path:
    """Require repository-local runtime artifacts to be ignored by Git."""
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return resolved
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", str(resolved)],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("runtime artifact path must be outside Git tracking")
    return resolved


def claim_single_cell_process(
    *,
    authority_path: Path,
    campaign_id: str,
    cell_id: str,
    replicate: int,
    spec_sha256: str,
    spec_path: Path,
    workload_path: Path,
    authority: dict[str, Any],
    workload: dict[str, Any],
    cell_spec: dict[str, Any],
    implementation_subject: str,
) -> CellClaim:
    """Create a durable exclusive claim so one cell spec cannot be retried."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", campaign_id):
        raise PermissionError("invalid campaign ID")
    if cell_id not in {
        "M0",
        "M1",
        "M2",
        "M3_PROFILE",
        "M3_A",
        "M3_B",
        "M4",
        "M5",
        "CPU_ONNX_REFERENCE",
    }:
        raise PermissionError("invalid cell ID")
    if replicate < 1 or replicate > 3:
        raise PermissionError("replicate is outside the frozen 1..3 range")
    if cell_id == "M3_PROFILE" and replicate != 1:
        raise PermissionError("M3 profiler characterization is one process only")
    if cell_id == "CPU_ONNX_REFERENCE" and replicate != 1:
        raise PermissionError("only one CPU ONNX reference process is allowed")
    claims = authority_path.resolve().parent / "claims" / campaign_id
    require_local_untracked_path(claims, repo_root=REPO_ROOT)
    claims.mkdir(parents=True, exist_ok=True)
    claim = claims / f"{cell_id}-replicate-{replicate}.json"
    payload = {
        "campaign_id": campaign_id,
        "cell_id": cell_id,
        "replicate": replicate,
        "cell_spec_sha256": spec_sha256,
        "cell_spec_path": str(spec_path.resolve()),
        "workload_path": str(workload_path.resolve()),
        "authority_path": str(authority_path.resolve()),
        "implementation_subject": implementation_subject,
        "workload_sha256": workload.get("workload_sha256"),
        "claimed_at_utc": _utc_now(),
        "claimed_monotonic_seconds": time.monotonic(),
        "status": "CLAIMED",
    }
    lock_path = claims / ".campaign.lock"
    with lock_path.open("a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        existing: list[dict[str, Any]] = []
        claim_times: list[datetime] = []
        for prior_path in claims.glob("*.json"):
            try:
                prior = json.loads(prior_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PermissionError("campaign claim ledger is corrupt") from exc
            if prior.get("status") == "CLAIMED":
                raise PermissionError("another campaign process is unfinished")
            existing.append(
                {
                    "cell_id": prior.get("cell_id"),
                    "replicate": prior.get("replicate"),
                    "duration_seconds": prior.get("duration_seconds", 0),
                }
            )
            try:
                claim_times.append(datetime.fromisoformat(str(prior["claimed_at_utc"])))
            except (KeyError, ValueError) as exc:
                raise PermissionError("campaign claim timestamp is invalid") from exc
        now = datetime.now(tz=UTC)
        claimed_monotonic = time.monotonic()
        prior_monotonic: list[float] = []
        for prior_path in claims.glob("*.json"):
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
            value = prior.get("claimed_monotonic_seconds")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise PermissionError("campaign monotonic timestamp is invalid")
            prior_monotonic.append(float(value))
        if prior_monotonic and claimed_monotonic < min(prior_monotonic):
            raise PermissionError("campaign monotonic clock moved backwards")
        if prior_monotonic and (
            claimed_monotonic - min(prior_monotonic) >= MAX_CAMPAIGN_SECONDS
        ):
            raise PermissionError("four-hour campaign wall-time ceiling exceeded")
        if __package__:
            from .campaign import authorize_cell_start
        else:
            from campaign import authorize_cell_start
        authorize_cell_start(
            claims_dir=claims,
            requested_replicate=replicate,
            requested_spec=cell_spec,
            authority=authority,
            workload=workload,
            implementation_subject=implementation_subject,
        )
        payload["claimed_at_utc"] = now.isoformat().replace("+00:00", "Z")
        payload["claimed_monotonic_seconds"] = claimed_monotonic
        enforce_cell_budget(existing + [{**payload, "duration_seconds": 0}])
        elapsed_wall = (
            claimed_monotonic - min(prior_monotonic) if prior_monotonic else 0.0
        )
        cumulative_duration = sum(float(item["duration_seconds"]) for item in existing)
        deadline_seconds = effective_cell_deadline_seconds(
            remaining_campaign_wall_seconds=MAX_CAMPAIGN_SECONDS - elapsed_wall,
            remaining_cumulative_seconds=MAX_CAMPAIGN_SECONDS - cumulative_duration,
        )
        if deadline_seconds <= 0:
            raise PermissionError("four-hour campaign deadline is exhausted")
        payload["deadline_seconds"] = deadline_seconds
        try:
            descriptor = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise PermissionError(
                "this cell process was already claimed; retries are forbidden"
            ) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    return CellClaim(claim, deadline_seconds, claimed_monotonic)


def complete_cell_process_claim(
    claim: CellClaim,
    *,
    duration_seconds: float,
    result_status: str,
    evidence_path: Path,
) -> None:
    """Finalize a cell claim after its evidence record has been written."""
    claim_path = claim.path
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    if payload.get("status") != "CLAIMED":
        raise RuntimeError("cell claim is not in CLAIMED state")
    payload["status"] = "COMPLETED"
    payload["duration_seconds"] = float(duration_seconds)
    payload["result_status"] = result_status
    payload["completed_at_utc"] = _utc_now()
    evidence_bytes = evidence_path.read_bytes()
    evidence = json.loads(evidence_bytes)
    if (
        evidence.get("cell_spec_sha256") != payload.get("cell_spec_sha256")
        or evidence.get("workload_sha256") != payload.get("workload_sha256")
        or evidence.get("implementation_subject")
        != payload.get("implementation_subject")
        or evidence.get("cell_id") != payload.get("cell_id")
        or evidence.get("replicate") != payload.get("replicate")
    ):
        raise RuntimeError("cell evidence does not match its process claim")
    payload["evidence_path"] = str(evidence_path.resolve())
    payload["evidence_sha256"] = hashlib.sha256(evidence_bytes).hexdigest()
    if __package__:
        from .evidence import reduce_authorized_cell_evidence
    else:
        from evidence import reduce_authorized_cell_evidence
    authority = json.loads(Path(payload["authority_path"]).read_text(encoding="utf-8"))
    workload = json.loads(Path(payload["workload_path"]).read_text(encoding="utf-8"))
    reduced = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=Path(payload["cell_spec_path"]),
        authority=authority,
        workload=workload,
    )
    allowed_result_statuses = {reduced["status"]}
    if reduced["status"] == "NON_OOM_FAILURE":
        allowed_result_statuses.add("FAILED")
    if result_status not in allowed_result_statuses:
        raise RuntimeError("process result status does not match reduced raw evidence")
    payload["result_status"] = reduced["status"]
    payload["evidence_validity"] = reduced["valid"]
    payload["gate_facts"] = reduced["gate_facts"]
    temporary = claim_path.with_suffix(".tmp")
    ledger = claim_path.parent
    overrun = False
    with (ledger / ".campaign.lock").open("a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        prior_durations = 0.0
        claim_monotonic_values: list[float] = []
        this_claimed_monotonic: float | None = None
        for path in ledger.glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            monotonic_value = item.get("claimed_monotonic_seconds")
            if not isinstance(monotonic_value, (int, float)) or not math.isfinite(
                monotonic_value
            ):
                raise RuntimeError("campaign monotonic timestamp is invalid")
            claim_monotonic_values.append(float(monotonic_value))
            if path == claim_path:
                this_claimed_monotonic = float(monotonic_value)
            if path != claim_path and item.get("status") == "COMPLETED":
                prior_durations += float(item.get("duration_seconds", 0.0))
        now_monotonic = time.monotonic()
        if claim_monotonic_values and now_monotonic < min(claim_monotonic_values):
            raise RuntimeError("campaign monotonic clock moved backwards")
        wall_elapsed = (
            now_monotonic - min(claim_monotonic_values)
            if claim_monotonic_values
            else 0.0
        )
        elapsed_this_cell = (
            now_monotonic - this_claimed_monotonic
            if this_claimed_monotonic is not None
            else float("inf")
        )
        payload["duration_seconds"] = elapsed_this_cell
        overrun = (
            wall_elapsed >= MAX_CAMPAIGN_SECONDS
            or prior_durations + elapsed_this_cell >= MAX_CAMPAIGN_SECONDS
            or elapsed_this_cell >= claim.deadline_seconds
            or duration_seconds >= claim.deadline_seconds
        )
        if overrun:
            payload["result_status"] = "CAMPAIGN_LIMIT_EXCEEDED"
            payload["evidence_validity"] = False
        temporary.write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, claim_path)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    if overrun:
        raise RuntimeError("campaign wall, cumulative, or cell deadline exceeded")


def parse_requested_allocation_bytes(exception_text: str) -> int | None:
    match = _OOM_ALLOCATION_RE.search(exception_text)
    if not match:
        return None
    magnitude = float(match.group(1))
    return int(magnitude * _SIZE_BYTES[match.group(2).lower()])


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _query_nvidia_smi() -> dict[str, Any]:
    """Return an owner-redacted GPU sample; command failures are data, not fatal."""
    query = [
        "nvidia-smi",
        "--query-gpu=index,memory.total,memory.used,memory.free,utilization.gpu,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        output = subprocess.check_output(query, text=True, timeout=2).strip()
        gpus = []
        for line in output.splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 6:
                continue
            gpus.append(
                {
                    "index": int(fields[0]),
                    "total_mib": int(fields[1]),
                    "used_mib": int(fields[2]),
                    "free_mib": int(fields[3]),
                    "utilization_pct": int(fields[4]),
                    "driver_version": fields[5],
                }
            )
        processes: list[dict[str, Any]] = []
        process_status = "observed"
        process_owners_observable = True
        try:
            process_output = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,used_memory",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=2,
            ).strip()
            for line in process_output.splitlines():
                fields = [field.strip() for field in line.split(",")]
                if len(fields) != 2:
                    continue
                try:
                    pid = int(fields[0])
                    used_mib = int(fields[1])
                except ValueError:
                    continue
                owner = "NOT_OBSERVABLE"
                try:
                    command = (
                        Path(f"/proc/{pid}/cmdline")
                        .read_bytes()
                        .decode("utf-8", errors="replace")
                    )
                    if "offline_rag" in command or "diag_16k_r04" in command:
                        owner = "SENECA_DIAGNOSTIC"
                    else:
                        owner = "OTHER_VISIBLE_PROCESS"
                except OSError:
                    process_owners_observable = False
                processes.append({"used_mib": used_mib, "owner_class": owner})
        except Exception:  # noqa: BLE001
            process_status = "NOT_OBSERVABLE"
            process_owners_observable = False
        return {
            "status": "observed",
            "timestamp_utc": _utc_now(),
            "monotonic_seconds": time.monotonic(),
            "gpus": gpus,
            "processes": processes,
            "processes_status": process_status,
            "process_owners_observable": process_owners_observable,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "timestamp_utc": _utc_now(),
            "monotonic_seconds": time.monotonic(),
            "error_type": type(exc).__name__,
        }


class DeviceSampler:
    """Bounded 10 Hz best-effort device/process sampler for one cell."""

    def __init__(self, interval_seconds: float = 0.1) -> None:
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_loop(self) -> None:
        next_sample = time.monotonic()
        while not self._stop.is_set():
            self.samples.append(_query_nvidia_smi())
            next_sample += self.interval_seconds
            delay = max(0.0, next_sample - time.monotonic())
            if delay == 0.0:
                next_sample = time.monotonic()
            self._stop.wait(delay)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("device sampler already started")
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        return list(self.samples)


def cuda_stage_snapshot(
    torch: Any, *, stage: str, synchronize: bool = True
) -> dict[str, Any]:
    """Capture PyTorch allocator and device facts at one named stage."""
    timestamp = _utc_now()
    try:
        if synchronize:
            torch.cuda.synchronize()
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        device_used = None
        device_memory_used = getattr(torch.cuda, "device_memory_used", None)
        if callable(device_memory_used):
            try:
                device_used = int(device_memory_used())
            except Exception:  # noqa: BLE001
                device_used = None
        return {
            "stage": stage,
            "timestamp_utc": timestamp,
            "monotonic_seconds": time.monotonic(),
            "status": "observed",
            "allocated_bytes": int(torch.cuda.memory_allocated()),
            "reserved_bytes": int(torch.cuda.memory_reserved()),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
            "device_free_bytes": int(free_bytes),
            "device_total_bytes": int(total_bytes),
            "device_used_bytes": device_used,
            "process": _process_usage_snapshot(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "stage": stage,
            "timestamp_utc": timestamp,
            "monotonic_seconds": time.monotonic(),
            "status": "unavailable",
            "error_type": type(exc).__name__,
            "process": _process_usage_snapshot(),
        }


def _process_usage_snapshot() -> dict[str, Any]:
    """Capture process RSS/CPU without importing a heavyweight monitor."""
    result: dict[str, Any] = {
        "peak_rss_bytes": None,
        "current_rss_bytes": None,
        "user_cpu_seconds": None,
        "system_cpu_seconds": None,
    }
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result["peak_rss_bytes"] = int(usage.ru_maxrss) * 1024
        result["user_cpu_seconds"] = float(usage.ru_utime)
        result["system_cpu_seconds"] = float(usage.ru_stime)
    except Exception as exc:  # noqa: BLE001
        result["rusage_error_type"] = type(exc).__name__
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                result["current_rss_bytes"] = int(line.split()[1]) * 1024
                break
    except OSError, ValueError, IndexError:
        pass
    return result


def reset_stage_peaks(torch: Any) -> None:
    torch.cuda.reset_peak_memory_stats()


@contextmanager
def allocator_history(torch: Any, *, snapshot_path: Path) -> Iterator[dict[str, Any]]:
    """Record bounded allocator history and dump immediately on cell OOM."""
    memory = getattr(torch.cuda, "memory", None)
    record = getattr(memory, "_record_memory_history", None)
    dump = getattr(memory, "_dump_snapshot", None)
    enabled = False
    state: dict[str, Any] = {
        "history_enabled": False,
        "snapshot_written": False,
        "oom_event_observed": None,
        "snapshot_path": str(snapshot_path),
    }
    try:
        if callable(record):
            try:
                record(max_entries=20_000, stack="python")
                enabled = True
                state["history_enabled"] = True
            except TypeError:
                record(
                    enabled="all", context="all", stacks="python", max_entries=20_000
                )
                enabled = True
                state["history_enabled"] = True
        yield state
    except BaseException as exc:
        if _is_cuda_oom(exc) and enabled and callable(dump):
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                dump(str(snapshot_path))
                state["snapshot_written"] = snapshot_path.is_file()
                state["oom_event_observed"] = (
                    _snapshot_contains_oom(snapshot_path)
                    if snapshot_path.is_file()
                    else None
                )
                state.update(_snapshot_allocator_summary(snapshot_path))
                state["snapshot_oom_requested_bytes"] = (
                    _snapshot_oom_requested_bytes(snapshot_path)
                    if snapshot_path.is_file()
                    else None
                )
                try:
                    stats = torch.cuda.memory_stats()
                    state["inactive_split_bytes"] = int(
                        stats.get("inactive_split_bytes.all.current", 0)
                    )
                except Exception:  # noqa: BLE001
                    state["inactive_split_bytes"] = None
            except Exception as dump_exc:  # noqa: BLE001
                state["snapshot_error_type"] = type(dump_exc).__name__
        raise
    finally:
        if enabled and callable(record):
            try:
                record(enabled=None)
            except Exception:  # noqa: BLE001
                try:
                    record(enabled="none")
                except Exception:  # noqa: BLE001
                    state["history_disable_failed"] = True


def _snapshot_contains_oom(path: Path) -> bool | None:
    try:
        # PyTorch snapshots are pickle; the diagnostic process wrote this file.
        import pickle

        with path.open("rb") as handle:
            snapshot = pickle.load(handle)
        traces = snapshot.get("device_traces", []) if isinstance(snapshot, dict) else []
        for trace in traces:
            if not isinstance(trace, list):
                continue
            for event in trace:
                if _contains_oom_marker(event):
                    return True
        return False
    except Exception:  # noqa: BLE001
        return None


def _snapshot_oom_requested_bytes(path: Path) -> int | None:
    """Read the requested size from an allocator OOM trace event, if present."""
    try:
        import pickle

        with path.open("rb") as handle:
            snapshot = pickle.load(handle)
        traces = snapshot.get("device_traces", []) if isinstance(snapshot, dict) else []
        sizes: set[int] = set()
        for trace in traces:
            if not isinstance(trace, list):
                continue
            for event in trace:
                if (
                    isinstance(event, dict)
                    and str(event.get("action", "")).lower() == "oom"
                ):
                    size = event.get("size", event.get("requested_bytes"))
                    if isinstance(size, int) and size >= 0:
                        sizes.add(size)
        return next(iter(sizes)) if len(sizes) == 1 else None
    except Exception:  # noqa: BLE001
        return None


def _contains_oom_marker(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() == "oom"
    if isinstance(value, dict):
        return any(_contains_oom_marker(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_oom_marker(item) for item in value)
    return False


def _snapshot_allocator_summary(path: Path) -> dict[str, Any]:
    try:
        import pickle

        with path.open("rb") as handle:
            snapshot = pickle.load(handle)
        segments = snapshot.get("segments", []) if isinstance(snapshot, dict) else []
        reusable: list[int] = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            for block in segment.get("blocks", []):
                if isinstance(block, dict) and block.get("state") in {
                    "inactive",
                    "inactive_split",
                }:
                    size = block.get("size")
                    if isinstance(size, int) and size >= 0:
                        reusable.append(size)
        return {
            "snapshot_reusable_bytes": sum(reusable),
            "snapshot_largest_reusable_block_bytes": max(reusable, default=0),
            "snapshot_segment_count": len(segments),
        }
    except Exception:  # noqa: BLE001
        return {
            "snapshot_reusable_bytes": None,
            "snapshot_largest_reusable_block_bytes": None,
            "snapshot_segment_count": None,
        }


def _is_cuda_oom(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "outofmemory" in type(exc).__name__.lower() or (
        "out of memory" in text and ("cuda" in text or "cublas" in text)
    )


def is_cuda_oom(exc: BaseException) -> bool:
    """Public narrow predicate for allocator-snapshot handling."""
    return _is_cuda_oom(exc)


def failure_classification(exc: BaseException | None) -> str:
    """Return a bounded failure class before exception details are redacted."""
    if exc is None:
        return "NONE"
    if is_cuda_oom(exc):
        return "CUDA_OOM"
    if isinstance(exc, TimeoutError):
        return "DEADLINE"
    return "NON_OOM_FAILURE"


class CacheActivationObserver:
    """Observe cache boundary facts while delegating every call unchanged."""

    def __init__(self) -> None:
        self.forward_use_cache_values: list[bool | None] = []
        self.dynamic_cache_construction_attempts = 0
        self.cache_update_attempts = 0
        self.non_null_cache_returns = 0
        self.forward_runtime_states: list[dict[str, Any]] = []
        self._patches: list[tuple[Any, str, Any]] = []

    def _replace(self, owner: Any, name: str, wrapper: Any) -> None:
        original = getattr(owner, name)
        self._patches.append((owner, name, original))
        setattr(owner, name, wrapper(original))

    def install(self) -> None:
        from transformers.cache_utils import DynamicCache
        from transformers.models.qwen3 import modeling_qwen3

        observer = self
        qwen_model = modeling_qwen3.Qwen3Model
        forward_signature = inspect.signature(qwen_model.forward)

        def wrap_forward(original: Any):
            @functools.wraps(original)
            def observed(model: Any, *args: Any, **kwargs: Any) -> Any:
                try:
                    bound = forward_signature.bind_partial(model, *args, **kwargs)
                    value = bound.arguments.get("use_cache")
                except TypeError:
                    value = kwargs.get("use_cache")
                if value is None:
                    value = getattr(getattr(model, "config", None), "use_cache", None)
                observer.forward_use_cache_values.append(
                    bool(value) if isinstance(value, bool) else None
                )
                try:
                    import torch

                    observer.forward_runtime_states.append(
                        {
                            "training": bool(getattr(model, "training", False)),
                            "grad_enabled": bool(torch.is_grad_enabled()),
                            "inference_mode": bool(torch.is_inference_mode_enabled()),
                        }
                    )
                except Exception:  # noqa: BLE001
                    observer.forward_runtime_states.append(
                        {"training": bool(getattr(model, "training", False))}
                    )
                result = original(model, *args, **kwargs)
                cache = getattr(result, "past_key_values", None)
                if cache is not None:
                    observer.non_null_cache_returns += 1
                return result

            return observed

        def wrap_init(original: Any):
            @functools.wraps(original)
            def observed(cache: Any, *args: Any, **kwargs: Any) -> Any:
                observer.dynamic_cache_construction_attempts += 1
                return original(cache, *args, **kwargs)

            return observed

        def wrap_update(original: Any):
            @functools.wraps(original)
            def observed(cache: Any, *args: Any, **kwargs: Any) -> Any:
                observer.cache_update_attempts += 1
                return original(cache, *args, **kwargs)

            return observed

        self._replace(qwen_model, "forward", wrap_forward)
        self._replace(DynamicCache, "__init__", wrap_init)
        self._replace(DynamicCache, "update", wrap_update)

    def restore(self) -> None:
        while self._patches:
            owner, name, original = self._patches.pop()
            setattr(owner, name, original)

    def summary(self) -> dict[str, Any]:
        return {
            "forward_use_cache_values": list(self.forward_use_cache_values),
            "dynamic_cache_construction_attempts": self.dynamic_cache_construction_attempts,
            "cache_update_attempts": self.cache_update_attempts,
            "non_null_cache_returns": self.non_null_cache_returns,
            "forward_runtime_states": list(self.forward_runtime_states),
            "activation_witness": bool(
                any(self.forward_use_cache_values)
                or self.dynamic_cache_construction_attempts
                or self.cache_update_attempts
                or self.non_null_cache_returns
            ),
        }


class SDPABackendObserver:
    """Observe actual SDPA shapes and backend eligibility without changing calls."""

    def __init__(self, torch: Any) -> None:
        self.torch = torch
        self.calls: list[dict[str, Any]] = []
        self._owner: Any | None = None
        self._name: str | None = None
        self._original: Any | None = None

    def install(self) -> None:
        functional = self.torch.nn.functional
        original = functional.scaled_dot_product_attention
        self._owner = functional
        self._name = "scaled_dot_product_attention"
        self._original = original
        observer = self

        @functools.wraps(original)
        def observed(*args: Any, **kwargs: Any) -> Any:
            names = (
                "query",
                "key",
                "value",
                "attn_mask",
                "dropout_p",
                "is_causal",
                "scale",
                "enable_gqa",
            )
            arguments = {
                name: kwargs[name] if name in kwargs else args[index]
                for index, name in enumerate(names[: len(args)])
            }
            for name in names[len(args) :]:
                if name in kwargs:
                    arguments[name] = kwargs[name]
            query = arguments.get("query")
            key = arguments.get("key")
            value = arguments.get("value")
            if query is None or key is None or value is None:
                return original(*args, **kwargs)
            attn_mask = arguments.get("attn_mask")
            dropout_p = arguments.get("dropout_p", 0.0)
            is_causal = arguments.get("is_causal", False)
            enable_gqa = arguments.get("enable_gqa", False)
            eligibility: dict[str, Any] = {}
            params_class = getattr(observer.torch.backends.cuda, "SDPAParams", None)
            try:
                if not callable(params_class):
                    raise TypeError("SDPAParams is unavailable")
                params = params_class(
                    query,
                    key,
                    value,
                    attn_mask,
                    dropout_p,
                    is_causal,
                    enable_gqa,
                )
                for backend, name in (
                    ("can_use_flash_attention", "FLASH_ATTENTION"),
                    ("can_use_efficient_attention", "EFFICIENT_ATTENTION"),
                    ("can_use_cudnn_attention", "CUDNN_ATTENTION"),
                ):
                    check = getattr(observer.torch.backends.cuda, backend, None)
                    if callable(check):
                        try:
                            eligibility[name] = bool(check(params, debug=False))
                        except Exception as exc:  # noqa: BLE001
                            eligibility[name] = {
                                "status": "UNAVAILABLE",
                                "error_type": type(exc).__name__,
                            }
                    else:
                        eligibility[name] = {"status": "UNAVAILABLE"}
            except Exception as exc:  # noqa: BLE001
                eligibility["status"] = "UNAVAILABLE"
                eligibility["error_type"] = type(exc).__name__
            observer.calls.append(
                {
                    "query_shape": list(query.shape),
                    "key_shape": list(key.shape),
                    "value_shape": list(value.shape),
                    "dtype": str(query.dtype),
                    "device_type": str(query.device.type),
                    "dropout_p": float(dropout_p),
                    "is_causal": bool(is_causal),
                    "enable_gqa": bool(enable_gqa),
                    "eligible_backends": eligibility,
                }
            )
            return original(*args, **kwargs)

        functional.scaled_dot_product_attention = observed

    def restore(self) -> None:
        if self._owner is not None and self._name and self._original is not None:
            setattr(self._owner, self._name, self._original)
            self._owner = None
            self._name = None
            self._original = None

    def summary(self) -> dict[str, Any]:
        return {
            "sdpa_call_count": len(self.calls),
            "calls": list(self.calls),
        }


def model_runtime_facts(model: Any) -> dict[str, Any]:
    """Extract config, dtype, module, inference, and attention facts only."""
    dtype_counts: dict[str, int] = {}
    classes: list[str] = []
    configs: list[dict[str, Any]] = []
    for module in model.modules():
        class_name = type(module).__name__
        if class_name not in classes:
            classes.append(class_name)
        config = getattr(module, "config", None)
        if config is not None:
            configs.append(
                {
                    "class": class_name,
                    "use_cache": getattr(config, "use_cache", None),
                    "attn_implementation": getattr(
                        config, "_attn_implementation", None
                    ),
                    "output_hidden_states": getattr(
                        config, "output_hidden_states", None
                    ),
                    "output_attentions": getattr(config, "output_attentions", None),
                }
            )
        parameters = getattr(module, "parameters", None)
        if callable(parameters):
            for parameter in parameters(recurse=False):
                dtype = str(getattr(parameter, "dtype", "unknown"))
                dtype_counts[dtype] = dtype_counts.get(dtype, 0) + 1
    try:
        import torch

        grad_enabled = bool(torch.is_grad_enabled())
        inference_mode = bool(torch.is_inference_mode_enabled())
    except Exception:  # noqa: BLE001
        grad_enabled = None
        inference_mode = None
    return {
        "module_classes": classes,
        "config_states": configs,
        "parameter_dtype_counts": dtype_counts,
        "model_training": bool(getattr(model, "training", False)),
        "grad_enabled": grad_enabled,
        "inference_mode": inference_mode,
        "max_seq_length": getattr(model, "max_seq_length", None),
    }


def safe_cell_evidence(
    payload: dict[str, Any], *, private_texts: list[str] | None = None
) -> dict[str, Any]:
    """Whitelist safe evidence fields; reject unknown fields rather than leak."""
    allowed = {
        "schema",
        "authority",
        "design_subject",
        "implementation_subject",
        "cell_id",
        "replicate",
        "cell_spec_sha256",
        "effective_controls",
        "workload_sha256",
        "model_revision",
        "runtime_versions",
        "device_facts",
        "stage_snapshots",
        "device_samples",
        "token_metrics",
        "cache_observation",
        "sdpa_observation",
        "model_facts",
        "encode_result",
        "oom_diagnostics",
        "exception",
        "failure_classification",
        "profiler_operators",
        "duration_seconds",
        "status",
    }
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"unsafe evidence fields: {', '.join(sorted(unknown))}")
    serialized = json.dumps(payload, allow_nan=False)
    forbidden_keys = {
        "embedding_text",
        "input_ids",
        "token_ids",
        "private_text",
        "source_text",
        "texts",
    }

    def inspect_keys(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden_keys.intersection(value):
                raise ValueError("private text/token fields are forbidden in evidence")
            for nested in value.values():
                inspect_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect_keys(nested)

    inspect_keys(payload)
    if any(text and text in serialized for text in (private_texts or [])):
        raise ValueError("private text/token IDs are forbidden in evidence")
    return payload
