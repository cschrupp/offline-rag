"""Fail-closed preflight for Slice 14B dry-run executions."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import (
    DESIGN_AUTHORITY_SHA_14,
    SUBSTRATE_PIN_14A,
    BenchmarkLevelV1,
    Performance14Error,
    PerformanceBenchmarkSuiteV1,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
    PreflightCheckV1,
    TelemetryAvailabilityV1,
    WorkingTreeStateV1,
)
from offline_rag.evaluation.performance_14.fixtures import (
    PerformanceSuitePlan,
    stable_case_id,
)
from offline_rag.evaluation.performance_14.identity import compute_suite_identity_hash
from offline_rag.evaluation.performance_14.machine import (
    capture_machine_profile_with_id,
)
from offline_rag.evaluation.performance_14.paths import default_dryrun_parent
from offline_rag.evaluation.performance_14.resources import (
    observe_ram_rss_bytes,
    observe_vram,
)

# Minimum free bytes under the dry-run root before measurement (256 MiB).
_MIN_DISK_FREE_BYTES = 256 * 1024 * 1024


def _run_git(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise Performance14Error(f"git invocation failed: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise Performance14Error(f"git {' '.join(args)} failed: {err}")
    return completed.stdout.strip()


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    toplevel = Path(_run_git(root, "rev-parse", "--show-toplevel")).resolve()
    if toplevel != root:
        raise Performance14Error(
            f"repo_root {root} is not the git toplevel {toplevel}"
        )
    if not (toplevel / "src" / "offline_rag").is_dir():
        raise Performance14Error(
            f"git toplevel {toplevel} is not an offline-rag project worktree"
        )
    return toplevel


def resolve_executing_sha(repo_root: Path) -> str:
    sha = _run_git(repo_root, "rev-parse", "--verify", "HEAD^{commit}")
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise Performance14Error(
            f"HEAD commit SHA must be 40 lowercase hex characters; got {sha!r}"
        )
    return sha


def capture_working_tree_state(repo_root: Path) -> tuple[WorkingTreeStateV1, str | None]:
    try:
        porcelain = _run_git(repo_root, "status", "--porcelain")
    except Performance14Error as exc:
        return "unavailable", str(exc)
    if not porcelain.strip():
        return "clean", None
    lines = porcelain.strip().splitlines()
    detail = f"{len(lines)} dirty path(s); first={lines[0][:120]}"
    return "dirty", detail


def assert_substrate_pin_reachable(repo_root: Path) -> None:
    """Require accepted 14A substrate SHA to be an ancestor of HEAD."""
    probe = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SUBSTRATE_PIN_14A, "HEAD"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise Performance14Error(
            f"accepted 14A substrate pin {SUBSTRATE_PIN_14A} is not an ancestor "
            "of HEAD; refuse dry-run without the locked measurement substrate"
        )


def assert_suite_identity(suite: PerformanceBenchmarkSuiteV1) -> str:
    recomputed = compute_suite_identity_hash(suite)
    if suite.suite_identity_hash is None:
        raise Performance14Error("suite_identity_hash must be set before preflight")
    if suite.suite_identity_hash != recomputed:
        raise Performance14Error(
            "suite identity mismatch: recorded "
            f"{suite.suite_identity_hash} != recomputed {recomputed}"
        )
    return recomputed


def assert_protocol_counts(
    *,
    level: BenchmarkLevelV1,
    warmup_count: int,
    measured_repetitions: int,
) -> None:
    if warmup_count < 0:
        raise Performance14Error("warmup_count must be >= 0")
    minimum = 5 if level == "C" else 10
    if measured_repetitions < minimum:
        raise Performance14Error(
            f"measured repetitions for level {level} must be >= {minimum}; "
            f"got {measured_repetitions}"
        )


def assert_case_membership(plan: PerformanceSuitePlan) -> None:
    expected = [stable_case_id(spec) for spec in plan.cases]
    if len(expected) != len(set(expected)):
        raise Performance14Error("duplicate case ids in suite plan")
    if sorted(expected) != sorted(plan.suite.case_ids):
        raise Performance14Error(
            "suite case_ids do not match planned case membership"
        )
    if len(expected) != len(plan.suite.case_ids):
        raise Performance14Error("expected case count does not match suite membership")
    for spec in plan.cases:
        if spec.benchmark_level != plan.suite.benchmark_level:
            raise Performance14Error(
                f"case {stable_case_id(spec)} level mismatch with suite"
            )
        if spec.cold_warm not in {"cold", "warm"}:
            raise Performance14Error("cold/warm classification missing")
        if spec.variant not in plan.suite.variants:
            raise Performance14Error(
                f"case variant {spec.variant!r} not declared in suite variants"
            )


def assert_paired_comparison_invariant(plan: PerformanceSuitePlan) -> None:
    """Prove complete subject×variant pairing (coverage + multiplicity)."""
    if len(plan.suite.variants) < 2:
        return
    if plan.baseline_variant is None or plan.treatment_variant is None:
        raise Performance14Error(
            "paired comparison requires baseline_variant and treatment_variant"
        )
    if plan.baseline_variant not in plan.suite.variants:
        raise Performance14Error("baseline_variant missing from suite variants")
    if plan.treatment_variant not in plan.suite.variants:
        raise Performance14Error("treatment_variant missing from suite variants")
    if plan.baseline_variant == plan.treatment_variant:
        raise Performance14Error("baseline and treatment variants must differ")
    if not plan.treatment_delta:
        raise Performance14Error(
            "paired comparison requires an explicit treatment_delta declaration"
        )

    by_subject_variant: dict[str, dict[str, list]] = defaultdict(
        lambda: defaultdict(list)
    )
    for spec in plan.cases:
        by_subject_variant[spec.subject_identity][spec.variant].append(spec)

    baseline = plan.baseline_variant
    treatment = plan.treatment_variant
    for subject, variant_map in sorted(by_subject_variant.items()):
        baseline_cases = variant_map.get(baseline, [])
        treatment_cases = variant_map.get(treatment, [])
        if not baseline_cases:
            raise Performance14Error(
                f"paired coverage missing baseline variant {baseline!r} "
                f"for subject {subject!r}"
            )
        if not treatment_cases:
            raise Performance14Error(
                f"paired coverage missing treatment variant {treatment!r} "
                f"for subject {subject!r}"
            )
        if len(baseline_cases) != len(treatment_cases):
            raise Performance14Error(
                f"paired coverage multiplicity mismatch for subject {subject!r}: "
                f"baseline={len(baseline_cases)} treatment={len(treatment_cases)}"
            )
        for left, right in zip(baseline_cases, treatment_cases, strict=True):
            if left.case_kind != right.case_kind:
                raise Performance14Error(
                    f"paired cases for {subject!r} differ in case_kind outside "
                    "declared treatment_delta"
                )
            if left.benchmark_level != right.benchmark_level:
                raise Performance14Error(
                    f"paired cases for {subject!r} differ in benchmark_level "
                    "outside declared treatment_delta"
                )
            if left.cold_warm != right.cold_warm:
                raise Performance14Error(
                    f"paired cases for {subject!r} differ in cold_warm outside "
                    "declared treatment_delta"
                )
            if (
                left.stage_or_path != right.stage_or_path
                and "stage_or_path" not in plan.treatment_delta
            ):
                raise Performance14Error(
                    f"paired cases for {subject!r} differ in stage_or_path "
                    "but treatment_delta does not declare stage_or_path"
                )


_MISSING = object()


def differing_config_paths(
    baseline: dict[str, object],
    treatment: dict[str, object],
) -> set[str]:
    """Return top-level config keys whose values differ between variants.

    Absence and explicit ``None`` are distinct (fail closed on missing-vs-null).
    """
    keys = set(baseline) | set(treatment)
    return {
        key
        for key in keys
        if baseline.get(key, _MISSING) != treatment.get(key, _MISSING)
    }


def assert_treatment_only_config_delta(plan: PerformanceSuitePlan) -> None:
    """Require actual per-variant config diffs to equal declared treatment_delta.

    Comparison is over top-level effective-configuration fields. Nested values
    under a declared treatment field may differ freely once that field is
    declared. Undeclared top-level differences fail closed.
    """
    if plan.baseline_variant is None or plan.treatment_variant is None:
        return
    if plan.baseline_variant not in plan.variant_configs:
        raise Performance14Error(
            f"variant_configs missing baseline variant {plan.baseline_variant!r}"
        )
    if plan.treatment_variant not in plan.variant_configs:
        raise Performance14Error(
            f"variant_configs missing treatment variant {plan.treatment_variant!r}"
        )
    declared = set(plan.treatment_delta)
    if not declared:
        raise Performance14Error(
            "paired comparison requires a non-empty treatment_delta"
        )
    actual = differing_config_paths(
        plan.variant_configs[plan.baseline_variant],
        plan.variant_configs[plan.treatment_variant],
    )
    undeclared = sorted(actual - declared)
    if undeclared:
        raise Performance14Error(
            "undeclared treatment configuration differences: "
            + ", ".join(undeclared)
        )
    missing = sorted(declared - actual)
    if missing:
        raise Performance14Error(
            "declared treatment_delta fields do not actually differ: "
            + ", ".join(missing)
        )


def assert_disk_capacity(dryrun_parent: Path) -> tuple[bool, int]:
    dryrun_parent.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(dryrun_parent)
    sufficient = usage.free >= _MIN_DISK_FREE_BYTES
    if not sufficient:
        raise Performance14Error(
            f"insufficient disk capacity under {dryrun_parent}: "
            f"free={usage.free} required>={_MIN_DISK_FREE_BYTES}"
        )
    return True, int(usage.free)


def assert_output_destination_writable(dryrun_parent: Path) -> Path:
    try:
        dryrun_parent.mkdir(parents=True, exist_ok=True)
        probe = dryrun_parent / f".perf14_write_probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise Performance14Error(
            f"output destination not writable: {dryrun_parent}: {exc}"
        ) from exc
    return dryrun_parent.resolve(strict=False)


def _fixture_input_checks(plan: PerformanceSuitePlan) -> list[PreflightCheckV1]:
    """Synthetic fixture runs explicitly mark corpus/index/model checks N/A."""
    if plan.population_kind != "performance_fixture":
        return [
            PreflightCheckV1(
                name="population_kind",
                status="failed",
                reason="14B dry-run currently authorizes performance_fixture only",
            )
        ]
    return [
        PreflightCheckV1(
            name="corpus_check",
            status="fixture_internal",
            reason="synthetic performance fixture population",
        ),
        PreflightCheckV1(
            name="index_check",
            status="not_applicable",
            reason="synthetic fixture — no corpus index required",
        ),
        PreflightCheckV1(
            name="embedding_model_check",
            status="not_applicable",
            reason="synthetic fixture — no embedding model required",
        ),
        PreflightCheckV1(
            name="reranker_check",
            status="not_applicable",
            reason="synthetic fixture — no reranker model required",
        ),
        PreflightCheckV1(
            name="generator_check",
            status="not_applicable",
            reason="synthetic fixture — no generator model required",
        ),
    ]


@dataclass
class PreflightAccumulator:
    """Accumulates known provenance across ordered preflight checks."""

    checks: list[PreflightCheckV1] = field(default_factory=list)
    executing_sha: str | None = None
    suite_id: str | None = None
    machine_profile_id: str | None = None
    machine_profile: PerformanceMachineProfileV1 | None = None
    working_tree_state: WorkingTreeStateV1 = "unavailable"
    working_tree_detail: str | None = None
    disk_capacity_sufficient: bool | None = None
    disk_free_bytes: int | None = None
    telemetry_ram: TelemetryAvailabilityV1 | None = None
    telemetry_vram: TelemetryAvailabilityV1 | None = None
    dryrun_parent: Path | None = None
    repo_root: Path | None = None
    failing_check: str | None = None
    error: str | None = None

    def add(
        self,
        name: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        self.checks.append(
            PreflightCheckV1(name=name, status=status, reason=reason)  # type: ignore[arg-type]
        )

    def fail(self, name: str, reason: str) -> None:
        self.failing_check = name
        self.error = reason
        self.add(name, "failed", reason)

    def run_check(self, name: str, fn):  # type: ignore[no-untyped-def]
        """Execute ``fn`` and record ``name`` as the exact failing_check on error."""
        try:
            return fn()
        except Performance14Error as exc:
            self.fail(name, str(exc))
            raise

    def to_record(self, *, status: str) -> PerformancePreflightRecordV1:
        return PerformancePreflightRecordV1(
            preflight_status=status,  # type: ignore[arg-type]
            working_tree_state=self.working_tree_state,
            working_tree_detail=self.working_tree_detail,
            disk_capacity_sufficient=self.disk_capacity_sufficient,
            disk_free_bytes=self.disk_free_bytes,
            telemetry_ram=self.telemetry_ram,
            telemetry_vram=self.telemetry_vram,
            checks=list(self.checks),
            failing_check=self.failing_check,
            executing_sha=self.executing_sha,
            machine_profile_id=self.machine_profile_id,
            suite_id=self.suite_id,
        )


@dataclass(frozen=True, slots=True)
class PreflightContext:
    repo_root: Path
    executing_sha: str
    suite_id: str
    machine_profile_id: str
    machine_profile: PerformanceMachineProfileV1
    design_authority_sha: str
    substrate_pin_14a: str
    dryrun_parent: Path
    record: PerformancePreflightRecordV1
    working_tree_state: WorkingTreeStateV1


def run_preflight(
    plan: PerformanceSuitePlan,
    *,
    repo_root: Path | None = None,
    dryrun_parent: Path | None = None,
) -> PreflightContext:
    """Fail-closed preflight before any measurement observations are taken.

    On failure, raises ``Performance14Error`` with ``.preflight_record`` and
    ``.preflight_partial`` attached so callers can persist known provenance.
    ``failing_check`` is the exact machine-readable check name.
    """
    acc = PreflightAccumulator()
    try:
        root = acc.run_check("repository_root", lambda: resolve_repo_root(repo_root))
        acc.repo_root = root
        acc.add("repository_root", "passed")

        executing_sha = acc.run_check(
            "executing_sha", lambda: resolve_executing_sha(root)
        )
        acc.executing_sha = executing_sha
        acc.add("executing_sha", "passed", executing_sha)

        working_state, working_detail = capture_working_tree_state(root)
        acc.working_tree_state = working_state
        acc.working_tree_detail = working_detail
        acc.add(
            "working_tree_state",
            "passed",
            working_detail or working_state,
        )

        acc.run_check("substrate_pin", lambda: assert_substrate_pin_reachable(root))
        acc.add("substrate_pin", "passed", SUBSTRATE_PIN_14A)

        suite_id = acc.run_check(
            "suite_identity", lambda: assert_suite_identity(plan.suite)
        )
        acc.suite_id = suite_id
        acc.add("suite_identity", "passed", suite_id)

        acc.run_check("case_membership", lambda: assert_case_membership(plan))
        acc.add("case_membership", "passed")

        acc.run_check(
            "protocol_counts",
            lambda: assert_protocol_counts(
                level=plan.suite.benchmark_level,
                warmup_count=plan.warmup_count,
                measured_repetitions=plan.measured_repetitions,
            ),
        )
        acc.add(
            "protocol_counts",
            "passed",
            f"warmup={plan.warmup_count}; measured={plan.measured_repetitions}",
        )

        acc.run_check(
            "paired_comparison_invariant",
            lambda: assert_paired_comparison_invariant(plan),
        )
        acc.add("paired_comparison_invariant", "passed")

        if len(plan.suite.variants) >= 2:
            acc.run_check(
                "treatment_config_delta",
                lambda: assert_treatment_only_config_delta(plan),
            )
            acc.add("treatment_config_delta", "passed")

        for check in _fixture_input_checks(plan):
            if check.status == "failed":
                acc.fail(
                    check.name,
                    check.reason or f"preflight check failed: {check.name}",
                )
                raise Performance14Error(
                    check.reason or f"preflight check failed: {check.name}"
                )
            acc.checks.append(check)

        def _prepare_output() -> Path:
            parent = (
                Path(dryrun_parent).expanduser().resolve(strict=False)
                if dryrun_parent is not None
                else default_dryrun_parent(root)
            )
            return assert_output_destination_writable(parent)

        parent = acc.run_check("output_writable", _prepare_output)
        acc.dryrun_parent = parent
        acc.add("output_writable", "passed", str(parent))

        disk_ok, free_bytes = acc.run_check(
            "disk_capacity", lambda: assert_disk_capacity(parent)
        )
        acc.disk_capacity_sufficient = disk_ok
        acc.disk_free_bytes = free_bytes
        acc.add("disk_capacity", "passed", f"free_bytes={free_bytes}")

        machine_profile, machine_profile_id = acc.run_check(
            "machine_profile",
            lambda: capture_machine_profile_with_id(
                offline_rag_commit_sha=executing_sha
            ),
        )
        acc.machine_profile = machine_profile
        acc.machine_profile_id = machine_profile_id
        acc.add("machine_profile", "passed", machine_profile_id)

        ram_av, _rss = observe_ram_rss_bytes()
        vram_av, _, _, _ = observe_vram()
        acc.telemetry_ram = ram_av
        acc.telemetry_vram = vram_av
        acc.add("telemetry_ram", "passed", ram_av)
        acc.add("telemetry_vram", "passed", vram_av)

        record = acc.to_record(status="passed")
        return PreflightContext(
            repo_root=root,
            executing_sha=executing_sha,
            suite_id=suite_id,
            machine_profile_id=machine_profile_id,
            machine_profile=machine_profile,
            design_authority_sha=DESIGN_AUTHORITY_SHA_14,
            substrate_pin_14a=SUBSTRATE_PIN_14A,
            dryrun_parent=parent,
            record=record,
            working_tree_state=working_state,
        )
    except Performance14Error as exc:
        if acc.failing_check is None:
            # Last-resort only for unexpected paths that bypassed run_check.
            acc.fail("preflight", str(exc))
        record = acc.to_record(status="failed")
        exc.preflight_record = record  # type: ignore[attr-defined]
        exc.preflight_partial = acc  # type: ignore[attr-defined]
        raise
