"""Process-owned qualified dual-backend embedding runtime (P1)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from offline_rag.core.ids import SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT
from offline_rag.dense.embedding_artifacts import RepresentationInspection
from offline_rag.dense.execution_profile import EmbeddingProfileResolution
from offline_rag.dense.failure import CudaMemoryExhaustedError
from offline_rag.dense.onnx_embedder import SentenceTransformersOnnxEmbedder


class RuntimeState(StrEnum):
    UNLOADED = "UNLOADED"
    LOADING = "LOADING"
    READY = "READY"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class RuntimeFailureKind(StrEnum):
    """Typed discriminator for terminal FAILED transitions only.

    Answers which accepted runtime transition failed. Does not classify
    CUDA/OOM/provider/user-input/retryability.
    """

    INITIALIZATION = "initialization"
    EXECUTION = "execution"


class QualifiedEmbeddingRuntimeError(RuntimeError):
    """Terminal or construction failure for the qualified runtime."""


class QualifiedEmbeddingRuntime:
    """Lazy Embedder that binds one qualified profile for the process lifetime."""

    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT

    def __init__(
        self,
        *,
        profile_resolution: EmbeddingProfileResolution,
        representation: RepresentationInspection,
        model_id: str,
        model_revision: str,
        dimension: int,
        normalize: bool,
        query_text_contract: str,
        backend_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.profile_resolution = profile_resolution
        self.profile = profile_resolution.profile
        self.representation = representation
        self.model_id = model_id
        self.model_revision = model_revision
        self.dimension = dimension
        self.normalize = normalize
        self.query_text_contract = query_text_contract

        self.configured_device = profile_resolution.configured_device
        self.configured_precision = profile_resolution.configured_precision
        self.resolved_device = self.profile.device
        self.device = self.profile.device
        self.resolved_precision = self.profile.precision
        self.cuda_available = profile_resolution.cuda_available
        self.torch_cuda_build = profile_resolution.torch_cuda_build
        self.device_selection_reason = profile_resolution.selection_reason
        self.precision_selection_reason = profile_resolution.selection_reason
        self.profile_id = self.profile.profile_id
        self.representation_id = self.profile.representation_id
        self.batch_size = self.profile.batch_size
        self.configured_batch_size = self.profile.batch_size
        self.effective_batch_size = self.profile.batch_size
        self.last_execution_batch_sizes: list[int] | None = None
        self.last_execution_padded_token_workload: int | None = None

        self._state = RuntimeState.UNLOADED
        self._backend: Any | None = None
        self._failure: str | None = None
        self._failure_kind: RuntimeFailureKind | None = None
        self._init_lock = threading.Lock()
        self._backend_factory_calls = 0
        self._backend_factory = backend_factory

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def backend_factory_calls(self) -> int:
        return self._backend_factory_calls

    @property
    def failure_reason(self) -> str | None:
        return self._failure

    @property
    def failure_kind(self) -> RuntimeFailureKind | None:
        return self._failure_kind

    def observe_execution_facts(self) -> dict[str, str | None]:
        """Observability must not load the backend."""
        facts: dict[str, str | None] = {"dtype": None, "attention_backend": None}
        if self._state != RuntimeState.READY or self._backend is None:
            return facts
        observe = getattr(self._backend, "observe_execution_facts", None)
        if callable(observe):
            try:
                observed = observe()
            except Exception:  # noqa: BLE001
                return facts
            if isinstance(observed, dict):
                dtype = observed.get("dtype")
                attention = observed.get("attention_backend")
                if dtype is not None:
                    facts["dtype"] = str(dtype)
                if attention is not None:
                    facts["attention_backend"] = str(attention)
        return facts

    def _ensure_ready(self) -> Any:
        if self._state is RuntimeState.CLOSED:
            raise QualifiedEmbeddingRuntimeError(
                "qualified embedding runtime is CLOSED"
            )
        if self._state is RuntimeState.FAILED:
            raise QualifiedEmbeddingRuntimeError(
                f"qualified embedding runtime is FAILED: {self._failure}"
            )
        if self._state is RuntimeState.READY and self._backend is not None:
            return self._backend

        with self._init_lock:
            if self._state is RuntimeState.CLOSED:
                raise QualifiedEmbeddingRuntimeError(
                    "qualified embedding runtime is CLOSED"
                )
            if self._state is RuntimeState.FAILED:
                raise QualifiedEmbeddingRuntimeError(
                    f"qualified embedding runtime is FAILED: {self._failure}"
                )
            if self._state is RuntimeState.READY and self._backend is not None:
                return self._backend

            self._state = RuntimeState.LOADING
            try:
                self._backend_factory_calls += 1
                if self._backend_factory is not None:
                    backend = self._backend_factory()
                else:
                    backend = self._default_construct_backend()
                # Heavy model/session materialization belongs in LOADING.
                # Lightweight wrapper construction alone must not flip READY.
                self._materialize_backend(backend)
                self._backend = backend
                self._state = RuntimeState.READY
                return backend
            except Exception as exc:
                self._failure = f"{type(exc).__name__}: {exc}"
                self._failure_kind = RuntimeFailureKind.INITIALIZATION
                self._backend = None
                self._state = RuntimeState.FAILED
                raise QualifiedEmbeddingRuntimeError(
                    f"qualified embedding backend initialization failed: {self._failure}"
                ) from exc

    @staticmethod
    def _materialize_backend(backend: Any) -> None:
        """Run the backend's heavy initialization while still LOADING.

        Prefers an explicit ``ensure_initialized`` hook; falls back to ``_load``
        for the accepted ST/ONNX backends. Backends with no heavy phase are no-ops.
        """
        ensure = getattr(backend, "ensure_initialized", None)
        if callable(ensure):
            ensure()
            return
        load = getattr(backend, "_load", None)
        if callable(load):
            load()

    def _default_construct_backend(self) -> Any:
        profile = self.profile
        if profile.profile_id == "cpu_onnx_fp32_v1":
            return SentenceTransformersOnnxEmbedder(
                representation=self.representation,
                model_id=self.model_id,
                model_revision=self.model_revision,
                dimension=self.dimension,
                normalize=self.normalize,
                batch_size=profile.batch_size,
                query_text_contract=self.query_text_contract,
            )
        if profile.profile_id == "cuda_fp16_v1":
            from offline_rag.dense.embedder import SentenceTransformersEmbedder

            instance = self.representation.instance_path
            if instance is None:
                raise QualifiedEmbeddingRuntimeError(
                    "cuda_fp16_v1 requires torch_st_v1 instance_path"
                )
            return SentenceTransformersEmbedder(
                model_path=Path(instance),
                model_id=self.model_id,
                model_revision=self.model_revision,
                dimension=self.dimension,
                normalize=self.normalize,
                device="cuda",
                batch_size=profile.batch_size,
                query_instruction=None,
                document_instruction=None,
                expected_dimension=self.dimension,
                query_text_contract=self.query_text_contract,
                configured_device=self.configured_device,
                cuda_available=True,
                torch_cuda_build=self.torch_cuda_build,
                device_selection_reason=str(self.device_selection_reason),
                configured_precision=self.configured_precision,
                resolved_precision="fp16",
                precision_selection_reason="explicit_fp16_cuda",
            )
        raise QualifiedEmbeddingRuntimeError(
            f"unsupported profile_id: {profile.profile_id}"
        )

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
            raise TypeError("embed_documents requires a sequence of strings")
        # Caller-side validation before backend execution must not poison runtime.
        for item in texts:
            if not isinstance(item, str):
                raise TypeError("embed_documents requires string texts")
        backend = self._ensure_ready()
        try:
            vectors = backend.embed_documents(texts)
            self._remember_effective_batch_size(backend)
            self.last_execution_batch_sizes = getattr(
                backend, "last_execution_batch_sizes", None
            )
            self.last_execution_padded_token_workload = getattr(
                backend, "last_execution_padded_token_workload", None
            )
            return vectors
        except CudaMemoryExhaustedError as exc:
            self._remember_effective_batch_size(backend)
            self._mark_failed(exc)
            raise
        except QualifiedEmbeddingRuntimeError:
            raise
        except Exception as exc:
            self._remember_effective_batch_size(backend)
            self._mark_failed(exc)
            raise QualifiedEmbeddingRuntimeError(
                f"qualified embedding execution failed: {self._failure}"
            ) from exc

    def _remember_effective_batch_size(self, backend: Any) -> None:
        effective = getattr(backend, "effective_batch_size", None)
        if effective is None:
            effective = getattr(backend, "batch_size", None)
        if isinstance(effective, int) and effective > 0:
            self.effective_batch_size = effective

    def embed_query(self, text: str) -> list[float]:
        if not isinstance(text, str):
            raise TypeError("embed_query requires a string")
        backend = self._ensure_ready()
        try:
            return backend.embed_query(text)
        except QualifiedEmbeddingRuntimeError:
            raise
        except Exception as exc:
            self._mark_failed(exc)
            raise QualifiedEmbeddingRuntimeError(
                f"qualified embedding execution failed: {self._failure}"
            ) from exc

    def _mark_failed(self, exc: BaseException) -> None:
        with self._init_lock:
            if self._state is RuntimeState.CLOSED:
                return
            # Terminal classification is immutable once FAILED.
            if self._state is RuntimeState.FAILED:
                return
            if self._backend is not None:
                self._remember_effective_batch_size(self._backend)
            self._failure = f"{type(exc).__name__}: {exc}"
            self._failure_kind = RuntimeFailureKind.EXECUTION
            release = getattr(self._backend, "release", None)
            if callable(release):
                try:
                    release()
                except Exception:  # noqa: BLE001, S110 — best-effort release
                    pass
            self._backend = None
            self._state = RuntimeState.FAILED

    def close(self) -> None:
        with self._init_lock:
            release = getattr(self._backend, "release", None)
            if callable(release):
                try:
                    release()
                except Exception:  # noqa: BLE001, S110 — best-effort release
                    pass
            self._backend = None
            self._state = RuntimeState.CLOSED


__all__ = [
    "QualifiedEmbeddingRuntime",
    "QualifiedEmbeddingRuntimeError",
    "RuntimeFailureKind",
    "RuntimeState",
]
