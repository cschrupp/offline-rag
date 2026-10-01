"""Slice 14B Level A/B/C benchmark runners (dry-run / diagnostic only).

Uses accepted Slice 14A substrate
``c087b8c1f038bd049809db2bf7e761ee0db93b58``.

Outputs are DIAGNOSTIC ONLY / NON-AUTHORITATIVE. Frozen 14C campaigns and
authoritative hybrid-vs-reranker evidence production remain NOT AUTHORIZED.
"""

from __future__ import annotations

import hashlib
import platform
import sys
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
from offline_rag.evaluation.performance_14.artifacts import write_run_artifacts
from offline_rag.evaluation.performance_14.contracts import (
    SUBSTRATE_PIN_14A,
    BenchmarkLevelV1,
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
    PerformanceRunAggregateV1,
    RunStatusV1,
)
from offline_rag.evaluation.performance_14.fixtures import (
    PerformanceCaseSpec,
    PerformanceSuitePlan,
    stable_case_id,
    suite_plan_for_level,
)
from offline_rag.evaluation.performance_14.identity import (
    compute_case_identity_hash,
    compute_config_identity_hash,
    compute_run_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.paths import (
    allocate_dryrun_run_dir,
    default_dryrun_parent,
)
from offline_rag.evaluation.performance_14.preflight import (
    PreflightAccumulator,
    PreflightContext,
    run_preflight,
)
from offline_rag.evaluation.performance_14.report import render_report_markdown
from offline_rag.evaluation.performance_14.resources import capture_resource_observation
from offline_rag.evaluation.performance_14.scheduling import paired_alternating_schedule
from offline_rag.evaluation.performance_14.statistics import derive_latency_stats
from offline_rag.evaluation.performance_14.timing import (
    measure_stage,
    validate_stage_id,
)

StageCallable = Callable[[PerformanceCaseSpec], None]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_stage_work(spec: PerformanceCaseSpec) -> None:
    """Deterministic synthetic load (no I/O / no model calls)."""
    digest = hashlib.sha256(
        f"{spec.subject_identity}:{spec.variant}:{spec.stage_or_path}".encode()
    ).digest()
    acc = 0
    for _ in range(200 + digest[0]):
        acc = (acc + digest[acc % len(digest)]) % 997
    if acc < 0:  # pragma: no cover
        raise RuntimeError("unreachable")


def _ordered_case_specs(plan: PerformanceSuitePlan) -> list[PerformanceCaseSpec]:
    """Order cases by paired/alternating subject×variant schedule.

    Proves every subject×variant cell is present before ordering.
    """
    buckets: dict[tuple[str, str], list[PerformanceCaseSpec]] = defaultdict(list)
    for spec in plan.cases:
        buckets[(spec.subject_identity, spec.variant)].append(spec)
    subjects: list[str] = []
    for spec in plan.cases:
        if spec.subject_identity not in subjects:
            subjects.append(spec.subject_identity)
    variants = list(plan.suite.variants)
    for subject in subjects:
        for variant in variants:
            if not buckets.get((subject, variant)):
                raise Performance14Error(
                    f"paired schedule missing subject×variant cell "
                    f"({subject!r}, {variant!r})"
                )
    ordered: list[PerformanceCaseSpec] = []
    for subject, variant in paired_alternating_schedule(subjects, variants):
        ordered.extend(buckets[(subject, variant)])
    if len(ordered) != len(plan.cases):
        raise Performance14Error(
            "paired schedule did not cover the full suite membership"
        )
    return ordered


def _observe_once(
    spec: PerformanceCaseSpec,
    *,
    is_warmup: bool,
    stage_runner: StageCallable,
    force_failure: bool,
    force_exclusion: bool,
) -> PerformanceBenchmarkObservationV1:
    stage_id = validate_stage_id(spec.stage_or_path)
    if force_exclusion:
        return PerformanceBenchmarkObservationV1(
            observation_status="excluded_instrumentation_error",
            stage_id=stage_id,
            is_warmup=is_warmup,
            exclusion_reason="injected_instrumentation_clock_skew",
        )
    if force_failure:
        return PerformanceBenchmarkObservationV1(
            observation_status="failed",
            stage_id=stage_id,
            is_warmup=is_warmup,
            failure_reason="injected_execution_failure",
        )

    # Pre-stage resource sample (peak remains None unless genuinely measured).
    # Resource telemetry failure must not invalidate an otherwise valid timing.
    resource = None
    try:
        resource = capture_resource_observation(stage_id)
    except Exception:  # noqa: BLE001 — telemetry must not fail the observation
        resource = None

    try:
        with measure_stage(stage_id) as timing:
            stage_runner(spec)
        return PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id=stage_id,
            duration_seconds=float(timing["duration_seconds"]),
            is_warmup=is_warmup,
            resource=resource,
        )
    except Exception as exc:  # noqa: BLE001 — observation fail-closed
        return PerformanceBenchmarkObservationV1(
            observation_status="failed",
            stage_id=stage_id,
            is_warmup=is_warmup,
            failure_reason=f"{type(exc).__name__}: {exc}",
            resource=resource,
        )


def _execute_case(
    spec: PerformanceCaseSpec,
    *,
    warmup_count: int,
    measured_repetitions: int,
    stage_runner: StageCallable,
    failure_subjects: set[str],
    exclusion_subjects: set[str],
) -> PerformanceBenchmarkCaseV1:
    case_id = stable_case_id(spec)
    warmups: list[PerformanceBenchmarkObservationV1] = []
    measured: list[PerformanceBenchmarkObservationV1] = []
    force_fail = spec.subject_identity in failure_subjects
    force_excl = spec.subject_identity in exclusion_subjects
    for _ in range(warmup_count):
        warmups.append(
            _observe_once(
                spec,
                is_warmup=True,
                stage_runner=stage_runner,
                force_failure=False,
                force_exclusion=False,
            )
        )
    for index in range(measured_repetitions):
        measured.append(
            _observe_once(
                spec,
                is_warmup=False,
                stage_runner=stage_runner,
                force_failure=force_fail and index == 0,
                force_exclusion=force_excl and index == 0 and not force_fail,
            )
        )
    failures = [
        obs.failure_reason
        for obs in measured
        if obs.observation_status == "failed" and obs.failure_reason
    ]
    resources = [
        obs.resource
        for obs in [*warmups, *measured]
        if obs.resource is not None
    ]
    case_status = "failed" if failures else "completed"
    case = PerformanceBenchmarkCaseV1(
        case_id=case_id,
        case_kind=spec.case_kind,
        benchmark_level=spec.benchmark_level,
        stage_or_path=spec.stage_or_path,
        subject_identity=spec.subject_identity,
        variant=spec.variant,
        cold_warm=spec.cold_warm,
        case_status=case_status,
        warmup_count=len(warmups),
        warmup_observations=warmups,
        measured_observations=measured,
        failures=failures,
        resource_samples=resources,
    )
    derived = derive_latency_stats(
        [*warmups, *measured],
        warmup_count=len(warmups),
    )
    case_hash = compute_case_identity_hash(case)
    return case.model_copy(update={"derived": derived, "case_identity_hash": case_hash})


def _config_payload(plan: PerformanceSuitePlan) -> dict[str, Any]:
    return {
        "benchmark_level": plan.suite.benchmark_level,
        "population_identity": plan.suite.population_identity,
        "variants": sorted(plan.suite.variants),
        "warmup_count": plan.warmup_count,
        "measured_repetitions": plan.measured_repetitions,
        "baseline_variant": plan.baseline_variant,
        "treatment_variant": plan.treatment_variant,
        "treatment_delta": list(plan.treatment_delta),
        # Effective per-variant configuration is identity-bearing for perfcfg_.
        "variant_configs": plan.variant_configs,
        "diagnostic_only": True,
        "authoritative": False,
        "substrate_pin_14a": SUBSTRATE_PIN_14A,
    }


def _build_manifest(
    *,
    plan: PerformanceSuitePlan,
    preflight: PreflightContext,
    run_nonce: str,
    execution_mode: str,
    run_label: str | None,
) -> PerformanceBenchmarkRunManifestV1:
    assert isinstance(preflight.machine_profile, PerformanceMachineProfileV1)
    config_id = compute_config_identity_hash(_config_payload(plan))
    corpus_id = f"corpus_fixture_{plan.suite.population_identity}"
    env = {
        "os": platform.system() or "unknown",
        "dry_run": "true",
        "evidence_class": "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE",
        "substrate_pin_14a": SUBSTRATE_PIN_14A,
        "preflight_status": preflight.record.preflight_status,
        "working_tree_state": preflight.working_tree_state,
    }
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=preflight.suite_id,
        executing_sha=preflight.executing_sha,
        machine_profile_id=preflight.machine_profile_id,
        machine_profile=preflight.machine_profile,
        config_id=config_id,
        corpus_id=corpus_id,
        model_ids={"fixture_runner": "synthetic_stage_work_v1"},
        warmup_policy=f"warmup={plan.warmup_count}",
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=env,
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode=execution_mode,
        run_status=None,
        run_nonce=run_nonce,
        run_label=run_label,
    )
    run_hash = compute_run_identity_hash(manifest)
    return manifest.model_copy(update={"run_identity_hash": run_hash})


def _failed_preflight_manifest(
    *,
    plan: PerformanceSuitePlan,
    suite_id: str,
    run_nonce: str,
    run_label: str | None,
    record: PerformancePreflightRecordV1,
    partial: PreflightAccumulator | None,
) -> PerformanceBenchmarkRunManifestV1:
    executing_sha = (
        (partial.executing_sha if partial is not None else None)
        or record.executing_sha
        or "unresolved"
    )
    machine_profile_id = (
        (partial.machine_profile_id if partial is not None else None)
        or record.machine_profile_id
        or "perfhost_unresolved"
    )
    machine_profile = partial.machine_profile if partial is not None else None
    config_id = compute_config_identity_hash(
        {
            "preflight": "failed",
            "level": plan.suite.benchmark_level,
            "substrate_pin_14a": SUBSTRATE_PIN_14A,
            "failing_check": record.failing_check or "unknown",
        }
    )
    env = {
        "dry_run": "true",
        "evidence_class": "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE",
        "preflight_status": "failed",
        "working_tree_state": record.working_tree_state,
        "substrate_pin_14a": SUBSTRATE_PIN_14A,
    }
    if record.failing_check:
        env["failing_check"] = record.failing_check
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=suite_id,
        executing_sha=executing_sha,
        machine_profile_id=machine_profile_id,
        machine_profile=machine_profile,
        config_id=config_id,
        corpus_id=f"corpus_fixture_{plan.suite.population_identity}",
        model_ids={"fixture_runner": "synthetic_stage_work_v1"},
        warmup_policy=f"warmup={plan.warmup_count}",
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=env,
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode="dry_run_diagnostic",
        run_status="failed_preflight",
        run_nonce=run_nonce,
        run_label=run_label,
    )
    return manifest.model_copy(
        update={"run_identity_hash": compute_run_identity_hash(manifest)}
    )


@dataclass
class PerformanceDryRunResult:
    """Result of a Slice 14B dry-run (diagnostic / non-authoritative)."""

    run_id: str
    output_dir: Path
    run_status: RunStatusV1
    level: BenchmarkLevelV1
    suite_id: str
    manifest: PerformanceBenchmarkRunManifestV1
    aggregate: PerformanceRunAggregateV1
    cases: list[PerformanceBenchmarkCaseV1] = field(default_factory=list)
    preflight: PerformancePreflightRecordV1 | None = None
    run_label: str | None = None
    error: str | None = None
    diagnostic_only: bool = True
    authoritative: bool = False


def run_performance_14b_dryrun(
    *,
    level: BenchmarkLevelV1,
    run_label: str | None = None,
    repo_root: Path | None = None,
    dryrun_parent: Path | None = None,
    plan: PerformanceSuitePlan | None = None,
    stage_runner: StageCallable | None = None,
    failure_subjects: Sequence[str] | None = None,
    exclusion_subjects: Sequence[str] | None = None,
) -> PerformanceDryRunResult:
    """Execute a Level A/B/C diagnostic dry-run and persist artifacts.

    ``run_id`` is always the sealed ``perfrun_<sha256>`` identity.
    Optional ``run_label`` is presentation-only and excluded from identity.
    Artifacts are confined under ``performance_14_dryrun/``.
    """
    suite_plan = plan if plan is not None else suite_plan_for_level(level)
    if suite_plan.suite.benchmark_level != level:
        raise Performance14Error(
            f"plan level {suite_plan.suite.benchmark_level!r} != requested {level!r}"
        )
    if not suite_plan.diagnostic_only or suite_plan.authoritative:
        raise Performance14Error(
            "14B dry-run requires diagnostic_only=True and authoritative=False"
        )

    runner = stage_runner or _default_stage_work
    fail_set = set(failure_subjects or ())
    excl_set = set(exclusion_subjects or ())
    run_nonce = uuid.uuid4().hex

    if suite_plan.suite.suite_identity_hash is None:
        suite_plan = replace(
            suite_plan,
            suite=suite_plan.suite.model_copy(
                update={
                    "suite_identity_hash": compute_suite_identity_hash(
                        suite_plan.suite
                    )
                }
            ),
        )
    suite_id = suite_plan.suite.suite_identity_hash
    assert suite_id is not None

    try:
        preflight = run_preflight(
            suite_plan,
            repo_root=repo_root,
            dryrun_parent=dryrun_parent,
        )
    except Performance14Error as exc:
        record = getattr(exc, "preflight_record", None)
        partial = getattr(exc, "preflight_partial", None)
        if record is None:
            record = PerformancePreflightRecordV1(
                preflight_status="failed",
                working_tree_state="unavailable",
                checks=[],
                failing_check="preflight",
            )
        manifest = _failed_preflight_manifest(
            plan=suite_plan,
            suite_id=suite_id,
            run_nonce=run_nonce,
            run_label=run_label,
            record=record,
            partial=partial,
        )
        perfrun_id = manifest.run_identity_hash
        assert perfrun_id is not None
        parent = (
            Path(dryrun_parent).resolve(strict=False)
            if dryrun_parent is not None
            else (
                partial.dryrun_parent
                if partial is not None and partial.dryrun_parent is not None
                else default_dryrun_parent(repo_root)
            )
        )
        out = allocate_dryrun_run_dir(
            suite_id=suite_id,
            run_id=perfrun_id,
            repo_root=repo_root,
            dryrun_parent=parent,
        )
        out.mkdir(parents=True, exist_ok=False)
        empty = build_run_aggregate(
            suite_id=suite_id,
            run_id=perfrun_id,
            run_status="failed_preflight",
            benchmark_level=level,
            cases=[],
        )
        report = render_report_markdown(
            run_id=perfrun_id,
            manifest=manifest,
            aggregate=empty,
            cases=[],
            error=str(exc),
        )
        write_run_artifacts(
            out,
            manifest=manifest,
            aggregate=empty,
            cases=[],
            report_markdown=report,
            preflight=record,
        )
        return PerformanceDryRunResult(
            run_id=perfrun_id,
            output_dir=out,
            run_status="failed_preflight",
            level=level,
            suite_id=suite_id,
            manifest=manifest,
            aggregate=empty,
            cases=[],
            preflight=record,
            run_label=run_label,
            error=str(exc),
        )

    manifest = _build_manifest(
        plan=suite_plan,
        preflight=preflight,
        run_nonce=run_nonce,
        execution_mode="dry_run_diagnostic",
        run_label=run_label,
    )
    sealed_identity = manifest.run_identity_hash
    assert sealed_identity is not None

    out = allocate_dryrun_run_dir(
        suite_id=suite_id,
        run_id=sealed_identity,
        repo_root=preflight.repo_root,
        dryrun_parent=preflight.dryrun_parent,
    )
    out.mkdir(parents=True, exist_ok=False)

    cases: list[PerformanceBenchmarkCaseV1] = []
    run_status: RunStatusV1 = "completed"
    error: str | None = None
    try:
        for spec in _ordered_case_specs(suite_plan):
            cases.append(
                _execute_case(
                    spec,
                    warmup_count=suite_plan.warmup_count,
                    measured_repetitions=suite_plan.measured_repetitions,
                    stage_runner=runner,
                    failure_subjects=fail_set,
                    exclusion_subjects=excl_set,
                )
            )
    except Exception as exc:  # noqa: BLE001 — campaign fail-closed
        run_status = "failed_during_execution"
        error = str(exc)

    terminal_manifest = manifest.model_copy(update={"run_status": run_status})
    if compute_run_identity_hash(terminal_manifest) != sealed_identity:
        raise Performance14Error(
            "run_identity_hash changed after terminalization; "
            "run_status/run_label must remain excluded from perfrun_ identity"
        )
    manifest = terminal_manifest

    aggregate = build_run_aggregate(
        suite_id=suite_id,
        run_id=sealed_identity,
        run_status=run_status,
        benchmark_level=level,
        cases=cases,
    )
    report = render_report_markdown(
        run_id=sealed_identity,
        manifest=manifest,
        aggregate=aggregate,
        cases=cases,
        error=error,
    )
    write_run_artifacts(
        out,
        manifest=manifest,
        aggregate=aggregate,
        cases=cases,
        report_markdown=report,
        preflight=preflight.record,
    )
    return PerformanceDryRunResult(
        run_id=sealed_identity,
        output_dir=out,
        run_status=run_status,
        level=level,
        suite_id=suite_id,
        manifest=manifest,
        aggregate=aggregate,
        cases=cases,
        preflight=preflight.record,
        run_label=run_label,
        error=error,
    )


def run_all_level_dryruns(
    *,
    repo_root: Path | None = None,
    dryrun_parent: Path | None = None,
    stage_runner: StageCallable | None = None,
) -> Mapping[BenchmarkLevelV1, PerformanceDryRunResult]:
    """Convenience: execute Level A, B, and C diagnostic dry-runs."""
    return {
        level: run_performance_14b_dryrun(
            level=level,
            repo_root=repo_root,
            dryrun_parent=dryrun_parent,
            stage_runner=stage_runner,
        )
        for level in ("A", "B", "C")
    }
