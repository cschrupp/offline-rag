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
    PerformanceCaseSpec,
    build_level_a_suite_plan,
    build_level_b_suite_plan,
    build_level_c_suite_plan,
)
from offline_rag.evaluation.performance_14.harness import _observe_once
from offline_rag.evaluation.performance_14.identity import compute_run_identity_hash
from offline_rag.evaluation.performance_14.paths import (
    allocate_dryrun_run_dir,
    assert_under_dryrun_root,
    validate_path_segment,
)
from offline_rag.evaluation.performance_14.preflight import (
    assert_paired_comparison_invariant,
    assert_protocol_counts,
)


def _dryrun_parent(tmp_path: Path) -> Path:
    parent = tmp_path / "eval" / "results" / "performance_14_dryrun"
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def _noop_stage(_spec: object) -> None:
    return None


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


def test_paired_invariant_requires_complete_subject_coverage() -> None:
    plan = build_level_b_suite_plan()
    # Drop all treatment cases for one subject.
    truncated = tuple(
        spec
        for spec in plan.cases
        if not (
            spec.subject_identity == "q_fixture_001"
            and spec.variant == plan.treatment_variant
        )
    )
    broken = replace(
        plan,
        cases=truncated,
        suite=plan.suite.model_copy(
            update={
                "case_ids": [
                    f"{c.benchmark_level.lower()}_{c.local_case_id}_{c.variant}_{c.cold_warm}"
                    for c in truncated
                ],
                "suite_identity_hash": None,
            }
        ),
    )
    with pytest.raises(Performance14Error, match="paired coverage missing"):
        assert_paired_comparison_invariant(broken)


def test_path_segment_rejects_traversal() -> None:
    with pytest.raises(Performance14Error, match="single path segment"):
        validate_path_segment("../evil", field_name="run_id")
    with pytest.raises(Performance14Error, match="single path segment"):
        validate_path_segment("a/b", field_name="suite_id")


def test_output_confined_to_dryrun_root(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    outside = tmp_path / "elsewhere" / "run"
    with pytest.raises(Performance14Error, match="not under dry-run root"):
        assert_under_dryrun_root(outside, dryrun_parent=dryrun)
    reserved = tmp_path / "eval" / "results" / "performance_14" / "x"
    with pytest.raises(Performance14Error, match="reserved"):
        assert_under_dryrun_root(reserved, repo_root=tmp_path, dryrun_parent=dryrun)


def test_allocate_requires_perfrun_identity(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    with pytest.raises(Performance14Error, match="perfrun_"):
        allocate_dryrun_run_dir(
            suite_id="perfsuite_abc",
            run_id="dryrun_not_canonical",
            dryrun_parent=dryrun,
        )


def test_immutable_run_dir_rejects_overwrite(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    run_id = "perfrun_" + ("a" * 64)
    target = allocate_dryrun_run_dir(
        suite_id="perfsuite_abc",
        run_id=run_id,
        dryrun_parent=dryrun,
    )
    target.mkdir(parents=True)
    with pytest.raises(Performance14Error, match="already exists"):
        allocate_dryrun_run_dir(
            suite_id="perfsuite_abc",
            run_id=run_id,
            dryrun_parent=dryrun,
        )


def test_level_b_dryrun_canonical_perfrun_path(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    result = run_performance_14b_dryrun(
        level="B",
        run_label="unit_level_b",
        repo_root=Path.cwd(),
        dryrun_parent=dryrun,
        stage_runner=_noop_stage,
    )
    assert result.run_id.startswith("perfrun_")
    assert result.run_id == result.manifest.run_identity_hash
    assert result.aggregate.run_id == result.run_id
    assert result.run_label == "unit_level_b"
    assert result.diagnostic_only is True
    assert result.authoritative is False
    assert result.manifest.run_status == "completed"
    assert result.preflight is not None
    assert result.preflight.preflight_status == "passed"
    assert result.preflight.working_tree_state in {"clean", "dirty"}
    assert result.preflight.disk_capacity_sufficient is True
    assert result.preflight.telemetry_ram in {"available", "unavailable", "unevaluable"}
    check_names = {c.name for c in result.preflight.checks}
    assert "corpus_check" in check_names
    assert "index_check" in check_names

    assert compute_run_identity_hash(result.manifest) == result.manifest.run_identity_hash
    assert result.output_dir.name == result.run_id
    assert result.output_dir.parent.name == result.suite_id
    assert dryrun in result.output_dir.parents or result.output_dir.parent.parent == dryrun

    assert (result.output_dir / "run_manifest.json").is_file()
    assert (result.output_dir / "aggregate.json").is_file()
    assert (result.output_dir / "preflight.json").is_file()
    assert (result.output_dir / "report.md").is_file()
    assert len(list((result.output_dir / "cases").glob("*.json"))) == 4

    subjects_variants = [
        (case.subject_identity, case.variant) for case in result.cases
    ]
    assert subjects_variants == [
        ("q_fixture_001", "hybrid"),
        ("q_fixture_001", "hybrid_rerank"),
        ("q_fixture_002", "hybrid"),
        ("q_fixture_002", "hybrid_rerank"),
    ]

    aggregate = json.loads(
        (result.output_dir / "aggregate.json").read_text(encoding="utf-8")
    )
    assert aggregate["run_id"] == result.run_id
    assert aggregate["overall"]["n"] == aggregate["overall"]["valid_count"]
    report = (result.output_dir / "report.md").read_text(encoding="utf-8")
    assert "DIAGNOSTIC ONLY" in report
    assert result.run_id in report


def test_level_a_and_c_dryrun_complete(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    for level in ("A", "C"):
        result = run_performance_14b_dryrun(
            level=level,  # type: ignore[arg-type]
            run_label=f"unit_level_{level.lower()}",
            repo_root=Path.cwd(),
            dryrun_parent=dryrun,
            stage_runner=_noop_stage,
        )
        assert result.run_status == "completed"
        assert result.run_id.startswith("perfrun_")
        assert result.output_dir.name == result.run_id
        assert dryrun.resolve() in result.output_dir.resolve().parents


def test_failure_and_exclusion_accounting(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    plan = build_level_a_suite_plan(warmup_count=1, measured_repetitions=10)
    result = run_performance_14b_dryrun(
        level="A",
        run_label="unit_fail_excl",
        repo_root=Path.cwd(),
        dryrun_parent=dryrun,
        plan=plan,
        stage_runner=_noop_stage,
        failure_subjects=["doc_fixture_001"],
        exclusion_subjects=["doc_fixture_002"],
    )
    assert result.run_status == "completed"
    assert result.aggregate.overall is not None
    assert result.aggregate.overall.failure_count >= 1
    assert result.aggregate.overall.instrumentation_exclusion_count >= 1


def test_preflight_rejects_insufficient_reps(tmp_path: Path) -> None:
    dryrun = _dryrun_parent(tmp_path)
    plan = build_level_c_suite_plan(warmup_count=0, measured_repetitions=3)
    result = run_performance_14b_dryrun(
        level="C",
        run_label="unit_preflight_fail",
        repo_root=Path.cwd(),
        dryrun_parent=dryrun,
        plan=plan,
        stage_runner=_noop_stage,
    )
    assert result.run_status == "failed_preflight"
    assert result.run_id.startswith("perfrun_")
    assert result.error is not None
    assert ">= 5" in result.error
    assert result.preflight is not None
    assert result.preflight.preflight_status == "failed"
    # Known facts preserved when resolved before the failing check.
    assert result.manifest.executing_sha != "unknown"
    assert result.manifest.executing_sha != "unresolved"
    assert (result.output_dir / "preflight.json").is_file()
    assert (result.output_dir / "run_manifest.json").is_file()


def test_resource_sample_taken_before_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def fake_capture(stage_id: str, **_kwargs: object) -> object:
        events.append(f"resource:{stage_id}")
        from offline_rag.evaluation.performance_14.contracts import (
            PerformanceResourceObservationV1,
        )

        return PerformanceResourceObservationV1(
            stage_id=stage_id,
            ram_availability="unavailable",
            vram_availability="unavailable",
        )

    def fake_measure(stage_id: str):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager

        @contextmanager
        def _cm():  # type: ignore[no-untyped-def]
            events.append(f"measure:{stage_id}")
            events.append("timer_start")
            result: dict[str, float] = {}
            try:
                yield result
            finally:
                result["duration_seconds"] = 0.001
                events.append("timer_stop")

        return _cm()

    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.harness.capture_resource_observation",
        fake_capture,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.harness.measure_stage",
        fake_measure,
    )

    spec = PerformanceCaseSpec(
        case_kind="micro_stage",
        benchmark_level="A",
        stage_or_path="parse",
        subject_identity="doc_fixture_001",
        variant="stage_isolated",
        cold_warm="warm",
        local_case_id="parse_doc_fixture_001",
    )

    def stage(spec: PerformanceCaseSpec) -> None:
        events.append(f"stage:{spec.stage_or_path}")

    obs = _observe_once(
        spec,
        is_warmup=False,
        stage_runner=stage,
        force_failure=False,
        force_exclusion=False,
    )
    assert obs.observation_status == "valid"
    assert events.index("resource:parse") < events.index("timer_start")
    assert events.index("timer_start") < events.index("stage:parse")
    assert events.index("stage:parse") < events.index("timer_stop")


def test_artifact_write_refuses_overwrite(tmp_path: Path) -> None:
    from offline_rag.evaluation.performance_14.artifacts import write_run_artifacts
    from offline_rag.evaluation.performance_14.contracts import (
        PerformanceBenchmarkRunManifestV1,
        PerformanceRunAggregateV1,
    )
    from offline_rag.evaluation.performance_14.statistics import derive_latency_stats

    out = tmp_path / "run"
    out.mkdir()
    (out / "cases").mkdir()
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id="perfsuite_x",
        executing_sha="a" * 40,
        machine_profile_id="perfhost_x",
        config_id="perfcfg_x",
        corpus_id="corpus_x",
        warmup_policy="warmup=0",
        repetition_counts={"measured": 10},
        start_timestamp="2026-01-01T00:00:00Z",
        execution_mode="dry_run_diagnostic",
        run_nonce="n1",
        run_identity_hash="perfrun_" + ("b" * 64),
        run_status="completed",
    )
    aggregate = PerformanceRunAggregateV1(
        suite_id="perfsuite_x",
        run_id=manifest.run_identity_hash or "perfrun_x",
        run_status="completed",
        benchmark_level="A",
        overall=derive_latency_stats([]),
    )
    with pytest.raises(Performance14Error, match="existing cases directory"):
        write_run_artifacts(
            out,
            manifest=manifest,
            aggregate=aggregate,
            cases=[],
            report_markdown="# x\n",
        )
