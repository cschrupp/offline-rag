"""Independent process for a specifically labeled scratch session."""

import subprocess
from pathlib import Path
from time import monotonic, sleep

from docker_adapter import owned_container, terminate
from host_watchdog import available_kib


def supervise(*, name, session, deadline, done, abort, restore, verify):
    """Keep restoration ownership outside the HTTP driver process.

    The launcher must keep this supervisor alive independently and supply
    trusted, separately bounded host restoration commands.
    """
    done = Path(done)
    abort = Path(abort)
    while not done.exists():
        try:
            safe = monotonic() < deadline and available_kib() >= 2 * 1024 * 1024
        except (OSError, ValueError):
            safe = False
        if not safe:
            abort.touch()
            break
        sleep(0.1)
    terminate(name, session)
    if owned_container(name, session) is not None:
        raise RuntimeError("cannot restore before container termination")
    subprocess.run(restore, timeout=540, check=True)
    subprocess.run(verify, timeout=300, check=True)
    return 124 if abort.exists() else 0
