"""Slice 14A/14B performance measurement package.

Design authority: docs/milestone7_performance_ui.md
Accepted design SHA: 89a395ae4df7aff23c2da2c8c44fd6fe405459a6
Accepted 14A substrate: c087b8c1f038bd049809db2bf7e761ee0db93b58

14A: contracts, identities, statistics, timing, resources, machine profile,
passive instrumentation.

14B: Level A/B/C dry-run runners, fail-closed preflight, immutable run dirs,
paired scheduling, aggregate/report derivation. Dry-run outputs are
DIAGNOSTIC ONLY / NON-AUTHORITATIVE.

14C frozen campaigns and authoritative evidence production remain NOT
AUTHORIZED by this package alone.
"""

from offline_rag.evaluation.performance_14.contracts import (
    DESIGN_AUTHORITY_SHA_14,
    MEASUREMENT_PROTOCOL_VERSION_V1,
    PERFORMANCE_BENCHMARK_AGGREGATE_V1,
    PERFORMANCE_BENCHMARK_CASE_V1,
    PERFORMANCE_BENCHMARK_OBSERVATION_V1,
    PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1,
    PERFORMANCE_BENCHMARK_SUITE_V1,
    PERFORMANCE_MACHINE_PROFILE_V1,
    PERFORMANCE_RESOURCE_OBSERVATION_V1,
    SEMANTIC_STAGE_ENVELOPES_V1,
    SEMANTIC_STAGE_IDS_V1,
    SLICE14_DESIGN_BASELINE_SHA,
    STATISTICS_SEMANTICS_VERSION_V1,
    SUBSTRATE_PIN_14A,
    TIMING_BOUNDARY_VERSION_V1,
    DerivedLatencyStatsV1,
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceBenchmarkSuiteV1,
    PerformanceMachineProfileV1,
    PerformanceResourceObservationV1,
    PerformanceRunAggregateV1,
)
from offline_rag.evaluation.performance_14.harness import (
    PerformanceDryRunResult,
    run_all_level_dryruns,
    run_performance_14b_dryrun,
)
from offline_rag.evaluation.performance_14.identity import (
    compute_case_identity_hash,
    compute_config_identity_hash,
    compute_machine_profile_hash,
    compute_run_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.instrumentation import (
    DEFAULT_INSTRUMENTER,
    PassiveStageInstrumenter,
    observe_stage,
)
from offline_rag.evaluation.performance_14.machine import (
    capture_machine_profile,
    capture_machine_profile_with_id,
)
from offline_rag.evaluation.performance_14.resources import capture_resource_observation
from offline_rag.evaluation.performance_14.scheduling import paired_alternating_schedule
from offline_rag.evaluation.performance_14.statistics import (
    derive_latency_stats,
    linear_percentile,
)
from offline_rag.evaluation.performance_14.timing import (
    measure_stage,
    monotonic_now,
    stage_envelope,
    timed_call,
    validate_stage_id,
)

__all__ = [
    "DEFAULT_INSTRUMENTER",
    "DESIGN_AUTHORITY_SHA_14",
    "MEASUREMENT_PROTOCOL_VERSION_V1",
    "PERFORMANCE_BENCHMARK_AGGREGATE_V1",
    "PERFORMANCE_BENCHMARK_CASE_V1",
    "PERFORMANCE_BENCHMARK_OBSERVATION_V1",
    "PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1",
    "PERFORMANCE_BENCHMARK_SUITE_V1",
    "PERFORMANCE_MACHINE_PROFILE_V1",
    "PERFORMANCE_RESOURCE_OBSERVATION_V1",
    "SEMANTIC_STAGE_ENVELOPES_V1",
    "SEMANTIC_STAGE_IDS_V1",
    "SLICE14_DESIGN_BASELINE_SHA",
    "STATISTICS_SEMANTICS_VERSION_V1",
    "SUBSTRATE_PIN_14A",
    "TIMING_BOUNDARY_VERSION_V1",
    "DerivedLatencyStatsV1",
    "PassiveStageInstrumenter",
    "Performance14Error",
    "PerformanceBenchmarkCaseV1",
    "PerformanceBenchmarkObservationV1",
    "PerformanceBenchmarkRunManifestV1",
    "PerformanceBenchmarkSuiteV1",
    "PerformanceDryRunResult",
    "PerformanceMachineProfileV1",
    "PerformanceResourceObservationV1",
    "PerformanceRunAggregateV1",
    "capture_machine_profile",
    "capture_machine_profile_with_id",
    "capture_resource_observation",
    "compute_case_identity_hash",
    "compute_config_identity_hash",
    "compute_machine_profile_hash",
    "compute_run_identity_hash",
    "compute_suite_identity_hash",
    "derive_latency_stats",
    "linear_percentile",
    "measure_stage",
    "monotonic_now",
    "observe_stage",
    "paired_alternating_schedule",
    "run_all_level_dryruns",
    "run_performance_14b_dryrun",
    "stage_envelope",
    "timed_call",
    "validate_stage_id",
]
