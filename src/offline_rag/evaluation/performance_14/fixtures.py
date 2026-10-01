"""Deterministic synthetic performance fixtures for Slice 14B dry-run.

These fixtures establish stable timing/load subjects for harness validation.
They do **not** establish retrieval quality and are not a frozen 14C suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from offline_rag.evaluation.performance_14.contracts import (
    BenchmarkLevelV1,
    PerformanceBenchmarkSuiteV1,
)
from offline_rag.evaluation.performance_14.identity import compute_suite_identity_hash

PopulationKindV1 = Literal["performance_fixture"]

# Diagnostic dry-run defaults meet locked minima without long wall time.
DEFAULT_WARMUP_COUNT = 1
DEFAULT_MEASURED_REPS_MICRO = 10
DEFAULT_MEASURED_REPS_GENERATION = 5

DRYRUN_POPULATION_A = "perfpop_dryrun_level_a_v1"
DRYRUN_POPULATION_B = "perfpop_dryrun_level_b_v1"
DRYRUN_POPULATION_C = "perfpop_dryrun_level_c_v1"

VARIANT_HYBRID = "hybrid"
VARIANT_HYBRID_RERANK = "hybrid_rerank"


@dataclass(frozen=True, slots=True)
class PerformanceCaseSpec:
    """One scheduled case definition (identity-bearing fields only)."""

    case_kind: str
    benchmark_level: BenchmarkLevelV1
    stage_or_path: str
    subject_identity: str
    variant: str
    cold_warm: Literal["cold", "warm"]
    local_case_id: str


@dataclass(frozen=True, slots=True)
class PerformanceSuitePlan:
    """In-memory suite plan used by the 14B dry-run harness."""

    suite: PerformanceBenchmarkSuiteV1
    cases: tuple[PerformanceCaseSpec, ...]
    warmup_count: int
    measured_repetitions: int
    baseline_variant: str | None
    treatment_variant: str | None
    treatment_delta: tuple[str, ...]
    population_kind: PopulationKindV1 = "performance_fixture"
    diagnostic_only: bool = True
    authoritative: bool = False


def _stable_case_id(spec: PerformanceCaseSpec) -> str:
    return (
        f"{spec.benchmark_level.lower()}_"
        f"{spec.local_case_id}_{spec.variant}_{spec.cold_warm}"
    )


def build_level_a_suite_plan(
    *,
    warmup_count: int = DEFAULT_WARMUP_COUNT,
    measured_repetitions: int = DEFAULT_MEASURED_REPS_MICRO,
) -> PerformanceSuitePlan:
    """Level A micro/stage fixtures (parse/chunk/embed diagnostics)."""
    subjects = ("doc_fixture_001", "doc_fixture_002")
    stages = ("parse", "chunk", "embed")
    variant = "stage_isolated"
    cases: list[PerformanceCaseSpec] = []
    for subject in subjects:
        for stage in stages:
            cases.append(
                PerformanceCaseSpec(
                    case_kind="micro_stage",
                    benchmark_level="A",
                    stage_or_path=stage,
                    subject_identity=subject,
                    variant=variant,
                    cold_warm="warm",
                    local_case_id=f"{stage}_{subject}",
                )
            )
    case_ids = [_stable_case_id(spec) for spec in cases]
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="A",
        population_identity=DRYRUN_POPULATION_A,
        variants=[variant],
        case_ids=case_ids,
    )
    suite = suite.model_copy(
        update={"suite_identity_hash": compute_suite_identity_hash(suite)}
    )
    return PerformanceSuitePlan(
        suite=suite,
        cases=tuple(cases),
        warmup_count=warmup_count,
        measured_repetitions=measured_repetitions,
        baseline_variant=None,
        treatment_variant=None,
        treatment_delta=(),
    )


def build_level_b_suite_plan(
    *,
    warmup_count: int = DEFAULT_WARMUP_COUNT,
    measured_repetitions: int = DEFAULT_MEASURED_REPS_MICRO,
) -> PerformanceSuitePlan:
    """Level B pipeline paired comparison (hybrid vs hybrid+reranker)."""
    subjects = ("q_fixture_001", "q_fixture_002")
    variants = (VARIANT_HYBRID, VARIANT_HYBRID_RERANK)
    cases: list[PerformanceCaseSpec] = []
    for subject in subjects:
        for variant in variants:
            cases.append(
                PerformanceCaseSpec(
                    case_kind="pipeline_query",
                    benchmark_level="B",
                    stage_or_path="fusion" if variant == VARIANT_HYBRID else "rerank",
                    subject_identity=subject,
                    variant=variant,
                    cold_warm="warm",
                    local_case_id=subject,
                )
            )
    case_ids = [_stable_case_id(spec) for spec in cases]
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="B",
        population_identity=DRYRUN_POPULATION_B,
        variants=list(variants),
        case_ids=case_ids,
    )
    suite = suite.model_copy(
        update={"suite_identity_hash": compute_suite_identity_hash(suite)}
    )
    return PerformanceSuitePlan(
        suite=suite,
        cases=tuple(cases),
        warmup_count=warmup_count,
        measured_repetitions=measured_repetitions,
        baseline_variant=VARIANT_HYBRID,
        treatment_variant=VARIANT_HYBRID_RERANK,
        treatment_delta=("reranker_enablement", "reranker_configuration", "stage_or_path"),
    )


def build_level_c_suite_plan(
    *,
    warmup_count: int = DEFAULT_WARMUP_COUNT,
    measured_repetitions: int = DEFAULT_MEASURED_REPS_GENERATION,
) -> PerformanceSuitePlan:
    """Level C end-to-end user-path fixtures (synthetic generation envelope)."""
    subjects = ("e2e_fixture_001", "e2e_fixture_002")
    variant = "end_to_end_warm"
    cases = [
        PerformanceCaseSpec(
            case_kind="end_to_end_query",
            benchmark_level="C",
            stage_or_path="end_to_end",
            subject_identity=subject,
            variant=variant,
            cold_warm="warm",
            local_case_id=subject,
        )
        for subject in subjects
    ]
    case_ids = [_stable_case_id(spec) for spec in cases]
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="C",
        population_identity=DRYRUN_POPULATION_C,
        variants=[variant],
        case_ids=case_ids,
    )
    suite = suite.model_copy(
        update={"suite_identity_hash": compute_suite_identity_hash(suite)}
    )
    return PerformanceSuitePlan(
        suite=suite,
        cases=tuple(cases),
        warmup_count=warmup_count,
        measured_repetitions=measured_repetitions,
        baseline_variant=None,
        treatment_variant=None,
        treatment_delta=(),
    )


def suite_plan_for_level(level: BenchmarkLevelV1) -> PerformanceSuitePlan:
    if level == "A":
        return build_level_a_suite_plan()
    if level == "B":
        return build_level_b_suite_plan()
    if level == "C":
        return build_level_c_suite_plan()
    raise ValueError(f"unknown benchmark level: {level!r}")


def stable_case_id(spec: PerformanceCaseSpec) -> str:
    return _stable_case_id(spec)
