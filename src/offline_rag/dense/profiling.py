"""Env-gated observational dense indexing profile (16K-D D0/D1 tooling).

Enabled only when ``OFFLINE_RAG_DIAG_DENSE_PROFILE=1``. Disabled path must not
alter embedding inputs, vectors, persistence, or Qdrant materialization.

D1 stall-attribution fields (CUDA events, process CPU/context switches, external
GPU samples) are collected only while profiling is enabled. Explicit CUDA
synchronization for device timing is diagnostic-gated and absent when disabled.
"""

from __future__ import annotations

import hashlib
import os
import resource
import statistics
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

DIAG_DENSE_PROFILE_ENV = "OFFLINE_RAG_DIAG_DENSE_PROFILE"
PROFILE_CONTRACT = "dense-cuda-profile-v2"


def dense_profile_enabled() -> bool:
    return os.environ.get(DIAG_DENSE_PROFILE_ENV, "").strip() == "1"


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return float(sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight)


def _token_distribution(token_counts: list[int]) -> dict[str, int | None]:
    if not token_counts:
        return {
            "min": None,
            "median": None,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    ordered = sorted(float(v) for v in token_counts)
    p50 = int(round(_percentile(ordered, 50.0) or 0))
    return {
        "min": int(min(token_counts)),
        "median": p50,
        "p50": p50,
        "p95": int(round(_percentile(ordered, 95.0) or 0)),
        "p99": int(round(_percentile(ordered, 99.0) or 0)),
        "max": int(max(token_counts)),
    }


def batch_identity_digest(chunk_ids: list[str]) -> str:
    """Deterministic digest over ordered chunk IDs (no private text)."""
    payload = "\n".join(chunk_ids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _process_rusage_snapshot() -> dict[str, Any]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "status": "observed",
            "error": None,
            "user_time_s": float(usage.ru_utime),
            "system_time_s": float(usage.ru_stime),
            "voluntary_context_switches": int(usage.ru_nvcsw),
            "involuntary_context_switches": int(usage.ru_nivcsw),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "user_time_s": None,
            "system_time_s": None,
            "voluntary_context_switches": None,
            "involuntary_context_switches": None,
        }


def _rusage_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    if before.get("status") != "observed" or after.get("status") != "observed":
        return {
            "status": "unavailable",
            "error": before.get("error") or after.get("error") or "rusage_unavailable",
            "user_time_s": None,
            "system_time_s": None,
            "cpu_time_s": None,
            "voluntary_context_switches": None,
            "involuntary_context_switches": None,
        }
    user = float(after["user_time_s"]) - float(before["user_time_s"])
    system = float(after["system_time_s"]) - float(before["system_time_s"])
    return {
        "status": "observed",
        "error": None,
        "user_time_s": user,
        "system_time_s": system,
        "cpu_time_s": user + system,
        "voluntary_context_switches": int(after["voluntary_context_switches"])
        - int(before["voluntary_context_switches"]),
        "involuntary_context_switches": int(after["involuntary_context_switches"])
        - int(before["involuntary_context_switches"]),
    }


def sample_external_gpu_state() -> dict[str, Any]:
    """Best-effort nvidia-smi sample outside the encode critical path."""
    query = (
        "utilization.gpu,utilization.memory,"
        "clocks.current.graphics,clocks.current.sm,clocks.current.memory,"
        "temperature.gpu,power.draw,pstate,"
        "clocks_event_reasons.sw_power_cap,clocks_event_reasons.hw_thermal_slowdown,"
        "clocks_event_reasons.sw_thermal_slowdown,clocks_event_reasons.hw_slowdown"
    )
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        if not out:
            return {"status": "unavailable", "error": "empty_nvidia_smi", "sample": None}
        parts = [p.strip() for p in out.split(",")]
        keys = [
            "utilization_gpu_pct",
            "utilization_memory_pct",
            "clock_graphics_mhz",
            "clock_sm_mhz",
            "clock_memory_mhz",
            "temperature_c",
            "power_draw_w",
            "pstate",
            "throttle_sw_power_cap",
            "throttle_hw_thermal_slowdown",
            "throttle_sw_thermal_slowdown",
            "throttle_hw_slowdown",
        ]
        sample: dict[str, Any] = {}
        for key, raw in zip(keys, parts, strict=False):
            if key == "pstate" or key.startswith("throttle_"):
                sample[key] = raw
                continue
            try:
                sample[key] = float(raw)
            except ValueError:
                sample[key] = raw
        return {"status": "observed", "error": None, "sample": sample}
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "sample": None,
        }


def observe_cuda_allocator_state() -> dict[str, Any]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {
                "status": "unavailable",
                "error": "cuda_not_available",
                "allocated_bytes": None,
                "reserved_bytes": None,
                "peak_allocated_bytes": None,
            }
        return {
            "status": "observed",
            "error": None,
            "allocated_bytes": int(torch.cuda.memory_allocated()),
            "reserved_bytes": int(torch.cuda.memory_reserved()),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "allocated_bytes": None,
            "reserved_bytes": None,
            "peak_allocated_bytes": None,
            "peak_reserved_bytes": None,
        }


def observe_cuda_global_memory_state() -> dict[str, Any]:
    """Best-effort device-wide free/total memory from the active CUDA runtime."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {
                "status": "unavailable",
                "error": "cuda_not_available",
                "free_bytes": None,
                "total_bytes": None,
            }
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        return {
            "status": "observed",
            "error": None,
            "free_bytes": int(free_bytes),
            "total_bytes": int(total_bytes),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "free_bytes": None,
            "total_bytes": None,
        }


@dataclass(frozen=True)
class DenseEncodeBatchContext:
    """Private-text-free identity and token facts for one logical outer batch."""

    batch_index: int
    item_count: int
    batch_identity_digest: str | None
    chunk_ids_digest: str | None
    token_length_stats: dict[str, int | None] | None
    aggregate_input_tokens: int | None
    padded_token_workload: int | None
    padding_fraction: float | None


_encode_batch_context_var: ContextVar[DenseEncodeBatchContext | None] = ContextVar(
    "dense_encode_batch_context", default=None
)


def get_dense_encode_batch_context() -> DenseEncodeBatchContext | None:
    return _encode_batch_context_var.get()


@contextmanager
def dense_encode_batch_context(
    *,
    batch_index: int,
    item_count: int,
    token_counts: list[int] | None,
    max_sequence_length: int | None,
    chunk_ids: list[str],
) -> Iterator[DenseEncodeBatchContext]:
    counts = list(token_counts or [])
    aggregate = sum(counts) if counts else None
    padded = None
    padding_fraction = None
    if item_count > 0 and max_sequence_length is not None and max_sequence_length > 0:
        padded = int(item_count * max_sequence_length)
        if aggregate is not None:
            padding_fraction = 1.0 - (float(aggregate) / float(padded))
    chunk_digest = batch_identity_digest(chunk_ids) if chunk_ids else None
    identity = None
    if chunk_digest is not None:
        identity = hashlib.sha256(
            f"{batch_index}:{item_count}:{chunk_digest}".encode()
        ).hexdigest()
    context = DenseEncodeBatchContext(
        batch_index=batch_index,
        item_count=item_count,
        batch_identity_digest=identity,
        chunk_ids_digest=chunk_digest,
        token_length_stats=_token_distribution(counts) if counts else None,
        aggregate_input_tokens=aggregate,
        padded_token_workload=padded,
        padding_fraction=padding_fraction,
    )
    token = _encode_batch_context_var.set(context)
    try:
        yield context
    finally:
        _encode_batch_context_var.reset(token)


@dataclass
class DenseBatchProfile:
    batch_index: int
    item_count: int
    model_input_token_counts: list[int]
    max_sequence_length: int | None
    encode_ms: float
    persistence_ms: float
    peak_vram_bytes_after: int | None = None
    # D1 stall-attribution (null/unavailable when not collected)
    batch_identity_digest: str | None = None
    chunk_ids_digest: str | None = None
    token_length_stats: dict[str, int | None] | None = None
    aggregate_input_tokens: int | None = None
    padded_token_workload: int | None = None
    padding_fraction: float | None = None
    encode_cuda_device_ms: float | None = None
    encode_cuda_device_status: str = "not_attempted"
    encode_cuda_device_error: str | None = None
    process_cpu_delta: dict[str, Any] | None = None
    cuda_allocator_after: dict[str, Any] | None = None
    gpu_external_before: dict[str, Any] | None = None
    gpu_external_after: dict[str, Any] | None = None


@dataclass
class DenseProfileCollector:
    """In-process collector for one dense indexing run."""

    cold_or_warm: str = "unknown"
    oversized_unsplittable_count: int = 0
    embeddings_generated: int = 0
    embeddings_reused: int = 0
    batches: list[DenseBatchProfile] = field(default_factory=list)
    encode_attempts: list[dict[str, Any]] = field(default_factory=list)
    encode_ms_total: float = 0.0
    persistence_ms_total: float = 0.0
    point_construction_ms: float | None = None
    qdrant_materialization_ms: float | None = None
    tokenizer_status: str = "not_attempted"
    tokenizer_error: str | None = None
    peak_vram_bytes: int | None = None
    peak_vram_status: str = "not_attempted"
    peak_vram_error: str | None = None
    first_batch_encode_ms: float | None = None
    steady_state_encode_ms_mean: float | None = None
    stall_attribution_tooling: bool = True
    _token_counts: list[int] = field(default_factory=list)

    def record_encode_attempt(
        self,
        *,
        batch_context: DenseEncodeBatchContext,
        effective_batch_size: int,
        elapsed_ms: float,
        outcome: str,
        next_effective_batch_size: int | None,
        cuda_allocator_before: dict[str, Any] | None,
        cuda_memory_before: dict[str, Any] | None,
        external_gpu_before: dict[str, Any] | None,
        cleanup_status: str | None,
        cuda_allocator_after_cleanup: dict[str, Any] | None,
        cuda_memory_after_cleanup: dict[str, Any] | None,
        external_gpu_after: dict[str, Any] | None,
    ) -> None:
        """Store bounded attempt facts without embedding text or exception text."""
        self.encode_attempts.append(
            {
                "logical_outer_batch_index": batch_context.batch_index,
                "logical_item_count": batch_context.item_count,
                "effective_batch_size": effective_batch_size,
                "batch_identity_digest": batch_context.batch_identity_digest,
                "chunk_ids_digest": batch_context.chunk_ids_digest,
                "token_length_stats": batch_context.token_length_stats,
                "aggregate_input_tokens": batch_context.aggregate_input_tokens,
                "padded_token_workload": batch_context.padded_token_workload,
                "padding_fraction": batch_context.padding_fraction,
                "encode_ms": elapsed_ms,
                "outcome": outcome,
                "next_effective_batch_size": next_effective_batch_size,
                "cuda_allocator_before": cuda_allocator_before,
                "cuda_memory_before": cuda_memory_before,
                "external_gpu_before": external_gpu_before,
                "cleanup_status": cleanup_status,
                "cuda_allocator_after_cleanup": cuda_allocator_after_cleanup,
                "cuda_memory_after_cleanup": cuda_memory_after_cleanup,
                "external_gpu_after": external_gpu_after,
            }
        )

    def record_batch(
        self,
        *,
        batch_index: int,
        item_count: int,
        token_counts: list[int] | None,
        max_sequence_length: int | None,
        encode_ms: float,
        persistence_ms: float,
        peak_vram_bytes_after: int | None,
        chunk_ids: list[str] | None = None,
        encode_cuda_device_ms: float | None = None,
        encode_cuda_device_status: str = "not_attempted",
        encode_cuda_device_error: str | None = None,
        process_cpu_delta: dict[str, Any] | None = None,
        cuda_allocator_after: dict[str, Any] | None = None,
        gpu_external_before: dict[str, Any] | None = None,
        gpu_external_after: dict[str, Any] | None = None,
    ) -> None:
        counts = list(token_counts or [])
        self._token_counts.extend(counts)
        self.encode_ms_total += encode_ms
        self.persistence_ms_total += persistence_ms
        if batch_index == 0:
            self.first_batch_encode_ms = encode_ms

        token_stats = _token_distribution(counts) if counts else None
        aggregate = sum(counts) if counts else None
        padded = None
        padding_fraction = None
        if (
            counts
            and max_sequence_length is not None
            and item_count > 0
            and max_sequence_length > 0
        ):
            padded = int(item_count * max_sequence_length)
            padding_fraction = 1.0 - (float(aggregate or 0) / float(padded))

        identity = None
        chunk_digest = None
        if chunk_ids:
            chunk_digest = batch_identity_digest(chunk_ids)
            identity = hashlib.sha256(
                f"{batch_index}:{item_count}:{chunk_digest}".encode()
            ).hexdigest()

        self.batches.append(
            DenseBatchProfile(
                batch_index=batch_index,
                item_count=item_count,
                model_input_token_counts=counts,
                max_sequence_length=max_sequence_length,
                encode_ms=encode_ms,
                persistence_ms=persistence_ms,
                peak_vram_bytes_after=peak_vram_bytes_after,
                batch_identity_digest=identity,
                chunk_ids_digest=chunk_digest,
                token_length_stats=token_stats,
                aggregate_input_tokens=aggregate,
                padded_token_workload=padded,
                padding_fraction=padding_fraction,
                encode_cuda_device_ms=encode_cuda_device_ms,
                encode_cuda_device_status=encode_cuda_device_status,
                encode_cuda_device_error=encode_cuda_device_error,
                process_cpu_delta=process_cpu_delta,
                cuda_allocator_after=cuda_allocator_after,
                gpu_external_before=gpu_external_before,
                gpu_external_after=gpu_external_after,
            )
        )
        if peak_vram_bytes_after is not None:
            if self.peak_vram_bytes is None or peak_vram_bytes_after > self.peak_vram_bytes:
                self.peak_vram_bytes = peak_vram_bytes_after
                self.peak_vram_status = "observed"

    def finalize_encode_split(self) -> None:
        if len(self.batches) >= 2:
            steady = [b.encode_ms for b in self.batches[1:]]
            self.steady_state_encode_ms_mean = float(statistics.fmean(steady))
        elif len(self.batches) == 1:
            self.steady_state_encode_ms_mean = None

    def summarize(self) -> dict[str, Any]:
        self.finalize_encode_split()
        token_dist = _token_distribution(self._token_counts)
        per_batch_max = [
            b.max_sequence_length
            for b in self.batches
            if b.max_sequence_length is not None
        ]
        total_model_tokens = sum(self._token_counts)
        encode_sec = self.encode_ms_total / 1000.0 if self.encode_ms_total > 0 else None
        chunks_per_sec = None
        if self.embeddings_generated > 0 and encode_sec and encode_sec > 0:
            chunks_per_sec = self.embeddings_generated / encode_sec
        tokens_per_sec = None
        if total_model_tokens > 0 and encode_sec and encode_sec > 0:
            tokens_per_sec = total_model_tokens / encode_sec
        return {
            "contract": PROFILE_CONTRACT,
            "stall_attribution_tooling": self.stall_attribution_tooling,
            "cold_or_warm": self.cold_or_warm,
            "oversized_unsplittable_count": self.oversized_unsplittable_count,
            "embeddings_generated": self.embeddings_generated,
            "embeddings_reused": self.embeddings_reused,
            "batch_count": len(self.batches),
            "model_input_token_count_total": total_model_tokens,
            "model_input_token_stats": token_dist,
            "per_batch_max_sequence_length": {
                "max": max(per_batch_max) if per_batch_max else None,
                "values": per_batch_max,
            },
            "timing_ms": {
                "encode_total": self.encode_ms_total,
                "embedding_artifact_persistence_total": self.persistence_ms_total,
                "dense_point_construction": self.point_construction_ms,
                "qdrant_materialization_upsert": self.qdrant_materialization_ms,
                "first_batch_encode": self.first_batch_encode_ms,
                "steady_state_encode_mean": self.steady_state_encode_ms_mean,
            },
            "throughput": {
                "generated_chunks_per_sec_encode": chunks_per_sec,
                "model_input_tokens_per_sec_encode": tokens_per_sec,
            },
            "tokenizer_status": self.tokenizer_status,
            "tokenizer_error": self.tokenizer_error,
            "peak_vram_bytes": self.peak_vram_bytes,
            "peak_vram_status": self.peak_vram_status,
            "peak_vram_error": self.peak_vram_error,
            "batches": [self._batch_dict(b) for b in self.batches],
            "encode_attempts": list(self.encode_attempts),
        }

    @staticmethod
    def _batch_dict(b: DenseBatchProfile) -> dict[str, Any]:
        return {
            "batch_index": b.batch_index,
            "batch_identity_digest": b.batch_identity_digest,
            "chunk_ids_digest": b.chunk_ids_digest,
            "item_count": b.item_count,
            "max_sequence_length": b.max_sequence_length,
            "token_length_stats": b.token_length_stats,
            "aggregate_input_tokens": b.aggregate_input_tokens
            if b.aggregate_input_tokens is not None
            else sum(b.model_input_token_counts),
            "padded_token_workload": b.padded_token_workload,
            "padding_fraction": b.padding_fraction,
            "encode_ms": b.encode_ms,
            "encode_cuda_device_ms": b.encode_cuda_device_ms,
            "encode_cuda_device_status": b.encode_cuda_device_status,
            "encode_cuda_device_error": b.encode_cuda_device_error,
            "persistence_ms": b.persistence_ms,
            "peak_vram_bytes_after": b.peak_vram_bytes_after,
            "process_cpu_delta": b.process_cpu_delta,
            "cuda_allocator_after": b.cuda_allocator_after,
            "gpu_external_before": b.gpu_external_before,
            "gpu_external_after": b.gpu_external_after,
        }


_collector_var: ContextVar[DenseProfileCollector | None] = ContextVar(
    "dense_profile_collector", default=None
)


def get_dense_profile_collector() -> DenseProfileCollector | None:
    return _collector_var.get()


@contextmanager
def dense_profile_session(
    collector: DenseProfileCollector | None = None,
) -> Iterator[DenseProfileCollector | None]:
    """Bind a collector for the current context when profiling is enabled."""
    if not dense_profile_enabled():
        yield None
        return
    active = collector if collector is not None else DenseProfileCollector()
    token: Token = _collector_var.set(active)
    try:
        yield active
    finally:
        _collector_var.reset(token)


def _resolve_embedder_tokenizer(embedder: object) -> Any:
    """Prefer already-loaded ST tokenizer; else load tokenizer-only from model_path.

    Never calls the full SentenceTransformer weight load — that would distort
    first-batch encode timing.
    """
    model = getattr(embedder, "_model", None)
    if model is not None:
        tokenizer = getattr(model, "tokenizer", None)
        if tokenizer is not None:
            return tokenizer
    model_path = getattr(embedder, "model_path", None)
    if model_path is not None:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(
            str(model_path),
            local_files_only=True,
            trust_remote_code=False,
        )
    raise RuntimeError("no tokenizer source on embedder")


def observe_model_input_token_counts(
    embedder: object,
    texts: list[str],
    collector: DenseProfileCollector,
) -> tuple[list[int] | None, int | None]:
    """Count tokens with the embedder tokenizer on the exact encode payloads.

    Never mutates texts. Failures are recorded; callers must not invent counts.
    """
    if not texts:
        return [], 0
    try:
        tokenizer = _resolve_embedder_tokenizer(embedder)
        counts: list[int] = []
        max_len = 0
        for text in texts:
            encoded = tokenizer(
                text,
                add_special_tokens=True,
                truncation=False,
                padding=False,
                return_attention_mask=False,
            )
            ids = encoded.get("input_ids") if isinstance(encoded, dict) else None
            if ids is None and hasattr(encoded, "input_ids"):
                ids = encoded.input_ids
            if ids is None:
                raise RuntimeError("tokenizer returned no input_ids")
            if ids and isinstance(ids[0], (list, tuple)):
                length = len(ids[0])
            else:
                length = len(ids)
            counts.append(int(length))
            if length > max_len:
                max_len = length
        collector.tokenizer_status = "observed"
        collector.tokenizer_error = None
        return counts, max_len
    except Exception as exc:  # noqa: BLE001 — observational only
        collector.tokenizer_status = "unavailable"
        collector.tokenizer_error = f"{type(exc).__name__}: {exc}"
        return None, None


def observe_peak_vram_bytes(collector: DenseProfileCollector) -> int | None:
    """Best-effort CUDA allocator peak; never fabricates a value."""
    try:
        import torch

        if not torch.cuda.is_available():
            collector.peak_vram_status = "unavailable"
            collector.peak_vram_error = "cuda_not_available"
            return None
        peak = int(torch.cuda.max_memory_allocated())
        collector.peak_vram_status = "observed"
        collector.peak_vram_error = None
        if collector.peak_vram_bytes is None or peak > collector.peak_vram_bytes:
            collector.peak_vram_bytes = peak
        return peak
    except Exception as exc:  # noqa: BLE001
        collector.peak_vram_status = "unavailable"
        collector.peak_vram_error = f"{type(exc).__name__}: {exc}"
        return None


def reset_peak_vram_stats() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # noqa: BLE001
        return


@contextmanager
def timed_ms() -> Iterator[list[float]]:
    """Yield a one-element list that receives elapsed milliseconds."""
    bucket = [0.0]
    started = time.perf_counter()
    try:
        yield bucket
    finally:
        bucket[0] = (time.perf_counter() - started) * 1000.0


@contextmanager
def profiled_encode_timing() -> Iterator[dict[str, Any]]:
    """Host-wall + optional CUDA-event device timing (profile path only).

    CUDA event synchronize runs only inside this diagnostic context so the
    production/disabled path never pays for forced sync.

    Interval contract (F001): ``encode_ms`` and ``process_cpu_delta`` bracket
    only the yielded encode body. CUDA event allocation/start-record and
    end-event synchronize run outside that rusage/wall interval so diagnostic
    setup cannot contaminate host-vs-device attribution.
    """
    result: dict[str, Any] = {
        "encode_ms": 0.0,
        "encode_cuda_device_ms": None,
        "encode_cuda_device_status": "not_attempted",
        "encode_cuda_device_error": None,
        "process_cpu_delta": None,
    }
    start_event = None
    end_event = None
    cuda_ok = False
    try:
        import torch

        if torch.cuda.is_available():
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            start_event.record()
            cuda_ok = True
    except Exception as exc:  # noqa: BLE001
        result["encode_cuda_device_status"] = "unavailable"
        result["encode_cuda_device_error"] = f"{type(exc).__name__}: {exc}"

    # Snapshot rusage only after CUDA diagnostic setup; wall and rusage share
    # the same encode-body interval (before end-event synchronize).
    before_rusage = _process_rusage_snapshot()
    wall_started = time.perf_counter()
    try:
        yield result
    finally:
        result["encode_ms"] = (time.perf_counter() - wall_started) * 1000.0
        after_rusage = _process_rusage_snapshot()
        result["process_cpu_delta"] = _rusage_delta(before_rusage, after_rusage)
        if cuda_ok and start_event is not None and end_event is not None:
            try:
                end_event.record()
                end_event.synchronize()
                result["encode_cuda_device_ms"] = float(start_event.elapsed_time(end_event))
                result["encode_cuda_device_status"] = "observed"
                result["encode_cuda_device_error"] = None
            except Exception as exc:  # noqa: BLE001
                result["encode_cuda_device_status"] = "unavailable"
                result["encode_cuda_device_error"] = f"{type(exc).__name__}: {exc}"
        elif result["encode_cuda_device_status"] == "not_attempted":
            result["encode_cuda_device_status"] = "unavailable"
            result["encode_cuda_device_error"] = "cuda_not_available"


@dataclass
class PracticalTimingCollector:
    """Wall-clock component timers for D2 practical measurement (no CUDA sync)."""

    encode_ms: float = 0.0
    embedding_persistence_ms: float = 0.0
    point_construction_ms: float = 0.0
    qdrant_ms: float = 0.0


_practical_var: ContextVar[PracticalTimingCollector | None] = ContextVar(
    "dense_practical_timing", default=None
)


def get_practical_timing_collector() -> PracticalTimingCollector | None:
    return _practical_var.get()


@contextmanager
def dense_practical_timing_session() -> Iterator[PracticalTimingCollector]:
    """Always-on lightweight wall timers (production-representative)."""
    collector = PracticalTimingCollector()
    token: Token = _practical_var.set(collector)
    try:
        yield collector
    finally:
        _practical_var.reset(token)


__all__ = [
    "DIAG_DENSE_PROFILE_ENV",
    "PROFILE_CONTRACT",
    "DenseBatchProfile",
    "DenseEncodeBatchContext",
    "DenseProfileCollector",
    "PracticalTimingCollector",
    "batch_identity_digest",
    "dense_encode_batch_context",
    "dense_practical_timing_session",
    "dense_profile_enabled",
    "dense_profile_session",
    "get_dense_encode_batch_context",
    "get_dense_profile_collector",
    "get_practical_timing_collector",
    "observe_cuda_allocator_state",
    "observe_cuda_global_memory_state",
    "observe_model_input_token_counts",
    "observe_peak_vram_bytes",
    "profiled_encode_timing",
    "reset_peak_vram_stats",
    "sample_external_gpu_state",
    "timed_ms",
]
