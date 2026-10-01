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
from offline_rag.evaluation.performance_14.paths import allocate_dryrun_run_dir
from offline_rag.evaluation.performance_14.preflight import (
    PreflightContext,
    run_preflight,
)
from offline_rag.evaluation.performance_14.report import render_report_markdown
from offline_rag.evaluation.performance_14.resources import capture_resource_observation
from offline_rag.evaluation.performance_14.scheduling import paired_alternating_schedule
from offline_rag.evaluation.performance_14.statistics import derive_latency_stats
from offline_rag.evaluation.performance_14.timing import timed_call, validate_stage_id

StageCallable = Callable[[PerformanceCaseSpec], None]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_stage_work(spec: PerformanceCaseSpec) -> None:
    """Deterministic synthetic load (no I/O / no model calls)."""
    digest = hashlib.sha256(
        f"{spec.subject_identity}:{spec.variant}:{spec.stage_or_path}".encode()
    ).digest()
    # Tiny CPU burn keyed by fixture identity — keeps dry-run fast and local.
    acc = 0
    for _ in range(200 + digest[0]):
        acc = (acc + digest[acc % len(digest)]) % 997
    if acc < 0:  # pragma: no cover — unreachable guard for side-effect retention
        raise RuntimeError("unreachable")


def _ordered_case_specs(plan: PerformanceSuitePlan) -> list[PerformanceCaseSpec]:
    """Order cases by paired/alternating subject×variant schedule.

    Multiple stage cases sharing the same (subject, variant) are preserved in
    their plan declaration order under each scheduled pair.
    """
    from collections import defaultdict

    buckets: dict[tuple[str, str], list[PerformanceCaseSpec]] = defaultdict(list)
    for spec in plan.cases:
        buckets[(spec.subject_identity, spec.variant)].append(spec)
    subjects: list[str] = []
    for spec in plan.cases:
        if spec.subject_identity not in subjects:
            subjects.append(spec.subject_identity)
    variants = list(plan.suite.variants)
    ordered: list[PerformanceCaseSpec] = []
    for subject, variant in paired_alternating_schedule(subjects, variants):
        ordered.extend(buckets.get((subject, variant), []))
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
    try:
        _value, sample = timed_call(stage_id, lambda: stage_runner(spec))
        resource = capture_resource_observation(stage_id)
        return PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id=stage_id,
            duration_seconds=sample.duration_seconds,
            is_warmup=is_warmup,
            resource=resource,
        )
    except Exception as exc:  # noqa: BLE001 — observation fail-closed
        return PerformanceBenchmarkObservationV1(
            observation_status="failed",
            stage_id=stage_id,
            is_warmup=is_warmup,
            failure_reason=f"{type(exc).__name__}: {exc}",
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
        # Inject failure/exclusion only on the first measured attempt so
        # accounting remains visible without collapsing the whole case sample.
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
) -> PerformanceBenchmarkRunManifestV1:
    assert isinstance(preflight.machine_profile, PerformanceMachineProfileV1)
    config_id = compute_config_identity_hash(_config_payload(plan))
    corpus_id = f"corpus_fixture_{plan.suite.population_identity}"
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
        environment={
            "os": platform.system() or "unknown",
            "dry_run": "true",
            "evidence_class": "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE",
            "substrate_pin_14a": SUBSTRATE_PIN_14A,
        },
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode=execution_mode,
        run_status=None,
        run_nonce=run_nonce,
    )
    run_hash = compute_run_identity_hash(manifest)
    return manifest.model_copy(update={"run_identity_hash": run_hash})


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
    error: str | None = None
    diagnostic_only: bool = True
    authoritative: bool = False


def run_performance_14b_dryrun(
    *,
    level: BenchmarkLevelV1,
    run_id: str | None = None,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    plan: PerformanceSuitePlan | None = None,
    stage_runner: StageCallable | None = None,
    failure_subjects: Sequence[str] | None = None,
    exclusion_subjects: Sequence[str] | None = None,
    skip_mkdir: bool = False,
) -> PerformanceDryRunResult:
    """Execute a Level A/B/C diagnostic dry-run and persist artifacts.

    Never writes under ``eval/results/performance_14/``.
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

    rid = run_id or f"dryrun_{uuid.uuid4().hex[:12]}"
    runner = stage_runner or _default_stage_work
    fail_set = set(failure_subjects or ())
    excl_set = set(exclusion_subjects or ())

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

    out = allocate_dryrun_run_dir(
        suite_id=suite_id,
        run_id=rid,
        output_dir=output_dir,
        repo_root=repo_root,
    )
    if not skip_mkdir:
        out.mkdir(parents=True, exist_ok=False)

    try:
        preflight = run_preflight(suite_plan, output_dir=out, repo_root=repo_root)
    except Performance14Error as exc:
        empty = build_run_aggregate(
            suite_id=suite_id,
            run_id=rid,
            run_status="failed_preflight",
            benchmark_level=level,
            cases=[],
        )
        machine_profile_id = "perfhost_preflight_unavailable"
        config_id = compute_config_identity_hash(
            {
                "preflight": "failed",
                "level": level,
                "substrate_pin_14a": SUBSTRATE_PIN_14A,
            }
        )
        manifest = PerformanceBenchmarkRunManifestV1(
            suite_id=suite_id,
            executing_sha="unknown",
            machine_profile_id=machine_profile_id,
            config_id=config_id,
            corpus_id="corpus_preflight_failed",
            model_ids={},
            warmup_policy="unvalidated",
            repetition_counts={},
            start_timestamp=_utc_now_iso(),
            environment={
                "dry_run": "true",
                "evidence_class": "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE",
            },
            runtime_versions={"python": sys.version.split()[0]},
            execution_mode="dry_run_diagnostic",
            run_status="failed_preflight",
            run_nonce=uuid.uuid4().hex,
        )
        manifest = manifest.model_copy(
            update={"run_identity_hash": compute_run_identity_hash(manifest)}
        )
        report = render_report_markdown(
            run_id=rid,
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
        )
        return PerformanceDryRunResult(
            run_id=rid,
            output_dir=out,
            run_status="failed_preflight",
            level=level,
            suite_id=suite_id,
            manifest=manifest,
            aggregate=empty,
            cases=[],
            error=str(exc),
        )

    run_nonce = uuid.uuid4().hex
    manifest = _build_manifest(
        plan=suite_plan,
        preflight=preflight,
        run_nonce=run_nonce,
        execution_mode="dry_run_diagnostic",
    )
    # Identity is sealed pre-measurement (run_status still None).
    sealed_identity = manifest.run_identity_hash
    assert sealed_identity is not None

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
    # Provenance check: terminalization must not flip perfrun_ identity.
    if compute_run_identity_hash(terminal_manifest) != sealed_identity:
        raise Performance14Error(
            "run_identity_hash changed after terminalization; "
            "run_status must remain excluded from perfrun_ identity"
        )
    manifest = terminal_manifest

    aggregate = build_run_aggregate(
        suite_id=suite_id,
        run_id=rid,
        run_status=run_status,
        benchmark_level=level,
        cases=cases,
    )
    report = render_report_markdown(
        run_id=rid,
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
    )
    return PerformanceDryRunResult(
        run_id=rid,
        output_dir=out,
        run_status=run_status,
        level=level,
        suite_id=suite_id,
        manifest=manifest,
        aggregate=aggregate,
        cases=cases,
        error=error,
    )


def run_all_level_dryruns(
    *,
    repo_root: Path | None = None,
    stage_runner: StageCallable | None = None,
) -> Mapping[BenchmarkLevelV1, PerformanceDryRunResult]:
    """Convenience: execute Level A, B, and C diagnostic dry-runs."""
    return {
        level: run_performance_14b_dryrun(
            level=level,
            repo_root=repo_root,
            stage_runner=stage_runner,
        )
        for level in ("A", "B", "C")
    }
