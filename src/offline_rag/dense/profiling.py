"""Env-gated observational dense indexing profile (16K-D D0).

Enabled only when ``OFFLINE_RAG_DIAG_DENSE_PROFILE=1``. Disabled path must not
alter embedding inputs, vectors, persistence, or Qdrant materialization.
Detailed per-batch records belong in benchmark/evidence artifacts — not the
durable ManagedOperationMetrics DTO.
"""

from __future__ import annotations

import os
import statistics
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any, Iterator  # noqa: TC003 — runtime Any used by helpers

DIAG_DENSE_PROFILE_ENV = "OFFLINE_RAG_DIAG_DENSE_PROFILE"


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
        return {"p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(float(v) for v in token_counts)
    return {
        "p50": int(round(_percentile(ordered, 50.0) or 0)),
        "p95": int(round(_percentile(ordered, 95.0) or 0)),
        "p99": int(round(_percentile(ordered, 99.0) or 0)),
        "max": int(max(token_counts)),
    }


@dataclass
class DenseBatchProfile:
    batch_index: int
    item_count: int
    model_input_token_counts: list[int]
    max_sequence_length: int | None
    encode_ms: float
    persistence_ms: float
    peak_vram_bytes_after: int | None = None


@dataclass
class DenseProfileCollector:
    """In-process collector for one dense indexing run."""

    cold_or_warm: str = "unknown"
    oversized_unsplittable_count: int = 0
    embeddings_generated: int = 0
    embeddings_reused: int = 0
    batches: list[DenseBatchProfile] = field(default_factory=list)
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
    _token_counts: list[int] = field(default_factory=list)

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
    ) -> None:
        counts = list(token_counts or [])
        self._token_counts.extend(counts)
        self.encode_ms_total += encode_ms
        self.persistence_ms_total += persistence_ms
        if batch_index == 0:
            self.first_batch_encode_ms = encode_ms
        self.batches.append(
            DenseBatchProfile(
                batch_index=batch_index,
                item_count=item_count,
                model_input_token_counts=counts,
                max_sequence_length=max_sequence_length,
                encode_ms=encode_ms,
                persistence_ms=persistence_ms,
                peak_vram_bytes_after=peak_vram_bytes_after,
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
            "contract": "dense-cuda-profile-v1",
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
            "batches": [
                {
                    "batch_index": b.batch_index,
                    "item_count": b.item_count,
                    "max_sequence_length": b.max_sequence_length,
                    "model_input_token_count_sum": sum(b.model_input_token_counts),
                    "encode_ms": b.encode_ms,
                    "persistence_ms": b.persistence_ms,
                    "peak_vram_bytes_after": b.peak_vram_bytes_after,
                }
                for b in self.batches
            ],
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
            # HF may return batch dim for a single string.
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


__all__ = [
    "DIAG_DENSE_PROFILE_ENV",
    "DenseBatchProfile",
    "DenseProfileCollector",
    "dense_profile_enabled",
    "dense_profile_session",
    "get_dense_profile_collector",
    "observe_model_input_token_counts",
    "observe_peak_vram_bytes",
    "reset_peak_vram_stats",
    "timed_ms",
]
