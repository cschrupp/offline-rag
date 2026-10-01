"""RAM/VRAM resource observation for Slice 14A.

Missing telemetry is ``unavailable`` / ``unevaluable`` — never inferred as zero.
Missing RAM/VRAM does not invalidate otherwise valid timing results.
"""

from __future__ import annotations

import os
from typing import Any

from offline_rag.evaluation.performance_14.contracts import (
    PerformanceResourceObservationV1,
    TelemetryAvailabilityV1,
)


def _read_linux_rss_bytes() -> int | None:
    """Best-effort RSS from ``/proc/self/status`` (Linux)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    # VmRSS: <kB> kB
                    return int(parts[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def observe_ram_rss_bytes() -> tuple[TelemetryAvailabilityV1, int | None]:
    rss = _read_linux_rss_bytes()
    if rss is None:
        return "unavailable", None
    return "available", rss


def observe_vram(
    *,
    probe: Any | None = None,
) -> tuple[TelemetryAvailabilityV1, int | None, int | None, str | None]:
    """Return (availability, used_before, peak, device_id).

    Default: unavailable (no CUDA dependency required for 14A). Optional
    ``probe`` may be a callable ``() -> tuple[int, int, str]`` returning
    (used_bytes, peak_bytes, device_id) when a later harness supplies it.
    """
    if probe is None:
        return "unavailable", None, None, None
    try:
        used, peak, device_id = probe()
        return "available", int(used), int(peak), str(device_id)
    except (TypeError, ValueError, RuntimeError, OSError):
        return "unevaluable", None, None, None


def capture_resource_observation(
    stage_id: str,
    *,
    vram_probe: Any | None = None,
    note: str | None = None,
) -> PerformanceResourceObservationV1:
    """Capture a single resource sample for ``stage_id``.

    Instantaneous RSS is recorded as ``ram_rss_bytes_before`` only.
    ``ram_rss_bytes_peak`` remains ``None`` until a genuine peak sampler exists
    (do not synthesize peak = before).
    """
    ram_av, ram_rss = observe_ram_rss_bytes()
    vram_av, vram_used, vram_peak, device_id = observe_vram(probe=vram_probe)
    return PerformanceResourceObservationV1(
        stage_id=stage_id,
        ram_availability=ram_av,
        ram_rss_bytes_before=ram_rss if ram_av == "available" else None,
        ram_rss_bytes_peak=None,
        vram_availability=vram_av,
        vram_used_bytes_before=vram_used if vram_av == "available" else None,
        # Peak only when the optional probe actually supplies a peak reading.
        vram_used_bytes_peak=vram_peak if vram_av == "available" else None,
        device_id=device_id,
        note=note,
    )


def process_pid() -> int:
    return os.getpid()
