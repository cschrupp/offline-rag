"""Deterministic run-level aggregate derivation for Slice 14."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from offline_rag.evaluation.performance_14.contracts import (
    STATISTICS_SEMANTICS_VERSION_V1,
    BenchmarkLevelV1,
    DerivedLatencyStatsV1,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformancePathLatencyV1,
    PerformanceRunAggregateV1,
    PerformanceStageStatsV1,
    PerformanceVariantQualityV1,
    PerformanceVariantResourceV1,
    PerformanceVariantStatsV1,
    RunStatusV1,
    TelemetryAvailabilityV1,
)
from offline_rag.evaluation.performance_14.evidence_14c import (
    VARIANT_TOTAL_PATH,
    path_samples_to_observations,
)
from offline_rag.evaluation.performance_14.statistics import derive_latency_stats


def _empty_stats() -> DerivedLatencyStatsV1:
    return DerivedLatencyStatsV1(
        statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
        attempted_count=0,
        valid_count=0,
        n=0,
        min=None,
        p50=None,
        p95=None,
        max=None,
        failure_count=0,
        warmup_count=0,
        instrumentation_exclusion_count=0,
    )


def build_run_aggregate(
    *,
    suite_id: str,
    run_id: str,
    run_status: RunStatusV1,
    benchmark_level: BenchmarkLevelV1,
    cases: Sequence[PerformanceBenchmarkCaseV1],
    diagnostic_only: bool = True,
    authoritative: bool = False,
    evidence_class: str = "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE",
    path_latency: Sequence[PerformancePathLatencyV1] | None = None,
    quality_by_variant: Sequence[PerformanceVariantQualityV1] | None = None,
    resource_by_variant: Sequence[PerformanceVariantResourceV1] | None = None,
    vram_availability: TelemetryAvailabilityV1 = "unavailable",
) -> PerformanceRunAggregateV1:
    """Roll case-level raw observations into deterministic suite aggregates."""
    if run_status == "failed_preflight":
        return PerformanceRunAggregateV1(
            suite_id=suite_id,
            run_id=run_id,
            run_status=run_status,
            benchmark_level=benchmark_level,
            case_ids=[],
            by_variant=[],
            by_stage_or_path=[],
            overall=_empty_stats(),
            path_latency=list(path_latency or ()),
            quality_by_variant=list(quality_by_variant or ()),
            resource_by_variant=list(resource_by_variant or ()),
            vram_availability=vram_availability,
            diagnostic_only=diagnostic_only,
            authoritative=authoritative,
            evidence_class=evidence_class,
        )

    by_variant_obs: dict[str, list[PerformanceBenchmarkObservationV1]] = defaultdict(
        list
    )
    by_stage_obs: dict[str, list[PerformanceBenchmarkObservationV1]] = defaultdict(list)
    variant_rollup_obs: list[PerformanceBenchmarkObservationV1] = []
    case_ids: list[str] = []
    for case in cases:
        case_ids.append(case.case_id)
        measured = list(case.measured_observations)
        warmups = list(case.warmup_observations)
        combined = warmups + measured
        for obs in combined:
            by_stage_obs[obs.stage_id].append(obs)

        # Prefer retrieval-path total samples for variant cost comparison.
        total_path = VARIANT_TOTAL_PATH.get(case.variant)
        path_samples = [
            sample
            for sample in (case.path_samples or [])
            if total_path is not None and sample.path == total_path
        ]
        if path_samples:
            chosen = path_samples_to_observations(path_samples)
        else:
            # Diagnostic / single-stage cases: use labeled stage observations.
            chosen = combined
        by_variant_obs[case.variant].extend(chosen)
        variant_rollup_obs.extend(chosen)

    by_variant = [
        PerformanceVariantStatsV1(
            variant=variant,
            stats=derive_latency_stats(observations),
        )
        for variant, observations in sorted(by_variant_obs.items())
    ]
    by_stage = [
        PerformanceStageStatsV1(
            stage_or_path=stage,
            stats=derive_latency_stats(observations),
        )
        for stage, observations in sorted(by_stage_obs.items())
    ]
    overall = (
        derive_latency_stats(variant_rollup_obs) if variant_rollup_obs else _empty_stats()
    )
    return PerformanceRunAggregateV1(
        suite_id=suite_id,
        run_id=run_id,
        run_status=run_status,
        benchmark_level=benchmark_level,
        case_ids=sorted(case_ids),
        by_variant=by_variant,
        by_stage_or_path=by_stage,
        overall=overall,
        path_latency=list(path_latency or ()),
        quality_by_variant=list(quality_by_variant or ()),
        resource_by_variant=list(resource_by_variant or ()),
        vram_availability=vram_availability,
        diagnostic_only=diagnostic_only,
        authoritative=authoritative,
        evidence_class=evidence_class,
    )
