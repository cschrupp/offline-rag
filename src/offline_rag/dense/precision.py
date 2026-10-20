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
    Post-conversion dtype must be observably float16; never infer success.
    """
    from offline_rag.dense.embedder import EmbedderError

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
        raise EmbedderError(
            "FP16 embedding execution was requested, but the loaded model does "
            "not expose half() for deterministic post-load conversion."
        )
    half()

    try:
        first = model[0] if len(model) else None  # type: ignore[index]
        auto_model = getattr(first, "auto_model", None)
        if auto_model is None:
            raise EmbedderError(
                "FP16 embedding conversion completed but post-conversion dtype "
                f"could not be observed (missing auto_model; before={before!r})."
            )
        param = next(auto_model.parameters(), None)
        if param is None:
            raise EmbedderError(
                "FP16 embedding conversion completed but post-conversion dtype "
                f"could not be observed (no parameters; before={before!r})."
            )
        after = str(param.dtype).removeprefix("torch.")
    except EmbedderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EmbedderError(
            "FP16 embedding conversion completed but post-conversion dtype "
            f"could not be observed/verified (before={before!r}): "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if after not in {"float16", "torch.float16"}:
        raise EmbedderError(
            "FP16 embedding conversion did not yield float16 parameters "
            f"(before={before!r}, after={after!r})."
        )
    return {"dtype_before": before, "dtype_after": after}


def is_cuda_resource_exhaustion(exc: BaseException) -> bool:
    """True only for CUDA memory/resource exhaustion — not generic CUDA errors."""
    name = type(exc).__name__
    name_l = name.lower()
    msg = str(exc).lower()
    text = f"{name}: {exc}".lower()

    # Class-name OOM (e.g. torch.cuda.OutOfMemoryError).
    if "outofmemory" in name_l:
        return True

    # Explicit allocator / memory exhaustion status codes.
    if (
        "cublas_status_alloc_failed" in text
        or "cudnn_status_alloc_failed" in text
    ):
        return True

    if "resource exhausted" in msg or "insufficient memory" in msg:
        return True

    if "cuda out of memory" in msg:
        return True

    # Bare "out of memory" only with CUDA-flavored context (not generic CUDAError).
    if "out of memory" in msg and (
        "cuda" in name_l or "cuda" in msg or "cublas" in msg or "cudnn" in msg
    ):
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
