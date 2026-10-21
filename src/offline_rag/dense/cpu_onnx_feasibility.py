"""16K-D CPU-ONNX-01 same-model ONNX Runtime CPU feasibility — frozen planner.

Authority: S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001
Exact parent: e5af0a78f25696a720de79a02777ea3836351fb1

Pure decision ladder. Scientific / benchmark ONNX execution is not
authorized while ``EXECUTION_AUTHORIZED`` is False.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

IMPLEMENTATION_AUTH = (
    "S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-AUTH-001"
)
IMPLEMENTATION_REWORK_AUTH = (
    "S16-K-D-POST-CPUOV-CPU-ONNX-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001"
)
EXACT_PARENT = "e5af0a78f25696a720de79a02777ea3836351fb1"
REWORK_PARENT = "c17ac13ee05dec1c476455c29dc4600bfb2b1071"
DESIGN_DOC = "docs/slice16k_d_cpu_onnx_feasibility.md"
EXPERIMENT_ID = "16K-D-CPU-ONNX-01"
PARITY_CONTRACT_ID = "d2-retrieval-parity-v1"

EXECUTION_AUTHORIZED = False

EXPECTED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
EXPECTED_DIMENSION = 1024
FROZEN_BATCH_SIZE = 32
FROZEN_NORMALIZE = True
FROZEN_DEVICE = "cpu"
FROZEN_BACKEND = "onnx"
FROZEN_ONNX_PROVIDER = "CPUExecutionProvider"
FROZEN_ORT_INTRA_OP_THREADS = 8
FROZEN_ORT_INTER_OP_THREADS = 1
FROZEN_QINT8_TARGET = "avx2"

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
EXPECTED_SCREEN_CHUNK_IDS_DIGEST = (
    "9dfda07f0b0801eaa413c741450b48595e1d702c2bca728862b8e20848c64807"
)

SCREEN_VIABLE_MAX_MIN = 25.0
FEASIBLE_MAX_MIN = 25.0

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

WeightFormat = Literal["fp32", "qint8_avx2"]
StageId = Literal[
    "export_fp32",
    "export_qint8_avx2",
    "screen_qint8_avx2",
    "parity_qint8_avx2",
    "full_confirm",
]
Terminal = Literal[
    "awaiting_stage",
    "select_onnx_qint8_avx2",
    "stop_incompatible",
    "stop_too_slow",
    "stop_parity_fail",
    "eligible_full_confirm",
]
NextAction = Literal[
    "run_export_fp32",
    "run_export_qint8_avx2",
    "run_screen_qint8_avx2",
    "run_parity_qint8_avx2",
    "run_full_confirm",
    "none",
]


@dataclass(frozen=True)
class StageResult:
    stage_id: StageId
    ok: bool
    chunks_per_sec: float | None = None
    projected_full_minutes: float | None = None
    parity_ok: bool | None = None
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


def project_full_minutes(chunks_per_sec: float) -> float:
    if chunks_per_sec <= 0:
        raise ValueError("chunks_per_sec must be positive")
    return float(EXPECTED_CHILD_COUNT) / float(chunks_per_sec) / 60.0


def classify_screen_projection(projected_minutes: float) -> str:
    """ONNX screen: ≤25 viable; >25 too_slow (no excellent band required)."""
    if projected_minutes <= SCREEN_VIABLE_MAX_MIN:
        return "viable"
    return "too_slow"


def parity_thresholds_pass(metrics: dict[str, Any]) -> bool:
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


def full_confirm_passes(result: StageResult) -> bool:
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


def plan_next(history: list[StageResult]) -> FeasibilityPlan:
    """Deterministic ONNX ladder: FP32 source → QINT8 AVX2 → one screen → parity."""
    export_fp32 = _latest(history, "export_fp32")
    if export_fp32 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_export_fp32",
            reason="start_export_fp32_source",
        )
    if not export_fp32.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="export_fp32_failed",
        )

    export_q = _latest(history, "export_qint8_avx2")
    if export_q is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_export_qint8_avx2",
            reason="fp32_ok_export_qint8_avx2",
        )
    if not export_q.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="export_qint8_avx2_failed",
        )

    screen = _latest(history, "screen_qint8_avx2")
    if screen is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_screen_qint8_avx2",
            reason="qint8_ok_run_screen",
            selected_candidate="qint8_avx2",
        )
    if not screen.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="screen_qint8_avx2_failed",
            selected_candidate="qint8_avx2",
        )
    if screen.chunks_per_sec is None or screen.projected_full_minutes is None:
        raise ValueError("screen_qint8_avx2 missing throughput fields")
    if float(screen.projected_full_minutes) > SCREEN_VIABLE_MAX_MIN:
        return FeasibilityPlan(
            terminal="stop_too_slow",
            next_action="none",
            reason="screen_qint8_avx2_too_slow_move_to_llamacpp",
            selected_candidate="qint8_avx2",
        )

    parity = _latest(history, "parity_qint8_avx2")
    if parity is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_parity_qint8_avx2",
            reason="screen_viable_run_parity",
            selected_candidate="qint8_avx2",
        )
    if not parity.ok or parity.parity_ok is not True:
        return FeasibilityPlan(
            terminal="stop_parity_fail",
            next_action="none",
            reason="parity_qint8_avx2_failed",
            selected_candidate="qint8_avx2",
        )

    full = _latest(history, "full_confirm")
    if full is None:
        return FeasibilityPlan(
            terminal="eligible_full_confirm",
            next_action="run_full_confirm",
            reason="parity_pass_full_confirm_eligible",
            selected_candidate="qint8_avx2",
            full_confirm_eligible=True,
        )
    if full_confirm_passes(full):
        return FeasibilityPlan(
            terminal="select_onnx_qint8_avx2",
            next_action="none",
            reason="full_confirm_pass",
            selected_candidate="qint8_avx2",
            full_confirm_eligible=True,
        )
    return FeasibilityPlan(
        terminal="stop_too_slow",
        next_action="none",
        reason="full_confirm_failed",
        selected_candidate="qint8_avx2",
        full_confirm_eligible=True,
    )


def assert_frozen_runtime_knobs(
    *,
    batch_size: int,
    normalize: bool,
    device: str,
    backend: str,
    ort_intra_op_threads: int | None = None,
    ort_inter_op_threads: int | None = None,
) -> None:
    if batch_size != FROZEN_BATCH_SIZE:
        raise ValueError(f"batch_size must be {FROZEN_BATCH_SIZE}")
    if normalize is not FROZEN_NORMALIZE:
        raise ValueError(f"normalize must be {FROZEN_NORMALIZE}")
    if device != FROZEN_DEVICE:
        raise ValueError(f"device must be {FROZEN_DEVICE!r}")
    if backend != FROZEN_BACKEND:
        raise ValueError(f"backend must be {FROZEN_BACKEND!r}")
    if ort_intra_op_threads is not None and (
        ort_intra_op_threads != FROZEN_ORT_INTRA_OP_THREADS
    ):
        raise ValueError(
            f"ort_intra_op_threads must be {FROZEN_ORT_INTRA_OP_THREADS}"
        )
    if ort_inter_op_threads is not None and (
        ort_inter_op_threads != FROZEN_ORT_INTER_OP_THREADS
    ):
        raise ValueError(
            f"ort_inter_op_threads must be {FROZEN_ORT_INTER_OP_THREADS}"
        )


def assert_transition_allowed(history: list[StageResult], action: NextAction) -> None:
    plan = plan_next(history)
    if plan.next_action != action:
        raise ValueError(
            f"transition refused: requested={action!r} planned={plan.next_action!r} "
            f"reason={plan.reason!r}"
        )


def refuse_hub_substitution(
    *, local_model_dir_exists: bool, allow_download: bool
) -> None:
    if allow_download:
        raise ValueError("Hub download / substitution is refused for CPU-ONNX-01")
    if not local_model_dir_exists:
        raise ValueError("local pinned embedding artifacts missing")


def plan_to_dict(plan: FeasibilityPlan) -> dict[str, Any]:
    return asdict(plan)


def stage_result_to_dict(result: StageResult) -> dict[str, Any]:
    return asdict(result)


__all__ = [
    "DESIGN_DOC",
    "EXACT_PARENT",
    "EXECUTION_AUTHORIZED",
    "EXPECTED_CHILD_COUNT",
    "EXPECTED_CHUNK_MANIFEST_SHA256",
    "EXPECTED_CHUNK_SET_ID",
    "EXPECTED_DIMENSION",
    "EXPECTED_MODEL_ID",
    "EXPECTED_MODEL_REVISION",
    "EXPECTED_SCREEN_CHUNK_IDS_DIGEST",
    "EXPERIMENT_ID",
    "FEASIBLE_MAX_MIN",
    "FROZEN_BACKEND",
    "FROZEN_BATCH_SIZE",
    "FROZEN_DEVICE",
    "FROZEN_NORMALIZE",
    "FROZEN_ONNX_PROVIDER",
    "FROZEN_ORT_INTER_OP_THREADS",
    "FROZEN_ORT_INTRA_OP_THREADS",
    "FROZEN_QINT8_TARGET",
    "FeasibilityPlan",
    "IMPLEMENTATION_AUTH",
    "IMPLEMENTATION_REWORK_AUTH",
    "PARITY_CONTRACT_ID",
    "PARITY_DOC_COUNT",
    "PARITY_QUERY_COUNT",
    "PARITY_THRESHOLDS",
    "REWORK_PARENT",
    "SCREEN_CHILD_COUNT",
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
    "stage_result_to_dict",
]
