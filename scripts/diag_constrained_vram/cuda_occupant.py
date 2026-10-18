#!/usr/bin/env python3
"""External CUDA memory occupant for constrained-VRAM diagnostics.

Standalone: no Seneca imports. Allocates ordinary CUDA tensors until
nvidia-smi free VRAM enters [min_free_mib, max_free_mib], then holds
allocation until SIGTERM/SIGINT. Release is by process exit only.
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from pathlib import Path


def nvidia_memory() -> dict[str, int]:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    total, used, free = [int(x.strip()) for x in out.split(",")]
    return {"total_mib": total, "used_mib": used, "free_mib": free}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-free-mib", type=int, required=True)
    parser.add_argument("--max-free-mib", type=int, required=True)
    parser.add_argument("--chunk-mib", type=int, default=256)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--hold-seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.min_free_mib > args.max_free_mib:
        print("min_free_mib must be <= max_free_mib", file=sys.stderr)
        return 2

    import torch

    if not torch.cuda.is_available():
        print("CUDA not available", file=sys.stderr)
        return 2

    device = torch.device("cuda:0")
    blocks: list[torch.Tensor] = []
    allocated_mib = 0
    stop = {"flag": False}

    def _stop(*_a: object) -> None:
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    # Target: free VRAM in [min, max]. If free > max, allocate; if free < min, fail.
    mem = nvidia_memory()
    if mem["free_mib"] < args.min_free_mib:
        print(
            json.dumps(
                {
                    "error": "free_vram_already_below_band",
                    "memory": mem,
                    "band": [args.min_free_mib, args.max_free_mib],
                }
            ),
            file=sys.stderr,
        )
        return 3

    elements_per_mib = (1024 * 1024) // 4  # float32
    chunk_elems = args.chunk_mib * elements_per_mib

    while mem["free_mib"] > args.max_free_mib and not stop["flag"]:
        try:
            blocks.append(torch.empty(chunk_elems, dtype=torch.float32, device=device))
            allocated_mib += args.chunk_mib
        except RuntimeError as exc:
            print(f"allocation_stopped: {type(exc).__name__}", file=sys.stderr)
            break
        mem = nvidia_memory()
        # Fine-tune: if we overshoot below min, drop last block.
        if mem["free_mib"] < args.min_free_mib and blocks:
            blocks.pop()
            allocated_mib = max(0, allocated_mib - args.chunk_mib)
            mem = nvidia_memory()
            break

    mem = nvidia_memory()
    in_band = args.min_free_mib <= mem["free_mib"] <= args.max_free_mib
    status = {
        "pid": __import__("os").getpid(),
        "allocated_mib": allocated_mib,
        "blocks": len(blocks),
        "in_band": in_band,
        "band_mib": [args.min_free_mib, args.max_free_mib],
        "memory": mem,
        "torch_cuda": torch.cuda.get_device_name(0),
    }
    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    args.status_file.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status), flush=True)
    if not in_band:
        return 4

    deadline = time.time() + args.hold_seconds
    while not stop["flag"] and time.time() < deadline:
        time.sleep(0.5)
    # Keep reference to blocks until exit so memory stays held.
    _ = len(blocks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
