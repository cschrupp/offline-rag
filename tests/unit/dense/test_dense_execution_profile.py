"""P1 qualified execution profile resolver matrix."""

from __future__ import annotations

import pytest

from offline_rag.dense.embedder import EmbedderError
from offline_rag.dense.execution_profile import (
    CPU_ONNX_FP32_V1,
    CUDA_FP16_V1,
    PROFILES,
    resolve_qualified_embedding_profile,
)


def test_closed_profile_vocabulary() -> None:
    assert set(PROFILES) == {"cuda_fp16_v1", "cpu_onnx_fp32_v1"}
    assert "qint8" not in PROFILES
    assert "openvino" not in str(PROFILES).lower()
    assert "gguf" not in str(PROFILES).lower()


def test_cpu_native_selects_onnx_even_on_cuda_host() -> None:
    res = resolve_qualified_embedding_profile(
        "cpu",
        "native",
        probe=lambda: (True, "12.8", False),
    )
    assert res.profile is CPU_ONNX_FP32_V1
    assert res.selection_reason == "explicit_cpu_onnx_fp32"
    assert res.cuda_available is True


def test_cpu_fp16_errors() -> None:
    with pytest.raises(EmbedderError, match="fp16"):
        resolve_qualified_embedding_profile(
            "cpu",
            "fp16",
            probe=lambda: (True, "12.8", False),
        )


def test_cuda_native_and_fp16_select_cuda_fp16() -> None:
    for precision in ("native", "fp16"):
        res = resolve_qualified_embedding_profile(
            "cuda",
            precision,
            probe=lambda: (True, "12.8", False),
        )
        assert res.profile is CUDA_FP16_V1
        assert res.selection_reason == "explicit_cuda_fp16"


def test_cuda_without_cuda_errors() -> None:
    with pytest.raises(EmbedderError, match="CUDA is unavailable"):
        resolve_qualified_embedding_profile(
            "cuda",
            "native",
            probe=lambda: (False, "12.8", False),
        )
    with pytest.raises(EmbedderError, match="CUDA is unavailable"):
        resolve_qualified_embedding_profile(
            "cuda",
            "fp16",
            probe=lambda: (False, None, True),
        )


def test_auto_native_with_cuda() -> None:
    res = resolve_qualified_embedding_profile(
        "auto",
        "native",
        probe=lambda: (True, "12.8", False),
    )
    assert res.profile is CUDA_FP16_V1
    assert res.selection_reason == "auto_cuda_fp16"


def test_auto_native_without_cuda() -> None:
    res = resolve_qualified_embedding_profile(
        "auto",
        "native",
        probe=lambda: (False, "12.8", False),
    )
    assert res.profile is CPU_ONNX_FP32_V1
    assert res.selection_reason == "auto_cpu_onnx_fp32_cuda_unavailable"


def test_auto_native_probe_failure() -> None:
    res = resolve_qualified_embedding_profile(
        "auto",
        "native",
        probe=lambda: (False, "12.8", True),
    )
    assert res.profile is CPU_ONNX_FP32_V1
    assert res.selection_reason == "auto_cpu_onnx_fp32_cuda_probe_failed"


def test_auto_fp16_with_cuda() -> None:
    res = resolve_qualified_embedding_profile(
        "auto",
        "fp16",
        probe=lambda: (True, "12.8", False),
    )
    assert res.profile is CUDA_FP16_V1


def test_auto_fp16_without_cuda_errors() -> None:
    with pytest.raises(EmbedderError, match="fp16"):
        resolve_qualified_embedding_profile(
            "auto",
            "fp16",
            probe=lambda: (False, "12.8", False),
        )
    with pytest.raises(EmbedderError, match="fp16"):
        resolve_qualified_embedding_profile(
            "auto",
            "fp16",
            probe=lambda: (False, None, True),
        )
