"""Slice 14B unit tests — runners, preflight, scheduling, artifacts, dry-run."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from offline_rag.evaluation.performance_14 import (
    SUBSTRATE_PIN_14A,
    Performance14Error,
    paired_alternating_schedule,
    run_performance_14b_dryrun,
)
from offline_rag.evaluation.performance_14.fixtures import (
    build_level_a_suite_plan,
    build_level_b_suite_plan,
    build_level_c_suite_plan,
)
from offline_rag.evaluation.performance_14.identity import compute_run_identity_hash
from offline_rag.evaluation.performance_14.paths import (
    allocate_dryrun_run_dir,
    assert_outside_reserved_root,
)
from offline_rag.evaluation.performance_14.preflight import (
    assert_paired_comparison_invariant,
    assert_protocol_counts,
)


def test_substrate_pin_constant() -> None:
    assert SUBSTRATE_PIN_14A.startswith("c087b8c1")


def test_paired_alternating_schedule_order() -> None:
    ordered = paired_alternating_schedule(
        ["q1", "q2"],
        ["hybrid", "hybrid_rerank"],
    )
    assert ordered == [
        ("q1", "hybrid"),
        ("q1", "hybrid_rerank"),
        ("q2", "hybrid"),
        ("q2", "hybrid_rerank"),
    ]


def test_protocol_minima_fail_closed() -> None:
    with pytest.raises(Performance14Error, match=">= 10"):
        assert_protocol_counts(level="A", warmup_count=0, measured_repetitions=9)
    with pytest.raises(Performance14Error, match=">= 5"):
        assert_protocol_counts(level="C", warmup_count=0, measured_repetitions=4)
    assert_protocol_counts(level="B", warmup_count=1, measured_repetitions=10)
    assert_protocol_counts(level="C", warmup_count=1, measured_repetitions=5)


def test_paired_invariant_requires_treatment_delta() -> None:
    plan = build_level_b_suite_plan()
    assert_paired_comparison_invariant(plan)
    broken = replace(plan, treatment_delta=())
    with pytest.raises(Performance14Error, match="treatment_delta"):
        assert_paired_comparison_invariant(broken)


def test_refuse_reserved_authoritative_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    reserved = repo / "eval" / "results" / "performance_14" / "run1"
    with pytest.raises(Performance14Error, match="reserved"):
        assert_outside_reserved_root(reserved, repo_root=repo)


def test_immutable_run_dir_rejects_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "suite" / "run1"
    target.mkdir(parents=True)
    with pytest.raises(Performance14Error, match="already exists"):
        allocate_dryrun_run_dir(
            suite_id="suite",
            run_id="run1",
            output_dir=target,
            repo_root=tmp_path,
        )


def _noop_stage(_spec: object) -> None:
    return None


def test_level_b_dryrun_artifacts_and_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path.cwd()
    out = tmp_path / "level_b_run"
    result = run_performance_14b_dryrun(
        level="B",
        run_id="unit_level_b",
        output_dir=out,
        repo_root=repo_root,
        stage_runner=_noop_stage,
    )
    assert result.diagnostic_only is True
    assert result.authoritative is False
    assert result.run_status == "completed"
    assert result.manifest.run_status == "completed"
    assert result.manifest.environment["evidence_class"] == (
        "DIAGNOSTIC_ONLY_NON_AUTHORITATIVE"
    )
    assert result.aggregate.diagnostic_only is True
    assert result.aggregate.authoritative is False
    # Terminalization must not change perfrun_ identity.
    assert compute_run_identity_hash(result.manifest) == result.manifest.run_identity_hash

    assert (out / "run_manifest.json").is_file()
    assert (out / "aggregate.json").is_file()
    assert (out / "report.md").is_file()
    case_files = sorted((out / "cases").glob("*.json"))
    assert len(case_files) == len(result.cases) == 4

    # Paired order: subject then variant alternation.
    subjects_variants = [
        (case.subject_identity, case.variant) for case in result.cases
    ]
    assert subjects_variants == [
        ("q_fixture_001", "hybrid"),
        ("q_fixture_001", "hybrid_rerank"),
        ("q_fixture_002", "hybrid"),
        ("q_fixture_002", "hybrid_rerank"),
    ]

    aggregate = json.loads((out / "aggregate.json").read_text(encoding="utf-8"))
    assert aggregate["overall"]["n"] == aggregate["overall"]["valid_count"]
    assert aggregate["overall"]["attempted_count"] == (
        aggregate["overall"]["valid_count"]
        + aggregate["overall"]["failure_count"]
        + aggregate["overall"]["instrumentation_exclusion_count"]
    )
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "DIAGNOSTIC ONLY" in report
    assert "NON-AUTHORITATIVE" in report


def test_level_a_and_c_dryrun_complete(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    for level, run_id in (("A", "unit_level_a"), ("C", "unit_level_c")):
        result = run_performance_14b_dryrun(
            level=level,  # type: ignore[arg-type]
            run_id=run_id,
            output_dir=tmp_path / run_id,
            repo_root=repo_root,
            stage_runner=_noop_stage,
        )
        assert result.run_status == "completed"
        assert result.level == level
        assert result.cases
        assert all(case.derived is not None for case in result.cases)


def test_failure_and_exclusion_accounting(tmp_path: Path) -> None:
    plan = build_level_a_suite_plan(warmup_count=1, measured_repetitions=10)
    # Pick one subject for injected failure and another for exclusion.
    result = run_performance_14b_dryrun(
        level="A",
        run_id="unit_fail_excl",
        output_dir=tmp_path / "fail_excl",
        repo_root=Path.cwd(),
        plan=plan,
        stage_runner=_noop_stage,
        failure_subjects=["doc_fixture_001"],
        exclusion_subjects=["doc_fixture_002"],
    )
    assert result.run_status == "completed"
    assert result.aggregate.overall is not None
    assert result.aggregate.overall.failure_count >= 1
    assert result.aggregate.overall.instrumentation_exclusion_count >= 1
    assert result.aggregate.overall.attempted_count == (
        result.aggregate.overall.valid_count
        + result.aggregate.overall.failure_count
        + result.aggregate.overall.instrumentation_exclusion_count
    )


def test_preflight_rejects_insufficient_reps(tmp_path: Path) -> None:
    plan = build_level_c_suite_plan(warmup_count=0, measured_repetitions=3)
    result = run_performance_14b_dryrun(
        level="C",
        run_id="unit_preflight_fail",
        output_dir=tmp_path / "preflight_fail",
        repo_root=Path.cwd(),
        plan=plan,
        stage_runner=_noop_stage,
    )
    assert result.run_status == "failed_preflight"
    assert result.error is not None
    assert ">= 5" in result.error
    assert (tmp_path / "preflight_fail" / "run_manifest.json").is_file()
    assert (tmp_path / "preflight_fail" / "aggregate.json").is_file()
    assert (tmp_path / "preflight_fail" / "report.md").is_file()
