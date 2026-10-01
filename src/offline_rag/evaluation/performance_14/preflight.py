"""Fail-closed preflight for Slice 14B dry-run executions."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from offline_rag.evaluation.performance_14.contracts import (
    DESIGN_AUTHORITY_SHA_14,
    SUBSTRATE_PIN_14A,
    BenchmarkLevelV1,
    Performance14Error,
    PerformanceBenchmarkSuiteV1,
    PerformanceMachineProfileV1,
)
from offline_rag.evaluation.performance_14.fixtures import PerformanceSuitePlan
from offline_rag.evaluation.performance_14.identity import compute_suite_identity_hash
from offline_rag.evaluation.performance_14.machine import (
    capture_machine_profile_with_id,
)
from offline_rag.evaluation.performance_14.paths import (
    assert_outside_reserved_root,
    default_dryrun_parent,
)


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
    from offline_rag.evaluation.performance_14.fixtures import stable_case_id

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
    """For multi-variant suites, require an explicit treatment delta declaration."""
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


def assert_output_destination_writable(
    output_dir: Path,
    *,
    repo_root: Path,
) -> Path:
    resolved = assert_outside_reserved_root(output_dir, repo_root=repo_root)
    parent = resolved.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / f".perf14_write_probe_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise Performance14Error(
            f"output destination not writable: {parent}: {exc}"
        ) from exc
    return resolved


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


def run_preflight(
    plan: PerformanceSuitePlan,
    *,
    output_dir: Path,
    repo_root: Path | None = None,
) -> PreflightContext:
    """Fail-closed preflight before any measurement observations are taken."""
    root = resolve_repo_root(repo_root)
    executing_sha = resolve_executing_sha(root)
    assert_substrate_pin_reachable(root)
    suite_id = assert_suite_identity(plan.suite)
    assert_case_membership(plan)
    assert_protocol_counts(
        level=plan.suite.benchmark_level,
        warmup_count=plan.warmup_count,
        measured_repetitions=plan.measured_repetitions,
    )
    assert_paired_comparison_invariant(plan)
    assert_output_destination_writable(output_dir, repo_root=root)
    machine_profile, machine_profile_id = capture_machine_profile_with_id(
        offline_rag_commit_sha=executing_sha
    )
    return PreflightContext(
        repo_root=root,
        executing_sha=executing_sha,
        suite_id=suite_id,
        machine_profile_id=machine_profile_id,
        machine_profile=machine_profile,
        design_authority_sha=DESIGN_AUTHORITY_SHA_14,
        substrate_pin_14a=SUBSTRATE_PIN_14A,
        dryrun_parent=default_dryrun_parent(root),
    )
