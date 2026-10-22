"""Qualified dual-backend embedding execution profiles (P1).

Closed production vocabulary only: ``cuda_fp16_v1`` and ``cpu_onnx_fp32_v1``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from offline_rag.dense.device import (
    ConfiguredEmbeddingDevice,
    CudaProbeResult,
    probe_torch_cuda,
)

EmbeddingExecutionProfileId = Literal["cuda_fp16_v1", "cpu_onnx_fp32_v1"]
EmbeddingRepresentationId = Literal["torch_st_v1", "onnx_fp32_v1"]
BackendFamily = Literal["sentence_transformers_torch", "sentence_transformers_onnx"]
ProfileSelectionReason = Literal[
    "explicit_cpu_onnx_fp32",
    "explicit_cuda_fp16",
    "auto_cuda_fp16",
    "auto_cpu_onnx_fp32_cuda_unavailable",
    "auto_cpu_onnx_fp32_cuda_probe_failed",
]


@dataclass(frozen=True)
class EmbeddingExecutionProfile:
    profile_id: EmbeddingExecutionProfileId
    representation_id: EmbeddingRepresentationId
    backend_family: BackendFamily
    device: Literal["cpu", "cuda"]
    precision: Literal["fp16", "fp32"]
    provider: str | None
    batch_size: int
    runtime_options: dict[str, Any]


CUDA_FP16_V1 = EmbeddingExecutionProfile(
    profile_id="cuda_fp16_v1",
    representation_id="torch_st_v1",
    backend_family="sentence_transformers_torch",
    device="cuda",
    precision="fp16",
    provider=None,
    batch_size=32,
    runtime_options={},
)

CPU_ONNX_FP32_V1 = EmbeddingExecutionProfile(
    profile_id="cpu_onnx_fp32_v1",
    representation_id="onnx_fp32_v1",
    backend_family="sentence_transformers_onnx",
    device="cpu",
    precision="fp32",
    provider="CPUExecutionProvider",
    batch_size=32,
    runtime_options={
        "ort_intra_op_threads": 8,
        "ort_inter_op_threads": 1,
    },
)

PROFILES: dict[EmbeddingExecutionProfileId, EmbeddingExecutionProfile] = {
    "cuda_fp16_v1": CUDA_FP16_V1,
    "cpu_onnx_fp32_v1": CPU_ONNX_FP32_V1,
}


@dataclass(frozen=True)
class EmbeddingProfileResolution:
    configured_device: ConfiguredEmbeddingDevice
    configured_precision: Literal["native", "fp16"]
    profile: EmbeddingExecutionProfile
    selection_reason: ProfileSelectionReason
    cuda_available: bool
    torch_cuda_build: str | None
    selected_representation_status: str | None = None


def resolve_qualified_embedding_profile(
    configured_device: ConfiguredEmbeddingDevice | str,
    configured_precision: Literal["native", "fp16"] | str,
    *,
    probe: Callable[[], CudaProbeResult] | None = None,
) -> EmbeddingProfileResolution:
    """Resolve effective config + hardware into exactly one qualified profile.

    Fail closed on unauthorized combinations. Never silently fall back after
    selecting a profile.
    """
    from offline_rag.dense.embedder import EmbedderError

    device_policy = str(configured_device).strip().lower()
    if device_policy not in {"auto", "cpu", "cuda"}:
        raise ValueError(f"unsupported embedding device policy: {configured_device!r}")
    precision_policy = str(configured_precision).strip().lower()
    if precision_policy not in {"native", "fp16"}:
        raise ValueError(
            f"unsupported embedding precision policy: {configured_precision!r}"
        )
    configured: ConfiguredEmbeddingDevice = device_policy  # type: ignore[assignment]
    configured_prec: Literal["native", "fp16"] = precision_policy  # type: ignore[assignment]

    probe_fn = probe or probe_torch_cuda
    cuda_available, torch_cuda_build, probe_raised = probe_fn()
    cuda_usable = bool(cuda_available) and not probe_raised

    if configured == "cpu":
        if configured_prec == "fp16":
            raise EmbedderError(
                "CPU embedding execution with precision='fp16' is not authorized "
                "under the dual-backend architecture (cpu_onnx_fp32_v1 is FP32 only)."
            )
        return EmbeddingProfileResolution(
            configured_device="cpu",
            configured_precision=configured_prec,
            profile=CPU_ONNX_FP32_V1,
            selection_reason="explicit_cpu_onnx_fp32",
            cuda_available=cuda_available and not probe_raised,
            torch_cuda_build=torch_cuda_build,
        )

    if configured == "cuda":
        if not cuda_usable:
            raise EmbedderError(
                "CUDA embedding execution was requested, but CUDA is unavailable."
            )
        return EmbeddingProfileResolution(
            configured_device="cuda",
            configured_precision=configured_prec,
            profile=CUDA_FP16_V1,
            selection_reason="explicit_cuda_fp16",
            cuda_available=True,
            torch_cuda_build=torch_cuda_build,
        )

    # AUTO
    if configured_prec == "fp16":
        if not cuda_usable:
            raise EmbedderError(
                "AUTO embedding with precision='fp16' requires usable CUDA; "
                "refusing CPU fallback for fp16."
            )
        return EmbeddingProfileResolution(
            configured_device="auto",
            configured_precision=configured_prec,
            profile=CUDA_FP16_V1,
            selection_reason="auto_cuda_fp16",
            cuda_available=True,
            torch_cuda_build=torch_cuda_build,
        )

    # AUTO + native
    if cuda_usable:
        return EmbeddingProfileResolution(
            configured_device="auto",
            configured_precision=configured_prec,
            profile=CUDA_FP16_V1,
            selection_reason="auto_cuda_fp16",
            cuda_available=True,
            torch_cuda_build=torch_cuda_build,
        )
    if probe_raised:
        return EmbeddingProfileResolution(
            configured_device="auto",
            configured_precision=configured_prec,
            profile=CPU_ONNX_FP32_V1,
            selection_reason="auto_cpu_onnx_fp32_cuda_probe_failed",
            cuda_available=False,
            torch_cuda_build=torch_cuda_build,
        )
    return EmbeddingProfileResolution(
        configured_device="auto",
        configured_precision=configured_prec,
        profile=CPU_ONNX_FP32_V1,
        selection_reason="auto_cpu_onnx_fp32_cuda_unavailable",
        cuda_available=False,
        torch_cuda_build=torch_cuda_build,
    )


__all__ = [
    "CPU_ONNX_FP32_V1",
    "CUDA_FP16_V1",
    "PROFILES",
    "BackendFamily",
    "EmbeddingExecutionProfile",
    "EmbeddingExecutionProfileId",
    "EmbeddingProfileResolution",
    "EmbeddingRepresentationId",
    "ProfileSelectionReason",
    "resolve_qualified_embedding_profile",
]
