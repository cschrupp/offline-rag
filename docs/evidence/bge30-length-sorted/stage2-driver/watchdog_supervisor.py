"""Independent teardown and restoration supervisor for local Docker rehearsal."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from docker_adapter import docker, owned_container, session_containers, terminate
from host_watchdog import available_kib

BASELINE_LABEL = "io.seneca.stage2.baseline"


def container_by_name(name: str, label: str):
    ids = docker(
        "ps", "-aq", "--filter", f"label={label}=true", "--filter", f"name=^{name}$"
    ).split()
    if not ids:
        return None
    if len(ids) != 1:
        raise RuntimeError("ambiguous baseline container identity")
    item = json.loads(docker("inspect", ids[0]))[0]
    if item["Name"] != "/" + name or item["Config"]["Labels"].get(label) != "true":
        raise RuntimeError("baseline container identity mismatch")
    return item


def pid_alive(pid: int) -> bool:
    stat = Path(f"/proc/{pid}/stat")
    try:
        if stat.read_text(encoding="ascii").split()[2] == "Z":
            return False
    except (OSError, IndexError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def assert_mounts_released(root: Path) -> None:
    containers = docker("ps", "-aq").split()
    if not containers:
        return
    for item in json.loads(docker("inspect", *containers)):
        for mount in item.get("Mounts", []):
            source = Path(mount.get("Source", "/")).resolve()
            if source == root or root in source.parents:
                raise RuntimeError("a Docker container still mounts rehearsal storage")


def verify_baseline(name: str, root: Path, *, inject_failure: bool = False) -> None:
    item = container_by_name(name, BASELINE_LABEL)
    if item is None:
        raise RuntimeError("baseline container missing during restoration")
    if not item["State"]["Running"]:
        docker("start", item["Id"], timeout=20)
    item = container_by_name(name, BASELINE_LABEL)
    if item is None or not item["State"]["Running"]:
        raise RuntimeError("baseline failed to restart")
    if inject_failure:
        raise RuntimeError("injected restoration verification failure")
    docker(
        "exec",
        item["Id"],
        "python",
        "-c",
        "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200",
        timeout=5,
    )
    assert_mounts_released(root)


def supervise(
    *,
    root: Path,
    session: str,
    name: str,
    baseline: str,
    driver_pid: int,
    driver_done: Path,
    heartbeat: Path,
    result_path: Path,
    ceiling_seconds: float = 2400,
    memory_floor_kib: int = 2 * 1024 * 1024,
    inject_restore_failure: bool = False,
) -> int:
    """Watch the driver independently, then always teardown and restore."""
    root = root.resolve(strict=True)
    started = time.monotonic()
    deadline = started + ceiling_seconds
    abort_reason = None
    while pid_alive(driver_pid):
        if time.monotonic() >= deadline:
            abort_reason = "diagnostic_execution_ceiling"
            break
        try:
            if available_kib() < memory_floor_kib:
                abort_reason = "host_memory_floor"
                break
        except (OSError, ValueError):
            abort_reason = "host_memory_unavailable"
            break
        try:
            heartbeat_age = time.time() - heartbeat.stat().st_mtime
        except OSError:
            heartbeat_age = time.time() - started
        if heartbeat_age > 15:
            abort_reason = "driver_heartbeat_lost"
            break
        time.sleep(0.1)

    # Only this session label/name is ever passed to teardown.
    restoration_error = None
    driver_exit = None
    try:
        owned = owned_container(name, session)
        if owned is not None:
            terminate(name, session)
        if session_containers(session):
            raise RuntimeError("session containers remain after teardown")
        assert_mounts_released(root)
        if pid_alive(driver_pid):
            try:
                os.kill(driver_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            until = time.monotonic() + 5
            while pid_alive(driver_pid) and time.monotonic() < until:
                time.sleep(0.05)
            if pid_alive(driver_pid):
                try:
                    os.kill(driver_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if driver_done.exists():
            record = json.loads(driver_done.read_text(encoding="utf-8"))
            driver_exit = record.get("exit_code")
            if driver_exit != 0:
                abort_reason = abort_reason or "driver_failed"
        else:
            abort_reason = abort_reason or "driver_terminated_without_completion"
        verify_baseline(baseline, root, inject_failure=inject_restore_failure)
    # Persist restoration failure even if the supervisor is interrupted.
    except BaseException as exc:  # noqa: BLE001
        restoration_error = f"{type(exc).__name__}: {exc}"

    result = {
        "state": "restored" if restoration_error is None else "restoration_failed",
        "abort_reason": abort_reason,
        "driver_exit_code": driver_exit,
        "restoration_error": restoration_error,
        "session_containers_remaining": len(session_containers(session)),
        "recorded_at_unix": time.time(),
    }
    result_path.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return 0 if restoration_error is None and abort_reason is None else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--driver-pid", type=int, required=True)
    parser.add_argument("--driver-done", type=Path, required=True)
    parser.add_argument("--heartbeat", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--ceiling", type=float, default=2400)
    parser.add_argument("--inject-restore-failure", action="store_true")
    options = parser.parse_args()
    code = supervise(
        root=options.root,
        session=options.session,
        name=options.name,
        baseline=options.baseline,
        driver_pid=options.driver_pid,
        driver_done=options.driver_done,
        heartbeat=options.heartbeat,
        result_path=options.result,
        ceiling_seconds=options.ceiling,
        inject_restore_failure=options.inject_restore_failure,
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
