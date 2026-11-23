"""Run the complete 36-send local HTTP rehearsal under an external watchdog.

This is a deterministic synthetic route/lifecycle exercise, not a native
performance or scientific-parity campaign.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter
from pathlib import Path

from docker_adapter import IMAGE, docker
from host_watchdog import available_kib

DRIVER_DIR = Path(__file__).resolve().parent
REPOSITORY = DRIVER_DIR.parents[3]
TOKENIZER_SOURCE = REPOSITORY / "models/tokenizers/tiktoken"


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def verify_pinned_image() -> dict:
    item = json.loads(docker("image", "inspect", IMAGE))[0]
    if item.get("Id") != IMAGE:
        raise RuntimeError("pinned image ID mismatch")
    if item.get("Os") != "linux" or item.get("Architecture") != "amd64":
        raise RuntimeError("pinned image platform mismatch")
    return {
        "image_id": item["Id"],
        "os": item["Os"],
        "architecture": item["Architecture"],
    }


def create_baseline(root: Path, session: str, script: Path) -> str:
    name = f"seneca-stage2-baseline-{session}"
    docker(
        "run",
        "-d",
        "--network",
        "none",
        "--cpus",
        "1",
        "--memory",
        "128m",
        "--label",
        "io.seneca.stage2.baseline=true",
        "--name",
        name,
        "--mount",
        f"type=bind,src={script},dst=/baseline_server.py,readonly",
        "--entrypoint",
        "python",
        IMAGE,
        "-B",
        "/baseline_server.py",
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            docker(
                "exec",
                name,
                "python",
                "-c",
                "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=1).status == 200",
                timeout=3,
            )
            break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(0.05)
    else:
        raise RuntimeError("disposable baseline failed its initial health check")
    docker("stop", "--timeout", "3", name, timeout=8)
    return name


def remove_restored_baseline(name: str) -> None:
    """Remove only the verified disposable baseline after restoration proof."""
    ids = docker(
        "ps",
        "-aq",
        "--filter",
        "label=io.seneca.stage2.baseline=true",
        "--filter",
        f"name=^{name}$",
    ).split()
    if len(ids) != 1:
        raise RuntimeError("baseline cleanup identity is missing or ambiguous")
    item = json.loads(docker("inspect", ids[0]))[0]
    if (
        item["Name"] != "/" + name
        or item["Config"]["Labels"].get("io.seneca.stage2.baseline") != "true"
    ):
        raise RuntimeError("refusing to remove a non-owned baseline container")
    if item["State"]["Running"]:
        docker("stop", "--timeout", "3", ids[0], timeout=8)
    docker("rm", ids[0], timeout=8)


def create_inputs(root: Path) -> None:
    (root / "inputs").mkdir()
    target = root / "inputs/tiktoken"
    shutil.copytree(TOKENIZER_SOURCE, target)
    if not (target / "offline-rag-tokenizer.json").is_file():
        raise RuntimeError("pinned tokenizer fixture is incomplete")
    for directory in (root, root / "inputs", target):
        os.chmod(directory, 0o755)
    for work in (root / "work-consecutive", root / "work-length_sorted_8"):
        work.mkdir(mode=0o777)
        os.chmod(work, 0o777)
    for directory in (root / "journal", root / "control"):
        directory.mkdir(mode=0o777)
        os.chmod(directory, 0o777)


def run_driver(
    root: Path, session: str, baseline: str, *, inject_restore_failure=False
) -> dict:
    start_file = root / "start"
    done_file = root / "driver_done.json"
    heartbeat = root / "heartbeat"
    supervisor_result = root / "supervisor_result.json"
    baseline_script = Path(tempfile.gettempdir()) / f"stage2-baseline-{session}.py"

    driver_code = r"""
import json, os, sys, threading, time, traceback
from pathlib import Path
from driver import Driver
from docker_adapter import DockerHTTPAdapter
from host_watchdog import available_kib

root, session, start = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
journal, control = root / "journal", root / "control"
heartbeat = root / "heartbeat"
done = root / "driver_done.json"
stopping = threading.Event()

def beat():
    while not stopping.wait(0.5):
        heartbeat.touch()

def emit(row):
    with (journal / "driver-events.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

thread = threading.Thread(target=beat, daemon=True)
thread.start()
code = 1
try:
    deadline = time.monotonic() + 30
    while not start.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("external supervisor did not arm")
        time.sleep(0.02)
    adapter = DockerHTTPAdapter(
        session=session,
        journal=journal,
        control=control,
        inputs=root / "inputs",
        driver_dir=Path(os.environ["STAGE2_DRIVER_DIR"]),
        work_roots={
            "consecutive": root / "work-consecutive",
            "length_sorted_8": root / "work-length_sorted_8",
        },
    )
    Driver(
        adapter,
        lambda: available_kib() >= 2 * 1024 * 1024,
        emit,
        duration=2400,
        watchdog=0.1,
    ).run()
    code = 0
except BaseException as exc:
    emit({"event": "driver_exception", "exception": type(exc).__name__, "message": str(exc)[:500]})
    traceback.print_exc(file=sys.stderr)
finally:
    stopping.set()
    thread.join(timeout=1)
    done.write_text(json.dumps({"exit_code": code}) + "\n", encoding="utf-8")
raise SystemExit(code)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(DRIVER_DIR)
    env["STAGE2_DRIVER_DIR"] = str(DRIVER_DIR)
    driver = subprocess.Popen(
        [sys.executable, "-c", driver_code, str(root), session, str(start_file)],
        env=env,
    )
    heartbeat.touch()
    supervisor_args = [
        sys.executable,
        str(DRIVER_DIR / "watchdog_supervisor.py"),
        "--root",
        str(root),
        "--session",
        session,
        "--name",
        f"seneca-stage2-{session}",
        "--baseline",
        baseline,
        "--driver-pid",
        str(driver.pid),
        "--driver-done",
        str(done_file),
        "--heartbeat",
        str(heartbeat),
        "--result",
        str(supervisor_result),
    ]
    if inject_restore_failure:
        supervisor_args.append("--inject-restore-failure")
    supervisor = subprocess.Popen(supervisor_args, env=env, start_new_session=True)
    # The supervisor is running before the first diagnostic container is made.
    time.sleep(0.15)
    start_file.touch()
    driver_code_result = driver.wait(timeout=2450)
    supervisor_code = supervisor.wait(timeout=120)
    if not supervisor_result.exists():
        raise RuntimeError("independent supervisor produced no restoration record")
    restoration = json.loads(supervisor_result.read_text(encoding="utf-8"))
    if (
        driver_code_result != 0
        or supervisor_code != 0
        or restoration["state"] != "restored"
    ):
        raise RuntimeError(
            f"rehearsal or restoration failed: driver={driver_code_result}, "
            f"supervisor={supervisor_code}, restoration={restoration}"
        )
    baseline_script.unlink(missing_ok=True)
    return {
        "driver_exit_code": driver_code_result,
        "supervisor_exit_code": supervisor_code,
        "restoration": restoration,
    }


def validate_ledger(root: Path) -> dict:
    journal = root / "journal"
    driver_rows = [
        json.loads(line)
        for line in (journal / "driver-events.jsonl").read_text().splitlines()
    ]
    attempts = [row for row in driver_rows if row.get("event") == "send_attempt"]
    settled = [row for row in driver_rows if row.get("event") == "settled"]
    if len(attempts) != 36 or len({row["ordinal"] for row in attempts}) != 36:
        raise RuntimeError("driver attempt ledger is not exactly 36 unique sends")
    if len(settled) != 36 or {row["ordinal"] for row in settled} != {
        row["ordinal"] for row in attempts
    }:
        raise RuntimeError("driver settlement ledger does not match sends")
    terminal_files = sorted(journal.glob("*.terminal.json"))
    if len(terminal_files) != 36:
        raise RuntimeError("expected one server-correlated terminal record per send")
    outcomes = [json.loads(path.read_text(encoding="utf-8")) for path in terminal_files]
    load = [row for row in attempts if row["case"] == "load"]
    lifecycle = [row for row in attempts if row["case"] != "load"]
    if len(load) != 28 or len(lifecycle) != 8:
        raise RuntimeError("load/lifecycle submission count mismatch")
    if Counter(row["strategy"] for row in attempts) != {
        "consecutive": 18,
        "length_sorted_8": 18,
    }:
        raise RuntimeError("per-arm submission count mismatch")
    for ordinal in range(1, 37):
        record = json.loads((journal / f"{ordinal}.terminal.json").read_text())
        if record["ordinal"] != ordinal or not record["settled"]:
            raise RuntimeError("terminal record ordinal mismatch")
    return {
        "attempts": len(attempts),
        "settled": len(settled),
        "load": len(load),
        "lifecycle": len(lifecycle),
        "per_strategy": dict(Counter(row["strategy"] for row in attempts)),
        "terminal_files": len(terminal_files),
        "outcomes": [
            {
                "ordinal": row["ordinal"],
                "strategy": next(
                    item["strategy"]
                    for item in attempts
                    if item["ordinal"] == row["ordinal"]
                ),
                "case": next(
                    item["case"]
                    for item in attempts
                    if item["ordinal"] == row["ordinal"]
                ),
                "admission": row["admission"],
                "terminal": row["terminal"],
                "reason": row["reason"],
                "http_status": row["http_status"],
                "server_http_status": row["server_http_status"],
                "worker_returned": row["worker_returned"],
                "slot_released": row["slot_released"],
            }
            for row in outcomes
        ],
    }


def archive_rehearsal(root: Path, destination: Path) -> dict:
    """Retain the complete sanitized correlation journal before scratch cleanup."""
    source = root / "journal"
    if not source.is_dir():
        raise RuntimeError("successful rehearsal has no journal to archive")
    destination.mkdir(parents=True, exist_ok=False)
    archive = destination / "raw"
    archive.mkdir()
    copied = []
    for path in sorted(source.iterdir()):
        if path.is_file() and (
            path.name in {"events.jsonl", "driver-events.jsonl"}
            or path.name.endswith(".terminal.json")
        ):
            target = archive / path.name
            shutil.copy2(path, target)
            copied.append(
                {
                    "path": target.relative_to(destination).as_posix(),
                    "bytes": target.stat().st_size,
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
    if len(copied) != 38:
        raise RuntimeError(f"expected 38 raw correlation files, found {len(copied)}")
    for name in ("driver_done.json", "supervisor_result.json"):
        path = root / name
        if not path.is_file():
            raise RuntimeError(f"successful rehearsal is missing {name}")
        target = destination / name
        shutil.copy2(path, target)
        copied.append(
            {
                "path": target.relative_to(destination).as_posix(),
                "bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    manifest = {"files": copied, "raw_correlation_file_count": 38}
    write_json(destination / "archive_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--archive-root", type=Path, default=DRIVER_DIR / "local-rehearsal"
    )
    options = parser.parse_args()
    image = verify_pinned_image()
    if available_kib() < 2 * 1024 * 1024:
        raise RuntimeError("host MemAvailable below 2 GiB before rehearsal")
    session = uuid.uuid4().hex[:16]
    root = Path(tempfile.mkdtemp(prefix=f"seneca-stage2-{session}-")).resolve()
    os.chmod(root, 0o755)
    create_inputs(root)
    baseline_script = Path(tempfile.gettempdir()) / f"stage2-baseline-{session}.py"
    shutil.copy2(DRIVER_DIR / "baseline_server.py", baseline_script)
    os.chmod(baseline_script, 0o644)
    completed = False
    try:
        baseline = create_baseline(root, session, baseline_script)
        orchestration = run_driver(root, session, baseline)
        ledger = validate_ledger(root)
        archive_path = options.archive_root / session
        archive_manifest = archive_rehearsal(root, archive_path)
        remove_restored_baseline(baseline)
        result = {
            "classification": "LOCAL_SYNTHETIC_REHEARSAL_PASS",
            "not_native_performance_or_scientific_parity": True,
            "source_revision": "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
            "diagnostic_image": image,
            "session": session,
            "orchestration": orchestration,
            "ledger": ledger,
            "raw_archive": archive_path.relative_to(DRIVER_DIR.parent).as_posix()
            if archive_path.is_relative_to(DRIVER_DIR.parent)
            else str(archive_path),
            "raw_archive_manifest": archive_manifest,
            "journal_sha256": hashlib.sha256(
                (root / "journal/events.jsonl").read_bytes()
            ).hexdigest(),
            "host_memavailable_kib_after": available_kib(),
        }
        destination = options.output or archive_path / "LOCAL_REHEARSAL_RESULT.json"
        write_json(destination, result)
        completed = True
        print(
            json.dumps({"result": str(destination), **result}, sort_keys=True, indent=2)
        )
    except BaseException:
        print(
            f"Rehearsal scratch and failure evidence retained at: {root}",
            file=sys.stderr,
        )
        raise
    finally:
        if completed and baseline_script.exists():
            baseline_script.unlink()
        # Preserve the diagnostic ledger on any failed rehearsal. Successful
        # evidence is written before scratch teardown; the caller may request
        # an output path outside the scratch directory.
        if completed:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
