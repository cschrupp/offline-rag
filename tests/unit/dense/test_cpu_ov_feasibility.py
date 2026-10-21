"""Fail-closed ladder regressions for CPU-OV-01 harness AUTH."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.dense.cpu_ov_feasibility import (
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    FROZEN_BATCH_SIZE,
    PARITY_DOC_COUNT,
    PARITY_QUERY_COUNT,
    SCREEN_CHILD_COUNT,
    StageResult,
    assert_frozen_runtime_knobs,
    assert_transition_allowed,
    classify_screen_projection,
    parity_thresholds_pass,
    plan_next,
    project_full_minutes,
    refuse_hub_substitution,
)
from offline_rag.dense.cpu_ov_harness import (
    run_export_compat,
    run_full_confirm,
    run_parity,
    run_screen,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
)

REPO = Path(__file__).resolve().parents[3]


def test_execution_remains_locked() -> None:
    assert EXECUTION_AUTHORIZED is False


def test_projection_helpers() -> None:
    # ~0.0932 cps → ~231 min (C0-like)
    minutes = project_full_minutes(0.0932)
    assert 230.0 < minutes < 232.0
    assert classify_screen_projection(8.0) == "excellent"
    assert classify_screen_projection(20.0) == "viable"
    assert classify_screen_projection(30.0) == "too_slow"


def test_cannot_run_int8_before_fp16_screen() -> None:
    history: list[StageResult] = [
        StageResult(stage_id="export_compat", ok=True),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_screen_fp16"
    with pytest.raises(ValueError, match="unauthorized transition"):
        assert_transition_allowed(history, "run_screen_int8")


def test_excellent_fp16_skips_int8_and_requires_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),  # ~7.2 min
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_parity_fp16"
    assert plan.int8_eligible is False
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_screen_int8")
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_full_confirm")


def test_fp16_parity_fail_stops_without_int8() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=False),
    ]
    plan = plan_next(history)
    assert plan.terminal == "stop_parity_fail"
    assert plan.next_action == "none"
    assert plan.int8_eligible is False


def test_viable_fp16_opens_int8_only_after_parity_pass() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=1.2,
            projected_full_minutes=project_full_minutes(1.2),  # ~18 min
        ),
    ]
    assert plan_next(history).next_action == "run_parity_fp16"
    history.append(StageResult(stage_id="parity_fp16", ok=True, parity_ok=True))
    plan = plan_next(history)
    assert plan.next_action == "run_screen_int8"
    assert plan.int8_eligible is True


def test_too_slow_fp16_opens_int8_without_fp16_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=0.5,
            projected_full_minutes=project_full_minutes(0.5),  # ~43 min
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_screen_int8"
    assert plan.reason == "fp16_too_slow_open_int8_screen"


def test_cannot_full_run_before_eligibility() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    with pytest.raises(ValueError, match="full confirm not eligible"):
        run_full_confirm(history=history, selected_candidate="fp16")


def test_full_confirm_eligible_after_excellent_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.full_confirm_eligible is True
    assert plan.selected_candidate == "fp16"
    assert plan.next_action == "run_full_confirm"
    payload = run_full_confirm(history=history, selected_candidate="fp16")
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["full_confirm_eligible"] is True


def test_choose_faster_between_viable_fp16_and_int8() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=1.2,
            projected_full_minutes=project_full_minutes(1.2),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
        StageResult(
            stage_id="screen_int8",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),  # faster
        ),
        StageResult(stage_id="parity_int8", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.selected_candidate == "int8"
    assert plan.next_action == "run_full_confirm"


def test_frozen_knobs_and_hub_refusal() -> None:
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=True,
        device="cpu",
        backend="openvino",
    )
    with pytest.raises(ValueError, match="batch"):
        assert_frozen_runtime_knobs(
            batch_size=16, normalize=True, device="cpu", backend="openvino"
        )
    with pytest.raises(ValueError, match="Hub"):
        refuse_hub_substitution(local_model_dir_exists=True, allow_download=True)
    with pytest.raises(ValueError, match="missing"):
        refuse_hub_substitution(local_model_dir_exists=False, allow_download=False)


def test_parity_threshold_helper_fail_closed() -> None:
    good = {
        "median_document_vector_cosine": 0.9995,
        "min_document_vector_cosine": 0.996,
        "median_query_vector_cosine": 0.9995,
        "min_query_vector_cosine": 0.996,
        "top1_agreement": 16,
        "mean_top10_set_overlap": 0.99,
        "min_top10_set_overlap": 0.9,
    }
    assert parity_thresholds_pass(good) is True
    bad = dict(good)
    bad["top1_agreement"] = 14
    assert parity_thresholds_pass(bad) is False
    assert parity_thresholds_pass({}) is False


def test_deterministic_selection_sizes() -> None:
    ids = [f"chunk_{i:04d}" for i in range(EXPECTED_CHILD_COUNT)]
    screen = select_screen_chunk_ids(ids)
    assert len(screen) == SCREEN_CHILD_COUNT
    docs, queries = select_parity_populations(ids)
    assert len(docs) == PARITY_DOC_COUNT
    assert len(queries) == PARITY_QUERY_COUNT
    assert queries == docs[:PARITY_QUERY_COUNT]
    # Content-independent: sorting by sha256(chunk_id)
    assert screen == sorted(ids, key=sha256_text)[:SCREEN_CHILD_COUNT]


def test_locked_export_and_screen_refuse_without_running() -> None:
    history: list[StageResult] = []
    export = run_export_compat(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "fp16",
        repo_root=REPO,
    )
    assert export["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert export["executor_ready"] is True

    history = [StageResult(stage_id="export_compat", ok=True)]
    screen = run_screen(history=history, weight_format="fp16", repo_root=REPO)
    assert screen["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert screen["screen_child_count"] == SCREEN_CHILD_COUNT

    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    parity = run_parity(history=history, weight_format="fp16", repo_root=REPO)
    assert parity["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert parity["document_count"] == PARITY_DOC_COUNT
    assert parity["query_count"] == PARITY_QUERY_COUNT


def test_projection_never_stored_as_full_wall_in_screen_builder() -> None:
    from offline_rag.dense.cpu_ov_harness import build_screen_result

    result = build_screen_result(stage_id="screen_fp16", chunks_per_sec=2.0)
    assert result.projected_full_minutes is not None
    assert result.full_wall_minutes is None
