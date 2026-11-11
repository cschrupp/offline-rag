"""Cross-process tests for lease ownership and OS-managed release semantics."""

from __future__ import annotations

import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from offline_rag.core import platform_lock
from offline_rag.core.platform_lock import acquire_exclusive, release_exclusive

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HOLDER = """
import os, sys
from offline_rag.core.platform_lock import acquire_exclusive, release_exclusive
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
acquire_exclusive(fd, blocking=True)
print('acquired', flush=True)
if len(sys.argv) > 2:
    with open(sys.argv[2], 'w', encoding='ascii') as marker:
        marker.write('acquired')
sys.stdin.read(1)
release_exclusive(fd)
os.close(fd)
"""


def _spawn_holder(
    path: Path, *, marker_path: Path | None = None
) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    source = str(_REPO_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        value for value in (source, existing) if value
    )
    command = [sys.executable, "-c", _HOLDER, str(path)]
    if marker_path is not None:
        command.append(str(marker_path))
    process = subprocess.Popen(
        command,
        cwd=_REPO_ROOT,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process


def _start_holder(path: Path) -> subprocess.Popen[str]:
    process = _spawn_holder(path)
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "acquired"
    return process


def test_nonblocking_acquire_reports_live_owner_and_release_reuses_lockfile(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resource.lock"
    holder = _start_holder(path)
    fd = os.open(path, os.O_RDWR)
    try:
        try:
            acquire_exclusive(fd, blocking=False)
        except BlockingIOError:
            pass
        else:
            raise AssertionError("second process acquired a live owner's lease")
    finally:
        os.close(fd)
        assert holder.stdin is not None
        holder.stdin.write("x")
        holder.stdin.flush()
        assert holder.wait(timeout=5) == 0

    fd = os.open(path, os.O_RDWR)
    try:
        acquire_exclusive(fd, blocking=False)
        release_exclusive(fd)
    finally:
        os.close(fd)
    assert path.exists(), "lease file persists after release; ownership is OS-managed"


def test_process_death_releases_live_owner_lease(tmp_path: Path) -> None:
    path = tmp_path / "owner-death.lock"
    holder = _start_holder(path)
    holder.terminate()
    assert holder.wait(timeout=5) is not None

    fd = os.open(path, os.O_RDWR)
    try:
        acquire_exclusive(fd, blocking=False)
        release_exclusive(fd)
    finally:
        os.close(fd)


def test_blocking_acquire_waits_for_owner_without_timeout_theft(
    tmp_path: Path,
) -> None:
    path = tmp_path / "blocking.lock"
    holder = _start_holder(path)
    marker_path = tmp_path / "contender-acquired"
    contender = _spawn_holder(path, marker_path=marker_path)
    time.sleep(0.15)
    assert not marker_path.exists(), "blocking acquisition must wait for live owner"

    assert holder.stdin is not None
    holder.stdin.write("x")
    holder.stdin.flush()
    assert holder.wait(timeout=5) == 0
    deadline = time.monotonic() + 5
    while not marker_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker_path.exists(), "contender should acquire after owner releases"
    assert contender.stdout is not None
    assert contender.stdout.readline().strip() == "acquired"
    assert contender.stdin is not None
    contender.stdin.write("x")
    contender.stdin.flush()
    assert contender.wait(timeout=5) == 0


def test_windows_blocking_adapter_retries_lock_contention(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class LockViolation(OSError):
        winerror = 33

    attempts = 0
    calls: list[tuple[int, int, int]] = []

    def locking(fd: int, mode: int, length: int) -> None:
        nonlocal attempts
        calls.append((fd, mode, length))
        if mode == 1 and attempts < 2:
            attempts += 1
            raise LockViolation("live lock owner")

    fake_msvcrt = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(platform_lock.sys, "platform", "win32")
    sleeps: list[float] = []
    monkeypatch.setattr(platform_lock.time, "sleep", sleeps.append)

    path = tmp_path / "windows.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        acquire_exclusive(fd, blocking=True)
        release_exclusive(fd)
    finally:
        os.close(fd)

    assert sleeps == [platform_lock._WINDOWS_RETRY_SECONDS] * 2
    assert [mode for _, mode, _ in calls] == [1, 1, 1, 2]
    assert path.stat().st_size == platform_lock._WINDOWS_LOCK_LENGTH


def test_windows_nonblocking_adapter_maps_only_lock_violation_to_busy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class LockViolation(OSError):
        winerror = 33

    def locking(_fd: int, mode: int, _length: int) -> None:
        if mode == 1:
            raise LockViolation("live lock owner")

    fake_msvcrt = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(platform_lock.sys, "platform", "win32")
    path = tmp_path / "windows-nonblocking.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        with pytest.raises(BlockingIOError):
            acquire_exclusive(fd, blocking=False)
    finally:
        os.close(fd)


def test_posix_only_resource_measurements_remain_unavailable_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    from offline_rag.dense import d2_observability, profiling

    original_import = builtins.__import__

    def import_without_resource(name: str, *args: object, **kwargs: object):
        if name == "resource":
            raise ImportError("resource module unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_resource)
    snapshot = profiling._process_rusage_snapshot()
    facts = d2_observability.capture_cpu_baseline_facts()

    assert snapshot["status"] == "unavailable"
    assert snapshot["user_time_s"] is None
    assert facts["process_cpu_time_s"] is None
    assert facts["peak_rss_bytes"] is None
