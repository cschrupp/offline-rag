"""16K-D CPU-GGUF-01 llama.cpp Q8_0 CPU feasibility — frozen planner.

Authority: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001
Rework: S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001
Exact parent: 5fca0844878b1c73ce23e75a7dee9023b4730a9f
Rework parent: 3cb62330abd168a00a1ff67459f8af3aa3ed27da

Pure decision ladder. Scientific / benchmark llama.cpp execution is not
authorized while ``EXECUTION_AUTHORIZED`` is False.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

IMPLEMENTATION_AUTH = (
    "S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-AUTH-001"
)
IMPLEMENTATION_REWORK_AUTH = (
    "S16-K-D-POST-CPUONNX-CPU-GGUF-FEASIBILITY-IMPLEMENTATION-REWORK-AUTH-001"
)
EXACT_PARENT = "5fca0844878b1c73ce23e75a7dee9023b4730a9f"
REWORK_PARENT = "3cb62330abd168a00a1ff67459f8af3aa3ed27da"
DESIGN_DOC = "docs/slice16k_d_cpu_gguf_feasibility.md"
EXPERIMENT_ID = "16K-D-CPU-GGUF-01"
PARITY_CONTRACT_ID = "d2-retrieval-parity-v1"

EXECUTION_AUTHORIZED = False

# Official Qwen GGUF pin (immutable external artifact).
EXPECTED_GGUF_REPO_ID = "Qwen/Qwen3-Embedding-0.6B-GGUF"
EXPECTED_GGUF_REVISION = "71a379860247873620c83349673f4bcbdbc24922"
EXPECTED_GGUF_FILENAME = "Qwen3-Embedding-0.6B-Q8_0.gguf"
EXPECTED_GGUF_SHA256 = (
    "a0e820fb3f8f448d3582862f9161bfaf58a63f89b46353f061e017597655821c"
)
EXPECTED_GGUF_BYTES = 639_291_488  # ~639 MB as published; verified by SHA256

EXPECTED_DIMENSION = 1024
FROZEN_BATCH_SIZE = 32
FROZEN_NORMALIZE = True
FROZEN_DEVICE = "cpu"
FROZEN_BACKEND = "llama_cpp"
FROZEN_POOLING = "last"
FROZEN_N_GPU_LAYERS = 0
FROZEN_THREADS = 8
FROZEN_THREADS_BATCH = 8
FROZEN_QUANT = "Q8_0"

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

CandidateId = Literal["q8_0"]
StageId = Literal[
    "stage0_compat",
    "screen_q8_0",
    "parity_q8_0",
    "full_confirm",
]
Terminal = Literal[
    "awaiting_stage",
    "select_gguf_q8_0",
    "stop_incompatible",
    "stop_too_slow",
    "stop_parity_fail",
    "eligible_full_confirm",
]
NextAction = Literal[
    "run_stage0_compat",
    "run_screen_q8_0",
    "run_parity_q8_0",
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
    selected_candidate: CandidateId | None = None
    full_confirm_eligible: bool = False


def project_full_minutes(chunks_per_sec: float) -> float:
    if chunks_per_sec <= 0:
        raise ValueError("chunks_per_sec must be positive")
    return float(EXPECTED_CHILD_COUNT) / float(chunks_per_sec) / 60.0


def classify_screen_projection(projected_minutes: float) -> str:
    """GGUF screen: ≤25 viable; >25 too_slow."""
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
    """Deterministic GGUF ladder: Stage-0 compat → one Q8_0 screen → parity."""
    stage0 = _latest(history, "stage0_compat")
    if stage0 is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_stage0_compat",
            reason="start_stage0_artifact_runtime_compat",
        )
    if not stage0.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="stage0_compat_failed",
        )

    screen = _latest(history, "screen_q8_0")
    if screen is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_screen_q8_0",
            reason="stage0_ok_run_screen",
            selected_candidate="q8_0",
        )
    if not screen.ok:
        return FeasibilityPlan(
            terminal="stop_incompatible",
            next_action="none",
            reason="screen_q8_0_failed",
            selected_candidate="q8_0",
        )
    if screen.chunks_per_sec is None or screen.projected_full_minutes is None:
        raise ValueError("screen_q8_0 missing throughput fields")
    if float(screen.projected_full_minutes) > SCREEN_VIABLE_MAX_MIN:
        return FeasibilityPlan(
            terminal="stop_too_slow",
            next_action="none",
            reason="screen_q8_0_too_slow_move_to_model_change",
            selected_candidate="q8_0",
        )

    parity = _latest(history, "parity_q8_0")
    if parity is None:
        return FeasibilityPlan(
            terminal="awaiting_stage",
            next_action="run_parity_q8_0",
            reason="screen_viable_run_parity",
            selected_candidate="q8_0",
        )
    if not parity.ok or parity.parity_ok is not True:
        return FeasibilityPlan(
            terminal="stop_parity_fail",
            next_action="none",
            reason="parity_q8_0_failed",
            selected_candidate="q8_0",
        )

    full = _latest(history, "full_confirm")
    if full is None:
        return FeasibilityPlan(
            terminal="eligible_full_confirm",
            next_action="run_full_confirm",
            reason="parity_pass_full_confirm_eligible",
            selected_candidate="q8_0",
            full_confirm_eligible=True,
        )
    if full_confirm_passes(full):
        return FeasibilityPlan(
            terminal="select_gguf_q8_0",
            next_action="none",
            reason="full_confirm_pass",
            selected_candidate="q8_0",
            full_confirm_eligible=True,
        )
    return FeasibilityPlan(
        terminal="stop_too_slow",
        next_action="none",
        reason="full_confirm_failed",
        selected_candidate="q8_0",
        full_confirm_eligible=True,
    )


def assert_frozen_runtime_knobs(
    *,
    batch_size: int,
    normalize: bool,
    device: str,
    backend: str,
    pooling: str | None = None,
    n_gpu_layers: int | None = None,
    threads: int | None = None,
    threads_batch: int | None = None,
) -> None:
    if batch_size != FROZEN_BATCH_SIZE:
        raise ValueError(f"batch_size must be {FROZEN_BATCH_SIZE}")
    if normalize is not FROZEN_NORMALIZE:
        raise ValueError(f"normalize must be {FROZEN_NORMALIZE}")
    if device != FROZEN_DEVICE:
        raise ValueError(f"device must be {FROZEN_DEVICE!r}")
    if backend != FROZEN_BACKEND:
        raise ValueError(f"backend must be {FROZEN_BACKEND!r}")
    if pooling is not None and pooling != FROZEN_POOLING:
        raise ValueError(f"pooling must be {FROZEN_POOLING!r}")
    if n_gpu_layers is not None and n_gpu_layers != FROZEN_N_GPU_LAYERS:
        raise ValueError(f"n_gpu_layers must be {FROZEN_N_GPU_LAYERS}")
    if threads is not None and threads != FROZEN_THREADS:
        raise ValueError(f"threads must be {FROZEN_THREADS}")
    if threads_batch is not None and threads_batch != FROZEN_THREADS_BATCH:
        raise ValueError(f"threads_batch must be {FROZEN_THREADS_BATCH}")


def assert_transition_allowed(history: list[StageResult], action: NextAction) -> None:
    plan = plan_next(history)
    if plan.next_action != action:
        raise ValueError(
            f"transition refused: requested={action!r} planned={plan.next_action!r} "
            f"reason={plan.reason!r}"
        )


def refuse_hub_substitution(*, local_gguf_exists: bool, allow_download: bool) -> None:
    if allow_download:
        raise ValueError("Hub download / substitution is refused for CPU-GGUF-01")
    if not local_gguf_exists:
        raise ValueError("local pinned GGUF artifact missing")


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
    "EXPECTED_GGUF_BYTES",
    "EXPECTED_GGUF_FILENAME",
    "EXPECTED_GGUF_REPO_ID",
    "EXPECTED_GGUF_REVISION",
    "EXPECTED_GGUF_SHA256",
    "EXPECTED_SCREEN_CHUNK_IDS_DIGEST",
    "EXPERIMENT_ID",
    "FEASIBLE_MAX_MIN",
    "FROZEN_BACKEND",
    "FROZEN_BATCH_SIZE",
    "FROZEN_DEVICE",
    "FROZEN_NORMALIZE",
    "FROZEN_N_GPU_LAYERS",
    "FROZEN_POOLING",
    "FROZEN_QUANT",
    "FROZEN_THREADS",
    "FROZEN_THREADS_BATCH",
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
