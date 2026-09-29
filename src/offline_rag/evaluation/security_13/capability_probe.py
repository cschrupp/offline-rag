"""Harness-owned forbidden-capability sink instrumentation (OD-13-10 / Q5).

Record-and-block: forbidden sinks are recorded and then refused. They never
delegate to the underlying operation. Incomplete instrumentation yields
``complete=False`` so callers set ``capability_invocations=None``.

Filesystem coverage intentionally includes ``builtins.open``, ``io.open``, and
``os.open`` so ``pathlib.Path.read_text`` / ``write_text`` cannot bypass the
probe. The system temp tree is **not** wholesale-allowlisted.
"""

from __future__ import annotations

import builtins
import io
import os
import socket
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


class CapabilityBlockedError(RuntimeError):
    """Raised when a forbidden capability sink is blocked by the harness probe."""


@dataclass
class CapabilityProbe:
    """Records forbidden capability invocations observed during a case run."""

    invocations: list[str] = field(default_factory=list)
    installed: bool = False
    complete: bool = False
    _allowlisted_open_prefixes: tuple[str, ...] = ()

    def record(self, label: str) -> None:
        self.invocations.append(label)


def _default_allowlisted_open_prefixes() -> tuple[str, ...]:
    """Narrow allowlist: interpreter/runtime only.

    Explicitly excludes the repository, cwd, and the wholesale system temp tree.
    """
    prefixes = [str(Path(sys.prefix).resolve())]
    # Read-only OS paths used by interpreters / SSL.
    prefixes.extend(["/usr", "/lib", "/lib64", "/etc/ssl", "/etc/pki", "/proc", "/dev"])
    return tuple(prefixes)


@contextmanager
def install_capability_probe(
    *,
    allowlisted_open_prefixes: tuple[str, ...] | None = None,
    repo_root: Path | None = None,
) -> Iterator[CapabilityProbe]:
    """Install record-and-block spies for shell/subprocess, opens, and network.

    ``repo_root`` is accepted for API compatibility but is **not** allowlisted.
    Observed zero forbidden calls → ``invocations == []`` (evaluable).
    Observed calls → recorded labels; underlying side effect never runs.
    ``complete`` is True only when all sink patches installed successfully.
    """
    del repo_root  # intentionally not allowlisted
    prefixes = (
        allowlisted_open_prefixes
        if allowlisted_open_prefixes is not None
        else _default_allowlisted_open_prefixes()
    )
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
            resolved == prefix
            or resolved.startswith(prefix.rstrip("/") + "/")
            or str(text).startswith(prefix)
            for prefix in prefixes
        )

    def _blocked(label: str) -> None:
        probe.record(label)
        raise CapabilityBlockedError(
            f"security_13 capability probe blocked {label}"
        )

    def _sp_run(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("subprocess.run")

    def _sp_popen(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("subprocess.Popen")

    def _sp_call(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("subprocess.call")

    def _os_system(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("os.system")

    def _guarded_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if _is_allowlisted_path(file):
            return originals["io.open"](file, *args, **kwargs)
        probe.record(f"open:{file!s}")
        raise CapabilityBlockedError(
            f"security_13 capability probe blocked open:{file!s}"
        )

    def _os_open(path: Any, flags: int, mode: int = 0o777, *args: Any, **kwargs: Any) -> int:
        if _is_allowlisted_path(path):
            return originals["os.open"](path, flags, mode, *args, **kwargs)
        probe.record(f"os.open:{path!s}")
        raise CapabilityBlockedError(
            f"security_13 capability probe blocked os.open:{path!s}"
        )

    def _socket_create(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("socket.socket")

    def _urlopen(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        _blocked("urllib.request.urlopen")

    try:
        originals["subprocess.run"] = subprocess.run
        originals["subprocess.Popen"] = subprocess.Popen
        originals["subprocess.call"] = subprocess.call
        originals["os.system"] = os.system
        originals["builtins.open"] = builtins.open
        originals["io.open"] = io.open
        originals["os.open"] = os.open
        originals["socket.socket"] = socket.socket
        originals["urllib.request.urlopen"] = urllib_request.urlopen

        subprocess.run = _sp_run  # type: ignore[assignment]
        subprocess.Popen = _sp_popen  # type: ignore[assignment]
        subprocess.call = _sp_call  # type: ignore[assignment]
        os.system = _os_system  # type: ignore[assignment]
        # Patch both bindings: pathlib uses io.open; application code may use builtins.open.
        builtins.open = _guarded_open  # type: ignore[assignment]
        io.open = _guarded_open  # type: ignore[assignment]
        os.open = _os_open  # type: ignore[assignment]
        socket.socket = _socket_create  # type: ignore[assignment,misc]
        urllib_request.urlopen = _urlopen  # type: ignore[assignment]

        probe.installed = True
        probe.complete = True
        yield probe
    finally:
        if "subprocess.run" in originals:
            subprocess.run = originals["subprocess.run"]  # type: ignore[assignment]
        if "subprocess.Popen" in originals:
            subprocess.Popen = originals["subprocess.Popen"]  # type: ignore[assignment]
        if "subprocess.call" in originals:
            subprocess.call = originals["subprocess.call"]  # type: ignore[assignment]
        if "os.system" in originals:
            os.system = originals["os.system"]  # type: ignore[assignment]
        if "builtins.open" in originals:
            builtins.open = originals["builtins.open"]  # type: ignore[assignment]
        if "io.open" in originals:
            io.open = originals["io.open"]  # type: ignore[assignment]
        if "os.open" in originals:
            os.open = originals["os.open"]  # type: ignore[assignment]
        if "socket.socket" in originals:
            socket.socket = originals["socket.socket"]  # type: ignore[assignment,misc]
        if "urllib.request.urlopen" in originals:
            urllib_request.urlopen = originals[
                "urllib.request.urlopen"
            ]  # type: ignore[assignment]
