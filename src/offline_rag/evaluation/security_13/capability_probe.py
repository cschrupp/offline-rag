"""Harness-owned forbidden-capability sink instrumentation (OD-13-10 / Q5)."""

from __future__ import annotations

import builtins
import os
import socket
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


@dataclass
class CapabilityProbe:
    """Records forbidden capability invocations observed during a case run."""

    invocations: list[str] = field(default_factory=list)
    installed: bool = False
    complete: bool = False
    _allowlisted_open_prefixes: tuple[str, ...] = ()

    def record(self, label: str) -> None:
        self.invocations.append(label)


def _default_allowlisted_open_prefixes(repo_root: Path | None) -> tuple[str, ...]:
    prefixes = [
        str(Path(sys.prefix).resolve()),
        str(Path(tempfile.gettempdir()).resolve()),
        str(Path.cwd().resolve()),
    ]
    if repo_root is not None:
        prefixes.append(str(Path(repo_root).resolve()))
    # Common read-only OS paths used by interpreters / SSL.
    prefixes.extend(["/usr", "/lib", "/lib64", "/etc/ssl", "/etc/pki", "/proc", "/dev"])
    return tuple(prefixes)


@contextmanager
def install_capability_probe(
    *,
    allowlisted_open_prefixes: tuple[str, ...] | None = None,
    repo_root: Path | None = None,
) -> Iterator[CapabilityProbe]:
    """Install in-process spies for shell/subprocess, non-allowlisted opens, sockets.

    Observed zero forbidden calls → ``invocations == []`` (evaluable).
    Observed calls → recorded labels.
    ``complete`` is True only when all sink patches installed successfully.
    """
    prefixes = allowlisted_open_prefixes
    if prefixes is None:
        prefixes = _default_allowlisted_open_prefixes(repo_root)
    probe = CapabilityProbe(_allowlisted_open_prefixes=prefixes)
    originals: dict[str, Any] = {}

    def _is_allowlisted_path(path_obj: object) -> bool:
        try:
            text = os.fspath(path_obj)  # type: ignore[arg-type]
        except TypeError:
            return False
        try:
            resolved = str(Path(str(text)).expanduser().resolve(strict=False))
        except OSError:
            resolved = str(text)
        return any(
            resolved == prefix or resolved.startswith(prefix.rstrip("/") + "/")
            or str(text).startswith(prefix)
            for prefix in prefixes
        )

    def _sp_run(*args: Any, **kwargs: Any) -> Any:
        probe.record("subprocess.run")
        return originals["subprocess.run"](*args, **kwargs)

    def _sp_popen(*args: Any, **kwargs: Any) -> Any:
        probe.record("subprocess.Popen")
        return originals["subprocess.Popen"](*args, **kwargs)

    def _sp_call(*args: Any, **kwargs: Any) -> Any:
        probe.record("subprocess.call")
        return originals["subprocess.call"](*args, **kwargs)

    def _os_system(*args: Any, **kwargs: Any) -> Any:
        probe.record("os.system")
        return originals["os.system"](*args, **kwargs)

    def _builtins_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if not _is_allowlisted_path(file):
            probe.record(f"open:{file!s}")
        return originals["open"](file, *args, **kwargs)

    def _socket_create(*args: Any, **kwargs: Any) -> Any:
        probe.record("socket.socket")
        return originals["socket.socket"](*args, **kwargs)

    def _urlopen(*args: Any, **kwargs: Any) -> Any:
        probe.record("urllib.request.urlopen")
        return originals["urllib.request.urlopen"](*args, **kwargs)

    try:
        originals["subprocess.run"] = subprocess.run
        originals["subprocess.Popen"] = subprocess.Popen
        originals["subprocess.call"] = subprocess.call
        originals["os.system"] = os.system
        originals["open"] = builtins.open
        originals["socket.socket"] = socket.socket
        originals["urllib.request.urlopen"] = urllib_request.urlopen
        subprocess.run = _sp_run  # type: ignore[assignment]
        subprocess.Popen = _sp_popen  # type: ignore[assignment]
        subprocess.call = _sp_call  # type: ignore[assignment]
        os.system = _os_system  # type: ignore[assignment]
        builtins.open = _builtins_open  # type: ignore[assignment]
        socket.socket = _socket_create  # type: ignore[assignment,misc]
        urllib_request.urlopen = _urlopen  # type: ignore[assignment]
        probe.installed = True
        probe.complete = True
        yield probe
    except Exception:
        probe.complete = False
        raise
    finally:
        if "subprocess.run" in originals:
            subprocess.run = originals["subprocess.run"]  # type: ignore[assignment]
        if "subprocess.Popen" in originals:
            subprocess.Popen = originals["subprocess.Popen"]  # type: ignore[assignment]
        if "subprocess.call" in originals:
            subprocess.call = originals["subprocess.call"]  # type: ignore[assignment]
        if "os.system" in originals:
            os.system = originals["os.system"]  # type: ignore[assignment]
        if "open" in originals:
            builtins.open = originals["open"]  # type: ignore[assignment]
        if "socket.socket" in originals:
            socket.socket = originals["socket.socket"]  # type: ignore[assignment,misc]
        if "urllib.request.urlopen" in originals:
            urllib_request.urlopen = originals["urllib.request.urlopen"]  # type: ignore[assignment]
