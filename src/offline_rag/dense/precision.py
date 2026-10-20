"""Embedding execution-precision policy (16K-D D2).

Precision is non-semantic execution policy for this tranche and must not affect
embedding/index identity hashes. ``fp16`` is allowed only on resolved CUDA.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ConfiguredEmbeddingPrecision = Literal["native", "fp16"]
ResolvedEmbeddingPrecision = Literal["native", "fp16"]
PrecisionSelectionReason = Literal[
    "native_default",
    "explicit_native",
    "explicit_fp16_cuda",
]


@dataclass(frozen=True)
class EmbeddingPrecisionResolution:
    configured_precision: ConfiguredEmbeddingPrecision
    resolved_precision: ResolvedEmbeddingPrecision
    selection_reason: PrecisionSelectionReason
    resolved_device: Literal["cpu", "cuda"]


def resolve_embedding_precision(
    configured: ConfiguredEmbeddingPrecision | str,
    *,
    resolved_device: Literal["cpu", "cuda"] | str,
) -> EmbeddingPrecisionResolution:
    """Resolve precision policy against an already-resolved execution device."""
    policy = str(configured).strip().lower()
    if policy not in {"native", "fp16"}:
        raise ValueError(f"unsupported embedding precision policy: {configured!r}")
    device = str(resolved_device).strip().lower()
    if device not in {"cpu", "cuda"}:
        raise ValueError(f"unsupported resolved embedding device: {resolved_device!r}")
    configured_precision: ConfiguredEmbeddingPrecision = policy  # type: ignore[assignment]
    resolved: Literal["cpu", "cuda"] = device  # type: ignore[assignment]

    if configured_precision == "native":
        return EmbeddingPrecisionResolution(
            configured_precision="native",
            resolved_precision="native",
            selection_reason=(
                "native_default" if policy == "native" else "explicit_native"
            ),
            resolved_device=resolved,
        )

    # fp16
    if resolved != "cuda":
        from offline_rag.dense.embedder import EmbedderError

        raise EmbedderError(
            "FP16 embedding execution was requested, but the resolved embedding "
            "device is not CUDA. CPU + FP16 fails closed (no silent conversion "
            "or fallback)."
        )
    return EmbeddingPrecisionResolution(
        configured_precision="fp16",
        resolved_precision="fp16",
        selection_reason="explicit_fp16_cuda",
        resolved_device="cuda",
    )


def apply_fp16_after_load(model: object) -> dict[str, str | None]:
    """Convert a loaded SentenceTransformer model to FP16 once.

    Must be called after model construction and before the first encode.
    """
    import torch

    before: str | None = None
    after: str | None = None
    try:
        first = model[0] if len(model) else None  # type: ignore[index]
        auto_model = getattr(first, "auto_model", None)
        if auto_model is not None:
            param = next(auto_model.parameters(), None)
            if param is not None:
                before = str(param.dtype).removeprefix("torch.")
    except Exception:  # noqa: BLE001
        before = None

    half = getattr(model, "half", None)
    if not callable(half):
        from offline_rag.dense.embedder import EmbedderError

        raise EmbedderError(
            "FP16 embedding execution was requested, but the loaded model does "
            "not expose half() for deterministic post-load conversion."
        )
    half()

    try:
        first = model[0] if len(model) else None  # type: ignore[index]
        auto_model = getattr(first, "auto_model", None)
        if auto_model is not None:
            param = next(auto_model.parameters(), None)
            if param is not None:
                after = str(param.dtype).removeprefix("torch.")
    except Exception:  # noqa: BLE001
        after = "float16" if torch.float16 else None

    if after not in {"float16", "torch.float16"}:
        from offline_rag.dense.embedder import EmbedderError

        raise EmbedderError(
            "FP16 embedding conversion did not yield float16 parameters "
            f"(before={before!r}, after={after!r})."
        )
    return {"dtype_before": before, "dtype_after": after}


def is_cuda_resource_exhaustion(exc: BaseException) -> bool:
    """Heuristic: CUDA OOM / resource exhaustion under a correct-identity run."""
    name = type(exc).__name__
    text = f"{name}: {exc}".lower()
    needles = (
        "out of memory",
        "cuda out of memory",
        "cudaerror",
        "cudnn_status_alloc_failed",
        "cublas_status_alloc_failed",
        "resource exhausted",
        "insufficient memory",
    )
    if any(n in text for n in needles):
        return True
    # PyTorch CUDA OOM class name variants.
    if "outofmemory" in name.lower():
        return True
    return False


def classify_treatment_failure(
    exc: BaseException,
    *,
    identity_correct: bool,
) -> Literal["valid_negative_resource", "invalid"]:
    """Map an exception to D2 validity when identity is already decided."""
    if identity_correct and is_cuda_resource_exhaustion(exc):
        return "valid_negative_resource"
    return "invalid"


__all__ = [
    "ConfiguredEmbeddingPrecision",
    "EmbeddingPrecisionResolution",
    "PrecisionSelectionReason",
    "ResolvedEmbeddingPrecision",
    "apply_fp16_after_load",
    "classify_treatment_failure",
    "is_cuda_resource_exhaustion",
    "resolve_embedding_precision",
]
