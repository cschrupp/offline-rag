#!/usr/bin/env python3
"""Run one constrained-VRAM diagnostic condition against Seneca.

External orchestration only. Does not import Seneca product packages for
classification; reads durable ProductQueryTrace JSON from disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/user/projects/technical_rag")
WS = "ws_fdd77b77611448eb93cdc239d2610281"
SNAP = "snap_3c4048d380b1f5db12a20f820082c1942ccaacc96e368dfb04c22aba5090a9c9"
QUESTION = "what is common valor?"
OCCUPANT = ROOT / "scripts/diag_constrained_vram/cuda_occupant.py"
EVIDENCE_DIR = ROOT / "docs/evidence/16k_constrained_vram"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=False, **kwargs)


def nvidia_memory() -> dict:
    out = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).strip()
    name, total, used, free = [x.strip() for x in out.split(",")]
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
    return {
        "name": name,
        "total_mib": int(total),
        "used_mib": int(used),
        "free_mib": int(free),
        "compute_apps": apps,
    }


def pgrep_api() -> list[int]:
    cp = run(["pgrep", "-f", r"/.venv/bin/python3 -m offline_rag.api.server"])
    if cp.returncode != 0:
        return []
    return [int(x) for x in cp.stdout.split() if x.strip()]


def kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.time() + 20
    while time.time() < deadline:
        alive = [p for p in pids if Path(f"/proc/{p}").exists()]
        if not alive:
            return
        time.sleep(0.2)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_api(log_path: Path) -> int:
    env = os.environ.copy()
    env["OFFLINE_RAG_DATA_DIR"] = str(ROOT / "data")
    env["OFFLINE_RAG_MODELS_DIR"] = str(ROOT / "models")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "offline_rag.api.server"],
        cwd=str(ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    # Wait for health
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"API exited early; see {log_path}")
        time.sleep(1)
    else:
        raise RuntimeError("API health timeout")
    pids = pgrep_api()
    if not pids:
        raise RuntimeError("API health ok but PID not found")
    return pids[-1]


def http_json(method: str, url: str, body: dict | None = None, timeout: float = 300.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, dict(resp.headers.items()), json.loads(raw), time.perf_counter() - t0, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            envelope = json.loads(raw)
        except Exception:
            envelope = {"_raw": raw[:4000]}
        return e.code, dict(e.headers.items()) if e.headers else {}, envelope, time.perf_counter() - t0, raw[:4000]


def read_internal_failure(trace_id: str | None) -> dict | None:
    if not trace_id:
        return None
    path = ROOT / "data" / "traces" / f"{trace_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def start_occupant(min_free: int, max_free: int, status_path: Path) -> subprocess.Popen[str]:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/python"),
            str(OCCUPANT),
            "--min-free-mib",
            str(min_free),
            "--max-free-mib",
            str(max_free),
            "--status-file",
            str(status_path),
        ],
        cwd=str(ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait until status file exists or process exits
    for _ in range(120):
        if status_path.is_file():
            break
        if proc.poll() is not None:
            out, err = proc.communicate()
            raise RuntimeError(f"occupant failed rc={proc.returncode} err={err} out={out}")
        time.sleep(0.25)
    else:
        proc.terminate()
        raise RuntimeError("occupant status timeout")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True)
    parser.add_argument("--band", choices=["none", "b1", "b2"], default="none")
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args()

    bands = {
        "none": None,
        "b1": (1500, 2000),
        "b2": (400, 800),
    }
    band = bands[args.band]

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"{args.condition}_{int(time.time())}"
    out_path = EVIDENCE_DIR / f"{run_id}.json"
    log_path = Path(f"/tmp/seneca-constrained-vram-{args.condition}.log")
    occ_status = EVIDENCE_DIR / f"{run_id}_occupant.json"

    # Cleanup prior
    kill_pids(pgrep_api())
    # kill leftover occupants
    cp = run(["pgrep", "-f", "scripts/diag_constrained_vram/cuda_occupant.py"])
    if cp.returncode == 0:
        kill_pids([int(x) for x in cp.stdout.split() if x.strip()])
    time.sleep(1)
    host_baseline = nvidia_memory()

    api_pid = start_api(log_path)
    after_health = nvidia_memory()
    # Health must not materially warm models: API should not appear with large VRAM.
    api_apps = [a for a in after_health["compute_apps"] if str(a.get("pid")) == str(api_pid)]
    health_warmed = False
    for app in api_apps:
        # Meaningful attribution only (ignore spurious WSL listings).
        mem_s = str(app.get("used_gpu_memory") or "0")
        digits = "".join(ch for ch in mem_s if ch.isdigit())
        if digits and int(digits) >= 200:
            health_warmed = True
            break

    occupant_proc = None
    occupant_info = None
    if band is not None:
        occupant_proc = start_occupant(band[0], band[1], occ_status)
        occupant_info = json.loads(occ_status.read_text(encoding="utf-8"))
        # verify still in band
        mem_check = nvidia_memory()
        if not (band[0] <= mem_check["free_mib"] <= band[1]):
            if occupant_proc.poll() is None:
                occupant_proc.terminate()
            raise RuntimeError(
                f"free VRAM {mem_check['free_mib']} not in band {band} after occupant"
            )

    pre_request = {
        "t": utc_now(),
        "gpu": nvidia_memory(),
        "api_pid": api_pid,
        "occupant": occupant_info,
        "health_warmed_models": health_warmed,
        "host_baseline_before_api": host_baseline,
        "after_health": after_health,
    }

    if health_warmed:
        # STOP semantics for this condition: do not issue query.
        result = {
            "condition": args.condition,
            "stop": "health_warmed_models",
            "git_sha": args.git_sha,
            "pre_request": pre_request,
        }
        out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        kill_pids([api_pid])
        if occupant_proc and occupant_proc.poll() is None:
            occupant_proc.terminate()
        return 10

    status, headers, envelope, wall_s, err_text = http_json(
        "POST",
        f"http://127.0.0.1:8080/v1/workspaces/{WS}/conversation/turn",
        {"question": QUESTION, "prior_turns": []},
    )
    post_request = {"t": utc_now(), "gpu": nvidia_memory(), "wall_s": wall_s}

    trace_id = None
    if isinstance(envelope, dict):
        trace_id = envelope.get("trace_id") or envelope.get("query_trace_id")
        err = envelope.get("error") or {}
        if isinstance(err, dict) and err.get("trace_id"):
            trace_id = err.get("trace_id") or trace_id
        # AppError envelope may put trace_id at top level
        if envelope.get("trace_id"):
            trace_id = envelope["trace_id"]

    # Also scan for latest trace if missing
    durable = read_internal_failure(trace_id) if trace_id else None
    if durable is None and status >= 500:
        # best-effort: newest trace file
        traces = sorted((ROOT / "data" / "traces").glob("trace_*.json"), key=lambda p: p.stat().st_mtime)
        if traces:
            durable = json.loads(traces[-1].read_text(encoding="utf-8"))
            trace_id = durable.get("trace_id")

    internal = (durable or {}).get("internal_failure") if durable else None

    # teardown
    kill_pids([api_pid])
    if occupant_proc and occupant_proc.poll() is None:
        occupant_proc.terminate()
        try:
            occupant_proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            occupant_proc.kill()
    time.sleep(1)
    after_teardown = nvidia_memory()

    result = {
        "condition": args.condition,
        "band": args.band,
        "git_sha": args.git_sha,
        "build_note": "instrumented observability subject 1630787 + docs through branch tip",
        "workspace_id": WS,
        "workspace_revision_expected": 13,
        "snapshot_id_expected": SNAP,
        "question": QUESTION,
        "question_sha256": hashlib.sha256(QUESTION.encode()).hexdigest(),
        "surface": "POST /v1/workspaces/{id}/conversation/turn",
        "prior_turns": [],
        "pre_request": pre_request,
        "http_status": status,
        "response_headers": headers,
        "envelope": envelope,
        "err_text": err_text,
        "wall_s": wall_s,
        "trace_id": trace_id,
        "durable_trace_error_code": (durable or {}).get("error_code"),
        "durable_trace_status": (durable or {}).get("status"),
        "durable_snapshot_id": (durable or {}).get("snapshot_id"),
        "internal_failure": internal,
        "post_request": post_request,
        "after_teardown": after_teardown,
        "api_log": str(log_path),
        "recorded_at": utc_now(),
    }
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "condition", "http_status", "trace_id", "internal_failure",
        "pre_request", "wall_s",
    )}, indent=2, default=str))
    print(f"WROTE {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
