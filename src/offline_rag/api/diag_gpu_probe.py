"""Env-gated in-process GPU diagnostic probe (tooling AUTH only).

Observes and conditions CUDA allocator / model residency inside the API
process. Not a public product contract. Never calls empty_cache, unload,
device migration, or workspace/query mutation.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Any

DIAG_GPU_PROBE_ENV = "OFFLINE_RAG_DIAG_GPU_PROBE"
DIAG_GPU_PROBE_TOKEN_ENV = "OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN"
DIAG_GPU_PROBE_HEADER = "X-Seneca-Diag-Token"

# Capability-only sizes (T5). Execution AUTH may pin different scientific sizes later.
H2_A_CAP_MIB = 256
H2_B_PRIME_MIB = 256
H2_B_BLOCK_MIB = 8
H2_B_BLOCK_COUNT = 16
H2_CAP_MIN_FREE_MIB = 1024

_SYNTHETIC_EMBED_TEXT = "seneca-diag-gpu-probe-touch-embedder"
_SYNTHETIC_RERANK_PAIR = (
    "seneca-diag-gpu-probe-query",
    "seneca-diag-gpu-probe-passage",
)

_MEMORY_STATS_KEYS = (
    "allocated_bytes.all.current",
    "reserved_bytes.all.current",
    "active_bytes.all.current",
    "inactive_split_bytes.all.current",
    "segment.all.current",
    "allocation.retry_count",
    "num_alloc_retries",
    "num_ooms",
)


def probe_flag_enabled() -> bool:
    return os.environ.get(DIAG_GPU_PROBE_ENV, "").strip() == "1"


def probe_token() -> str:
    return os.environ.get(DIAG_GPU_PROBE_TOKEN_ENV, "").strip()


@dataclass
class DiagGpuSession:
    """Process-local diagnostic session state (API worker)."""

    load_events: list[dict[str, Any]] = field(default_factory=list)
    held_blocks: list[Any] = field(default_factory=list)
    held_meta: dict[str, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record_event(self, op: str, **detail: Any) -> None:
        self.load_events.append({"op": op, **detail})


def _bytes_mib(n: int) -> int:
    return int(n) // (1024 * 1024)


def _model_loaded(obj: Any) -> bool:
    if obj is None:
        return False
    return getattr(obj, "_model", None) is not None


def _tensor_on_cuda(obj: Any) -> bool | None:
    """Best-effort: True/False if inspectable, None if unknown."""
    if obj is None or getattr(obj, "_model", None) is None:
        return False
    model = obj._model
    try:
        import torch

        if hasattr(model, "parameters"):
            param = next(model.parameters(), None)
            if param is None:
                return None
            return bool(param.is_cuda)
        # sentence-transformers wrapper
        auto = getattr(model, "_first_module", None) or getattr(model, "auto_model", None)
        if auto is None and hasattr(model, "__getitem__"):
            try:
                first = model[0]
                auto = getattr(first, "auto_model", None)
            except Exception:  # noqa: BLE001
                auto = None
        if auto is not None and hasattr(auto, "parameters"):
            param = next(auto.parameters(), None)
            if param is None:
                return None
            return bool(param.is_cuda)
    except Exception:  # noqa: BLE001
        return None
    return None


def collect_allocator_snapshot() -> dict[str, Any]:
    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return {"cuda_available": False, "error": type(exc).__name__}

    if not torch.cuda.is_available():
        return {
            "cuda_available": False,
            "device_name": None,
            "memory_allocated": None,
            "memory_reserved": None,
            "mem_get_info": None,
            "memory_stats": None,
        }

    device = torch.device("cuda:0")
    free_b, total_b = torch.cuda.mem_get_info(device)
    raw_stats = torch.cuda.memory_stats(device)
    stats = {k: raw_stats.get(k) for k in _MEMORY_STATS_KEYS}
    return {
        "cuda_available": True,
        "device_name": torch.cuda.get_device_name(device),
        "memory_allocated": int(torch.cuda.memory_allocated(device)),
        "memory_reserved": int(torch.cuda.memory_reserved(device)),
        "mem_get_info": {
            "free_bytes": int(free_b),
            "total_bytes": int(total_b),
            "free_mib": _bytes_mib(int(free_b)),
            "total_mib": _bytes_mib(int(total_b)),
        },
        "memory_stats": stats,
    }


def build_state(runtime: Any, session: DiagGpuSession) -> dict[str, Any]:
    resources = getattr(runtime, "resources", None)
    embedder = getattr(resources, "embedder", None) if resources else None
    reranker = getattr(resources, "reranker", None) if resources else None
    loaded = {
        "embedder": _model_loaded(embedder),
        "reranker": _model_loaded(reranker),
    }
    resident = {
        "embedder": _tensor_on_cuda(embedder),
        "reranker": _tensor_on_cuda(reranker),
    }
    alloc = collect_allocator_snapshot()
    return {
        "api_pid": os.getpid(),
        "probe_enabled": True,
        "loaded_model_inventory": loaded,
        "cuda_resident_model_inventory": resident,
        "diagnostic_load_action_sequence": list(session.load_events),
        "allocator": alloc,
        "held_diagnostic_allocation": {
            "blocks": len(session.held_blocks),
            "meta": dict(session.held_meta),
        },
    }


def _ensure_cuda_free_mib(min_free: int) -> None:
    snap = collect_allocator_snapshot()
    if not snap.get("cuda_available"):
        raise RuntimeError("CUDA not available for diagnostic allocator primitive")
    free = (snap.get("mem_get_info") or {}).get("free_mib")
    if free is None or int(free) < min_free:
        raise RuntimeError(
            f"capability precondition failed: free_mib={free} < {min_free}"
        )


def _alloc_uint8_mib(mib: int) -> Any:
    import torch

    n = int(mib) * 1024 * 1024
    return torch.empty(n, dtype=torch.uint8, device="cuda")


def run_action(runtime: Any, session: DiagGpuSession, op: str) -> dict[str, Any]:
    resources = getattr(runtime, "resources", None)
    if resources is None:
        raise RuntimeError("runtime resources unavailable")

    with session.lock:
        if op == "load_embedder":
            emb = resources.embedder
            if emb is None:
                raise RuntimeError("embedder resource missing")
            load = getattr(emb, "_load", None)
            if not callable(load):
                raise RuntimeError("embedder has no _load path")
            load()
            session.record_event(op, loaded=True)
            return {"ok": True, "op": op}

        if op == "load_reranker":
            rr = resources.reranker
            if rr is None:
                raise RuntimeError("reranker resource missing or disabled")
            load = getattr(rr, "_load", None)
            if not callable(load):
                raise RuntimeError("reranker has no _load path")
            load()
            session.record_event(op, loaded=True)
            return {"ok": True, "op": op}

        if op == "touch_embedder":
            emb = resources.embedder
            if emb is None:
                raise RuntimeError("embedder resource missing")
            emb.embed_query(_SYNTHETIC_EMBED_TEXT)
            session.record_event(op, prior_model_use=True)
            return {"ok": True, "op": op}

        if op == "touch_reranker":
            rr = resources.reranker
            if rr is None:
                raise RuntimeError("reranker resource missing or disabled")
            from offline_rag.rerank.protocol import RerankerPair

            q, p = _SYNTHETIC_RERANK_PAIR
            rr.score_pairs(
                [
                    RerankerPair(
                        chunk_id="diag_gpu_probe_chunk",
                        query_text=q,
                        passage_text=p,
                    )
                ]
            )
            session.record_event(op, prior_model_use=True)
            return {"ok": True, "op": op}

        if op == "h2_reserve_gap":
            _ensure_cuda_free_mib(H2_CAP_MIN_FREE_MIB)
            import torch

            before = collect_allocator_snapshot()
            block = _alloc_uint8_mib(H2_A_CAP_MIB)
            mid = collect_allocator_snapshot()
            del block
            torch.cuda.synchronize()
            after = collect_allocator_snapshot()
            session.held_meta = {
                "last_primitive": "h2_reserve_gap",
                "allocated_mib": H2_A_CAP_MIB,
                "refs_dropped": True,
                "empty_cache": False,
            }
            session.record_event(
                op,
                before=before,
                after_alloc=mid,
                after_release=after,
            )
            return {
                "ok": True,
                "op": op,
                "before": before,
                "after_alloc": mid,
                "after_release": after,
            }

        if op == "h2_fragment":
            _ensure_cuda_free_mib(H2_CAP_MIN_FREE_MIB)
            import torch

            before = collect_allocator_snapshot()
            prime = _alloc_uint8_mib(H2_B_PRIME_MIB)
            del prime
            torch.cuda.synchronize()
            blocks = [_alloc_uint8_mib(H2_B_BLOCK_MIB) for _ in range(H2_B_BLOCK_COUNT)]
            retained = [blocks[i] for i in range(H2_B_BLOCK_COUNT) if i % 2 == 0]
            released_idx = [i for i in range(H2_B_BLOCK_COUNT) if i % 2 == 1]
            # Drop odd-index refs by discarding the full list; keep only retained.
            del blocks
            session.held_blocks = retained
            torch.cuda.synchronize()
            after = collect_allocator_snapshot()
            pattern = {
                "prime_mib": H2_B_PRIME_MIB,
                "block_mib": H2_B_BLOCK_MIB,
                "block_count": H2_B_BLOCK_COUNT,
                "retained_indices": [i for i in range(H2_B_BLOCK_COUNT) if i % 2 == 0],
                "released_indices": released_idx,
                "retained_live_mib": (H2_B_BLOCK_COUNT // 2) * H2_B_BLOCK_MIB,
                "empty_cache": False,
            }
            session.held_meta = {"last_primitive": "h2_fragment", **pattern}
            session.record_event(op, before=before, after=after, pattern=pattern)
            return {"ok": True, "op": op, "before": before, "after": after, "pattern": pattern}

        if op == "release_h2":
            import torch

            session.held_blocks.clear()
            session.held_meta = {"last_primitive": "release_h2", "empty_cache": False}
            torch.cuda.synchronize()
            session.record_event(op)
            return {"ok": True, "op": op, "allocator": collect_allocator_snapshot()}

        raise ValueError(f"unknown diagnostic op: {op!r}")
