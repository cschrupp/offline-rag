"""Deterministic latency statistics for Slice 14A.

Semantics version: ``perf-stats-linear-interp-v1``

Percentiles use linear interpolation between closest ranks on the sorted
valid sample list. Index formula: ``rank = (p/100) * (n - 1)``.
Failures and instrumentation exclusions are counted separately and never
enter the latency sample set.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from offline_rag.evaluation.performance_14.contracts import (
    STATISTICS_SEMANTICS_VERSION_V1,
    DerivedLatencyStatsV1,
    PerformanceBenchmarkObservationV1,
    Performance14Error,
)


def linear_percentile(sorted_samples: Sequence[float], percentile: float) -> float:
    """Return percentile in ``[0, 100]`` via linear interpolation between ranks."""
    if not sorted_samples:
        raise Performance14Error("percentile requires a non-empty sample")
    if percentile < 0.0 or percentile > 100.0:
        raise Performance14Error("percentile must be in [0, 100]")
    n = len(sorted_samples)
    if n == 1:
        return float(sorted_samples[0])
    rank = (percentile / 100.0) * (n - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(sorted_samples[lo])
    weight = rank - lo
    return float(sorted_samples[lo] * (1.0 - weight) + sorted_samples[hi] * weight)


def derive_latency_stats(
    observations: Sequence[PerformanceBenchmarkObservationV1],
    *,
    warmup_count: int | None = None,
) -> DerivedLatencyStatsV1:
    """Derive deterministic stats from raw observations.

    Only ``observation_status == valid`` and ``is_warmup is False`` durations
    enter ``n`` / percentiles. Failures and exclusions are counted, not timed.
    """
    valid_durations: list[float] = []
    failure_count = 0
    exclusion_count = 0
    observed_warmup = 0
    for obs in observations:
        if obs.is_warmup:
            observed_warmup += 1
            continue
        if obs.observation_status == "valid":
            assert obs.duration_seconds is not None
            valid_durations.append(float(obs.duration_seconds))
        elif obs.observation_status == "failed":
            failure_count += 1
        elif obs.observation_status == "excluded_instrumentation_error":
            exclusion_count += 1
    warmup = warmup_count if warmup_count is not None else observed_warmup
    if not valid_durations:
        return DerivedLatencyStatsV1(
            statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
            n=0,
            min=None,
            p50=None,
            p95=None,
            max=None,
            failure_count=failure_count,
            warmup_count=warmup,
            instrumentation_exclusion_count=exclusion_count,
        )
    ordered = sorted(valid_durations)
    return DerivedLatencyStatsV1(
        statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
        n=len(ordered),
        min=ordered[0],
        p50=linear_percentile(ordered, 50.0),
        p95=linear_percentile(ordered, 95.0),
        max=ordered[-1],
        failure_count=failure_count,
        warmup_count=warmup,
        instrumentation_exclusion_count=exclusion_count,
    )
