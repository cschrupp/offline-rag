from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import offline_rag.dense.embedder as embedder_module
from offline_rag.dense.embedder import SentenceTransformersEmbedder
from offline_rag.dense.embedding_artifacts import (
    RepresentationInspection,
    RepresentationReadiness,
    RepresentationReasonCode,
)
from offline_rag.dense.embedding_runtime import (
    QualifiedEmbeddingRuntime,
    QualifiedEmbeddingRuntimeError,
    RuntimeState,
)
from offline_rag.dense.execution_profile import (
    CUDA_FP16_V1,
    EmbeddingProfileResolution,
)
from offline_rag.dense.failure import CudaMemoryExhaustedError, is_cuda_oom_error
from offline_rag.dense.profiling import (
    DenseProfileCollector,
    dense_encode_batch_context,
    dense_profile_session,
)


class AcceleratorError(RuntimeError):
    pass


class _Row:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return list(self.values)


class _EncodeModel:
    def __init__(self, *, oom_batch_sizes: set[int] | None = None) -> None:
        self.oom_batch_sizes = oom_batch_sizes or set()
        self.calls: list[tuple[int, list[str], int]] = []

    def encode(
        self,
        payloads: list[str],
        *,
        batch_size: int,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> list[_Row]:
        del normalize_embeddings, convert_to_numpy, show_progress_bar
        self.calls.append((batch_size, list(payloads), id(payloads)))
        if batch_size in self.oom_batch_sizes:
            raise AcceleratorError("CUDA error: out of memory")
        return [_Row([float(index), 1.0]) for index, _ in enumerate(payloads)]


def _embedder(
    *, device: str = "cuda", oom_batch_sizes: set[int] | None = None
) -> tuple[SentenceTransformersEmbedder, _EncodeModel]:
    embedder = object.__new__(SentenceTransformersEmbedder)
    embedder.device = device
    embedder.configured_batch_size = 32
    embedder.effective_batch_size = 32
    embedder.batch_size = 32
    embedder.document_instruction = "document: "
    embedder.normalize = False
    embedder.dimension = 2
    embedder._model = _EncodeModel(oom_batch_sizes=oom_batch_sizes)
    return embedder, embedder._model


def _oom() -> AcceleratorError:
    return AcceleratorError("CUDA error: out of memory")


@pytest.mark.parametrize(
    ("failed_batch_sizes", "expected_attempts", "expected_effective"),
    [
        (set(), [32], 32),
        ({32}, [32, 16], 16),
        ({32, 16}, [32, 16, 8], 8),
        ({32, 16, 8}, [32, 16, 8, 4], 4),
    ],
)
def test_cuda_adaptive_batch_ladder_and_payload_identity(
    failed_batch_sizes: set[int],
    expected_attempts: list[int],
    expected_effective: int,
    monkeypatch,
) -> None:
    embedder, model = _embedder(oom_batch_sizes=failed_batch_sizes)
    cleanup_calls: list[str] = []

    def cleanup(exc: BaseException | None = None) -> bool:
        del exc
        cleanup_calls.append("cleanup")
        return True

    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", cleanup)
    texts = ["first", "second", "third"]
    vectors = embedder.embed_documents(texts)

    assert [call[0] for call in model.calls] == expected_attempts
    assert len(vectors) == len(texts)
    assert vectors == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]
    assert embedder.configured_batch_size == 32
    assert embedder.effective_batch_size == expected_effective
    assert embedder.batch_size == expected_effective
    assert all(call[1] == ["document: first", "document: second", "document: third"] for call in model.calls)
    assert len({call[2] for call in model.calls}) == 1
    assert len(cleanup_calls) == len(expected_attempts) - 1


def test_cleanup_occurs_between_oom_attempts_and_cleanup_failure_is_ignored(
    monkeypatch,
) -> None:
    embedder, model = _embedder(oom_batch_sizes={32})
    events: list[str] = []

    def encode(*args: Any, **kwargs: Any) -> list[_Row]:
        events.append(f"encode-{kwargs['batch_size']}")
        return original_encode(*args, **kwargs)

    original_encode = model.encode
    model.encode = encode  # type: ignore[method-assign]

    def failed_cleanup(exc: BaseException | None = None) -> bool:
        del exc
        events.append("cleanup")
        return False

    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", failed_cleanup)
    embedder.embed_documents(["payload"])
    assert events == ["encode-32", "cleanup", "encode-16"]


def test_exhausted_cuda_ladder_raises_bounded_class_and_keeps_batch_four(
    monkeypatch,
) -> None:
    embedder, model = _embedder(oom_batch_sizes={32, 16, 8, 4})
    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", lambda exc=None: True)

    with pytest.raises(CudaMemoryExhaustedError) as error:
        embedder.embed_documents(["same logical input"])

    assert [call[0] for call in model.calls] == [32, 16, 8, 4]
    assert error.value.configured_batch_size == 32
    assert error.value.final_batch_size == 4
    assert embedder.effective_batch_size == 4
    assert str(error.value) == "CUDA embedding memory exhausted after bounded batch recovery"


def test_non_oom_cuda_exception_is_not_retried(monkeypatch) -> None:
    embedder, model = _embedder()
    model.oom_batch_sizes.clear()

    def fail(*args: Any, **kwargs: Any) -> list[_Row]:
        del args, kwargs
        raise AcceleratorError("CUDA illegal memory access")

    model.encode = fail  # type: ignore[method-assign]
    cleanup_calls: list[bool] = []
    monkeypatch.setattr(
        embedder_module,
        "cleanup_cuda_after_oom",
        lambda exc=None: cleanup_calls.append(True) or True,
    )
    with pytest.raises(AcceleratorError, match="illegal memory access"):
        embedder.embed_documents(["text"])
    assert len(model.calls) == 0
    assert cleanup_calls == []


def test_cpu_embedder_does_not_use_cuda_adaptation(monkeypatch) -> None:
    embedder, model = _embedder(device="cpu", oom_batch_sizes={32})
    cleanup_calls: list[bool] = []
    monkeypatch.setattr(
        embedder_module,
        "cleanup_cuda_after_oom",
        lambda exc=None: cleanup_calls.append(True) or True,
    )
    with pytest.raises(AcceleratorError, match="out of memory"):
        embedder.embed_documents(["text"])
    assert [call[0] for call in model.calls] == [32]
    assert cleanup_calls == []


def test_recovered_effective_batch_is_monotonic_and_new_embedder_resets(
    monkeypatch,
) -> None:
    embedder, model = _embedder(oom_batch_sizes={32})
    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", lambda exc=None: True)
    embedder.embed_documents(["first operation"])
    embedder.embed_documents(["second operation"])
    assert [call[0] for call in model.calls] == [32, 16, 16]

    fresh, fresh_model = _embedder()
    fresh.embed_documents(["fresh process runtime"])
    assert [call[0] for call in fresh_model.calls] == [32]


def test_oom_detector_is_specific_and_follows_exception_causes() -> None:
    assert is_cuda_oom_error(AcceleratorError("CUDA error: out of memory"))
    assert is_cuda_oom_error(RuntimeError("CUDA_ERROR_OUT_OF_MEMORY"))
    assert is_cuda_oom_error(RuntimeError("cudaErrorMemoryAllocation"))
    torch_oom_type = type(
        "OutOfMemoryError",
        (RuntimeError,),
        {"__module__": "torch.cuda"},
    )
    assert is_cuda_oom_error(torch_oom_type("allocation failed"))

    outer = RuntimeError("wrapped backend failure")
    outer.__cause__ = RuntimeError("CUDA_ERROR_OUT_OF_MEMORY")
    assert is_cuda_oom_error(outer)

    assert not is_cuda_oom_error(AcceleratorError("CUDA illegal memory access"))
    assert not is_cuda_oom_error(AcceleratorError("device-side assert triggered"))
    assert not is_cuda_oom_error(AcceleratorError("unknown accelerator failure"))
    assert not is_cuda_oom_error(RuntimeError("generic model failure"))


def test_failure_attempt_profile_contains_hashes_and_no_private_text(monkeypatch) -> None:
    embedder, _model = _embedder(oom_batch_sizes={32})
    monkeypatch.setenv("OFFLINE_RAG_DIAG_DENSE_PROFILE", "1")
    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", lambda exc=None: True)
    monkeypatch.setattr(
        SentenceTransformersEmbedder,
        "_cuda_attempt_snapshot",
        staticmethod(
            lambda: {
                "allocator": {"allocated_bytes": 12, "reserved_bytes": 24},
                "global_memory": {"free_bytes": 100, "total_bytes": 200},
                "external_gpu": {"status": "observed"},
            }
        ),
    )
    collector = DenseProfileCollector()
    with dense_profile_session(collector), dense_encode_batch_context(
        batch_index=7,
        item_count=2,
        token_counts=[3, 5],
        max_sequence_length=8,
        chunk_ids=["chunk-private-a", "chunk-private-b"],
    ):
        embedder.embed_documents(["private text alpha", "private text beta"])

    assert [item["outcome"] for item in collector.encode_attempts] == [
        "cuda_oom",
        "success",
    ]
    attempt = collector.encode_attempts[0]
    assert attempt["logical_outer_batch_index"] == 7
    assert attempt["effective_batch_size"] == 32
    assert attempt["next_effective_batch_size"] == 16
    assert attempt["token_length_stats"]["min"] == 3
    assert attempt["aggregate_input_tokens"] == 8
    assert attempt["padded_token_workload"] == 16
    assert attempt["cuda_memory_before"]["free_bytes"] == 100
    serialized = repr(collector.summarize())
    assert "private text" not in serialized
    assert "chunk-private" not in serialized


def _cuda_runtime(factory) -> QualifiedEmbeddingRuntime:
    resolution = EmbeddingProfileResolution(
        configured_device="auto",
        configured_precision="native",
        profile=CUDA_FP16_V1,
        selection_reason="auto_cuda_fp16",
        cuda_available=True,
        torch_cuda_build="13.0",
        selected_representation_status="ready",
    )
    representation = RepresentationInspection(
        representation_id="torch_st_v1",
        readiness=RepresentationReadiness.READY,
        reason_code=RepresentationReasonCode.OK,
        reason="ready",
        root=Path("/tmp"),
        instance_path=Path("/tmp"),
        graph_file_name=None,
    )
    return QualifiedEmbeddingRuntime(
        profile_resolution=resolution,
        representation=representation,
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="revision",
        dimension=2,
        normalize=False,
        query_text_contract="raw-query-v1",
        backend_factory=factory,
    )


def test_runtime_stays_ready_after_recovery_and_preserves_effective_batch(
    monkeypatch,
) -> None:
    backend, model = _embedder(oom_batch_sizes={32})
    monkeypatch.setattr(embedder_module, "cleanup_cuda_after_oom", lambda exc=None: True)
    runtime = _cuda_runtime(lambda: backend)
    vectors = runtime.embed_documents(["runtime payload"])

    assert len(vectors) == 1
    assert runtime.state is RuntimeState.READY
    assert runtime.configured_batch_size == 32
    assert runtime.effective_batch_size == 16
    assert [call[0] for call in model.calls] == [32, 16]


def test_runtime_exhaustion_is_terminal_and_never_constructs_cpu_fallback() -> None:
    factories: list[str] = []

    class ExhaustedBackend:
        configured_batch_size = 32
        effective_batch_size = 4

        def ensure_initialized(self) -> None:
            return None

        def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
            raise CudaMemoryExhaustedError(
                configured_batch_size=32,
                final_batch_size=4,
            )

        def release(self) -> None:
            return None

    def factory() -> ExhaustedBackend:
        factories.append("cuda")
        return ExhaustedBackend()

    runtime = _cuda_runtime(factory)
    with pytest.raises(CudaMemoryExhaustedError):
        runtime.embed_documents(["failed"])
    assert runtime.state is RuntimeState.FAILED
    assert runtime.effective_batch_size == 4
    assert factories == ["cuda"]
    with pytest.raises(QualifiedEmbeddingRuntimeError, match="FAILED"):
        runtime.embed_documents(["no resurrection"])
    assert factories == ["cuda"]
