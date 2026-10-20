"""16K-D D2 practical execution optimization campaign state machine.

Design subject: ``8f96657d73b2213fb9b43557b001bc4c5a42188b``
Authority: ``S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001``

Pure planning / validity helpers. Scientific cell execution is not authorized
under the implementation AUTH.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CellId = Literal["G1-1", "G1-2", "C0", "G1-3", "G2-1", "G2-2", "G2-3"]
ValidityClass = Literal["valid", "valid_negative_resource", "invalid"]
GpuLane = Literal["G1", "G2"]
CampaignTerminal = Literal[
    "select_g1",
    "select_g2",
    "stop_gpu",
    "awaiting_cell",
]

ALLOWED_CELLS: tuple[CellId, ...] = (
    "G1-1",
    "G1-2",
    "C0",
    "G1-3",
    "G2-1",
    "G2-2",
    "G2-3",
)

# Absolute maximum valid full cold runs under accepted design (F005).
MAX_VALID_FULL_RUNS = 7

# GPU timing thresholds (minutes).
GPU_MEDIAN_GATE_MIN = 10.0
GPU_VARIANCE_GATE_MIN = 12.0

ACCEPTED_DESIGN_SUBJECT = "8f96657d73b2213fb9b43557b001bc4c5a42188b"
DESIGN_DOC = "docs/slice16k_d_d2_practical_execution_optimization_design.md"
IMPLEMENTATION_AUTH = (
    "S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001"
)
# Scientific / benchmark execution remains closed under this AUTH.
EXECUTION_AUTHORIZED = False

WORKLOAD_LABEL = "D0-INCIDENT-1296-CHILD-V1"
EXPECTED_CHILD_COUNT = 1296
EXPECTED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
EXPECTED_CHUNK_SET_ID = (
    "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d"
)
EXPECTED_CORPUS_ID = (
    "corpus_3c74b057074e928cccf7da048c06db0cf6df63bbe546ec14c071604949f160e3"
)
EXPECTED_CHUNK_MANIFEST_SHA256 = (
    "de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3"
)
EXPECTED_CORPUS_MANIFEST_SHA256 = (
    "69cefa61214e0e5e0a5eb71df01e323ede6f1807226181ef4134faeceb91b353"
)


@dataclass(frozen=True)
class CellSpec:
    cell_id: CellId
    device: Literal["cpu", "cuda"]
    precision: Literal["native", "fp16"]
    batch_size: Literal[16, 32]
    grades_against_gpu_gate: bool


CELL_SPECS: dict[CellId, CellSpec] = {
    "G1-1": CellSpec("G1-1", "cuda", "fp16", 32, True),
    "G1-2": CellSpec("G1-2", "cuda", "fp16", 32, True),
    "C0": CellSpec("C0", "cpu", "native", 32, False),
    "G1-3": CellSpec("G1-3", "cuda", "fp16", 32, True),
    "G2-1": CellSpec("G2-1", "cuda", "fp16", 16, True),
    "G2-2": CellSpec("G2-2", "cuda", "fp16", 16, True),
    "G2-3": CellSpec("G2-3", "cuda", "fp16", 16, True),
}


@dataclass(frozen=True)
class CellResult:
    """One completed attempt for a frozen D2 cell."""

    cell_id: CellId
    validity: ValidityClass
    wall_minutes: float | None = None
    # Parity/correctness assessed for promotion decisions (None = not assessed).
    parity_ok: bool | None = None
    correctness_ok: bool | None = None


@dataclass(frozen=True)
class CampaignPlan:
    terminal: CampaignTerminal
    next_cell: CellId | None
    reason: str
    g2_eligible: bool
    valid_full_run_count: int
    selected_lane: GpuLane | None = None


def cell_spec(cell_id: str) -> CellSpec:
    if cell_id not in CELL_SPECS:
        raise ValueError(f"unauthorized D2 cell: {cell_id!r}")
    return CELL_SPECS[cell_id]  # type: ignore[index]


def grades_against_gpu_gate(cell_id: str) -> bool:
    """C0 must never be graded against the CUDA 10/12-minute proxy."""
    return cell_spec(cell_id).grades_against_gpu_gate


def count_valid_full_runs(history: list[CellResult]) -> int:
    """Count valid + valid_negative_resource full cold runs (not invalid)."""
    return sum(1 for r in history if r.validity != "invalid")


def _latest_valid(history: list[CellResult], cell_id: CellId) -> CellResult | None:
    for result in reversed(history):
        if result.cell_id == cell_id and result.validity != "invalid":
            return result
    return None


def _has_valid(history: list[CellResult], cell_id: CellId) -> bool:
    return _latest_valid(history, cell_id) is not None


def _two_run_screen_fails(w1: float, w2: float) -> bool:
    """True when a third run cannot satisfy the final timing gate."""
    if w1 > GPU_VARIANCE_GATE_MIN or w2 > GPU_VARIANCE_GATE_MIN:
        return True
    if w1 > GPU_MEDIAN_GATE_MIN and w2 > GPU_MEDIAN_GATE_MIN:
        return True
    return False


def _two_run_screen_eligible(w1: float, w2: float) -> bool:
    """Both ≤12 and at least one ≤10."""
    if w1 > GPU_VARIANCE_GATE_MIN or w2 > GPU_VARIANCE_GATE_MIN:
        return False
    return w1 <= GPU_MEDIAN_GATE_MIN or w2 <= GPU_MEDIAN_GATE_MIN


def _three_run_timing_ok(walls: list[float]) -> bool:
    if len(walls) != 3:
        return False
    if any(w > GPU_VARIANCE_GATE_MIN for w in walls):
        return False
    ordered = sorted(walls)
    median = ordered[1]
    return median <= GPU_MEDIAN_GATE_MIN


def _parity_failed(result: CellResult) -> bool:
    if result.parity_ok is False:
        return True
    if result.correctness_ok is False:
        return True
    return False


def _parity_passed(result: CellResult) -> bool:
    return result.parity_ok is True and result.correctness_ok is not False


def _plan(
    *,
    terminal: CampaignTerminal,
    next_cell: CellId | None,
    reason: str,
    g2_eligible: bool,
    history: list[CellResult],
    selected_lane: GpuLane | None = None,
) -> CampaignPlan:
    return CampaignPlan(
        terminal=terminal,
        next_cell=next_cell,
        reason=reason,
        g2_eligible=g2_eligible,
        valid_full_run_count=count_valid_full_runs(history),
        selected_lane=selected_lane,
    )


def plan_next(history: list[CellResult]) -> CampaignPlan:
    """Deterministic next action from completed cell results.

    Invalid attempts do not advance the campaign; the same cell is re-scheduled.
    High VRAM occupancy alone never opens G2 (no VRAM input exists here).
    """
    n_valid = count_valid_full_runs(history)
    if n_valid > MAX_VALID_FULL_RUNS:
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="eighth_or_beyond_valid_full_run_forbidden",
            g2_eligible=False,
            history=history,
        )

    # Retry path: last attempt invalid → same cell.
    if history and history[-1].validity == "invalid":
        return _plan(
            terminal="awaiting_cell",
            next_cell=history[-1].cell_id,
            reason="retry_invalid_attempt",
            g2_eligible=False,
            history=history,
        )

    g1_1 = _latest_valid(history, "G1-1")
    g1_2 = _latest_valid(history, "G1-2")
    c0 = _latest_valid(history, "C0")
    g1_3 = _latest_valid(history, "G1-3")
    g2_1 = _latest_valid(history, "G2-1")
    g2_2 = _latest_valid(history, "G2-2")
    g2_3 = _latest_valid(history, "G2-3")

    # --- G1 resource failure before both screens complete ---
    for early in (g1_1, g1_2):
        if early is not None and early.validity == "valid_negative_resource":
            if c0 is None:
                return _plan(
                    terminal="awaiting_cell",
                    next_cell="C0",
                    reason="g1_resource_failure_requires_c0_then_g2",
                    g2_eligible=True,
                    history=history,
                )
            if g2_1 is None:
                return _forbid_eighth_or(
                    history,
                    _plan(
                        terminal="awaiting_cell",
                        next_cell="G2-1",
                        reason="g1_resource_failure_open_g2",
                        g2_eligible=True,
                        history=history,
                    ),
                )
            # Fall through into G2 handling below via g2_* presence.

    if g1_1 is None:
        return _plan(
            terminal="awaiting_cell",
            next_cell="G1-1",
            reason="start_g1_screen",
            g2_eligible=False,
            history=history,
        )

    if g1_1.validity == "valid_negative_resource":
        # Handled above when c0/g2 not yet scheduled; if somehow here without
        # advancing, keep forcing C0/G2.
        if c0 is None:
            return _plan(
                terminal="awaiting_cell",
                next_cell="C0",
                reason="g1_resource_failure_requires_c0_then_g2",
                g2_eligible=True,
                history=history,
            )

    if g1_2 is None and g1_1.validity == "valid":
        return _plan(
            terminal="awaiting_cell",
            next_cell="G1-2",
            reason="continue_g1_screen",
            g2_eligible=False,
            history=history,
        )

    if g1_2 is not None and g1_2.validity == "valid_negative_resource":
        if c0 is None:
            return _plan(
                terminal="awaiting_cell",
                next_cell="C0",
                reason="g1_resource_failure_requires_c0_then_g2",
                g2_eligible=True,
                history=history,
            )
        if g2_1 is None:
            return _forbid_eighth_or(
                history,
                _plan(
                    terminal="awaiting_cell",
                    next_cell="G2-1",
                    reason="g1_resource_failure_open_g2",
                    g2_eligible=True,
                    history=history,
                ),
            )

    # Both G1 screens present as valid timing runs (not resource negatives).
    g1_screen_valid = (
        g1_1 is not None
        and g1_2 is not None
        and g1_1.validity == "valid"
        and g1_2.validity == "valid"
        and g1_1.wall_minutes is not None
        and g1_2.wall_minutes is not None
    )

    open_g2_after_c0 = False
    open_g1_3_after_c0 = False

    if g1_screen_valid:
        assert g1_1 is not None and g1_2 is not None
        assert g1_1.wall_minutes is not None and g1_2.wall_minutes is not None
        w1 = float(g1_1.wall_minutes)
        w2 = float(g1_2.wall_minutes)
        if _two_run_screen_fails(w1, w2):
            open_g2_after_c0 = True
        elif _two_run_screen_eligible(w1, w2):
            open_g1_3_after_c0 = True
        else:
            # Both ≤12 but neither ≤10 is impossible given fails/eligible split
            # (both >10 is fail; otherwise at least one ≤10). Defensive STOP.
            return _plan(
                terminal="stop_gpu",
                next_cell=None,
                reason="g1_screen_unclassified",
                g2_eligible=False,
                history=history,
            )

    # Resource-failure path already set open_g2 via earlier branches when c0 done.
    g1_resource_opened_g2 = any(
        r.cell_id in {"G1-1", "G1-2"} and r.validity == "valid_negative_resource"
        for r in history
        if r.validity != "invalid"
    )
    if g1_resource_opened_g2:
        open_g2_after_c0 = True
        open_g1_3_after_c0 = False

    if c0 is None and (open_g2_after_c0 or open_g1_3_after_c0 or g1_resource_opened_g2):
        return _plan(
            terminal="awaiting_cell",
            next_cell="C0",
            reason="mandatory_c0_cpu_baseline",
            g2_eligible=open_g2_after_c0 or g1_resource_opened_g2,
            history=history,
        )

    # --- After C0: G1-3 confirmation path ---
    if open_g1_3_after_c0 and not open_g2_after_c0 and not g1_resource_opened_g2:
        if g1_3 is None:
            return _forbid_eighth_or(
                history,
                _plan(
                    terminal="awaiting_cell",
                    next_cell="G1-3",
                    reason="g1_mathematically_eligible_run_g1_3",
                    g2_eligible=False,
                    history=history,
                ),
            )
        if g1_3.validity == "valid_negative_resource":
            # Confirmation-time resource failure → G2 eligible.
            if g2_1 is None:
                return _forbid_eighth_or(
                    history,
                    _plan(
                        terminal="awaiting_cell",
                        next_cell="G2-1",
                        reason="g1_confirmation_resource_failure_open_g2",
                        g2_eligible=True,
                        history=history,
                    ),
                )
            open_g2_after_c0 = True
        elif g1_3.validity == "valid":
            if _parity_failed(g1_3):
                return _plan(
                    terminal="stop_gpu",
                    next_cell=None,
                    reason="g1_parity_or_correctness_failure_terminal_g2_prohibited",
                    g2_eligible=False,
                    history=history,
                )
            walls = [
                float(g1_1.wall_minutes),  # type: ignore[union-attr]
                float(g1_2.wall_minutes),  # type: ignore[union-attr]
                float(g1_3.wall_minutes),  # type: ignore[arg-type]
            ]
            if _three_run_timing_ok(walls) and _parity_passed(g1_3):
                return _plan(
                    terminal="select_g1",
                    next_cell=None,
                    reason="g1_timing_and_parity_success",
                    g2_eligible=False,
                    history=history,
                    selected_lane="G1",
                )
            if not _three_run_timing_ok(walls):
                # Timing/variance confirmation failure → G2 may open (7-run path).
                open_g2_after_c0 = True
            else:
                # Timing ok but parity not yet recorded → wait for assessment.
                if g1_3.parity_ok is None:
                    return _plan(
                        terminal="stop_gpu",
                        next_cell=None,
                        reason="g1_parity_not_assessed_fail_closed",
                        g2_eligible=False,
                        history=history,
                    )

    # --- G2 path ---
    if open_g2_after_c0 or g2_1 is not None or g2_2 is not None or g2_3 is not None:
        return _plan_g2(history, g2_1=g2_1, g2_2=g2_2, g2_3=g2_3)

    return _plan(
        terminal="stop_gpu",
        next_cell=None,
        reason="campaign_state_unresolved",
        g2_eligible=False,
        history=history,
    )


def _forbid_eighth_or(history: list[CellResult], plan: CampaignPlan) -> CampaignPlan:
    if plan.next_cell is None:
        return plan
    if count_valid_full_runs(history) >= MAX_VALID_FULL_RUNS:
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="no_eighth_valid_full_run",
            g2_eligible=False,
            history=history,
        )
    return plan


def _plan_g2(
    history: list[CellResult],
    *,
    g2_1: CellResult | None,
    g2_2: CellResult | None,
    g2_3: CellResult | None,
) -> CampaignPlan:
    if g2_1 is None:
        return _forbid_eighth_or(
            history,
            _plan(
                terminal="awaiting_cell",
                next_cell="G2-1",
                reason="open_g2_screen",
                g2_eligible=True,
                history=history,
            ),
        )

    if g2_1.validity == "valid_negative_resource":
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_resource_failure_terminal",
            g2_eligible=True,
            history=history,
        )

    if g2_2 is None:
        return _forbid_eighth_or(
            history,
            _plan(
                terminal="awaiting_cell",
                next_cell="G2-2",
                reason="continue_g2_screen",
                g2_eligible=True,
                history=history,
            ),
        )

    if g2_2.validity == "valid_negative_resource":
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_resource_failure_terminal",
            g2_eligible=True,
            history=history,
        )

    assert g2_1.wall_minutes is not None and g2_2.wall_minutes is not None
    w1 = float(g2_1.wall_minutes)
    w2 = float(g2_2.wall_minutes)
    if _two_run_screen_fails(w1, w2):
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_two_run_screen_failed_no_g2_3",
            g2_eligible=True,
            history=history,
        )

    if g2_3 is None:
        return _forbid_eighth_or(
            history,
            _plan(
                terminal="awaiting_cell",
                next_cell="G2-3",
                reason="g2_mathematically_eligible_run_g2_3",
                g2_eligible=True,
                history=history,
            ),
        )

    if g2_3.validity == "valid_negative_resource":
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_resource_failure_terminal",
            g2_eligible=True,
            history=history,
        )

    if _parity_failed(g2_3):
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_parity_or_correctness_failure_terminal",
            g2_eligible=True,
            history=history,
        )

    walls = [w1, w2, float(g2_3.wall_minutes)]  # type: ignore[arg-type]
    if _three_run_timing_ok(walls) and _parity_passed(g2_3):
        return _plan(
            terminal="select_g2",
            next_cell=None,
            reason="g2_timing_and_parity_success",
            g2_eligible=True,
            history=history,
            selected_lane="G2",
        )

    if not _three_run_timing_ok(walls):
        return _plan(
            terminal="stop_gpu",
            next_cell=None,
            reason="g2_timing_or_variance_failure_terminal",
            g2_eligible=True,
            history=history,
        )

    return _plan(
        terminal="stop_gpu",
        next_cell=None,
        reason="g2_parity_not_assessed_fail_closed",
        g2_eligible=True,
        history=history,
    )


def assert_transition_allowed(
    history: list[CellResult],
    proposed_cell: str,
) -> None:
    """Raise ValueError if ``proposed_cell`` is not the frozen next cell."""
    plan = plan_next(history)
    if plan.next_cell is None:
        raise ValueError(
            f"campaign terminal={plan.terminal} reason={plan.reason}; "
            f"refusing cell {proposed_cell!r}"
        )
    if proposed_cell != plan.next_cell:
        raise ValueError(
            f"unauthorized transition: proposed {proposed_cell!r}, "
            f"expected {plan.next_cell!r} ({plan.reason})"
        )


def reject_vram_only_g2_open() -> None:
    """Documented invariant: VRAM occupancy alone must never open G2."""
    raise ValueError(
        "G2 cannot open because VRAM occupancy alone looks high; "
        "only G1 timing/variance failure or G1 valid resource failure may open G2"
    )


__all__ = [
    "ACCEPTED_DESIGN_SUBJECT",
    "ALLOWED_CELLS",
    "CELL_SPECS",
    "CampaignPlan",
    "CampaignTerminal",
    "CellId",
    "CellResult",
    "CellSpec",
    "DESIGN_DOC",
    "EXECUTION_AUTHORIZED",
    "EXPECTED_CHILD_COUNT",
    "EXPECTED_CHUNK_MANIFEST_SHA256",
    "EXPECTED_CHUNK_SET_ID",
    "EXPECTED_CORPUS_ID",
    "EXPECTED_CORPUS_MANIFEST_SHA256",
    "EXPECTED_MODEL_ID",
    "EXPECTED_MODEL_REVISION",
    "GPU_MEDIAN_GATE_MIN",
    "GPU_VARIANCE_GATE_MIN",
    "IMPLEMENTATION_AUTH",
    "MAX_VALID_FULL_RUNS",
    "ValidityClass",
    "WORKLOAD_LABEL",
    "assert_transition_allowed",
    "cell_spec",
    "count_valid_full_runs",
    "grades_against_gpu_gate",
    "plan_next",
    "reject_vram_only_g2_open",
]
