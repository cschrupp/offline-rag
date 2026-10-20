"""Lightweight D2 measurement / CPU baseline fact capture (non-perturbing)."""

from __future__ import annotations

import os
import resource
from typing import Any


def capture_cpu_baseline_facts(
    *,
    embedder: object | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Best-effort C0 facts. Must not tune threads or alter production path."""
    facts: dict[str, Any] = {
        "effective_dtype": None,
        "attention_backend": None,
        "batch_size": batch_size,
        "torch_num_threads": None,
        "torch_num_interop_threads": None,
        "cpu_logical_count": os.cpu_count(),
        "cpu_physical_count": None,
        "process_cpu_time_s": None,
        "peak_rss_bytes": None,
        "system_ram_total_bytes": None,
        "system_ram_available_bytes": None,
    }

    if embedder is not None:
        observe = getattr(embedder, "observe_execution_facts", None)
        if callable(observe):
            try:
                observed = observe()
            except Exception:  # noqa: BLE001
                observed = {}
            if isinstance(observed, dict):
                facts["effective_dtype"] = observed.get("dtype")
                facts["attention_backend"] = observed.get("attention_backend")
        facts["resolved_device"] = getattr(
            embedder, "resolved_device", getattr(embedder, "device", None)
        )
        facts["configured_precision"] = getattr(embedder, "configured_precision", None)
        facts["resolved_precision"] = getattr(embedder, "resolved_precision", None)

    try:
        import torch

        facts["torch_num_threads"] = int(torch.get_num_threads())
        facts["torch_num_interop_threads"] = int(torch.get_num_interop_threads())
    except Exception:  # noqa: BLE001
        pass

    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        facts["process_cpu_time_s"] = float(usage.ru_utime) + float(usage.ru_stime)
        # ru_maxrss is kilobytes on Linux.
        facts["peak_rss_bytes"] = int(usage.ru_maxrss) * 1024
    except Exception:  # noqa: BLE001
        pass

    try:
        # Optional; do not fail closed if unavailable.
        import psutil  # type: ignore[import-untyped]

        vm = psutil.virtual_memory()
        facts["system_ram_total_bytes"] = int(vm.total)
        facts["system_ram_available_bytes"] = int(vm.available)
        facts["cpu_physical_count"] = int(psutil.cpu_count(logical=False) or 0) or None
    except Exception:  # noqa: BLE001
        pass

    return facts


def capture_gpu_memory_facts() -> dict[str, Any]:
    """Safe CUDA memory peaks when CUDA is available; nulls otherwise."""
    facts: dict[str, Any] = {
        "peak_allocated_bytes": None,
        "peak_reserved_bytes": None,
        "total_vram_bytes": None,
    }
    try:
        import torch

        if not torch.cuda.is_available():
            return facts
        facts["peak_allocated_bytes"] = int(torch.cuda.max_memory_allocated())
        facts["peak_reserved_bytes"] = int(torch.cuda.max_memory_reserved())
        props = torch.cuda.get_device_properties(0)
        facts["total_vram_bytes"] = int(getattr(props, "total_mem", 0) or 0) or None
    except Exception:  # noqa: BLE001
        return facts
    return facts


def parity_probe_surface_status() -> dict[str, Any]:
    """Mechanical surface only — probe inputs/thresholds not frozen in this tranche."""
    return {
        "status": "not_frozen",
        "note": (
            "Retrieval-parity probe inputs and acceptance thresholds must be frozen "
            "under the later execution authority before the first FP16 treatment call."
        ),
        "execution_authorized": False,
    }


__all__ = [
    "capture_cpu_baseline_facts",
    "capture_gpu_memory_facts",
    "parity_probe_surface_status",
]
