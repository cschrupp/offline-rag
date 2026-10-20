#!/usr/bin/env python3
"""Capability-only demo for 16K-D D1 stall-attribution tooling.

Authority: S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-AUTH-001
Does NOT execute the scientific D1-A/D1-B campaign.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

AUTH = "S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-AUTH-001"
EVIDENCE = ROOT / "docs/evidence/16k_d_dense_cuda_tooling"


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _optional_cuda_matmul_timing() -> dict:
    """Tiny CUDA workload to prove event timing can be observed when GPU exists."""
    from offline_rag.dense.profiling import profiled_encode_timing

    try:
        import torch
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "encode_ms": None,
            "encode_cuda_device_ms": None,
        }
    if not torch.cuda.is_available():
        return {
            "status": "unavailable",
            "error": "cuda_not_available",
            "encode_ms": None,
            "encode_cuda_device_ms": None,
        }
    with profiled_encode_timing() as timing:
        a = torch.randn((1024, 1024), device="cuda", dtype=torch.float16)
        b = torch.randn((1024, 1024), device="cuda", dtype=torch.float16)
        _ = a @ b
    return {
        "status": timing["encode_cuda_device_status"],
        "error": timing["encode_cuda_device_error"],
        "encode_ms": timing["encode_ms"],
        "encode_cuda_device_ms": timing["encode_cuda_device_ms"],
        "process_cpu_delta_status": (timing.get("process_cpu_delta") or {}).get(
            "status"
        ),
    }


def main() -> int:
    from offline_rag.dense.embedder import FakeEmbedder
    from offline_rag.dense.profiling import (
        DIAG_DENSE_PROFILE_ENV,
        PROFILE_CONTRACT,
        DenseProfileCollector,
        batch_identity_digest,
        dense_profile_enabled,
        observe_cuda_allocator_state,
        profiled_encode_timing,
        sample_external_gpu_state,
    )

    # Disabled path must not enable profiling.
    os.environ.pop(DIAG_DENSE_PROFILE_ENV, None)
    assert dense_profile_enabled() is False

    os.environ[DIAG_DENSE_PROFILE_ENV] = "1"
    assert dense_profile_enabled() is True

    collector = DenseProfileCollector()
    texts = ["capability demo sentence one", "capability demo sentence two"]
    chunk_ids = ["chunk_cap_a", "chunk_cap_b"]
    embedder = FakeEmbedder(dimension=8)

    gpu_before = sample_external_gpu_state()
    with profiled_encode_timing() as timing:
        _ = embedder.embed_documents(texts)
    gpu_after = sample_external_gpu_state()
    allocator = observe_cuda_allocator_state()
    cuda_matmul = _optional_cuda_matmul_timing()

    # Fake embedder has no CUDA work — device timing may be unavailable or ~0.
    token_counts = [len(t.split()) for t in texts]  # shape placeholder for demo
    collector.record_batch(
        batch_index=0,
        item_count=len(texts),
        token_counts=token_counts,
        max_sequence_length=max(token_counts),
        encode_ms=float(timing["encode_ms"]),
        persistence_ms=0.0,
        peak_vram_bytes_after=None,
        chunk_ids=chunk_ids,
        encode_cuda_device_ms=timing["encode_cuda_device_ms"],
        encode_cuda_device_status=str(timing["encode_cuda_device_status"]),
        encode_cuda_device_error=timing["encode_cuda_device_error"],
        process_cpu_delta=timing["process_cpu_delta"],
        cuda_allocator_after=allocator,
        gpu_external_before=gpu_before,
        gpu_external_after=gpu_after,
    )
    summary = collector.summarize()
    batch0 = summary["batches"][0]

    required_keys = [
        "batch_identity_digest",
        "chunk_ids_digest",
        "item_count",
        "token_length_stats",
        "aggregate_input_tokens",
        "padded_token_workload",
        "padding_fraction",
        "encode_ms",
        "encode_cuda_device_ms",
        "encode_cuda_device_status",
        "process_cpu_delta",
        "cuda_allocator_after",
        "gpu_external_before",
        "gpu_external_after",
    ]
    missing = [k for k in required_keys if k not in batch0]
    if missing:
        raise SystemExit(f"capability demo missing batch keys: {missing}")

    capability = {
        "authority": AUTH,
        "contract": PROFILE_CONTRACT,
        "git_sha": _git_sha(),
        "recorded_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "scientific_execution": "NOT_AUTHORIZED",
        "demo": {
            "batch_identity_digest": batch0.get("batch_identity_digest"),
            "chunk_ids_digest": batch_identity_digest(chunk_ids),
            "item_count": batch0.get("item_count"),
            "token_length_stats": batch0.get("token_length_stats"),
            "aggregate_input_tokens": batch0.get("aggregate_input_tokens"),
            "padded_token_workload": batch0.get("padded_token_workload"),
            "padding_fraction": batch0.get("padding_fraction"),
            "encode_ms": batch0.get("encode_ms"),
            "encode_cuda_device_ms": batch0.get("encode_cuda_device_ms"),
            "encode_cuda_device_status": batch0.get("encode_cuda_device_status"),
            "process_cpu_delta": batch0.get("process_cpu_delta"),
            "cuda_allocator_after": batch0.get("cuda_allocator_after"),
            "gpu_external_before_status": (gpu_before or {}).get("status"),
            "gpu_external_after_status": (gpu_after or {}).get("status"),
            "gpu_external_after_sample": (gpu_after or {}).get("sample"),
            "optional_cuda_matmul_timing": cuda_matmul,
        },
        "notes": [
            "FakeEmbedder path proves host-wall + process CPU deltas without model CUDA work.",
            "nvidia-smi external sample runs outside encode; may be observed or unavailable.",
            "optional_cuda_matmul_timing proves CUDA-event device timing when a GPU is present.",
            "Unavailable metrics remain explicit null/unavailable — never fabricated.",
            "Scientific D1-A/D1-B campaign remains NOT AUTHORIZED under this tooling AUTH.",
        ],
    }

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "d1_tooling_capability.json"
    out.write_text(json.dumps(capability, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {out}")
    print(
        json.dumps(
            {
                "cuda_device_status": batch0.get("encode_cuda_device_status"),
                "gpu_external_after_status": (gpu_after or {}).get("status"),
                "process_cpu_status": (batch0.get("process_cpu_delta") or {}).get(
                    "status"
                ),
                "optional_cuda_matmul_status": cuda_matmul.get("status"),
                "contract": PROFILE_CONTRACT,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
