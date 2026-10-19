#!/usr/bin/env python3
"""Non-scientific capability runner for GPU residency/allocator diagnostic tooling.

Starts (or assumes) a loopback API with OFFLINE_RAG_DIAG_GPU_PROBE=1, exercises
G3–G7 primitives via the in-process probe, and writes structured evidence.
Does not issue historical conversation/turn requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/16k_gpu_residency_allocator_tooling"
HEADER = "X-Seneca-Diag-Token"


def _http(method: str, url: str, token: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            HEADER: token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"_raw": raw[:2000]}
        return e.code, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--token", default=os.environ.get("OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN", ""))
    parser.add_argument("--git-sha", default="")
    args = parser.parse_args()
    if not args.token:
        print("OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN required", file=sys.stderr)
        return 2

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    base = args.base_url.rstrip("/")
    results: dict = {
        "authority": "S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-AUTH-001",
        "git_sha": args.git_sha or subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "base_url": base,
        "steps": [],
    }

    def step(name: str, method: str, path: str, body: dict | None = None) -> dict:
        status, payload = _http(method, base + path, args.token, body)
        entry = {"name": name, "http_status": status, "payload": payload}
        results["steps"].append(entry)
        return entry

    # G3: state from API PID
    st = step("g3_state", "GET", "/v1/_diag/gpu/state")
    if st["http_status"] != 200:
        results["status"] = "FAILED"
        out = EVIDENCE / f"capability_{int(time.time())}.json"
        out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(results, indent=2))
        return 1

    alloc = (st["payload"].get("allocator") or {})
    if not alloc.get("cuda_available"):
        results["status"] = "BLOCKED"
        results["reason"] = "cuda_unavailable"
        out = EVIDENCE / f"capability_{int(time.time())}.json"
        out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "BLOCKED", "reason": "cuda_unavailable"}, indent=2))
        return 10

    free = (alloc.get("mem_get_info") or {}).get("free_mib")
    if free is None or int(free) < 1024:
        results["status"] = "BLOCKED"
        results["reason"] = f"free_mib={free} < 1024"
        out = EVIDENCE / f"capability_{int(time.time())}.json"
        out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "BLOCKED", "reason": results["reason"]}, indent=2))
        return 10

    # Allocator primitives before model loads so free-VRAM precondition holds.
    g4 = step("g4_h2_reserve_gap", "POST", "/v1/_diag/gpu/action", {"op": "h2_reserve_gap"})
    step("g4_release", "POST", "/v1/_diag/gpu/action", {"op": "release_h2"})
    g5 = step("g5_h2_fragment", "POST", "/v1/_diag/gpu/action", {"op": "h2_fragment"})
    step("g5_release", "POST", "/v1/_diag/gpu/action", {"op": "release_h2"})

    # G6 load orders (history recorded in diagnostic_load_action_sequence)
    step("g6_load_embedder", "POST", "/v1/_diag/gpu/action", {"op": "load_embedder"})
    step("g6_load_reranker", "POST", "/v1/_diag/gpu/action", {"op": "load_reranker"})
    st_ab = step("g6_state_ab", "GET", "/v1/_diag/gpu/state")
    seq = [
        e.get("op")
        for e in (st_ab["payload"].get("diagnostic_load_action_sequence") or [])
    ]
    results["load_sequence_ab"] = seq

    # G7: no workspace ops issued by this runner
    results["workspace_ops_issued"] = []
    required_ok = all(
        s["http_status"] == 200
        for s in results["steps"]
        if s["name"].startswith(("g3_", "g4_h2", "g5_h2", "g6_"))
    )
    if not required_ok or g4["http_status"] != 200 or g5["http_status"] != 200:
        results["status"] = "FAILED"
    else:
        results["status"] = "CAPABILITY_COMPLETE"
    out = EVIDENCE / f"capability_{int(time.time())}.json"
    text = json.dumps(results, indent=2) + "\n"
    out.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode()).hexdigest()
    print(json.dumps({"status": results["status"], "evidence": str(out), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
