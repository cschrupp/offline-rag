#!/usr/bin/env python3
"""Execute frozen GPU residency/allocator diagnostic campaign.

Authority: S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001
Contract: docs/slice16k_gpu_residency_allocator_diagnostic_execution.md
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/user/projects/technical_rag")
EVIDENCE = ROOT / "docs/evidence/16k_gpu_residency_allocator"
OCCUPANT = ROOT / "scripts/diag_constrained_vram/cuda_occupant.py"
MANIFEST = ROOT / "docs/evidence/16k_gpu_residency_allocator_tooling/instrumentation_manifest.json"
WS = "ws_fdd77b77611448eb93cdc239d2610281"
SNAP = "snap_3c4048d380b1f5db12a20f820082c1942ccaacc96e368dfb04c22aba5090a9c9"
QUESTION = "what is common valor?"
BASELINE = "163078753eeda33959c9957cfad4e82876a7a5f5"
TOOLING_SUBJECT = "a26ea53f6ce32c6454d21a6d6af988d50299ae49"
TOOLING_ACCEPT_PARENT = "a04d8f6131553beed0585a3c877cfbc2641c1863"
AUTH = "S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001"
HEADER = "X-Seneca-Diag-Token"
# Token from env only; never written to evidence.
TOKEN_ENV = "OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN"

CELLS_ORDER = [
    "C0",
    "H3-A",
    "H3-B",
    "H3-C",
    "H3-D",
    "H1-A",
    "H1-B",
    "H2-C",
    "H2-A",
    "H2-B",
    "H4-A",
]

CELL_OPS: dict[str, list[str]] = {
    "C0": [],
    "H3-A": ["load_embedder", "load_reranker"],
    "H3-B": ["load_reranker", "load_embedder"],
    "H3-C": ["touch_embedder", "touch_reranker"],
    "H3-D": ["touch_reranker", "touch_embedder"],
    "H1-A": ["load_embedder"],
    "H1-B": ["load_reranker"],
    "H2-C": ["load_embedder"],
    "H2-A": ["load_embedder", "h2_reserve_gap"],
    "H2-B": ["load_embedder", "h2_fragment"],
    "H4-A": ["load_embedder", "load_reranker"],  # occupant after
}

RECOVERY_CELL = {
    "H3-A": "C0",
    "H3-B": "C0",
    "H3-C": "C0",
    "H3-D": "C0",
    "H1-A": "C0",
    "H1-B": "C0",
    "H2-A": "H2-C",
    "H2-B": "H2-C",
    "H4-A": "H3-A",  # dual-resident E→R without occupant
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_product_baseline() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    allow = {e["path"]: e["sha256"] for e in manifest["allowlisted_src_offline_rag_deltas"]}
    names = subprocess.check_output(
        ["git", "diff", "--name-only", BASELINE, "--", "src/offline_rag/"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    mismatches = []
    for n in names:
        p = ROOT / n
        if not p.is_file():
            continue
        h = sha256_file(p)
        if n not in allow:
            mismatches.append({"path": n, "error": "unauthorized_delta", "sha256": h})
        elif allow[n] != h:
            mismatches.append({"path": n, "error": "digest_mismatch", "sha256": h, "expected": allow[n]})
    for path, expected in allow.items():
        actual = sha256_file(ROOT / path)
        if actual != expected:
            mismatches.append({"path": path, "error": "digest_mismatch", "sha256": actual, "expected": expected})
    return {
        "product_behavior_baseline_ok": not mismatches,
        "mismatches": mismatches,
        "allowlist": allow,
    }


def assert_binding() -> dict:
    w = json.loads((ROOT / "data/workspaces" / WS / "workspace.json").read_text())
    ok = (
        w.get("workspace_id") == WS
        and w.get("revision") == 13
        and w.get("current_snapshot_id") == SNAP
    )
    return {
        "binding_assert_ok": ok,
        "workspace_id": w.get("workspace_id"),
        "revision": w.get("revision"),
        "snapshot_id": w.get("current_snapshot_id"),
    }


def nvidia_memory() -> dict:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    total, used, free = [int(x.strip()) for x in out.split(",")]
    apps_raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader",
        ],
        text=True,
    ).strip()
    apps = []
    if apps_raw:
        for line in apps_raw.splitlines():
            parts = [p.strip() for p in line.split(",")]
            apps.append(
                {
                    "pid": parts[0] if parts else None,
                    "process_name": parts[1] if len(parts) > 1 else None,
                    "used_gpu_memory": parts[2] if len(parts) > 2 else None,
                }
            )
    return {"total_mib": total, "used_mib": used, "free_mib": free, "compute_apps": apps}


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 600.0):
    data = None if body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}, time.perf_counter() - t0, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            envelope = json.loads(raw)
        except Exception:
            envelope = {"_raw": raw[:4000]}
        return e.code, envelope, time.perf_counter() - t0, raw[:4000]


def pgrep_api() -> list[int]:
    cp = subprocess.run(
        ["pgrep", "-f", r"python -m offline_rag.api.server"],
        text=True,
        capture_output=True,
    )
    if cp.returncode != 0:
        return []
    return [int(x) for x in cp.stdout.split() if x.strip()]


def kill_api() -> None:
    for pid in pgrep_api():
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 25
    while time.time() < deadline and pgrep_api():
        time.sleep(0.2)
    for pid in pgrep_api():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(1)


def start_api(token: str, log_path: Path) -> int:
    kill_api()
    env = os.environ.copy()
    env["OFFLINE_RAG_DIAG_GPU_PROBE"] = "1"
    env[TOKEN_ENV] = token
    env["OFFLINE_RAG_DATA_DIR"] = str(ROOT / "data")
    env["OFFLINE_RAG_MODELS_DIR"] = str(ROOT / "models")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "w", encoding="utf-8")
    subprocess.Popen(
        ["uv", "run", "python", "-m", "offline_rag.api.server"],
        cwd=str(ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    for _ in range(120):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError(f"API health timeout; see {log_path}")
    pids = pgrep_api()
    if not pids:
        raise RuntimeError("API up but PID not found")
    return pids[-1]


def diag_headers(token: str) -> dict:
    return {HEADER: token}


def get_state(token: str) -> dict:
    status, body, _, _ = http_json(
        "GET", "http://127.0.0.1:8080/v1/_diag/gpu/state", headers=diag_headers(token)
    )
    if status != 200:
        raise RuntimeError(f"diag state failed: {status} {body}")
    return body


def diag_action(token: str, op: str) -> dict:
    status, body, _, err = http_json(
        "POST",
        "http://127.0.0.1:8080/v1/_diag/gpu/action",
        {"op": op},
        headers=diag_headers(token),
    )
    return {"http_status": status, "payload": body, "err": err}


def read_durable_trace(trace_id: str | None) -> dict | None:
    if not trace_id:
        return None
    path = ROOT / "data" / "traces" / f"{trace_id}.json"
    if not path.is_file():
        # try newest
        traces = sorted((ROOT / "data" / "traces").glob("trace_*.json"), key=lambda p: p.stat().st_mtime)
        if not traces:
            return None
        return json.loads(traces[-1].read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def extract_trace_id(envelope: dict) -> str | None:
    if not isinstance(envelope, dict):
        return None
    if envelope.get("trace_id"):
        return envelope["trace_id"]
    err = envelope.get("error") or {}
    if isinstance(err, dict) and err.get("trace_id"):
        return err["trace_id"]
    return envelope.get("query_trace_id")


def is_campaign_positive(http_status: int, durable: dict | None) -> bool:
    if http_status != 500:
        return False
    if not durable:
        return False
    internal = durable.get("internal_failure")
    if not isinstance(internal, dict):
        return False
    # CUDA-related under existing classifier
    cuda_class = internal.get("cuda_failure_class") or internal.get("cuda_class")
    if cuda_class:
        return True
    failure_class = str(internal.get("failure_class") or "").lower()
    stage = str(internal.get("failure_stage") or "").lower()
    blob = json.dumps(internal).lower()
    if "cuda" in blob or "cublas" in blob:
        return True
    if "cuda" in failure_class or "cuda" in stage:
        return True
    return False


def h2_manipulation_ok(cell: str, action_results: list[dict], pre_state: dict) -> tuple[bool, dict]:
    if cell == "H2-C":
        return True, {"kind": "control"}
    if cell == "H2-A":
        for ar in action_results:
            if ar.get("op") == "h2_reserve_gap" and ar.get("http_status") == 200:
                pl = ar.get("payload") or {}
                before = pl.get("before") or {}
                after_alloc = pl.get("after_alloc") or {}
                after_release = pl.get("after_release") or {}
                ba = before.get("memory_allocated")
                aa = after_alloc.get("memory_allocated")
                ra = after_release.get("memory_allocated")
                br = before.get("memory_reserved") or 0
                rr = after_release.get("memory_reserved") or 0
                # allocated returns near pre-action; reserved gap increased
                ok = (
                    ba is not None
                    and aa is not None
                    and ra is not None
                    and aa > ba
                    and abs(ra - ba) < 16 * 1024 * 1024
                    and rr > br
                )
                return ok, {
                    "kind": "h2_reserve_gap",
                    "before_allocated": ba,
                    "after_alloc_allocated": aa,
                    "after_release_allocated": ra,
                    "before_reserved": br,
                    "after_release_reserved": rr,
                    "established": ok,
                }
        return False, {"kind": "h2_reserve_gap", "established": False, "reason": "action_missing"}
    if cell == "H2-B":
        for ar in action_results:
            if ar.get("op") == "h2_fragment" and ar.get("http_status") == 200:
                pl = ar.get("payload") or {}
                pattern = pl.get("pattern") or {}
                after = pl.get("after") or {}
                stats = after.get("memory_stats") or {}
                inactive = stats.get("inactive_split_bytes.all.current")
                retained = pattern.get("retained_live_mib")
                ok = retained == 64 and inactive is not None and int(inactive) > 0
                return ok, {
                    "kind": "h2_fragment",
                    "retained_live_mib": retained,
                    "inactive_split_bytes": inactive,
                    "established": ok,
                }
        return False, {"kind": "h2_fragment", "established": False, "reason": "action_missing"}
    return True, {}


def start_occupant(status_path: Path) -> subprocess.Popen:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            str(OCCUPANT),
            "--min-free-mib",
            "400",
            "--max-free-mib",
            "800",
            "--status-file",
            str(status_path),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(120):
        if status_path.is_file():
            break
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"occupant failed: {err or out}")
        time.sleep(0.25)
    else:
        proc.terminate()
        raise RuntimeError("occupant status timeout")
    return proc


def run_cell(
    *,
    cell: str,
    role: str,
    token: str,
    git_sha: str,
    related: dict | None = None,
) -> dict:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    run_id = f"{cell}_{role}_{int(time.time())}"
    log_path = Path(f"/tmp/seneca-gpu-res-{run_id}.log")
    baseline = verify_product_baseline()
    binding = assert_binding()
    if not baseline["product_behavior_baseline_ok"] or not binding["binding_assert_ok"]:
        return {
            "cell": cell,
            "role": role,
            "run_id": run_id,
            "status": "RUN_STOP",
            "reason": "preflight_failed",
            "product_baseline": baseline,
            "binding": binding,
            "execution_authority": AUTH,
            "execution_git_sha": git_sha,
        }

    api_pid = start_api(token, log_path)
    occupant = None
    occ_status = None
    action_results = []
    conditioning_failure = None
    try:
        # Apply ops
        for op in CELL_OPS[cell]:
            # H2 free check after load_embedder before manip
            if cell in {"H2-A", "H2-B"} and op in {"h2_reserve_gap", "h2_fragment"}:
                st = get_state(token)
                loaded = st.get("loaded_model_inventory") or {}
                resident = st.get("cuda_resident_model_inventory") or {}
                free = ((st.get("allocator") or {}).get("mem_get_info") or {}).get("free_mib")
                if not loaded.get("embedder") or resident.get("embedder") is False:
                    conditioning_failure = {
                        "reason": "embedder_not_resident",
                        "state": st,
                    }
                    break
                if loaded.get("reranker") or resident.get("reranker"):
                    conditioning_failure = {
                        "reason": "reranker_unexpectedly_present",
                        "state": st,
                    }
                    break
                if free is None or int(free) < 1024:
                    return {
                        "cell": cell,
                        "role": role,
                        "run_id": run_id,
                        "status": "H2_NOT_EXECUTABLE",
                        "reason": f"free_mib={free} < 1024 after embedder-only",
                        "pre_manip_state": st,
                        "api_pid": api_pid,
                        "execution_authority": AUTH,
                        "execution_git_sha": git_sha,
                        "accepted_tooling_subject": TOOLING_SUBJECT,
                        "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
                        "product_baseline": baseline,
                        "binding": binding,
                        "host_gpu": nvidia_memory(),
                    }
            ar = diag_action(token, op)
            ar["op"] = op
            action_results.append(ar)
            if ar["http_status"] != 200:
                conditioning_failure = {"reason": "action_failed", "action": ar}
                break

        if conditioning_failure:
            evidence = {
                "cell": cell,
                "role": role,
                "run_id": run_id,
                "status": "CONDITIONING_FAILURE",
                "conditioning_failure": conditioning_failure,
                "action_results": [{k: v for k, v in a.items() if k != "err"} for a in action_results],
                "api_pid": api_pid,
                "execution_authority": AUTH,
                "execution_git_sha": git_sha,
                "accepted_tooling_subject": TOOLING_SUBJECT,
                "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
                "product_baseline": baseline,
                "binding": binding,
                "host_gpu": nvidia_memory(),
                "related": related,
            }
            path = EVIDENCE / f"{run_id}.json"
            path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            return evidence

        if cell == "H4-A":
            occ_path = EVIDENCE / f"{run_id}_occupant.json"
            occupant = start_occupant(occ_path)
            occ_status = json.loads(occ_path.read_text(encoding="utf-8"))
            mem = nvidia_memory()
            if not (400 <= mem["free_mib"] <= 800):
                evidence = {
                    "cell": cell,
                    "role": role,
                    "run_id": run_id,
                    "status": "CONDITIONING_FAILURE",
                    "reason": f"occupant free_mib={mem['free_mib']} not in 400-800",
                    "occupant": occ_status,
                    "host_gpu": mem,
                    "api_pid": api_pid,
                    "execution_authority": AUTH,
                    "execution_git_sha": git_sha,
                    "accepted_tooling_subject": TOOLING_SUBJECT,
                    "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
                    "product_baseline": baseline,
                    "binding": binding,
                    "related": related,
                }
                path = EVIDENCE / f"{run_id}.json"
                path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
                return evidence

        pre_state = get_state(token)
        manip_ok, manip_detail = h2_manipulation_ok(cell, action_results, pre_state)
        if cell in {"H2-A", "H2-B"} and not manip_ok:
            evidence = {
                "cell": cell,
                "role": role,
                "run_id": run_id,
                "status": "MANIPULATION_NOT_ESTABLISHED",
                "h2_manipulation": manip_detail,
                "pre_request_state": pre_state,
                "action_results": [{k: v for k, v in a.items() if k != "err"} for a in action_results],
                "api_pid": api_pid,
                "execution_authority": AUTH,
                "execution_git_sha": git_sha,
                "accepted_tooling_subject": TOOLING_SUBJECT,
                "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
                "product_baseline": baseline,
                "binding": binding,
                "host_gpu": nvidia_memory(),
                "related": related,
            }
            path = EVIDENCE / f"{run_id}.json"
            path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            return evidence

        # Re-verify binding immediately pre-request
        binding2 = assert_binding()
        if not binding2["binding_assert_ok"]:
            evidence = {
                "cell": cell,
                "role": role,
                "run_id": run_id,
                "status": "RUN_STOP",
                "reason": "binding_failed_pre_request",
                "binding": binding2,
                "execution_authority": AUTH,
                "execution_git_sha": git_sha,
            }
            path = EVIDENCE / f"{run_id}.json"
            path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            return evidence

        host_pre = nvidia_memory()
        status, envelope, wall_s, err_text = http_json(
            "POST",
            f"http://127.0.0.1:8080/v1/workspaces/{WS}/conversation/turn",
            {"question": QUESTION, "prior_turns": []},
        )
        trace_id = extract_trace_id(envelope)
        durable = read_durable_trace(trace_id)
        if durable and not trace_id:
            trace_id = durable.get("trace_id")
        positive = is_campaign_positive(status, durable)
        post_state = None
        try:
            post_state = get_state(token)
        except Exception as exc:  # noqa: BLE001
            post_state = {"error": type(exc).__name__}

        evidence = {
            "cell": cell,
            "role": role,
            "run_id": run_id,
            "status": "PRIMARY_COMPLETE",
            "conditioning_ops": CELL_OPS[cell],
            "action_results": [{k: v for k, v in a.items() if k != "err"} for a in action_results],
            "h2_manipulation": manip_detail,
            "pre_request_state": pre_state,
            "post_request_state": post_state,
            "api_pid": api_pid,
            "probe_api_pid": pre_state.get("api_pid"),
            "loaded_model_inventory": pre_state.get("loaded_model_inventory"),
            "cuda_resident_model_inventory": pre_state.get("cuda_resident_model_inventory"),
            "allocator_pre": pre_state.get("allocator"),
            "host_gpu_pre": host_pre,
            "host_gpu_post": nvidia_memory(),
            "occupant": occ_status,
            "http_status": status,
            "wall_s": wall_s,
            "envelope_keys": sorted(envelope.keys()) if isinstance(envelope, dict) else None,
            "trace_id": trace_id,
            "durable_trace_status": (durable or {}).get("status"),
            "durable_trace_error_code": (durable or {}).get("error_code"),
            "durable_snapshot_id": (durable or {}).get("snapshot_id"),
            "internal_failure": (durable or {}).get("internal_failure"),
            "candidate_positive": positive,
            "execution_authority": AUTH,
            "execution_git_sha": git_sha,
            "accepted_tooling_subject": TOOLING_SUBJECT,
            "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
            "product_baseline": {
                "product_behavior_baseline_ok": baseline["product_behavior_baseline_ok"],
                "allowlist_paths": list(baseline["allowlist"].keys()),
            },
            "binding": binding2,
            "question": QUESTION,
            "surface": "POST /v1/workspaces/{id}/conversation/turn",
            "related": related,
            "api_log": str(log_path),
            # never include token
        }
        path = EVIDENCE / f"{run_id}.json"
        path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        evidence["evidence_path"] = str(path)
        return evidence
    finally:
        if occupant and occupant.poll() is None:
            occupant.terminate()
            try:
                occupant.wait(timeout=15)
            except subprocess.TimeoutExpired:
                occupant.kill()
        kill_api()


def main() -> int:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        print(f"STOP: set {TOKEN_ENV} in the environment", file=sys.stderr)
        return 2
    os.environ[TOKEN_ENV] = token
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not git_sha.startswith("c9daa88"):
        print(f"STOP: unexpected tip {git_sha}", file=sys.stderr)
        return 2

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    summary: dict = {
        "authority": AUTH,
        "execution_git_sha": git_sha,
        "accepted_tooling_subject": TOOLING_SUBJECT,
        "tooling_acceptance_record_parent": TOOLING_ACCEPT_PARENT,
        "cells": [],
        "skipped": [],
        "stopping_condition": None,
        "scientific_disposition": None,
        "m0_m2_eligibility_gate": "NOT SATISFIED",
    }

    h1_h3_inconclusive_or_negative = True
    h2_executable_done = True
    positive_stop = False

    for cell in CELLS_ORDER:
        if cell == "H4-A":
            # only if H1-H3 and executable H2 negative/inconclusive
            if positive_stop:
                summary["skipped"].append({"cell": cell, "reason": "prior_positive_stop"})
                break
            # Check prior cells for reproduced positive - already handled by break
            # H4 only if no positive and priors not all blockers that make campaign inconclusive only
            pass

        if cell.startswith("H2") and not h2_executable_done and cell != "H2-C":
            # placeholder
            pass

        print(f"=== RUN {cell} primary ===", flush=True)
        result = run_cell(cell=cell, role="primary", token=token, git_sha=git_sha)
        summary["cells"].append(
            {
                "cell": cell,
                "role": "primary",
                "run_id": result.get("run_id"),
                "status": result.get("status"),
                "http_status": result.get("http_status"),
                "candidate_positive": result.get("candidate_positive"),
                "evidence_path": result.get("evidence_path") or str(EVIDENCE / f"{result.get('run_id')}.json"),
            }
        )

        if result.get("status") == "RUN_STOP":
            summary["stopping_condition"] = "preflight_or_binding_stop"
            summary["scientific_disposition"] = "INCONCLUSIVE"
            break

        if result.get("status") == "H2_NOT_EXECUTABLE":
            summary["skipped"].append({"cell": cell, "reason": result.get("reason")})
            if cell in {"H2-A", "H2-B", "H2-C"}:
                # Remaining H2 cells share the same free-VRAM precondition after embedder load.
                for later in ("H2-A", "H2-B", "H2-C"):
                    if later == cell:
                        continue
                    if later in CELLS_ORDER[CELLS_ORDER.index(cell) + 1 :]:
                        if not any(s.get("cell") == later for s in summary["skipped"]):
                            summary["skipped"].append(
                                {"cell": later, "reason": result.get("reason")}
                            )
                # remove future H2 from iteration by marking skip set
                h2_executable_done = False
            continue
        if cell.startswith("H2") and any(
            s.get("cell") == cell and "free_mib" in str(s.get("reason"))
            for s in summary["skipped"]
        ):
            continue

        if result.get("status") in {"CONDITIONING_FAILURE", "MANIPULATION_NOT_ESTABLISHED"}:
            # inconclusive for that cell; continue matrix
            continue

        if result.get("candidate_positive"):
            print(f"=== REPEAT {cell} ===", flush=True)
            rep = run_cell(
                cell=cell,
                role="repeat",
                token=token,
                git_sha=git_sha,
                related={"primary_run_id": result.get("run_id")},
            )
            summary["cells"].append(
                {
                    "cell": cell,
                    "role": "repeat",
                    "run_id": rep.get("run_id"),
                    "status": rep.get("status"),
                    "http_status": rep.get("http_status"),
                    "candidate_positive": rep.get("candidate_positive"),
                    "evidence_path": rep.get("evidence_path"),
                }
            )
            if rep.get("candidate_positive"):
                recovery_cell = RECOVERY_CELL[cell]
                print(f"=== RECOVERY {recovery_cell} for {cell} ===", flush=True)
                rec = run_cell(
                    cell=recovery_cell,
                    role=f"recovery_for_{cell}",
                    token=token,
                    git_sha=git_sha,
                    related={"primary_run_id": result.get("run_id"), "repeat_run_id": rep.get("run_id")},
                )
                summary["cells"].append(
                    {
                        "cell": recovery_cell,
                        "role": f"recovery_for_{cell}",
                        "run_id": rec.get("run_id"),
                        "status": rec.get("status"),
                        "http_status": rec.get("http_status"),
                        "candidate_positive": rec.get("candidate_positive"),
                        "evidence_path": rec.get("evidence_path"),
                    }
                )
                recovered = (
                    rec.get("status") == "PRIMARY_COMPLETE"
                    and not rec.get("candidate_positive")
                    and rec.get("http_status") != 500
                )
                if recovered:
                    summary["stopping_condition"] = f"reproduced_positive_with_recovery:{cell}"
                    summary["scientific_disposition"] = "POSITIVE"
                    summary["m0_m2_eligibility_gate"] = "SATISFIED"
                    positive_stop = True
                    break
                # reproduced but recovery failed → continue? Contract: only failure→repro→recovery establishes candidate.
                # If recovery fails, do not STOP as POSITIVE; continue matrix.
            # if repeat not positive, continue

        # H4 gate: skip if we somehow shouldn't - handled by order and positive_stop

    else:
        # completed loop without break from positive
        pass

    if summary["scientific_disposition"] is None:
        # Classify NEGATIVE vs INCONCLUSIVE
        statuses = [c.get("status") for c in summary["cells"]]
        material_blockers = [
            s
            for s in statuses
            if s
            in {
                "CONDITIONING_FAILURE",
                "MANIPULATION_NOT_ESTABLISHED",
                "H2_NOT_EXECUTABLE",
                "RUN_STOP",
            }
        ]
        primaries = [c for c in summary["cells"] if c.get("role") == "primary"]
        completed = [c for c in primaries if c.get("status") == "PRIMARY_COMPLETE"]
        # Did we execute all cells that should run?
        executed_cells = {c["cell"] for c in primaries}
        required = set(CELLS_ORDER)
        # H4 only if priors ok
        if "H4-A" not in executed_cells and "H4-A" not in {s.get("cell") for s in summary["skipped"]}:
            # if we broke early for other reasons
            pass
        if material_blockers and len(completed) < len(required) - len(summary["skipped"]):
            summary["scientific_disposition"] = "INCONCLUSIVE"
            summary["stopping_condition"] = summary["stopping_condition"] or "matrix_incomplete_or_blocked"
        else:
            summary["scientific_disposition"] = "NEGATIVE"
            summary["stopping_condition"] = "matrix_complete_without_reproduced_positive"
            summary["m0_m2_eligibility_gate"] = "NOT SATISFIED"

    # Ensure H4 skipped reason if positive stop before H4
    if positive_stop:
        for c in CELLS_ORDER:
            if c not in {x["cell"] for x in summary["cells"] if x.get("role") == "primary"}:
                if not any(s.get("cell") == c for s in summary["skipped"]):
                    summary["skipped"].append({"cell": c, "reason": "stopped_after_positive"})

    out = EVIDENCE / "campaign_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in (
        "scientific_disposition",
        "stopping_condition",
        "m0_m2_eligibility_gate",
        "cells",
        "skipped",
    )}, indent=2))
    print(f"WROTE {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
