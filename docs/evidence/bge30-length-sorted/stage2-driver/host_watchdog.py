"""Independent watchdog for a local, isolated diagnostic process group."""

import argparse
import os
import signal
import subprocess
from pathlib import Path
from time import monotonic, sleep


def available_kib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    raise ValueError("MemAvailable missing")


def run(command, *, ceiling, memory_floor, grace=5):
    process = subprocess.Popen(command, start_new_session=True)
    deadline = monotonic() + ceiling
    try:
        while process.poll() is None:
            if monotonic() >= deadline or available_kib() < memory_floor:
                return 124
            sleep(0.05)
        return process.returncode
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    raise SystemExit(run(options.command, ceiling=2400, memory_floor=2 * 1024 * 1024))
