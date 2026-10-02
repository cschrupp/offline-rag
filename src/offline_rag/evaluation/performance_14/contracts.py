"""Slice 14A performance benchmark contracts (design authority 89a395ae).

Evaluation-layer only. No runner, CLI, preflight execution, or result writes.
Observational measurement substrate — does not optimize the measured system.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.sufficiency.contracts import ExactNonBlankStr

PERFORMANCE_BENCHMARK_SUITE_V1 = "performance-benchmark-suite-v1"
PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1 = "performance-benchmark-run-manifest-v1"
PERFORMANCE_BENCHMARK_CASE_V1 = "performance-benchmark-case-v1"
PERFORMANCE_BENCHMARK_OBSERVATION_V1 = "performance-benchmark-observation-v1"
PERFORMANCE_MACHINE_PROFILE_V1 = "performance-machine-profile-v1"
PERFORMANCE_RESOURCE_OBSERVATION_V1 = "performance-resource-observation-v1"
PERFORMANCE_BENCHMARK_AGGREGATE_V1 = "performance-benchmark-aggregate-v1"
PERFORMANCE_PREFLIGHT_RECORD_V1 = "performance-preflight-record-v1"

DESIGN_AUTHORITY_SHA_14 = "89a395ae4df7aff23c2da2c8c44fd6fe405459a6"
SLICE14_DESIGN_BASELINE_SHA = "dcc6b07c20f97472cf506c4665af1f88f00a886b"
# Accepted Slice 14A technical result (contracts + instrumentation substrate).
SUBSTRATE_PIN_14A = "c087b8c1f038bd049809db2bf7e761ee0db93b58"

MEASUREMENT_PROTOCOL_VERSION_V1 = "perf-measurement-protocol-v1"
TIMING_BOUNDARY_VERSION_V1 = "perf-timing-boundaries-v1"
STATISTICS_SEMANTICS_VERSION_V1 = "perf-stats-linear-interp-v1"

BenchmarkLevelV1 = Literal["A", "B", "C"]
ColdWarmV1 = Literal["cold", "warm"]
RunStatusV1 = Literal["completed", "failed_preflight", "failed_during_execution"]
CaseStatusV1 = Literal["completed", "failed"]
ObservationStatusV1 = Literal["valid", "failed", "excluded_instrumentation_error"]
TelemetryAvailabilityV1 = Literal["available", "unavailable", "unevaluable"]
PreflightStatusV1 = Literal["passed", "failed"]
PreflightCheckStatusV1 = Literal[
    "passed", "failed", "not_applicable", "fixture_internal"
]
WorkingTreeStateV1 = Literal["clean", "dirty", "unavailable"]

SEMANTIC_STAGE_IDS_V1: tuple[str, ...] = (
    "document_load",
    "parse",
    "chunk",
    "embed",
    "dense_index_write",
    "lexical_index_write",
    "dense_retrieve",
    "lexical_retrieve",
    "fusion",
    "rerank",
    "context_assembly",
    "generation",
    "citation_validation",
    "end_to_end",
)

# Normative start→end envelopes (design §8). Implementations that time a
# different envelope under the same stage id are non-conforming.
SEMANTIC_STAGE_ENVELOPES_V1: dict[str, str] = {
    "document_load": "source accepted → content available to parser",
    "parse": "parser invocation → normalized parsed content blocks returned",
    "chunk": "parsed content → final chunks ready",
    "embed": "embedding batch submitted → vectors returned",
    "dense_index_write": "vectors/payload ready → persistent dense write complete",
    "lexical_index_write": "chunks ready → lexical write complete",
    "dense_retrieve": "dense request issued → dense candidate set available",
    "lexical_retrieve": "lexical request issued → lexical candidate set available",
    "fusion": "dense + lexical candidate sets available → fused ranking complete",
    "rerank": "finalized reranker input → reranked candidates returned",
    "context_assembly": (
        "final ranked candidates → GeneratorRequest evidence/context finalized"
    ),
    "generation": "generator request submitted → complete response",
    "citation_validation": "raw generation response → validated answer/citations",
    "end_to_end": "CLI/service query entry → accepted terminal result",
}

GenerationSubBoundaryV1 = Literal[
    "generation_total",
    "generation_ttft",
    "generation_decode",
    "tokens_per_second",
]

PERFORMANCE_LEVEL_C_ATTEMPT_V1 = "performance-level-c-attempt-v1"
PERFORMANCE_GENERATION_TELEMETRY_V1 = "performance-generation-telemetry-v1"
PERFORMANCE_LEVEL_C_STAGE_DISPOSITION_V1 = "performance-level-c-stage-disposition-v1"

LevelCStageIdV1 = Literal[
    "context_assembly",
    "generation",
    "citation_validation",
    "end_to_end",
]
LEVEL_C_STAGE_IDS_V1: tuple[LevelCStageIdV1, ...] = (
    "context_assembly",
    "generation",
    "citation_validation",
    "end_to_end",
)

LevelCStageDispositionStatusV1 = Literal[
    "valid",
    "failed",
    "excluded_instrumentation_error",
    "not_applicable",
]

LevelCTerminalStatusV1 = Literal[
    "answered",
    "insufficient_evidence",
    "model_abstain",
    "generation_failed",
    "citation_invalid",
    "orchestration_failed",
]


class Performance14Error(RuntimeError):
    """Fail-closed Slice 14 performance evaluation error."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DerivedLatencyStatsV1(StrictModel):
    """Deterministic latency summary over valid observation durations (seconds)."""

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_AGGREGATE_V1
    statistics_semantics_version: ExactNonBlankStr = STATISTICS_SEMANTICS_VERSION_V1
    attempted_count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    n: int = Field(ge=0)
    min: float | None = None
    p50: float | None = None
    p95: float | None = None
    max: float | None = None
    failure_count: int = Field(ge=0, default=0)
    warmup_count: int = Field(ge=0, default=0)
    instrumentation_exclusion_count: int = Field(ge=0, default=0)
    # Level-C: stages correctly skipped. NOT part of attempted_count.
    not_applicable_count: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def _stats_consistency(self) -> DerivedLatencyStatsV1:
        if self.n != self.valid_count:
            raise ValueError("n must equal valid_count")
        expected_attempted = (
            self.valid_count + self.failure_count + self.instrumentation_exclusion_count
        )
        if self.attempted_count != expected_attempted:
            raise ValueError(
                "attempted_count must equal "
                "valid_count + failure_count + instrumentation_exclusion_count"
            )
        if self.n == 0:
            if any(v is not None for v in (self.min, self.p50, self.p95, self.max)):
                raise ValueError("empty sample must not report latency percentiles")
            return self
        if None in (self.min, self.p50, self.p95, self.max):
            raise ValueError("n>0 requires min/p50/p95/max")
        assert self.min is not None and self.max is not None
        if self.min > self.max:
            raise ValueError("min must be <= max")
        return self


class PerformanceLevelCStageDispositionV1(StrictModel):
    """Per-stage applicability / outcome for one Level-C attempt."""

    contract: ExactNonBlankStr = PERFORMANCE_LEVEL_C_STAGE_DISPOSITION_V1
    status: LevelCStageDispositionStatusV1
    reason: ExactNonBlankStr | None = None

    @model_validator(mode="after")
    def _reason_rules(self) -> PerformanceLevelCStageDispositionV1:
        if self.status == "valid":
            if self.reason is not None:
                raise ValueError("valid disposition must not set reason")
        elif not self.reason:
            raise ValueError(f"{self.status} disposition requires reason")
        return self


class PerformanceGenerationTelemetryV1(StrictModel):
    """Provider-passthrough generation telemetry (no duplicated generation duration)."""

    contract: ExactNonBlankStr = PERFORMANCE_GENERATION_TELEMETRY_V1
    generator_invoked: bool
    ttft_availability: Literal["unevaluable"] = "unevaluable"
    ttft_seconds: float | None = None
    decode_availability: Literal["unevaluable"] = "unevaluable"
    decode_seconds: float | None = None
    output_token_count_availability: Literal["available", "unavailable"]
    output_token_count: int | None = None
    output_token_count_source: Literal[
        "provider_usage_completion_tokens",
        "unavailable",
    ]
    tokens_per_second_availability: Literal["unevaluable"] = "unevaluable"
    tokens_per_second: float | None = None

    @model_validator(mode="after")
    def _telemetry_rules(self) -> PerformanceGenerationTelemetryV1:
        if self.ttft_availability == "unevaluable" and self.ttft_seconds is not None:
            raise ValueError("unevaluable TTFT requires ttft_seconds=None")
        if self.decode_availability == "unevaluable" and self.decode_seconds is not None:
            raise ValueError("unevaluable decode requires decode_seconds=None")
        if (
            self.tokens_per_second_availability == "unevaluable"
            and self.tokens_per_second is not None
        ):
            raise ValueError("unevaluable tokens/sec requires tokens_per_second=None")
        if self.output_token_count_availability == "available":
            if self.output_token_count is None:
                raise ValueError("available output tokens require output_token_count")
            if isinstance(self.output_token_count, bool):
                raise ValueError("output_token_count must not be bool")
            if self.output_token_count < 0:
                raise ValueError("output_token_count must be >= 0")
            if self.output_token_count_source != "provider_usage_completion_tokens":
                raise ValueError(
                    "available tokens require source=provider_usage_completion_tokens"
                )
        else:
            if self.output_token_count is not None:
                raise ValueError("unavailable tokens require output_token_count=None")
            if self.output_token_count_source != "unavailable":
                raise ValueError("unavailable tokens require source=unavailable")
        return self


class PerformanceResourceObservationV1(StrictModel):
    """One RAM/VRAM sample. Missing telemetry is unavailable/unevaluable — never 0."""

    contract: ExactNonBlankStr = PERFORMANCE_RESOURCE_OBSERVATION_V1
    stage_id: ExactNonBlankStr
    ram_availability: TelemetryAvailabilityV1
    ram_rss_bytes_before: int | None = Field(default=None, ge=0)
    ram_rss_bytes_peak: int | None = Field(default=None, ge=0)
    vram_availability: TelemetryAvailabilityV1
    vram_used_bytes_before: int | None = Field(default=None, ge=0)
    vram_used_bytes_peak: int | None = Field(default=None, ge=0)
    device_id: ExactNonBlankStr | None = None
    note: ExactNonBlankStr | None = None
    # Warm-up samples may be retained for provenance but are excluded from
    # authoritative measured RAM summaries.
    is_warmup: bool = False

    @model_validator(mode="after")
    def _no_inferred_zero(self) -> PerformanceResourceObservationV1:
        if self.ram_availability != "available" and (
            self.ram_rss_bytes_before is not None or self.ram_rss_bytes_peak is not None
        ):
            raise ValueError("RAM bytes require ram_availability=available")
        if self.vram_availability != "available" and (
            self.vram_used_bytes_before is not None
            or self.vram_used_bytes_peak is not None
        ):
            raise ValueError("VRAM bytes require vram_availability=available")
        return self


class PerformancePathSampleV1(StrictModel):
    """One retrieval-path latency sample (not a locked semantic stage_id)."""

    path: ExactNonBlankStr
    duration_seconds: float = Field(gt=0)
    is_warmup: bool = False
    observation_status: ObservationStatusV1 = "valid"


class PerformanceBenchmarkObservationV1(StrictModel):
    """One raw timing observation (authoritative)."""

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_OBSERVATION_V1
    observation_status: ObservationStatusV1
    stage_id: ExactNonBlankStr
    duration_seconds: float | None = Field(default=None, ge=0.0)
    is_warmup: bool = False
    exclusion_reason: ExactNonBlankStr | None = None
    failure_reason: ExactNonBlankStr | None = None
    resource: PerformanceResourceObservationV1 | None = None

    @model_validator(mode="after")
    def _status_fields(self) -> PerformanceBenchmarkObservationV1:
        if self.observation_status == "valid":
            if self.duration_seconds is None:
                raise ValueError("valid observation requires duration_seconds")
            if self.exclusion_reason is not None:
                raise ValueError("valid observation must not set exclusion_reason")
        if (
            self.observation_status == "excluded_instrumentation_error"
            and not self.exclusion_reason
        ):
            raise ValueError("excluded_instrumentation_error requires exclusion_reason")
        if self.observation_status == "failed" and not self.failure_reason:
            raise ValueError("failed observation requires failure_reason")
        return self


class PerformanceLevelCAttemptV1(StrictModel):
    """One warm-up or measured Level-C query invocation (structural provenance)."""

    contract: ExactNonBlankStr = PERFORMANCE_LEVEL_C_ATTEMPT_V1
    attempt_index: int = Field(ge=0)
    is_warmup: bool
    subject_identity: ExactNonBlankStr
    terminal_status: LevelCTerminalStatusV1
    abstention_reason: Literal["empty_context", "model_abstain"] | None = None
    generation_failure_reason: ExactNonBlankStr | None = None
    generator_invoked: bool
    stage_dispositions: dict[str, PerformanceLevelCStageDispositionV1]
    context_assembly_observation: PerformanceBenchmarkObservationV1 | None = None
    generation_observation: PerformanceBenchmarkObservationV1 | None = None
    citation_validation_observation: PerformanceBenchmarkObservationV1 | None = None
    end_to_end_observation: PerformanceBenchmarkObservationV1 | None = None
    generation_telemetry: PerformanceGenerationTelemetryV1 | None = None

    @model_validator(mode="after")
    def _attempt_invariants(self) -> PerformanceLevelCAttemptV1:
        expected = set(LEVEL_C_STAGE_IDS_V1)
        keys = set(self.stage_dispositions.keys())
        if keys != expected:
            raise ValueError(
                "stage_dispositions must contain exactly "
                f"{list(LEVEL_C_STAGE_IDS_V1)}; got {sorted(keys)}"
            )
        obs_by_stage = {
            "context_assembly": self.context_assembly_observation,
            "generation": self.generation_observation,
            "citation_validation": self.citation_validation_observation,
            "end_to_end": self.end_to_end_observation,
        }
        for stage_id, disposition in self.stage_dispositions.items():
            observation = obs_by_stage[stage_id]
            status = disposition.status
            if status == "not_applicable":
                if observation is not None:
                    raise ValueError(
                        f"{stage_id}: not_applicable requires observation=None"
                    )
                continue
            if observation is None:
                raise ValueError(f"{stage_id}: {status} requires observation")
            if observation.stage_id != stage_id:
                raise ValueError(
                    f"{stage_id}: observation.stage_id mismatch "
                    f"({observation.stage_id!r})"
                )
            if observation.observation_status != status:
                raise ValueError(
                    f"{stage_id}: disposition {status!r} disagrees with "
                    f"observation_status {observation.observation_status!r}"
                )
            if status == "valid" and observation.duration_seconds is None:
                raise ValueError(f"{stage_id}: valid observation requires duration")
            if status == "failed" and not observation.failure_reason:
                raise ValueError(
                    f"{stage_id}: failed observation requires failure_reason"
                )
            if status == "excluded_instrumentation_error" and (
                not observation.exclusion_reason
            ):
                raise ValueError(
                    f"{stage_id}: excluded observation requires exclusion_reason"
                )
        return self


class PerformanceMachineProfileV1(StrictModel):
    """Identity-bearing machine/environment profile for a RUN (not a CASE)."""

    contract: ExactNonBlankStr = PERFORMANCE_MACHINE_PROFILE_V1
    os_name: ExactNonBlankStr
    os_version: ExactNonBlankStr
    architecture: ExactNonBlankStr
    cpu_model: ExactNonBlankStr
    physical_cores: int | None = Field(default=None, ge=1)
    logical_cores: int | None = Field(default=None, ge=1)
    system_ram_bytes: int | None = Field(default=None, ge=0)
    python_version: ExactNonBlankStr
    offline_rag_commit_sha: ExactNonBlankStr
    gpu_model: ExactNonBlankStr | None = None
    gpu_vram_bytes: int | None = Field(default=None, ge=0)
    gpu_driver_version: ExactNonBlankStr | None = None
    cuda_runtime_version: ExactNonBlankStr | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class PerformanceBenchmarkCaseV1(StrictModel):
    """Case definition / artifact body (observations excluded from identity)."""

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_CASE_V1
    case_id: ExactNonBlankStr
    case_kind: ExactNonBlankStr
    benchmark_level: BenchmarkLevelV1
    stage_or_path: ExactNonBlankStr
    subject_identity: ExactNonBlankStr
    variant: ExactNonBlankStr
    cold_warm: ColdWarmV1
    case_status: CaseStatusV1 = "completed"
    warmup_count: int = Field(ge=0, default=0)
    warmup_observations: list[PerformanceBenchmarkObservationV1] = Field(
        default_factory=list
    )
    measured_observations: list[PerformanceBenchmarkObservationV1] = Field(
        default_factory=list
    )
    failures: list[ExactNonBlankStr] = Field(default_factory=list)
    resource_samples: list[PerformanceResourceObservationV1] = Field(
        default_factory=list
    )
    derived: DerivedLatencyStatsV1 | None = None
    case_identity_hash: ExactNonBlankStr | None = None
    # Quality-vs-cost evidence (excluded from perfcase_/perfsuite_/perfcfg_).
    ranked_chunk_ids: list[ExactNonBlankStr] | None = None
    quality: PerformanceCaseQualityV1 | None = None
    # Retrieval-path latency samples (not semantic stage_ids). Warm-up identity
    # is preserved; measured rollups must exclude is_warmup=True.
    path_samples: list[PerformancePathSampleV1] = Field(default_factory=list)
    # Legacy float-only hybrid durations (unused by corrected 14C harness).
    hybrid_path_durations_seconds: list[float] = Field(default_factory=list)
    # Level-C attempt traces (result evidence; excluded from perfcase_ identity).
    level_c_attempts: list[PerformanceLevelCAttemptV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _level_c_attempt_provenance(self) -> PerformanceBenchmarkCaseV1:
        if not self.level_c_attempts:
            return self
        seen: set[tuple[bool, int]] = set()
        for attempt in self.level_c_attempts:
            if attempt.subject_identity != self.subject_identity:
                raise ValueError(
                    "level_c_attempts subject_identity must match case "
                    f"subject_identity ({self.subject_identity!r}); "
                    f"got {attempt.subject_identity!r}"
                )
            key = (attempt.is_warmup, attempt.attempt_index)
            if key in seen:
                raise ValueError(
                    "duplicate Level-C attempt key "
                    f"(is_warmup={attempt.is_warmup}, "
                    f"attempt_index={attempt.attempt_index})"
                )
            seen.add(key)
        return self


class PerformanceBenchmarkSuiteV1(StrictModel):
    """Suite definition — WHAT is measured (excludes machine/SHA/results)."""

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_SUITE_V1
    benchmark_level: BenchmarkLevelV1
    population_identity: ExactNonBlankStr
    variants: list[ExactNonBlankStr] = Field(min_length=1)
    case_ids: list[ExactNonBlankStr] = Field(min_length=1)
    measurement_protocol_version: ExactNonBlankStr = MEASUREMENT_PROTOCOL_VERSION_V1
    timing_boundary_version: ExactNonBlankStr = TIMING_BOUNDARY_VERSION_V1
    statistics_semantics_version: ExactNonBlankStr = STATISTICS_SEMANTICS_VERSION_V1
    suite_identity_hash: ExactNonBlankStr | None = None

    @field_validator("case_ids", "variants")
    @classmethod
    def _no_dupes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate membership ids are forbidden")
        return value


class PerformanceBenchmarkRunManifestV1(StrictModel):
    """Concrete execution provenance (minimum normative fields)."""

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_RUN_MANIFEST_V1
    suite_id: ExactNonBlankStr
    executing_sha: ExactNonBlankStr
    machine_profile_id: ExactNonBlankStr
    machine_profile: PerformanceMachineProfileV1 | None = None
    config_id: ExactNonBlankStr
    corpus_id: ExactNonBlankStr
    model_ids: dict[str, ExactNonBlankStr] = Field(default_factory=dict)
    warmup_policy: ExactNonBlankStr
    repetition_counts: dict[str, int] = Field(default_factory=dict)
    start_timestamp: ExactNonBlankStr
    environment: dict[str, ExactNonBlankStr] = Field(default_factory=dict)
    runtime_versions: dict[str, ExactNonBlankStr] = Field(default_factory=dict)
    execution_mode: ExactNonBlankStr
    run_status: RunStatusV1 | None = None
    run_nonce: ExactNonBlankStr | None = None
    run_identity_hash: ExactNonBlankStr | None = None
    # Optional human-readable label; excluded from perfrun_ identity.
    run_label: ExactNonBlankStr | None = None

    @field_validator("repetition_counts")
    @classmethod
    def _nonneg_reps(cls, value: dict[str, int]) -> dict[str, int]:
        for key, count in value.items():
            if count < 0:
                raise ValueError(f"repetition_counts[{key}] must be >= 0")
        return value


class PreflightCheckV1(StrictModel):
    """One machine-readable preflight check outcome."""

    name: ExactNonBlankStr
    status: PreflightCheckStatusV1
    reason: ExactNonBlankStr | None = None


class PerformancePreflightRecordV1(StrictModel):
    """Structured fail-closed preflight provenance for a dry-run."""

    contract: ExactNonBlankStr = PERFORMANCE_PREFLIGHT_RECORD_V1
    preflight_status: PreflightStatusV1
    working_tree_state: WorkingTreeStateV1
    working_tree_detail: ExactNonBlankStr | None = None
    disk_capacity_sufficient: bool | None = None
    disk_free_bytes: int | None = Field(default=None, ge=0)
    telemetry_ram: TelemetryAvailabilityV1 | None = None
    telemetry_vram: TelemetryAvailabilityV1 | None = None
    checks: list[PreflightCheckV1] = Field(default_factory=list)
    failing_check: ExactNonBlankStr | None = None
    executing_sha: ExactNonBlankStr | None = None
    machine_profile_id: ExactNonBlankStr | None = None
    suite_id: ExactNonBlankStr | None = None


class PerformanceVariantStatsV1(StrictModel):
    """Per-variant rollup of derived latency statistics."""

    variant: ExactNonBlankStr
    stats: DerivedLatencyStatsV1


class PerformanceStageStatsV1(StrictModel):
    """Per-stage / path rollup of derived latency statistics."""

    stage_or_path: ExactNonBlankStr
    stats: DerivedLatencyStatsV1


class PerformanceCaseQualityV1(StrictModel):
    """Accepted Slice-9 IR metrics for one case (Gold semantics reused)."""

    quality_eligible: bool
    requested_depth: int = Field(ge=1)
    returned_count: int = Field(ge=0)
    recall_at_1: float | None = None
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    precision_at_1: float | None = None
    precision_at_5: float | None = None
    precision_at_10: float | None = None
    hit_rate_at_1: float | None = None
    hit_rate_at_5: float | None = None
    hit_rate_at_10: float | None = None
    mrr: float | None = None
    ndcg_at_1: float | None = None
    ndcg_at_5: float | None = None
    ndcg_at_10: float | None = None


class PerformanceVariantQualityV1(StrictModel):
    """Macro-averaged IR metrics for one variant over eligible cases."""

    variant: ExactNonBlankStr
    eligible_case_count: int = Field(ge=0)
    recall_at_1: float | None = None
    recall_at_5: float | None = None
    recall_at_10: float | None = None
    precision_at_1: float | None = None
    precision_at_5: float | None = None
    precision_at_10: float | None = None
    hit_rate_at_1: float | None = None
    hit_rate_at_5: float | None = None
    hit_rate_at_10: float | None = None
    mrr: float | None = None
    ndcg_at_1: float | None = None
    ndcg_at_5: float | None = None
    ndcg_at_10: float | None = None


class PerformanceVariantResourceV1(StrictModel):
    """Deterministic RAM summary for one variant (VRAM reported separately)."""

    variant: ExactNonBlankStr
    ram_availability: TelemetryAvailabilityV1
    sample_count: int = Field(ge=0)
    ram_rss_bytes_min: int | None = Field(default=None, ge=0)
    ram_rss_bytes_p50: int | None = Field(default=None, ge=0)
    ram_rss_bytes_p95: int | None = Field(default=None, ge=0)
    ram_rss_bytes_max: int | None = Field(default=None, ge=0)


class PerformancePathLatencyV1(StrictModel):
    """Named retrieval-path latency rollup (hybrid / reranker / total)."""

    path: ExactNonBlankStr
    stats: DerivedLatencyStatsV1


class PerformanceRunAggregateV1(StrictModel):
    """Run-level aggregate.json body (deterministic derivation).

    Raw observations remain authoritative. Aggregates are recomputable.
    Diagnostic dry-runs and authoritative campaign runs share this contract;
    evidence-class flags must be mutually consistent.
    """

    contract: ExactNonBlankStr = PERFORMANCE_BENCHMARK_AGGREGATE_V1
    suite_id: ExactNonBlankStr
    run_id: ExactNonBlankStr
    run_status: RunStatusV1
    benchmark_level: BenchmarkLevelV1
    statistics_semantics_version: ExactNonBlankStr = STATISTICS_SEMANTICS_VERSION_V1
    case_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    by_variant: list[PerformanceVariantStatsV1] = Field(default_factory=list)
    by_stage_or_path: list[PerformanceStageStatsV1] = Field(default_factory=list)
    overall: DerivedLatencyStatsV1 | None = None
    path_latency: list[PerformancePathLatencyV1] = Field(default_factory=list)
    quality_by_variant: list[PerformanceVariantQualityV1] = Field(default_factory=list)
    resource_by_variant: list[PerformanceVariantResourceV1] = Field(
        default_factory=list
    )
    vram_availability: TelemetryAvailabilityV1 = "unavailable"
    diagnostic_only: bool = True
    authoritative: bool = False
    evidence_class: ExactNonBlankStr = "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE"

    @model_validator(mode="after")
    def _evidence_class_consistency(self) -> PerformanceRunAggregateV1:
        if self.authoritative and self.diagnostic_only:
            raise ValueError(
                "authoritative aggregates cannot also set diagnostic_only=True"
            )
        if self.authoritative:
            if self.evidence_class != "AUTHORITATIVE":
                raise ValueError(
                    "authoritative aggregates require evidence_class=AUTHORITATIVE"
                )
            return self
        if not self.diagnostic_only:
            raise ValueError(
                "non-authoritative aggregates must set diagnostic_only=True"
            )
        if self.evidence_class != "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE":
            raise ValueError(
                "diagnostic aggregates require "
                "evidence_class=DIAGNOSTIC_ONLY_NON_AUTHORITATIVE"
            )
        return self
