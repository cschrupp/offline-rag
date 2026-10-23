"""P1 QualifiedEmbeddingRuntime lifecycle tests."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from offline_rag.dense.embedding_artifacts import (
    RepresentationInspection,
    RepresentationReadiness,
    RepresentationReasonCode,
)
from offline_rag.dense.embedding_runtime import (
    QualifiedEmbeddingRuntime,
    QualifiedEmbeddingRuntimeError,
    RuntimeFailureKind,
    RuntimeState,
)
from offline_rag.dense.execution_profile import (
    CPU_ONNX_FP32_V1,
    EmbeddingProfileResolution,
)


def _resolution() -> EmbeddingProfileResolution:
    return EmbeddingProfileResolution(
        configured_device="cpu",
        configured_precision="native",
        profile=CPU_ONNX_FP32_V1,
        selection_reason="explicit_cpu_onnx_fp32",
        cuda_available=False,
        torch_cuda_build=None,
        selected_representation_status="ready",
    )


def _rep() -> RepresentationInspection:
    return RepresentationInspection(
        representation_id="onnx_fp32_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ok",
        root=Path("/tmp"),
        instance_path=Path("/tmp"),
        graph_file_name="onnx/model.onnx",
    )


class _FakeBackend:
    def __init__(self, *, fail_init: bool = False, fail_exec: bool = False) -> None:
        if fail_init:
            raise RuntimeError("init boom")
        self.fail_exec = fail_exec
        self.calls = 0

    def embed_documents(self, texts):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail_exec:
            raise RuntimeError("exec boom")
        return [[0.1] * 8 for _ in texts]

    def embed_query(self, text):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail_exec:
            raise RuntimeError("exec boom")
        return [0.1] * 8

    def release(self) -> None:
        return None


def _runtime(factory) -> QualifiedEmbeddingRuntime:  # type: ignore[no-untyped-def]
    return QualifiedEmbeddingRuntime(
        profile_resolution=_resolution(),
        representation=_rep(),
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        dimension=8,
        normalize=True,
        query_text_contract="raw-query-v1",
        backend_factory=factory,
    )


def test_construction_unloaded_and_observe_does_not_load() -> None:
    """C1 + C7: clean construction; reading classification is passive."""
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        return _FakeBackend()

    rt = _runtime(factory)
    assert rt.state is RuntimeState.UNLOADED
    assert rt.failure_kind is None
    assert rt.failure_reason is None
    assert rt.observe_execution_facts() == {"dtype": None, "attention_backend": None}
    assert rt.state is RuntimeState.UNLOADED
    assert rt.failure_kind is None
    assert rt.failure_reason is None
    assert calls["n"] == 0
    assert rt.backend_factory_calls == 0


def test_first_call_loads_ready() -> None:
    """C2: successful load leaves failure_kind None."""
    rt = _runtime(lambda: _FakeBackend())
    out = rt.embed_query("q")
    assert len(out) == 8
    assert rt.state is RuntimeState.READY
    assert rt.failure_kind is None
    assert rt.failure_reason is None
    assert rt.backend_factory_calls == 1


def test_concurrent_first_calls_single_factory() -> None:
    barrier = threading.Barrier(2)
    started = threading.Event()

    class SlowBackend(_FakeBackend):
        def __init__(self) -> None:
            started.set()
            time.sleep(0.05)
            super().__init__()

    rt = _runtime(SlowBackend)
    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            results.append(rt.embed_query("q"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == 2
    assert rt.backend_factory_calls == 1
    assert rt.state is RuntimeState.READY
    assert rt.failure_kind is None


def test_init_failure_is_terminal() -> None:
    """C3 + C5: initialization failure classification is typed and immutable."""
    rt = _runtime(lambda: _FakeBackend(fail_init=True))
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="initialization failed"):
        rt.embed_query("q")
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.INITIALIZATION
    assert rt.failure_reason is not None
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="FAILED"):
        rt.embed_query("q")
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.INITIALIZATION
    assert rt.backend_factory_calls == 1


def test_deferred_heavy_init_failure_is_initialization() -> None:
    """IR-001 F001: heavy materialization after wrapper construct stays INITIALIZATION."""

    class DeferredHeavyBackend:
        def __init__(self) -> None:
            self.materialized = False

        def ensure_initialized(self) -> None:
            raise RuntimeError("heavy session construct failed")

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            raise AssertionError("encode must not run after init failure")

        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            raise AssertionError("encode must not run after init failure")

        def release(self) -> None:
            return None

    rt = _runtime(DeferredHeavyBackend)
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="initialization failed"):
        rt.embed_query("q")
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.INITIALIZATION
    assert "heavy session construct failed" in (rt.failure_reason or "")


def test_exec_failure_after_successful_heavy_init() -> None:
    """IR-001 F001: only post-READY encode failures are EXECUTION."""

    class HeavyThenExecFail:
        def __init__(self) -> None:
            self.ready = False

        def ensure_initialized(self) -> None:
            self.ready = True

        def embed_query(self, text):  # type: ignore[no-untyped-def]
            assert self.ready
            raise RuntimeError("encode boom")

        def embed_documents(self, texts):  # type: ignore[no-untyped-def]
            assert self.ready
            raise RuntimeError("encode boom")

        def release(self) -> None:
            return None

    rt = _runtime(HeavyThenExecFail)
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="execution failed"):
        rt.embed_query("q")
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.EXECUTION


def test_exec_failure_is_terminal() -> None:
    """C4 + C5: execution failure classification is typed and immutable."""
    rt = _runtime(lambda: _FakeBackend(fail_exec=True))
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="execution failed"):
        rt.embed_query("q")
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.EXECUTION
    assert rt.failure_reason is not None
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="FAILED"):
        rt.embed_documents(["a"])
    assert rt.state is RuntimeState.FAILED
    assert rt.failure_kind is RuntimeFailureKind.EXECUTION
    assert rt.backend_factory_calls == 1


def test_caller_validation_does_not_poison() -> None:
    """C6: caller validation must not set failure_kind or FAILED."""
    rt = _runtime(lambda: _FakeBackend())
    with pytest.raises(TypeError):
        rt.embed_query(123)  # type: ignore[arg-type]
    assert rt.state is RuntimeState.UNLOADED
    assert rt.failure_kind is None
    assert rt.failure_reason is None
    with pytest.raises(TypeError):
        rt.embed_documents("not-a-sequence")  # type: ignore[arg-type]
    assert rt.state is RuntimeState.UNLOADED
    assert rt.failure_kind is None
    assert rt.embed_query("ok")
    assert rt.state is RuntimeState.READY
    assert rt.failure_kind is None
    with pytest.raises(TypeError):
        rt.embed_documents(["ok", 1])  # type: ignore[list-item]
    assert rt.state is RuntimeState.READY
    assert rt.failure_kind is None


def test_close_does_not_manufacture_failure_kind() -> None:
    rt = _runtime(lambda: _FakeBackend())
    rt.embed_query("q")
    rt.close()
    assert rt.state is RuntimeState.CLOSED
    assert rt.failure_kind is None
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="CLOSED"):
        rt.embed_query("q")
    assert rt.failure_kind is None


def test_close_is_terminal() -> None:
    rt = _runtime(lambda: _FakeBackend())
    rt.embed_query("q")
    rt.close()
    assert rt.state is RuntimeState.CLOSED
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="CLOSED"):
        rt.embed_query("q")


def test_no_global_inference_mutex_attribute() -> None:
    rt = _runtime(lambda: _FakeBackend())
    assert not hasattr(rt, "_inference_lock")
    assert not hasattr(rt, "_encode_lock")
