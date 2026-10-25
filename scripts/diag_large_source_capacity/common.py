"""Reusable, best-effort measurements for large-source qualification runs.

This module is intentionally script-owned.  It observes an existing Seneca
operation without changing product behavior or adding a runtime dependency.
Missing platform telemetry is represented as ``unavailable`` rather than zero.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_CONTRACT = "large-source-capacity-evidence-v1"


def _read_proc_value(prefix: str) -> int | None:
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(prefix):
                    fields = line.split()
                    return int(fields[1]) * 1024
    except OSError, ValueError, IndexError:
        return None
    return None


def current_rss_bytes() -> int | None:
    """Read current process RSS from Linux ``/proc``."""
    try:
        from offline_rag.evaluation.performance_14.resources import (
            observe_ram_rss_bytes,
        )

        status, value = observe_ram_rss_bytes()
        return value if status == "available" else None
    except Exception:  # noqa: BLE001
        return _read_proc_value("VmRSS:")


def lifetime_max_rss_bytes() -> int | None:
    """Return the process-lifetime ``ru_maxrss`` high-water mark."""
    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports KiB; callers run on Linux for the qualification harness.
        return value * 1024
    except OSError, ValueError:
        return None


def available_ram_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except OSError, ValueError, IndexError:
        return None
    return None


def rusage_snapshot() -> dict[str, Any]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "status": "observed",
            "user_s": float(usage.ru_utime),
            "system_s": float(usage.ru_stime),
            "voluntary_context_switches": int(usage.ru_nvcsw),
            "involuntary_context_switches": int(usage.ru_nivcsw),
            "ru_maxrss_bytes": lifetime_max_rss_bytes(),
        }
    except (OSError, ValueError) as exc:
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


def rusage_delta(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    if before.get("status") != "observed" or after.get("status") != "observed":
        return {"status": "unavailable", "error": "rusage_unavailable"}
    user = float(after["user_s"]) - float(before["user_s"])
    system = float(after["system_s"]) - float(before["system_s"])
    return {
        "status": "observed",
        "cpu_user_s": user,
        "cpu_system_s": system,
        "cpu_total_s": user + system,
        "voluntary_context_switches": int(after["voluntary_context_switches"])
        - int(before["voluntary_context_switches"]),
        "involuntary_context_switches": int(after["involuntary_context_switches"])
        - int(before["involuntary_context_switches"]),
    }


def cpu_metrics(
    before: Mapping[str, Any], after: Mapping[str, Any], wall_s: float
) -> dict[str, Any]:
    delta = rusage_delta(before, after)
    total = delta.get("cpu_total_s")
    delta["wall_s"] = float(wall_s)
    delta["cpu_equivalent_pct"] = (
        100.0 * float(total) / wall_s
        if delta.get("status") == "observed" and total is not None and wall_s > 0
        else None
    )
    delta["logical_cpu_count"] = os.cpu_count()
    delta["physical_cpu_count"] = _physical_cpu_count()
    return delta


def _physical_cpu_count() -> int | None:
    try:
        import psutil  # type: ignore[import-untyped]

        return int(psutil.cpu_count(logical=False) or 0) or None
    except Exception:  # noqa: BLE001
        return None


def _gpu_snapshot() -> dict[str, Any]:
    """Compose existing CUDA allocator and nvidia-smi observers."""
    try:
        from offline_rag.api.diag_gpu_probe import collect_allocator_snapshot

        allocator = collect_allocator_snapshot()
    except Exception as exc:  # noqa: BLE001
        allocator = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
    try:
        from offline_rag.dense.profiling import sample_external_gpu_state

        external = sample_external_gpu_state()
    except Exception as exc:  # noqa: BLE001
        external = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
    available = (
        bool(allocator.get("cuda_available")) or external.get("status") == "observed"
    )
    return {
        "status": "observed" if available else "unavailable",
        "allocator": allocator,
        "external": external,
    }


def reset_cuda_peak_memory_stats() -> dict[str, Any]:
    """Reset CUDA allocator peaks when available; never fail a CPU run."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"status": "unavailable", "error": "cuda_not_available"}
        from offline_rag.dense.profiling import reset_peak_vram_stats

        reset_peak_vram_stats()
        return {"status": "observed", "action": "reset_peak_memory_stats"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


@dataclass
class StageTracker:
    """Diagnostic stage labels derived from existing product boundaries."""

    started: float = field(default_factory=time.perf_counter)
    current: str = "idle"
    transitions: list[dict[str, Any]] = field(default_factory=list)
    stage_reports: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_stage(self, stage: str) -> None:
        with self._lock:
            now = time.perf_counter()
            if stage == self.current and self.transitions:
                return
            self.current = stage
            self.transitions.append({"offset_s": now - self.started, "stage": stage})

    def before_stage(self, stage: str) -> None:
        self.set_stage(stage)

    def after_stage(self, stage: str) -> None:
        if stage == "publish":
            self.set_stage("finalization")

    def document_phase(self, event: Any) -> None:
        phase = str(getattr(event, "phase", ""))
        if phase == "parsing":
            source_name = str(getattr(event, "source_name", ""))
            self.set_stage(
                "pdf_parsing" if source_name.lower().endswith(".pdf") else "parsing"
            )
        elif phase == "parsed" and self.current in {"pdf_parsing", "parsing"}:
            self.set_stage("ingest")

    def after_stage_report(self, stage: str, report: object) -> None:
        payload: dict[str, Any] = {"stage": stage}
        if hasattr(report, "model_dump"):
            try:
                payload["report"] = report.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                payload["report"] = {"status": "unevaluable"}
        else:
            payload["report_type"] = type(report).__name__
        with self._lock:
            self.stage_reports.append(payload)

    def stage_at(self) -> str:
        with self._lock:
            return self.current

    def duration_summary(self, end_offset_s: float) -> dict[str, float]:
        with self._lock:
            events = list(self.transitions)
            current = self.current
        if not events:
            return {}
        result: dict[str, float] = {}
        for index, event in enumerate(events):
            finish = (
                events[index + 1]["offset_s"]
                if index + 1 < len(events)
                else end_offset_s
            )
            name = str(event["stage"])
            result[name] = result.get(name, 0.0) + max(
                0.0, float(finish - event["offset_s"])
            )
        if current not in result:
            result[current] = 0.0
        return result


@dataclass
class DiskUsageTracker:
    """Per-root and aggregate directory growth observations."""

    roots: Mapping[str, Path]
    filesystem_root: Path
    baseline: dict[str, int] = field(init=False)
    peak: dict[str, int] = field(init=False)
    final: dict[str, int] = field(init=False)
    free_before: int | None = field(init=False)
    minimum_free: int | None = field(init=False)
    free_after: int | None = field(init=False)
    _aggregate_roots: dict[str, Path] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._aggregate_roots = _non_nested_roots(self.roots)
        self.baseline = self._measure()
        self.peak = dict(self.baseline)
        self.final = dict(self.baseline)
        self.free_before = _free_bytes(self.filesystem_root)
        self.minimum_free = self.free_before
        self.free_after = self.free_before

    def _measure(self) -> dict[str, int]:
        values = {name: directory_size(path) for name, path in self.roots.items()}
        values["__aggregate__"] = sum(
            directory_size(path) for path in self._aggregate_roots.values()
        )
        return values

    def sample(self) -> dict[str, Any]:
        observed = self._measure()
        self.final = observed
        for key, value in observed.items():
            self.peak[key] = max(self.peak.get(key, 0), value)
        free = _free_bytes(self.filesystem_root)
        if free is not None:
            self.minimum_free = (
                free if self.minimum_free is None else min(self.minimum_free, free)
            )
            self.free_after = free
        return {"roots": observed, "free_bytes": free}

    def summary(self) -> dict[str, Any]:
        self.sample()
        roots: dict[str, Any] = {}
        for name in self.roots:
            base = self.baseline.get(name, 0)
            peak = self.peak.get(name, base)
            final = self.final.get(name, base)
            roots[name] = {
                "baseline_bytes": base,
                "peak_observed_bytes": peak,
                "final_bytes": final,
                "peak_growth_bytes": peak - base,
                "final_growth_bytes": final - base,
            }
        base = self.baseline.get("__aggregate__", 0)
        peak = self.peak.get("__aggregate__", base)
        final = self.final.get("__aggregate__", base)
        return {
            "roots": roots,
            "aggregate": {
                "baseline_bytes": base,
                "peak_observed_bytes": peak,
                "final_bytes": final,
                "peak_growth_bytes": peak - base,
                "final_growth_bytes": final - base,
            },
            "free_bytes_before": self.free_before,
            "minimum_free_bytes_observed": self.minimum_free,
            "free_bytes_peak_consumption": (
                self.free_before - self.minimum_free
                if self.free_before is not None and self.minimum_free is not None
                else None
            ),
            "free_bytes_after": self.free_after,
        }


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _non_nested_roots(roots: Mapping[str, Path]) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for name, raw in sorted(
        roots.items(), key=lambda item: len(item[1].resolve().parts)
    ):
        path = raw.resolve()
        if any(_is_under(path, parent) for parent in selected.values()):
            continue
        selected[name] = path
    return selected


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _free_bytes(path: Path) -> int | None:
    try:
        candidate = path if path.exists() else path.parent
        if not candidate.exists():
            candidate = Path.cwd()
        return int(shutil.disk_usage(candidate).free)
    except OSError:
        return None


@dataclass
class ProcessSampler:
    """Background current-RSS sampler with optional GPU and disk cadence."""

    stage_provider: Callable[[], str]
    rss_interval_s: float = 0.2
    gpu_interval_s: float = 1.0
    disk_interval_s: float = 1.0
    disk_tracker: DiskUsageTracker | None = None
    max_samples: int = 20_000
    samples: list[dict[str, Any]] = field(default_factory=list)
    rss_start_bytes: int | None = None
    rss_current_bytes: int | None = None
    rss_peak_window_bytes: int | None = None
    _started: float | None = field(default=None, init=False, repr=False)
    _last_gpu: float = field(default=0.0, init=False, repr=False)
    _last_disk: float = field(default=0.0, init=False, repr=False)
    _stop: threading.Event = field(
        default_factory=threading.Event, init=False, repr=False
    )
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def start(self) -> None:
        self._started = time.perf_counter()
        self._stop.clear()
        self._sample(force=True)
        self._thread = threading.Thread(
            target=self._run, name="l4-rss-sampler", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.rss_interval_s * 4))
        self._sample(force=True)

    def _run(self) -> None:
        while not self._stop.wait(max(0.01, self.rss_interval_s)):
            self._sample()

    def _sample(self, *, force: bool = False) -> None:
        if self._started is None:
            return
        now = time.perf_counter()
        rss = current_rss_bytes()
        if rss is not None:
            self.rss_current_bytes = rss
            self.rss_peak_window_bytes = max(self.rss_peak_window_bytes or rss, rss)
            self.rss_start_bytes = self.rss_start_bytes or rss
        sample: dict[str, Any] = {
            "monotonic_offset_s": now - self._started,
            "observed_stage": self.stage_provider(),
            "rss_bytes": rss,
            "process_cpu_user_s": None,
            "process_cpu_system_s": None,
            "system_available_ram_bytes": available_ram_bytes(),
        }
        usage = rusage_snapshot()
        if usage.get("status") == "observed":
            sample["process_cpu_user_s"] = usage["user_s"]
            sample["process_cpu_system_s"] = usage["system_s"]
        if force or now - self._last_gpu >= self.gpu_interval_s:
            sample["gpu"] = _gpu_snapshot()
            self._last_gpu = now
        if self.disk_tracker is not None and (
            force or now - self._last_disk >= self.disk_interval_s
        ):
            sample["disk"] = self.disk_tracker.sample()
            self._last_disk = now
        with self._lock:
            if len(self.samples) < self.max_samples:
                self.samples.append(sample)
            elif force:
                self.samples[-1] = sample

    def summary(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self.samples)
        parser_samples = [
            sample
            for sample in samples
            if sample.get("observed_stage") == "pdf_parsing"
        ]
        parser_rss = [
            sample["rss_bytes"]
            for sample in parser_samples
            if sample.get("rss_bytes") is not None
        ]
        parser_offsets = [sample["monotonic_offset_s"] for sample in parser_samples]
        parser_start = parser_rss[0] if parser_rss else None
        parser_peak = max(parser_rss) if parser_rss else None
        return {
            "rss_start_bytes": self.rss_start_bytes,
            "rss_current_bytes": self.rss_current_bytes,
            "rss_peak_window_bytes": self.rss_peak_window_bytes,
            "rss_delta_from_start_bytes": (
                self.rss_peak_window_bytes - self.rss_start_bytes
                if self.rss_peak_window_bytes is not None
                and self.rss_start_bytes is not None
                else None
            ),
            "ru_maxrss_lifetime_bytes": lifetime_max_rss_bytes(),
            "parser": {
                "status": "observed" if parser_samples else "unavailable",
                "rss_start_bytes": parser_start,
                "rss_peak_bytes": parser_peak,
                "rss_delta_bytes": parser_peak - parser_start
                if parser_peak is not None and parser_start is not None
                else None,
                "elapsed_s": (
                    max(parser_offsets) - min(parser_offsets)
                    if parser_offsets
                    else None
                ),
                "peak_kind": "observed_sampled_peak" if parser_samples else None,
                "sample_count": len(parser_samples),
            },
            "sample_timeline": samples,
        }


def fixture_identity(
    path: Path, *, label: str, role: str = "qualification_fixture"
) -> dict[str, Any]:
    from offline_rag.core.ids import content_hash_from_path

    media_type = (
        "application/pdf"
        if path.suffix.lower() == ".pdf"
        else "application/octet-stream"
    )
    return {
        "label": label,
        "role": role,
        "identifier": path.name,
        "sha256": content_hash_from_path(path),
        "byte_size": path.stat().st_size,
        "media_type": media_type,
    }


def machine_provenance() -> dict[str, Any]:
    uname = platform.uname()
    mem_total = None
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
                break
    except OSError, ValueError, IndexError:
        pass
    return {
        "python_version": sys.version.split()[0],
        "os": uname.system,
        "kernel": uname.release,
        "machine": uname.machine,
        "platform": platform.platform(),
        "cpu_identity": platform.processor() or uname.machine,
        "logical_cpu_count": os.cpu_count(),
        "physical_cpu_count": _physical_cpu_count(),
        "physical_ram_bytes": mem_total,
        "torch_version": _optional_version("torch"),
        "cuda_version": _optional_cuda_version(),
    }


def _optional_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception:  # noqa: BLE001
        return None


def _optional_cuda_version() -> str | None:
    try:
        import torch

        return getattr(torch.version, "cuda", None)
    except Exception:  # noqa: BLE001
        return None


def git_provenance(
    repo_root: Path = REPO_ROOT, source_paths: Sequence[Path] = ()
) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=repo_root, text=True
            ).strip()
        except OSError, subprocess.CalledProcessError:
            return None

    hashes: dict[str, str | None] = {}
    for path in source_paths:
        try:
            hashes[str(path.relative_to(repo_root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        except OSError, ValueError:
            hashes[str(path)] = None
    status = run("status", "--porcelain", "--untracked-files=no")
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "exact_git_sha": run("rev-parse", "HEAD"),
        "tracked_worktree_clean": status == "",
        "tracked_worktree_status": status or None,
        "harness_source_sha256": hashes,
    }


def sanitized_json(payload: Mapping[str, Any]) -> str:
    """Stable evidence serialization with no source-content fields."""
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


__all__ = [
    "EVIDENCE_CONTRACT",
    "REPO_ROOT",
    "DiskUsageTracker",
    "ProcessSampler",
    "StageTracker",
    "available_ram_bytes",
    "cpu_metrics",
    "current_rss_bytes",
    "directory_size",
    "fixture_identity",
    "git_provenance",
    "lifetime_max_rss_bytes",
    "machine_provenance",
    "reset_cuda_peak_memory_stats",
    "rusage_snapshot",
    "sanitized_json",
]
