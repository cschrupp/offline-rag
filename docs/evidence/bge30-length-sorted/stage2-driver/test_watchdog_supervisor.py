"""Docker integration tests for independent diagnostic teardown and restore."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
from docker_adapter import IMAGE, LABEL, docker, owned_container, terminate
from rehearse_stage2 import create_baseline, remove_restored_baseline
from watchdog_supervisor import supervise

DRIVER_DIR = Path(__file__).resolve().parent


def require_docker_image() -> None:
    try:
        item = json.loads(docker("image", "inspect", IMAGE))[0]
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("pinned local diagnostic Docker image is unavailable")
    if item.get("Id") != IMAGE:
        pytest.skip("pinned local diagnostic Docker image is unavailable")


def make_baseline(tmp_path: Path, session: str) -> str:
    require_docker_image()
    return create_baseline(tmp_path, session, DRIVER_DIR / "baseline_server.py")


def start_diagnostic(root: Path, session: str) -> str:
    name = f"seneca-stage2-{session}"
    docker(
        "run",
        "--detach",
        "--network",
        "none",
        "--label",
        f"{LABEL}={session}",
        "--name",
        name,
        "--mount",
        f"type=bind,src={root},dst=/scratch",
        "--entrypoint",
        "python",
        IMAGE,
        "-B",
        "-c",
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(3600)",
    )
    return name


def run_supervisor_in_thread(
    *,
    root: Path,
    session: str,
    baseline: str,
    driver_pid: int,
    ceiling: float = 5,
    inject_restore_failure: bool = False,
) -> tuple[threading.Thread, dict[str, int]]:
    result: dict[str, int] = {}
    heartbeat = root / "heartbeat"
    heartbeat.touch()
    done = root / "driver_done.json"
    args = {
        "root": root,
        "session": session,
        "name": f"seneca-stage2-{session}",
        "baseline": baseline,
        "driver_pid": driver_pid,
        "driver_done": done,
        "heartbeat": heartbeat,
        "result_path": root / "supervisor_result.json",
        "ceiling_seconds": ceiling,
        "inject_restore_failure": inject_restore_failure,
    }
    thread = threading.Thread(
        target=lambda: result.setdefault("code", supervise(**args)),
        daemon=True,
    )
    thread.start()
    return thread, result


def cleanup_session(name: str, session: str, baseline: str) -> None:
    if owned_container(name, session) is not None:
        terminate(name, session)
    remove_restored_baseline(baseline)


def test_watchdog_deadline_kills_unresponsive_container_and_restores(tmp_path):
    session = uuid.uuid4().hex[:12]
    baseline = make_baseline(tmp_path, session)
    name = start_diagnostic(tmp_path, session)
    driver = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    thread, outcome = run_supervisor_in_thread(
        root=tmp_path,
        session=session,
        baseline=baseline,
        driver_pid=driver.pid,
        ceiling=0.25,
    )
    try:
        thread.join(timeout=30)
        assert not thread.is_alive()
        driver.wait(timeout=5)
        result = json.loads((tmp_path / "supervisor_result.json").read_text())
        assert outcome["code"] == 1
        assert result["state"] == "restored"
        assert result["abort_reason"] == "diagnostic_execution_ceiling"
        assert result["session_containers_remaining"] == 0
        assert owned_container(name, session) is None
        assert driver.returncode != 0
        docker(
            "exec",
            baseline,
            "python",
            "-c",
            "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health').status == 200",
        )
    finally:
        if driver.poll() is None:
            driver.kill()
            driver.wait(timeout=5)
        cleanup_session(name, session, baseline)


def test_driver_termination_is_detected_and_container_is_reaped(tmp_path):
    session = uuid.uuid4().hex[:12]
    baseline = make_baseline(tmp_path, session)
    name = start_diagnostic(tmp_path, session)
    driver = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    thread, outcome = run_supervisor_in_thread(
        root=tmp_path,
        session=session,
        baseline=baseline,
        driver_pid=driver.pid,
    )
    try:
        time.sleep(0.25)
        os.kill(driver.pid, signal.SIGKILL)
        driver.wait(timeout=5)
        thread.join(timeout=30)
        assert not thread.is_alive()
        result = json.loads((tmp_path / "supervisor_result.json").read_text())
        assert outcome["code"] == 1
        assert result["state"] == "restored"
        assert result["abort_reason"] == "driver_terminated_without_completion"
        assert result["session_containers_remaining"] == 0
        assert owned_container(name, session) is None
    finally:
        if driver.poll() is None:
            driver.kill()
            driver.wait(timeout=5)
        cleanup_session(name, session, baseline)


def test_failed_restoration_verification_is_never_reported_as_success(tmp_path):
    session = uuid.uuid4().hex[:12]
    baseline = make_baseline(tmp_path, session)
    done = tmp_path / "driver_done.json"
    done.write_text('{"exit_code": 0}\n', encoding="utf-8")
    thread, outcome = run_supervisor_in_thread(
        root=tmp_path,
        session=session,
        baseline=baseline,
        driver_pid=2147483647,
        inject_restore_failure=True,
    )
    try:
        thread.join(timeout=20)
        assert not thread.is_alive()
        result = json.loads((tmp_path / "supervisor_result.json").read_text())
        assert outcome["code"] == 1
        assert result["state"] == "restoration_failed"
        assert (
            "injected restoration verification failure" in result["restoration_error"]
        )
    finally:
        remove_restored_baseline(baseline)
