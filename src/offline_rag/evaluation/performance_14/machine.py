"""Machine / environment profile capture for Slice 14A."""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

from offline_rag.evaluation.performance_14.contracts import PerformanceMachineProfileV1
from offline_rag.evaluation.performance_14.identity import compute_machine_profile_hash


def _cpu_model() -> str:
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def _system_ram_bytes() -> int | None:
    try:
        pages = os.sysconf("SC_PAGE_SIZE")
        phys = os.sysconf("SC_PHYS_PAGES")
        return int(pages) * int(phys)
    except (AttributeError, OSError, ValueError):
        return None


def _physical_cores() -> int | None:
    """Best-effort physical core count; ``None`` when topology is unavailable."""
    if platform.system() == "Linux":
        try:
            cores: set[tuple[str, str]] = set()
            physical_id: str | None = None
            core_id: str | None = None
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("physical id"):
                        physical_id = line.split(":", 1)[1].strip()
                    elif line.startswith("core id"):
                        core_id = line.split(":", 1)[1].strip()
                    elif not line.strip():
                        if physical_id is not None and core_id is not None:
                            cores.add((physical_id, core_id))
                        physical_id = None
                        core_id = None
            if physical_id is not None and core_id is not None:
                cores.add((physical_id, core_id))
            if cores:
                return len(cores)
            # Some containers expose cpuinfo without topology ids.
            cpu_cores: list[str] = []
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("cpu cores"):
                        cpu_cores.append(line.split(":", 1)[1].strip())
            if cpu_cores:
                # Prefer first reported package "cpu cores" value when unique.
                values = {int(v) for v in cpu_cores if v.isdigit()}
                if len(values) == 1:
                    return values.pop()
        except (OSError, ValueError):
            return None
    return None


def capture_machine_profile(
    *,
    offline_rag_commit_sha: str,
    gpu: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> PerformanceMachineProfileV1:
    """Capture the required machine profile fields for a benchmark RUN."""
    uname = platform.uname()
    logical = os.cpu_count()
    gpu = gpu or {}
    return PerformanceMachineProfileV1(
        os_name=uname.system or "unknown",
        os_version=uname.release or "unknown",
        architecture=uname.machine or platform.machine() or "unknown",
        cpu_model=_cpu_model(),
        physical_cores=_physical_cores(),
        logical_cores=logical,
        system_ram_bytes=_system_ram_bytes(),
        python_version=sys.version.split()[0],
        offline_rag_commit_sha=offline_rag_commit_sha,
        gpu_model=gpu.get("model"),
        gpu_vram_bytes=gpu.get("vram_bytes"),
        gpu_driver_version=gpu.get("driver_version"),
        cuda_runtime_version=gpu.get("cuda_runtime_version"),
        extra=dict(extra or {}),
    )


def capture_machine_profile_with_id(
    *,
    offline_rag_commit_sha: str,
    gpu: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[PerformanceMachineProfileV1, str]:
    profile = capture_machine_profile(
        offline_rag_commit_sha=offline_rag_commit_sha,
        gpu=gpu,
        extra=extra,
    )
    return profile, compute_machine_profile_hash(profile)
