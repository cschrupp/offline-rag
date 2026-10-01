"""Deterministic run-level aggregate derivation for Slice 14B."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from offline_rag.evaluation.performance_14.contracts import (
    STATISTICS_SEMANTICS_VERSION_V1,
    BenchmarkLevelV1,
    DerivedLatencyStatsV1,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceRunAggregateV1,
    PerformanceStageStatsV1,
    PerformanceVariantStatsV1,
    RunStatusV1,
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
            diagnostic_only=diagnostic_only,
            authoritative=authoritative,
            evidence_class=evidence_class,
        )

    by_variant_obs: dict[str, list[PerformanceBenchmarkObservationV1]] = defaultdict(
        list
    )
    by_stage_obs: dict[str, list[PerformanceBenchmarkObservationV1]] = defaultdict(list)
    all_obs: list[PerformanceBenchmarkObservationV1] = []
    case_ids: list[str] = []
    for case in cases:
        case_ids.append(case.case_id)
        measured = list(case.measured_observations)
        warmups = list(case.warmup_observations)
        combined = warmups + measured
        by_variant_obs[case.variant].extend(combined)
        by_stage_obs[case.stage_or_path].extend(combined)
        all_obs.extend(combined)

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
    overall = derive_latency_stats(all_obs) if all_obs else _empty_stats()
    return PerformanceRunAggregateV1(
        suite_id=suite_id,
        run_id=run_id,
        run_status=run_status,
        benchmark_level=benchmark_level,
        case_ids=sorted(case_ids),
        by_variant=by_variant,
        by_stage_or_path=by_stage,
        overall=overall,
        diagnostic_only=diagnostic_only,
        authoritative=authoritative,
        evidence_class=evidence_class,
    )
