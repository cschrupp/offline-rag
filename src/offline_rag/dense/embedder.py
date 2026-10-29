"""Embedder protocol and local implementations."""

from __future__ import annotations

import gc
import hashlib
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    MODEL_QUERY_PROMPT_V1,
    RAW_QUERY_V1,
    SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT,
)
from offline_rag.dense.failure import CudaMemoryExhaustedError, is_cuda_oom_error
from offline_rag.dense.provision import (
    require_embedding_artifacts,
    resolve_embedding_model_dir,
)
from offline_rag.dense.query_text import (
    MODEL_QUERY_PROMPT_NAME,
    resolve_query_text_contract,
)


class Embedder(Protocol):
    """Project-owned embedding interface."""

    model_id: str
    model_revision: str
    dimension: int
    normalize: bool
    adapter_contract: str
    query_text_contract: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document/passage texts."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [value / norm for value in vector]


def _digest_vector(text: str, *, dimension: int) -> list[float]:
    """Map text to a deterministic float vector via expanding SHA-256 digests."""
    if dimension <= 0:
        raise ValueError("dimension must be positive")
    values: list[float] = []
    seed = text.encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    offset = 0
    while len(values) < dimension:
        if offset >= len(digest):
            digest = hashlib.sha256(digest).digest()
            offset = 0
        # Map byte [0, 255] into [-1, 1].
        values.append((digest[offset] / 127.5) - 1.0)
        offset += 1
    return values


class FakeEmbedder:
    """Deterministic digest-based embedder for tests and CI (no Python hash())."""

    model_id = "fake"
    model_revision = "fake-v1"
    adapter_contract = "fake-embedder-v1"
    query_text_contract = RAW_QUERY_V1

    def __init__(
        self,
        *,
        dimension: int = 8,
        normalize: bool = True,
        query_text_contract: str = RAW_QUERY_V1,
        configured_device: str = "auto",
        configured_precision: str = "native",
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if query_text_contract != RAW_QUERY_V1:
            raise EmbedderError(
                f"FakeEmbedder only supports {RAW_QUERY_V1}; got {query_text_contract}"
            )
        if str(configured_precision).strip().lower() != "native":
            raise EmbedderError(
                "FakeEmbedder only supports precision='native' "
                f"(got {configured_precision!r})"
            )
        self.dimension = dimension
        self.normalize = normalize
        self.query_text_contract = query_text_contract
        # Safe test-backend diagnostics (do not import torch).
        self.configured_device = configured_device
        self.resolved_device = "test"
        self.device = "test"
        self.configured_precision = "native"
        self.resolved_precision = "native"
        self.precision_selection_reason = "native_default"
        self.cuda_available: bool | None = None
        self.torch_cuda_build: str | None = None
        self.device_selection_reason = "test_backend"

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def observe_execution_facts(self) -> dict[str, str | None]:
        """Fake backend has no trustworthy dtype/attention — leave absent."""
        return {"dtype": None, "attention_backend": None}

    def _embed_one(self, text: str) -> list[float]:
        vector = _digest_vector(text, dimension=self.dimension)
        if self.normalize:
            return _l2_normalize(vector)
        return vector


class SentenceTransformersEmbedder:
    """Load SentenceTransformers exclusively from a provisioned local directory."""

    adapter_contract = SENTENCE_TRANSFORMERS_ADAPTER_CONTRACT
    CUDA_OOM_BATCH_LADDER = (32, 16, 8, 4)

    def __init__(
        self,
        *,
        model_path: Path,
        model_id: str,
        model_revision: str,
        dimension: int,
        normalize: bool = True,
        device: str = "cpu",
        batch_size: int = 32,
        query_instruction: str | None = None,
        document_instruction: str | None = None,
        expected_dimension: int | None = None,
        query_text_contract: str = RAW_QUERY_V1,
        configured_device: str = "cpu",
        cuda_available: bool = False,
        torch_cuda_build: str | None = None,
        device_selection_reason: str = "explicit_cpu",
        configured_precision: str = "native",
        resolved_precision: str = "native",
        precision_selection_reason: str = "native_default",
    ) -> None:
        if device not in {"cpu", "cuda"}:
            raise EmbedderError(
                f"SentenceTransformersEmbedder requires resolved device "
                f"'cpu' or 'cuda'; got {device!r}"
            )
        if resolved_precision not in {"native", "fp16"}:
            raise EmbedderError(
                f"SentenceTransformersEmbedder requires resolved precision "
                f"'native' or 'fp16'; got {resolved_precision!r}"
            )
        if resolved_precision == "fp16" and device != "cuda":
            raise EmbedderError(
                "FP16 embedding execution requires resolved device 'cuda' "
                f"(got {device!r})."
            )
        self.model_path = Path(model_path).expanduser().resolve()
        self.model_id = model_id
        self.model_revision = model_revision
        self.dimension = dimension
        self.normalize = normalize
        self.device = device
        self.resolved_device = device
        self.configured_device = configured_device
        self.cuda_available = cuda_available
        self.torch_cuda_build = torch_cuda_build
        self.device_selection_reason = device_selection_reason
        self.configured_precision = configured_precision
        self.resolved_precision = resolved_precision
        self.precision_selection_reason = precision_selection_reason
        self.configured_batch_size = batch_size
        self.effective_batch_size = batch_size
        self.batch_size = batch_size
        self.query_instruction = query_instruction
        self.document_instruction = document_instruction
        self.query_text_contract = query_text_contract
        self._model = None
        self._precision_applied = False
        self._precision_conversion: dict[str, str | None] | None = None
        self.last_execution_batch_sizes: list[int] | None = None
        self.last_execution_padded_token_workload: int | None = None
        if (
            query_text_contract == MODEL_QUERY_PROMPT_V1
            and query_instruction is not None
        ):
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1} cannot be combined with "
                "indexing.embedding.query_instruction; use the model registered "
                f"{MODEL_QUERY_PROMPT_NAME!r} prompt only"
            )
        require_embedding_artifacts(
            self.model_path,
            expected_model_id=model_id,
            expected_revision=model_revision,
            expected_dimension=expected_dimension or dimension,
        )

    def ensure_initialized(self):
        """Materialize the SentenceTransformer model (heavy init). Idempotent."""
        return self._load()

    def _load(self):
        if self._model is not None:
            return self._model
        import torch
        from sentence_transformers import SentenceTransformer

        model_kwargs: dict[str, object] = {}
        config_kwargs: dict[str, object] = {}
        if self.device == "cuda":
            config_kwargs["use_cache"] = False
        if self.resolved_precision == "fp16":
            model_kwargs["torch_dtype"] = torch.float16

        model = SentenceTransformer(
            str(self.model_path),
            device=self.device,
            model_kwargs=model_kwargs,
            config_kwargs=config_kwargs,
            trust_remote_code=False,
            local_files_only=True,
        )
        self._verify_loaded_model(model)
        if self.resolved_precision == "fp16":
            # Parameters were materialized in FP16 by the model loader.
            self._precision_conversion = None
            self._precision_applied = True
        self._model = model
        return self._model

    def _verify_loaded_model(self, model: object) -> None:
        """Fail closed when CUDA cache or requested parameter dtype is wrong."""
        if self.device != "cuda" and self.resolved_precision != "fp16":
            return
        try:
            import torch

            first = model[0] if len(model) else None  # type: ignore[index]
            auto_model = getattr(first, "auto_model", None)
            if auto_model is None:
                raise EmbedderError(
                    "loaded embedding model does not expose its transformer model"
                )
            config = getattr(auto_model, "config", None)
            if (
                self.device == "cuda"
                and getattr(config, "use_cache", None) is not False
            ):
                raise EmbedderError(
                    "CUDA embedding model did not disable the generation KV cache"
                )
            parameter = next(auto_model.parameters(), None)
            if parameter is None:
                raise EmbedderError("loaded embedding model has no parameters")
            if self.resolved_precision == "fp16" and parameter.dtype != torch.float16:
                raise EmbedderError(
                    "direct FP16 model loading did not produce float16 parameters"
                )
        except EmbedderError:
            raise
        except Exception as exc:
            raise EmbedderError(
                "unable to verify embedding model cache/dtype settings"
            ) from exc

    @staticmethod
    def _tokenizer_and_max_length(model: object) -> tuple[Any, int]:
        """Return the SentenceTransformers tokenizer and active truncation bound."""
        try:
            first = model[0]  # type: ignore[index]
        except Exception as exc:
            raise EmbedderError(
                "CUDA token batching requires model module access"
            ) from exc
        tokenizer = getattr(first, "tokenizer", None)
        if tokenizer is None:
            tokenizer = getattr(model, "tokenizer", None)
        max_length = getattr(model, "max_seq_length", None)
        if not isinstance(max_length, int) or max_length <= 0:
            config = getattr(getattr(first, "auto_model", None), "config", None)
            max_length = getattr(config, "max_position_embeddings", None)
        if tokenizer is None or not isinstance(max_length, int) or max_length <= 0:
            raise EmbedderError(
                "CUDA token batching requires a tokenizer and finite max sequence length"
            )
        return tokenizer, max_length

    def _partition_cuda_payloads(
        self, model: object, payloads: list[str], *, batch_limit: int
    ) -> tuple[list[list[str]], list[int], int]:
        """Greedily partition in input order under the frozen padded-token rule."""
        tokenizer, max_length = self._tokenizer_and_max_length(model)
        token_counts: list[int] = []
        for text in payloads:
            encoded = tokenizer(
                text,
                add_special_tokens=True,
                truncation=True,
                max_length=max_length,
                padding=False,
                return_attention_mask=False,
            )
            input_ids = (
                encoded.get("input_ids")
                if isinstance(encoded, dict)
                else getattr(encoded, "input_ids", None)
            )
            if input_ids is None:
                raise EmbedderError("tokenizer returned no input_ids for CUDA batching")
            if input_ids and isinstance(input_ids[0], (list, tuple)):
                count = len(input_ids[0])
            else:
                count = len(input_ids)
            if count <= 0:
                raise EmbedderError("tokenizer returned an empty CUDA batch sequence")
            token_counts.append(count)

        ordered_counts = sorted(token_counts)
        p95_rank = max(1, math.ceil(0.95 * len(ordered_counts)))
        padded_token_budget = batch_limit * ordered_counts[p95_rank - 1]
        partitions: list[list[str]] = []
        partition_counts: list[list[int]] = []
        current_texts: list[str] = []
        current_counts: list[int] = []
        current_max = 0
        for text, count in zip(payloads, token_counts, strict=True):
            next_max = max(current_max, count)
            if current_texts and (
                len(current_texts) >= batch_limit
                or (len(current_texts) + 1) * next_max > padded_token_budget
            ):
                partitions.append(current_texts)
                partition_counts.append(current_counts)
                current_texts = []
                current_counts = []
                current_max = 0
                next_max = count
            current_texts.append(text)
            current_counts.append(count)
            current_max = next_max
        if current_texts:
            partitions.append(current_texts)
            partition_counts.append(current_counts)

        if len(partitions) == 1:
            partitions[0] = payloads

        batch_sizes = [len(partition) for partition in partitions]
        actual_padded_tokens = sum(
            len(counts) * max(counts) for counts in partition_counts
        )
        return partitions, batch_sizes, actual_padded_tokens

    def _require_model_query_prompt(self, model) -> None:
        prompts = getattr(model, "prompts", None)
        if not isinstance(prompts, dict) or MODEL_QUERY_PROMPT_NAME not in prompts:
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1} requires the provisioned embedding model "
                f"to expose prompts[{MODEL_QUERY_PROMPT_NAME!r}]; none found "
                f"(model_id={self.model_id})"
            )
        value = prompts[MODEL_QUERY_PROMPT_NAME]
        if not isinstance(value, str):
            raise EmbedderError(
                f"{MODEL_QUERY_PROMPT_V1}: prompts[{MODEL_QUERY_PROMPT_NAME!r}] "
                f"must be a string (got {type(value).__name__})"
            )

    def observe_execution_facts(self) -> dict[str, str | None]:
        """Introspect dtype/attention only when the model is already loaded.

        Never calls ``_load()`` — observability must not turn a cache-reused
        dense run into a model-loading run. Unloaded → dtype/attention null.
        """
        facts: dict[str, str | None] = {"dtype": None, "attention_backend": None}
        model = self._model
        if model is None:
            return facts
        try:
            first = model[0] if len(model) else None
            auto_model = getattr(first, "auto_model", None)
            if auto_model is None:
                return facts
            param = next(auto_model.parameters(), None)
            if param is not None:
                dtype = getattr(param, "dtype", None)
                if dtype is not None:
                    text = str(dtype)
                    facts["dtype"] = text.removeprefix("torch.")
            cfg = getattr(auto_model, "config", None)
            if cfg is not None:
                attention = getattr(cfg, "_attn_implementation", None)
                if attention is None:
                    attention = getattr(cfg, "attn_implementation", None)
                if attention is not None:
                    facts["attention_backend"] = str(attention)
        except Exception:  # noqa: BLE001
            return facts
        return facts

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        self.last_execution_batch_sizes = None
        self.last_execution_padded_token_workload = None
        payloads = [
            f"{self.document_instruction}{text}" if self.document_instruction else text
            for text in texts
        ]
        model = self._load()
        encode_payloads = list(payloads)
        batch_ladder = self._cuda_oom_batch_ladder()
        for attempt_index, attempt_batch_size in enumerate(batch_ladder):
            self.effective_batch_size = attempt_batch_size
            self.batch_size = attempt_batch_size
            if self.device == "cuda":
                execution_batches, execution_batch_sizes, padded_token_workload = (
                    self._partition_cuda_payloads(
                        model, encode_payloads, batch_limit=attempt_batch_size
                    )
                )
            else:
                execution_batches = [encode_payloads]
                execution_batch_sizes = [min(len(encode_payloads), attempt_batch_size)]
                padded_token_workload = None
            collector, batch_context = self._diagnostic_encode_context()
            diagnostics_before = (
                self._cuda_attempt_snapshot() if collector is not None else None
            )
            attempt_started = time.perf_counter()
            try:
                vectors = []
                for execution_batch, _execution_batch_size in zip(
                    execution_batches, execution_batch_sizes, strict=True
                ):
                    batch_vectors = model.encode(
                        execution_batch,
                        batch_size=attempt_batch_size,
                        normalize_embeddings=self.normalize,
                        convert_to_numpy=True,
                        show_progress_bar=False,
                    )
                    vectors.extend(batch_vectors)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - attempt_started) * 1000.0
                is_cuda_oom = self.device == "cuda" and is_cuda_oom_error(exc)
                next_batch_size = (
                    batch_ladder[attempt_index + 1]
                    if is_cuda_oom and attempt_index + 1 < len(batch_ladder)
                    else None
                )
                cleanup_status = None
                diagnostics_after_cleanup = None
                if next_batch_size is not None:
                    cleanup_status = (
                        "succeeded" if cleanup_cuda_after_oom(exc) else "failed"
                    )
                    diagnostics_after_cleanup = (
                        self._cuda_attempt_snapshot() if collector is not None else None
                    )
                self._record_cuda_attempt(
                    collector=collector,
                    batch_context=batch_context,
                    batch_size=attempt_batch_size,
                    elapsed_ms=elapsed_ms,
                    outcome="cuda_oom" if is_cuda_oom else "other_failure",
                    next_batch_size=next_batch_size,
                    before=diagnostics_before,
                    after_cleanup=diagnostics_after_cleanup,
                    cleanup_status=cleanup_status,
                    execution_batch_sizes=execution_batch_sizes,
                    execution_padded_token_workload=padded_token_workload,
                )
                if not is_cuda_oom:
                    raise
                if next_batch_size is None:
                    raise CudaMemoryExhaustedError(
                        configured_batch_size=self.configured_batch_size,
                        final_batch_size=attempt_batch_size,
                    ) from exc
                self.effective_batch_size = next_batch_size
                self.batch_size = next_batch_size
                continue

            elapsed_ms = (time.perf_counter() - attempt_started) * 1000.0
            self._record_cuda_attempt(
                collector=collector,
                batch_context=batch_context,
                batch_size=attempt_batch_size,
                elapsed_ms=elapsed_ms,
                outcome="success",
                next_batch_size=None,
                before=diagnostics_before,
                after_cleanup=None,
                cleanup_status=None,
                execution_batch_sizes=execution_batch_sizes,
                execution_padded_token_workload=padded_token_workload,
            )
            self.last_execution_batch_sizes = execution_batch_sizes
            self.last_execution_padded_token_workload = padded_token_workload
            return [self._coerce_vector(row.tolist()) for row in vectors]

        raise AssertionError("CUDA OOM batch ladder ended without an encode result")

    def _cuda_oom_batch_ladder(self) -> tuple[int, ...]:
        if self.device != "cuda":
            return (self.configured_batch_size,)
        current_batch_size = self.effective_batch_size
        try:
            start = self.CUDA_OOM_BATCH_LADDER.index(current_batch_size)
        except ValueError:
            return (current_batch_size,)
        return self.CUDA_OOM_BATCH_LADDER[start:]

    @staticmethod
    def _diagnostic_encode_context():
        from offline_rag.dense.profiling import (
            get_dense_encode_batch_context,
            get_dense_profile_collector,
        )

        return get_dense_profile_collector(), get_dense_encode_batch_context()

    @staticmethod
    def _cuda_attempt_snapshot() -> dict[str, object]:
        from offline_rag.dense.profiling import (
            observe_cuda_allocator_state,
            observe_cuda_global_memory_state,
            sample_external_gpu_state,
        )

        return {
            "allocator": observe_cuda_allocator_state(),
            "global_memory": observe_cuda_global_memory_state(),
            "external_gpu": sample_external_gpu_state(),
        }

    @staticmethod
    def _record_cuda_attempt(
        *,
        collector,
        batch_context,
        batch_size: int,
        elapsed_ms: float,
        outcome: str,
        next_batch_size: int | None,
        before: dict[str, object] | None,
        after_cleanup: dict[str, object] | None,
        cleanup_status: str | None,
        execution_batch_sizes: list[int],
        execution_padded_token_workload: int | None,
    ) -> None:
        if collector is None or batch_context is None:
            return
        collector.record_encode_attempt(
            batch_context=batch_context,
            effective_batch_size=batch_size,
            elapsed_ms=elapsed_ms,
            outcome=outcome,
            next_effective_batch_size=next_batch_size,
            cuda_allocator_before=(before or {}).get("allocator"),
            cuda_memory_before=(before or {}).get("global_memory"),
            external_gpu_before=(before or {}).get("external_gpu"),
            cleanup_status=cleanup_status,
            cuda_allocator_after_cleanup=(after_cleanup or {}).get("allocator"),
            cuda_memory_after_cleanup=(after_cleanup or {}).get("global_memory"),
            external_gpu_after=(after_cleanup or {}).get("external_gpu"),
            execution_batch_sizes=execution_batch_sizes,
            execution_padded_token_workload=execution_padded_token_workload,
        )

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        if self.query_text_contract == MODEL_QUERY_PROMPT_V1:
            self._require_model_query_prompt(model)
            vector = model.encode(
                text,
                prompt_name=MODEL_QUERY_PROMPT_NAME,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return self._coerce_vector(vector.tolist())

        # raw-query-v1: optional legacy string prefix, then bare encode.
        payload = f"{self.query_instruction}{text}" if self.query_instruction else text
        vector = model.encode(
            payload,
            normalize_embeddings=self.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return self._coerce_vector(vector.tolist())

    def _coerce_vector(self, values: list[float]) -> list[float]:
        if len(values) < self.dimension:
            values = values + [0.0] * (self.dimension - len(values))
        elif len(values) > self.dimension:
            values = values[: self.dimension]
        if self.normalize:
            return _l2_normalize(values)
        return values


class EmbedderError(RuntimeError):
    pass


def cleanup_cuda_after_oom(exc: BaseException | None = None) -> bool:
    """Release attempt-local traceback references and unused CUDA cache best-effort."""
    pending = [exc] if exc is not None else []
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        current.__traceback__ = None
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)

    succeeded = True
    try:
        gc.collect()
    except Exception:  # noqa: BLE001 — cleanup failure must not replace OOM
        succeeded = False
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 — cleanup failure must not replace OOM
        succeeded = False
    return succeeded


def make_embedder(settings: AppSettings) -> Embedder:
    """Construct the configured embedder (fake never silently substitutes).

    For production Qwen / sentence_transformers settings, resolves a qualified
    dual-backend execution profile, validates the selected representation, and
    returns a ``QualifiedEmbeddingRuntime`` in UNLOADED state (no heavy load).
    """
    from offline_rag.dense.embedding_artifacts import (
        RepresentationReadiness,
        inspect_selected_representation,
    )
    from offline_rag.dense.embedding_runtime import QualifiedEmbeddingRuntime
    from offline_rag.dense.execution_profile import resolve_qualified_embedding_profile

    emb = settings.indexing.embedding
    query = settings.dense.query_text
    query_contract = resolve_query_text_contract(
        strategy=query.strategy,
        contract_version=query.contract_version,
    )
    if emb.implementation == "fake":
        if query_contract != RAW_QUERY_V1:
            raise EmbedderError(
                f"{query_contract} requires sentence_transformers with a registered "
                f"{MODEL_QUERY_PROMPT_NAME!r} prompt; fake embedder cannot satisfy it"
            )
        return FakeEmbedder(
            dimension=emb.dimension,
            normalize=emb.normalize,
            query_text_contract=query_contract,
            configured_device=str(emb.device),
            configured_precision=str(emb.precision),
        )
    if emb.implementation != "sentence_transformers":
        raise EmbedderError(
            f"unsupported embedding implementation: {emb.implementation}"
        )

    # P1: query/document instruction strings are frozen null for qualified Qwen.
    if emb.query_instruction is not None or emb.document_instruction is not None:
        raise EmbedderError(
            "qualified dual-backend embedding requires query_instruction=null and "
            "document_instruction=null"
        )
    if query_contract != RAW_QUERY_V1:
        raise EmbedderError(
            f"qualified dual-backend P1 only authorizes {RAW_QUERY_V1}; "
            f"got {query_contract}"
        )

    profile_resolution = resolve_qualified_embedding_profile(
        emb.device,
        emb.precision,
    )
    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    representation = inspect_selected_representation(
        model_dir,
        profile_resolution.profile.representation_id,
        expected_model_id=emb.model_id,
        expected_revision=emb.revision,
        expected_dimension=emb.dimension,
    )
    if representation.readiness != RepresentationReadiness.READY:
        raise EmbedderError(
            "selected embedding representation is not READY for profile "
            f"{profile_resolution.profile.profile_id}: "
            f"representation={profile_resolution.profile.representation_id} "
            f"readiness={representation.readiness.value} "
            f"reason={representation.reason}"
        )
    # Attach status onto resolution for observability without mutating frozen profile.
    profile_resolution = profile_resolution.__class__(
        configured_device=profile_resolution.configured_device,
        configured_precision=profile_resolution.configured_precision,
        profile=profile_resolution.profile,
        selection_reason=profile_resolution.selection_reason,
        cuda_available=profile_resolution.cuda_available,
        torch_cuda_build=profile_resolution.torch_cuda_build,
        selected_representation_status=representation.readiness.value,
    )
    return QualifiedEmbeddingRuntime(
        profile_resolution=profile_resolution,
        representation=representation,
        model_id=emb.model_id,
        model_revision=emb.revision,
        dimension=emb.dimension,
        normalize=emb.normalize,
        query_text_contract=query_contract,
    )


def embedder_runtime_view(embedder: object) -> dict[str, object | None]:
    """Safe runtime diagnostics from the process-owned embedder."""
    configured = getattr(embedder, "configured_device", None)
    resolved = getattr(embedder, "resolved_device", getattr(embedder, "device", None))
    return {
        "configured_device": configured,
        "active_device": resolved,
        "configured_precision": getattr(embedder, "configured_precision", None),
        "resolved_precision": getattr(embedder, "resolved_precision", None),
        "precision_selection_reason": getattr(
            embedder, "precision_selection_reason", None
        ),
        "cuda_available": getattr(embedder, "cuda_available", None),
        "torch_cuda_build": getattr(embedder, "torch_cuda_build", None),
        "selection_reason": getattr(embedder, "device_selection_reason", None),
        "profile_id": getattr(embedder, "profile_id", None),
        "representation_id": getattr(embedder, "representation_id", None),
        "runtime_state": str(getattr(embedder, "state", None) or "") or None,
    }


def observe_embedder_execution_facts(embedder: object) -> dict[str, str | None]:
    """Best-effort dtype/attention facts; never invent FP32 or attention."""
    facts: dict[str, str | None] = {"dtype": None, "attention_backend": None}
    observe = getattr(embedder, "observe_execution_facts", None)
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
    dtype = getattr(embedder, "dtype", None)
    attention = getattr(embedder, "attention_backend", None)
    if dtype is not None:
        facts["dtype"] = str(dtype)
    if attention is not None:
        facts["attention_backend"] = str(attention)
    return facts
