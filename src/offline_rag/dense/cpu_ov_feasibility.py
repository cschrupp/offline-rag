"""16K-D CPU-OV-01 same-model OpenVINO CPU feasibility — frozen planner.

Authority: S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001
Rework parent: 47a28d008ae8494b4d928c850126c09ddaa38925

Pure decision ladder. Scientific / benchmark OpenVINO execution is not
authorized while ``EXECUTION_AUTHORIZED`` is False.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

# --- Authority / identity -------------------------------------------------

IMPLEMENTATION_AUTH = (
    "S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-AUTH-001"
)
IMPLEMENTATION_REWORK_AUTH = (
    "S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001"
)
IMPLEMENTATION_REWORK2_AUTH = (
    "S16-K-D-POST-D2-CPU-OPENVINO-FEASIBILITY-IMPLEMENTATION-REWORK2-AUTH-002"
)
EXACT_PARENT = "137bd65a9c0c11fd7989e9c72857730ba21e3191"
REWORK_PARENT = "47a28d008ae8494b4d928c850126c09ddaa38925"
# Commit topology parent (Stage-0 evidence tip). Implementation base remains eea4c97.
REWORK2_PARENT = "50906c4665a3d1d73fe9693207bcf1a0d82a65d5"
REWORK2_IMPLEMENTATION_BASE = "eea4c976a351fbb41d1cd3efc1337198813c2e22"
DESIGN_DOC = "docs/slice16k_d_cpu_openvino_feasibility.md"
EXPERIMENT_ID = "16K-D-CPU-OV-01"
PARITY_CONTRACT_ID = "d2-retrieval-parity-v1"

# Scientific execution remains closed under the harness AUTH / rework AUTH.
EXECUTION_AUTHORIZED = False

EXPECTED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
EXPECTED_DIMENSION = 1024
FROZEN_BATCH_SIZE = 32
FROZEN_NORMALIZE = True
FROZEN_DEVICE = "cpu"
FROZEN_BACKEND = "openvino"

# Workload / sampling
WORKLOAD_LABEL = "D0-INCIDENT-1296-CHILD-V1"
EXPECTED_CHILD_COUNT = 1296
SCREEN_CHILD_COUNT = 128
PARITY_DOC_COUNT = 64
PARITY_QUERY_COUNT = 16
EXPECTED_CHUNK_SET_ID = (
    "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d"
)
EXPECTED_CHUNK_MANIFEST_SHA256 = (
    "de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3"
)

# D2 C0 reference (encoding throughput after load) — not a pass/fail oracle.
C0_CHUNKS_PER_SEC = 0.0932
C0_WALL_MINUTES = 231.06513355945015

# Screen projection gates (minutes for projected 1296 encode).
SCREEN_EXCELLENT_MAX_MIN = 15.0
SCREEN_VIABLE_MAX_MIN = 25.0

# Final feasibility classes (full-run evidence; not usable as projection).
FEASIBLE_MAX_MIN = 25.0

# Parity gates — identical to d2-retrieval-parity-v1.
PARITY_THRESHOLDS: dict[str, float] = {
    "median_document_vector_cosine": 0.999,
    "min_document_vector_cosine": 0.995,
    "median_query_vector_cosine": 0.999,
    "min_query_vector_cosine": 0.995,
    "top1_agreement_min": 15,
    "top1_agreement_of": 16,
    "mean_top10_set_overlap": 0.95,
    "min_top10_set_overlap": 0.80,
}

WeightFormat = Literal["fp16", "int8"]
StageId = Literal[
    "export_compat",  # Stage-0 FP16-only
    "screen_fp16",
    "parity_fp16",
    "export_int8",  # conditional INT8 preparation (F004)
    "screen_int8",
    "parity_int8",
    "full_confirm",
]
Terminal = Literal[
    "awaiting_stage",
    "select_ov_fp16",
    "select_ov_int8",
    "stop_incompatible",
    "stop_too_slow",
    "stop_parity_fail",
    "eligible_full_confirm",
]
NextAction = Literal[
    "run_export_compat",
    "run_screen_fp16",
    "run_parity_fp16",
    "run_export_int8",
    "run_screen_int8",
    "run_parity_int8",
    "run_full_confirm",
    "none",
]


@dataclass(frozen=True)
class StageResult:
    """One completed (or recorded) stage for the feasibility ladder."""

    stage_id: StageId
    ok: bool
    # Screen measurements (encode throughput after load).
    chunks_per_sec: float | None = None
    projected_full_minutes: float | None = None
    # Parity assessment (explicit bools only; None = not assessed).
    parity_ok: bool | None = None
    # Full-run measured wall (minutes); never filled from a projection.
    full_wall_minutes: float | None = None
    embeddings_generated: int | None = None
    embeddings_reused: int | None = None
    embeddings_failed: int | None = None
    vectors_materialized: int | None = None
    dimension: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class FeasibilityPlan:
    terminal: Terminal
    next_action: NextAction
    reason: str
    selected_candidate: WeightFormat | None = None
    full_confirm_eligible: bool = False
    int8_eligible: bool = False


def project_full_minutes(chunks_per_sec: float) -> float:
    """Screening projection only — never confirmation evidence."""
    if chunks_per_sec <= 0:
        raise ValueError("chunks_per_sec must be positive")
    return float(EXPECTED_CHILD_COUNT) / float(chunks_per_sec) / 60.0


def classify_screen_projection(projected_minutes: float) -> str:
    if projected_minutes <= SCREEN_EXCELLENT_MAX_MIN:
        return "excellent"
    if projected_minutes <= SCREEN_VIABLE_MAX_MIN:
        return "viable"
    return "too_slow"


def parity_thresholds_pass(metrics: dict[str, Any]) -> bool:
    """Evaluate frozen d2-retrieval-parity-v1 gates (fail closed on missing)."""
    try:
        if float(metrics["median_document_vector_cosine"]) < PARITY_THRESHOLDS[
            "median_document_vector_cosine"
        ]:
            return False
        if float(metrics["min_document_vector_cosine"]) < PARITY_THRESHOLDS[
            "min_document_vector_cosine"
        ]:
            return False
        if float(metrics["median_query_vector_cosine"]) < PARITY_THRESHOLDS[
            "median_query_vector_cosine"
        ]:
            return False
        if float(metrics["min_query_vector_cosine"]) < PARITY_THRESHOLDS[
            "min_query_vector_cosine"
        ]:
            return False
        if int(metrics["top1_agreement"]) < int(
            PARITY_THRESHOLDS["top1_agreement_min"]
        ):
            return False
        if float(metrics["mean_top10_set_overlap"]) < PARITY_THRESHOLDS[
            "mean_top10_set_overlap"
        ]:
            return False
        if float(metrics["min_top10_set_overlap"]) < PARITY_THRESHOLDS[
            "min_top10_set_overlap"
        ]:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _latest(history: list[StageResult], stage_id: StageId) -> StageResult | None:
    for item in reversed(history):
        if item.stage_id == stage_id:
            return item
    return None


def _require_screen_fields(result: StageResult) -> None:
    if result.chunks_per_sec is None or result.projected_full_minutes is None:
        raise ValueError(
            f"screen stage {result.stage_id!r} missing chunks_per_sec/projected_full_minutes"
        )


def full_confirm_passes(result: StageResult) -> bool:
    """Frozen ≤25-minute feasibility gate + exact 1296 confirmation counts (F003).

    Screen projections (``projected_full_minutes``) never satisfy this gate.
    """
    if result.stage_id != "full_confirm":
        return False
    if not result.ok:
        return False
    if result.full_wall_minutes is None:
        return False
    if float(result.full_wall_minutes) > FEASIBLE_MAX_MIN:
        return False
    if result.embeddings_generated != EXPECTED_CHILD_COUNT:
        return False
    if result.embeddings_reused != 0:
        return False
    if result.embeddings_failed != 0:
        return False
    if result.vectors_materialized != EXPECTED_CHILD_COUNT:
        return False
    if result.dimension != EXPECTED_DIMENSION:
        return False
    return True


def _require_int8_export_then_screen(
    history: list[StageResult],
    *,
    reason_export: str,
    reason_screen: str,
) -> FeasibilityPlan | None:
    """INT8 preparation is conditional — export_int8 before screen_int8 (F004)."""
    export_int8 = _latest(history, "export_int8")
    if export_int8 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_export_int8",
            reason=reason_export,
            int8_eligible=True,
        )
    if not export_int8.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="export_int8_failed",
            int8_eligible=True,
        )
    screen_int8 = _latest(history, "screen_int8")
    if screen_int8 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_screen_int8",
            reason=reason_screen,
            int8_eligible=True,
        )
    return None


def plan_next(history: list[StageResult]) -> FeasibilityPlan:
    """Deterministic next action from completed stage results."""
    export = _latest(history, "export_compat")
    if export is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_export_compat",
            reason="start_export_compat_gate",
        )
    if not export.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="export_compat_failed",
        )

    screen_fp16 = _latest(history, "screen_fp16")
    if screen_fp16 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_screen_fp16",
            reason="export_ok_run_fp16_screen",
        )
    if not screen_fp16.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="fp16_screen_failed",
        )
    _require_screen_fields(screen_fp16)
    assert screen_fp16.projected_full_minutes is not None
    fp16_class = classify_screen_projection(screen_fp16.projected_full_minutes)

    # --- FP16 parity is required before any full run and before INT8 when eligible ---
    parity_fp16 = _latest(history, "parity_fp16")

    if fp16_class == "excellent":
        # Skip INT8. Require parity, then full-confirm eligibility.
        if parity_fp16 is None:
            return FeasibilityPlan(
                terminal="awaiting_stage",
                next_action="run_parity_fp16",
                reason="fp16_excellent_run_parity",
                selected_candidate=None,
                int8_eligible=False,
            )
        if parity_fp16.parity_ok is not True or not parity_fp16.ok:
            return FeasibilityPlan(
                terminal="stop_parity_fail",
                next_action="none",
                reason="fp16_parity_failed_stop_no_int8",
                int8_eligible=False,
            )
        full = _latest(history, "full_confirm")
        if full is None:
            return FeasibilityPlan(
                terminal="eligible_full_confirm",
                next_action="run_full_confirm",
                reason="fp16_excellent_parity_pass_full_eligible",
                selected_candidate="fp16",
                full_confirm_eligible=True,
                int8_eligible=False,
            )
        if full_confirm_passes(full):
            return FeasibilityPlan(
                terminal="select_ov_fp16",
                next_action="none",
                reason="fp16_full_confirm_ok",
                selected_candidate="fp16",
                full_confirm_eligible=True,
                int8_eligible=False,
            )
        reason = (
            "fp16_full_confirm_exceeds_25_min"
            if (
                full.full_wall_minutes is not None
                and float(full.full_wall_minutes) > FEASIBLE_MAX_MIN
            )
            else "fp16_full_confirm_failed"
        )
        terminal: Terminal = (
            "stop_too_slow"
            if reason == "fp16_full_confirm_exceeds_25_min"
            else "stop_incompatible"
        )
        return FeasibilityPlan(
            terminal=terminal,
            next_action="none",
            reason=reason,
            selected_candidate="fp16",
            int8_eligible=False,
        )

    if fp16_class == "too_slow":
        # Do not full-run FP16; do not require FP16 parity; open INT8 export then screen.
        pending = _require_int8_export_then_screen(
            history,
            reason_export="fp16_too_slow_open_int8_export",
            reason_screen="fp16_too_slow_int8_exported_run_screen",
        )
        if pending is not None:
            return pending
        screen_int8 = _latest(history, "screen_int8")
        assert screen_int8 is not None
        return _plan_int8_branch(history, screen_int8, require_choose_faster=False)

    # viable 15–25: need FP16 parity, then INT8 export+screen, then choose faster passer.
    if parity_fp16 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_parity_fp16",
            reason="fp16_viable_run_parity_before_int8",
            int8_eligible=True,
        )
    if parity_fp16.parity_ok is not True or not parity_fp16.ok:
        return FeasibilityPlan(
            terminal="stop_parity_fail",
            next_action="none",
            reason="fp16_parity_failed_stop_no_int8",
            int8_eligible=False,
        )

    pending = _require_int8_export_then_screen(
        history,
        reason_export="fp16_viable_parity_pass_export_int8",
        reason_screen="fp16_viable_int8_exported_run_screen",
    )
    if pending is not None:
        return pending
    screen_int8 = _latest(history, "screen_int8")
    assert screen_int8 is not None
    return _plan_int8_branch(
        history,
        screen_int8,
        require_choose_faster=True,
        fp16_screen=screen_fp16,
        fp16_parity_ok=True,
    )


def _plan_int8_branch(
    history: list[StageResult],
    screen_int8: StageResult,
    *,
    require_choose_faster: bool,
    fp16_screen: StageResult | None = None,
    fp16_parity_ok: bool = False,
) -> FeasibilityPlan:
    if not screen_int8.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="int8_screen_failed",
            int8_eligible=True,
        )
    _require_screen_fields(screen_int8)
    assert screen_int8.projected_full_minutes is not None
    int8_class = classify_screen_projection(screen_int8.projected_full_minutes)
    if int8_class == "too_slow":
        return FeasibilityPlan(
            terminal="stop_too_slow",
            next_action="none",
            reason="int8_projection_exceeds_25_min",
            int8_eligible=True,
        )

    parity_int8 = _latest(history, "parity_int8")
    if parity_int8 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_parity_int8",
            reason="int8_screen_ok_run_parity",
            int8_eligible=True,
        )
    if parity_int8.parity_ok is not True or not parity_int8.ok:
        return FeasibilityPlan(
            terminal="stop_parity_fail",
            next_action="none",
            reason="int8_parity_failed",
            int8_eligible=True,
        )

    # Choose candidate.
    selected: WeightFormat = "int8"
    if require_choose_faster and fp16_parity_ok and fp16_screen is not None:
        _require_screen_fields(fp16_screen)
        assert fp16_screen.projected_full_minutes is not None
        # Faster = lower projected minutes.
        if fp16_screen.projected_full_minutes <= screen_int8.projected_full_minutes:
            selected = "fp16"
        else:
            selected = "int8"

    full = _latest(history, "full_confirm")
    if full is None:
        return FeasibilityPlan(
            terminal="eligible_full_confirm",
            next_action="run_full_confirm",
            reason=f"{selected}_selected_full_eligible",
            selected_candidate=selected,
            full_confirm_eligible=True,
            int8_eligible=True,
        )
    if full_confirm_passes(full):
        terminal_sel: Terminal = (
            "select_ov_fp16" if selected == "fp16" else "select_ov_int8"
        )
        return FeasibilityPlan(
            terminal=terminal_sel,
            next_action="none",
            reason=f"{selected}_full_confirm_ok",
            selected_candidate=selected,
            full_confirm_eligible=True,
            int8_eligible=True,
        )
    reason = (
        f"{selected}_full_confirm_exceeds_25_min"
        if (
            full.full_wall_minutes is not None
            and float(full.full_wall_minutes) > FEASIBLE_MAX_MIN
        )
        else f"{selected}_full_confirm_failed"
    )
    terminal_fail: Terminal = (
        "stop_too_slow" if "exceeds_25_min" in reason else "stop_incompatible"
    )
    return FeasibilityPlan(
        terminal=terminal_fail,
        next_action="none",
        reason=reason,
        selected_candidate=selected,
        int8_eligible=True,
    )


def assert_transition_allowed(
    history: list[StageResult], proposed_action: NextAction
) -> None:
    plan = plan_next(history)
    if proposed_action == "none":
        raise ValueError("refusing action 'none'")
    if plan.next_action != proposed_action:
        raise ValueError(
            f"unauthorized transition: proposed {proposed_action!r}, "
            f"expected {plan.next_action!r} ({plan.reason})"
        )


def assert_frozen_runtime_knobs(
    *,
    batch_size: int,
    normalize: bool,
    device: str,
    backend: str,
) -> None:
    """Fail closed on any attempt to retune frozen knobs."""
    if batch_size != FROZEN_BATCH_SIZE:
        raise ValueError(
            f"batch_size {batch_size!r} != frozen {FROZEN_BATCH_SIZE} "
            "(batch sweep not authorized)"
        )
    if normalize is not FROZEN_NORMALIZE:
        raise ValueError("normalize must remain True (frozen)")
    if device != FROZEN_DEVICE:
        raise ValueError(f"device {device!r} != frozen {FROZEN_DEVICE!r}")
    if backend != FROZEN_BACKEND:
        raise ValueError(f"backend {backend!r} != frozen {FROZEN_BACKEND!r}")


def refuse_hub_substitution(*, local_model_dir_exists: bool, allow_download: bool) -> None:
    if allow_download:
        raise ValueError(
            "Hub download/substitution is not authorized; "
            "export must use the locally provisioned pinned checkpoint"
        )
    if not local_model_dir_exists:
        raise ValueError(
            "local pinned embedding checkpoint missing; refusing Hub fallback"
        )


def refuse_projection_as_confirmation(projected_full_minutes: float | None) -> None:
    """Guard: projected minutes must never be recorded as full_wall_minutes."""
    # Documentary helper used by harness writers/tests.
    if projected_full_minutes is None:
        return
    # No state mutation — callers must not assign projection into full_wall.
    _ = projected_full_minutes


def stage_result_to_dict(result: StageResult) -> dict[str, Any]:
    return asdict(result)


def plan_to_dict(plan: FeasibilityPlan) -> dict[str, Any]:
    return asdict(plan)


__all__ = [
    "C0_CHUNKS_PER_SEC",
    "C0_WALL_MINUTES",
    "DESIGN_DOC",
    "EXACT_PARENT",
    "EXECUTION_AUTHORIZED",
    "EXPECTED_CHILD_COUNT",
    "EXPECTED_CHUNK_MANIFEST_SHA256",
    "EXPECTED_CHUNK_SET_ID",
    "EXPECTED_DIMENSION",
    "EXPECTED_MODEL_ID",
    "EXPECTED_MODEL_REVISION",
    "EXPERIMENT_ID",
    "FEASIBLE_MAX_MIN",
    "FROZEN_BACKEND",
    "FROZEN_BATCH_SIZE",
    "FROZEN_DEVICE",
    "FROZEN_NORMALIZE",
    "FeasibilityPlan",
    "IMPLEMENTATION_AUTH",
    "IMPLEMENTATION_REWORK_AUTH",
    "IMPLEMENTATION_REWORK2_AUTH",
    "PARITY_CONTRACT_ID",
    "PARITY_DOC_COUNT",
    "PARITY_QUERY_COUNT",
    "PARITY_THRESHOLDS",
    "REWORK_PARENT",
    "REWORK2_IMPLEMENTATION_BASE",
    "REWORK2_PARENT",
    "SCREEN_CHILD_COUNT",
    "SCREEN_EXCELLENT_MAX_MIN",
    "SCREEN_VIABLE_MAX_MIN",
    "StageResult",
    "WORKLOAD_LABEL",
    "assert_frozen_runtime_knobs",
    "assert_transition_allowed",
    "classify_screen_projection",
    "full_confirm_passes",
    "parity_thresholds_pass",
    "plan_next",
    "plan_to_dict",
    "project_full_minutes",
    "refuse_hub_substitution",
    "refuse_projection_as_confirmation",
    "stage_result_to_dict",
]
