"""Embedding execution-device policy resolution (Slice 16L).

CPU vs CUDA is non-semantic execution policy and must not affect index identity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

ConfiguredEmbeddingDevice = Literal["auto", "cpu", "cuda"]
ResolvedEmbeddingDevice = Literal["cpu", "cuda"]
SelectionReason = Literal[
    "explicit_cpu",
    "explicit_cuda",
    "cuda_available",
    "cuda_unavailable",
    "cuda_probe_failed",
]

CudaProbeResult = tuple[bool, str | None, bool]
# (cuda_available, torch_cuda_build, probe_raised)


@dataclass(frozen=True)
class EmbeddingDeviceResolution:
    configured_device: ConfiguredEmbeddingDevice
    resolved_device: ResolvedEmbeddingDevice
    cuda_available: bool
    torch_cuda_build: str | None
    selection_reason: SelectionReason


def probe_torch_cuda() -> CudaProbeResult:
    """Probe CUDA via PyTorch only (no nvidia-smi / NVML).

    Returns ``(available, torch_cuda_build, probe_raised)``.
    ``torch_cuda_build`` is ``None`` for CPU-only PyTorch builds.
    """
    import torch

    build = getattr(getattr(torch, "version", None), "cuda", None)
    torch_cuda_build = str(build) if build else None
    try:
        available = bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 — optional accelerator probe must not crash AUTO
        return False, torch_cuda_build, True
    return available, torch_cuda_build, False


def resolve_embedding_device(
    configured: ConfiguredEmbeddingDevice | str,
    *,
    probe: Callable[[], CudaProbeResult] | None = None,
) -> EmbeddingDeviceResolution:
    """Resolve configured auto/cpu/cuda into a concrete execution device."""
    policy = str(configured).strip().lower()
    if policy not in {"auto", "cpu", "cuda"}:
        raise ValueError(f"unsupported embedding device policy: {configured!r}")
    configured_device: ConfiguredEmbeddingDevice = policy  # type: ignore[assignment]

    probe_fn = probe or probe_torch_cuda
    cuda_available, torch_cuda_build, probe_raised = probe_fn()

    if configured_device == "cpu":
        return EmbeddingDeviceResolution(
            configured_device="cpu",
            resolved_device="cpu",
            cuda_available=cuda_available,
            torch_cuda_build=torch_cuda_build,
            selection_reason="explicit_cpu",
        )

    if configured_device == "cuda":
        if probe_raised or not cuda_available:
            from offline_rag.dense.embedder import EmbedderError

            raise EmbedderError(
                "CUDA embedding execution was requested, but CUDA is unavailable."
            )
        return EmbeddingDeviceResolution(
            configured_device="cuda",
            resolved_device="cuda",
            cuda_available=True,
            torch_cuda_build=torch_cuda_build,
            selection_reason="explicit_cuda",
        )

    # AUTO
    if probe_raised:
        return EmbeddingDeviceResolution(
            configured_device="auto",
            resolved_device="cpu",
            cuda_available=False,
            torch_cuda_build=torch_cuda_build,
            selection_reason="cuda_probe_failed",
        )
    if cuda_available:
        return EmbeddingDeviceResolution(
            configured_device="auto",
            resolved_device="cuda",
            cuda_available=True,
            torch_cuda_build=torch_cuda_build,
            selection_reason="cuda_available",
        )
    return EmbeddingDeviceResolution(
        configured_device="auto",
        resolved_device="cpu",
        cuda_available=False,
        torch_cuda_build=torch_cuda_build,
        selection_reason="cuda_unavailable",
    )


def cuda_availability_reason(
    *,
    cuda_available: bool | None,
    torch_cuda_build: str | None,
    selection_reason: str | None,
) -> str | None:
    """Map runtime diagnostics to a product-safe CUDA unavailability reason."""
    if cuda_available is True:
        return None
    if selection_reason == "cuda_probe_failed":
        return "cuda_probe_failed"
    if torch_cuda_build is None:
        return "pytorch_cpu_only"
    return "cuda_device_unavailable"


__all__ = [
    "ConfiguredEmbeddingDevice",
    "CudaProbeResult",
    "EmbeddingDeviceResolution",
    "ResolvedEmbeddingDevice",
    "SelectionReason",
    "cuda_availability_reason",
    "probe_torch_cuda",
    "resolve_embedding_device",
]
