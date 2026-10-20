"""16K-D D2 campaign state machine + validity classification tests."""

from __future__ import annotations

import pytest

from offline_rag.dense.d2_campaign import (
    MAX_VALID_FULL_RUNS,
    CellResult,
    assert_transition_allowed,
    count_valid_full_runs,
    grades_against_gpu_gate,
    plan_next,
    reject_vram_only_g2_open,
)
from offline_rag.dense.precision import (
    classify_treatment_failure,
    is_cuda_resource_exhaustion,
    resolve_embedding_precision,
)
from offline_rag.dense.embedder import EmbedderError


def R(
    cell: str,
    validity: str = "valid",
    wall: float | None = 9.0,
    *,
    parity: bool | None = None,
    correctness: bool | None = None,
) -> CellResult:
    return CellResult(
        cell_id=cell,  # type: ignore[arg-type]
        validity=validity,  # type: ignore[arg-type]
        wall_minutes=wall,
        parity_ok=parity,
        correctness_ok=correctness,
    )


def test_g1_either_over_12_opens_c0_then_g2() -> None:
    plan = plan_next([R("G1-1", wall=13.0), R("G1-2", wall=9.0)])
    assert plan.next_cell == "C0"
    plan2 = plan_next([R("G1-1", wall=13.0), R("G1-2", wall=9.0), R("C0", wall=40.0)])
    assert plan2.next_cell == "G2-1"
    assert plan2.g2_eligible is True


def test_g1_both_over_10_opens_c0_then_g2() -> None:
    hist = [R("G1-1", wall=10.5), R("G1-2", wall=11.0)]
    assert plan_next(hist).next_cell == "C0"
    assert plan_next(hist + [R("C0", wall=50.0)]).next_cell == "G2-1"


def test_g1_eligible_opens_c0_then_g1_3() -> None:
    hist = [R("G1-1", wall=9.0), R("G1-2", wall=11.0)]
    assert plan_next(hist).next_cell == "C0"
    assert plan_next(hist + [R("C0", wall=50.0)]).next_cell == "G1-3"


def test_successful_g1_confirmation_selects_g1() -> None:
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.5),
        R("C0", wall=50.0),
        R("G1-3", wall=9.2, parity=True, correctness=True),
    ]
    plan = plan_next(hist)
    assert plan.terminal == "select_g1"
    assert plan.selected_lane == "G1"
    assert plan.next_cell is None


def test_missing_correctness_does_not_select_g1() -> None:
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G1-3", wall=9.0, parity=True, correctness=None),
    ]
    plan = plan_next(hist)
    assert plan.terminal == "stop_gpu"
    assert plan.selected_lane is None
    assert "not_assessed" in plan.reason


def test_missing_parity_does_not_select_g1() -> None:
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G1-3", wall=9.0, parity=None, correctness=True),
    ]
    plan = plan_next(hist)
    assert plan.terminal == "stop_gpu"
    assert plan.selected_lane is None
    assert "not_assessed" in plan.reason


def test_g1_confirmation_timing_failure_opens_g2_seven_run_ceiling() -> None:
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.5),
        R("C0", wall=50.0),
        # median of 9, 9.5, 13 → 9.5 ok? Wait 13 > 12 fails variance.
        R("G1-3", wall=13.0, parity=True, correctness=True),
    ]
    plan = plan_next(hist)
    assert plan.next_cell == "G2-1"
    assert plan.g2_eligible is True
    # Seven-run success path still within ceiling.
    seven = hist + [
        R("G2-1", wall=8.0),
        R("G2-2", wall=8.5),
        R("G2-3", wall=8.2, parity=True, correctness=True),
    ]
    assert count_valid_full_runs(seven) == 7
    assert plan_next(seven).terminal == "select_g2"


def test_g1_resource_failure_opens_c0_then_g2() -> None:
    hist = [R("G1-1", validity="valid_negative_resource", wall=None)]
    assert plan_next(hist).next_cell == "C0"
    assert plan_next(hist + [R("C0", wall=40.0)]).next_cell == "G2-1"


def test_g1_parity_failure_stops_g2_prohibited() -> None:
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G1-3", wall=9.0, parity=False, correctness=True),
    ]
    plan = plan_next(hist)
    assert plan.terminal == "stop_gpu"
    assert plan.next_cell is None
    assert plan.g2_eligible is False
    assert "parity" in plan.reason


def test_g2_failed_two_run_screen_stops_without_g2_3() -> None:
    hist = [
        R("G1-1", wall=13.0),
        R("G1-2", wall=13.0),
        R("C0", wall=40.0),
        R("G2-1", wall=11.0),
        R("G2-2", wall=11.5),
    ]
    plan = plan_next(hist)
    assert plan.terminal == "stop_gpu"
    assert plan.next_cell is None
    assert "no_g2_3" in plan.reason


def test_g2_eligible_runs_g2_3() -> None:
    hist = [
        R("G1-1", wall=13.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G2-1", wall=8.0),
        R("G2-2", wall=9.0),
    ]
    assert plan_next(hist).next_cell == "G2-3"


def test_g2_resource_parity_timing_terminal() -> None:
    base = [
        R("G1-1", wall=13.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G2-1", wall=8.0),
        R("G2-2", wall=8.0),
    ]
    assert (
        plan_next(
            base + [R("G2-3", validity="valid_negative_resource", wall=None)]
        ).terminal
        == "stop_gpu"
    )
    assert (
        plan_next(
            base + [R("G2-3", wall=8.0, parity=False, correctness=True)]
        ).terminal
        == "stop_gpu"
    )
    assert (
        plan_next(
            base + [R("G2-3", wall=13.0, parity=True, correctness=True)]
        ).terminal
        == "stop_gpu"
    )


def test_no_eighth_valid_full_run() -> None:
    # Force seven valid runs then refuse scheduling another.
    hist = [
        R("G1-1", wall=9.0),
        R("G1-2", wall=9.0),
        R("C0", wall=40.0),
        R("G1-3", wall=13.0, parity=True, correctness=True),
        R("G2-1", wall=8.0),
        R("G2-2", wall=8.0),
        R("G2-3", wall=8.0, parity=True, correctness=True),
    ]
    assert count_valid_full_runs(hist) == MAX_VALID_FULL_RUNS
    # Already selected G2 — terminal, no next.
    assert plan_next(hist).terminal == "select_g2"
    # If somehow still awaiting after 7 without selection, next is forbidden:
    # append an extra valid that exceeds ceiling.
    overflow = hist + [R("G1-1", wall=9.0)]  # ill-formed; count=8
    plan = plan_next(overflow)
    assert plan.terminal == "stop_gpu"
    assert "eighth" in plan.reason or plan.next_cell is None


def test_cpu_not_graded_against_gpu_gate() -> None:
    assert grades_against_gpu_gate("C0") is False
    assert grades_against_gpu_gate("G1-1") is True
    # C0 wall of 60 minutes does not itself open/close GPU gates.
    hist = [R("G1-1", wall=9.0), R("G1-2", wall=9.0), R("C0", wall=60.0)]
    assert plan_next(hist).next_cell == "G1-3"


def test_vram_only_cannot_open_g2() -> None:
    with pytest.raises(ValueError, match="VRAM"):
        reject_vram_only_g2_open()


def test_assert_transition_rejects_bad_cell() -> None:
    with pytest.raises(ValueError, match="unauthorized transition"):
        assert_transition_allowed([], "G2-1")
    assert_transition_allowed([], "G1-1")


def test_invalid_retry_same_cell() -> None:
    hist = [R("G1-1", validity="invalid", wall=None)]
    assert plan_next(hist).next_cell == "G1-1"


def test_resource_exhaustion_classification() -> None:
    oom = RuntimeError("CUDA out of memory")
    assert is_cuda_resource_exhaustion(oom)
    assert (
        classify_treatment_failure(oom, identity_correct=True)
        == "valid_negative_resource"
    )
    assert (
        classify_treatment_failure(oom, identity_correct=False) == "invalid"
    )
    other = RuntimeError("keyboard interrupt")
    assert classify_treatment_failure(other, identity_correct=True) == "invalid"


def test_generic_cuda_errors_are_not_valid_resource_negatives() -> None:
    class CUDAError(RuntimeError):
        pass

    illegal = CUDAError("illegal memory access")
    invalid = CUDAError("invalid argument")
    assert not is_cuda_resource_exhaustion(illegal)
    assert not is_cuda_resource_exhaustion(invalid)
    assert classify_treatment_failure(illegal, identity_correct=True) == "invalid"
    assert classify_treatment_failure(invalid, identity_correct=True) == "invalid"

    alloc = RuntimeError("CUBLAS_STATUS_ALLOC_FAILED")
    assert is_cuda_resource_exhaustion(alloc)


def test_fp16_cpu_fails_closed() -> None:
    with pytest.raises(EmbedderError, match="fails closed"):
        resolve_embedding_precision("fp16", resolved_device="cpu")
    ok = resolve_embedding_precision("fp16", resolved_device="cuda")
    assert ok.resolved_precision == "fp16"
