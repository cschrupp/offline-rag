#!/usr/bin/env python3
"""Host preflight and safe workstation metadata helpers (standard library only)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

LARGE_PDF_TOTAL_BYTES = 32_000_000_000
LARGE_PDF_AVAILABLE_BYTES = 19_388_303_360
OLLAMA_URL = "http://127.0.0.1:11434/api/tags"


def detect_target(
    *, system: str | None = None, machine: str | None = None, release: str | None = None
) -> tuple[str | None, list[str]]:
    """Return target and errors without mutating the machine."""
    system = system or platform.system()
    machine = machine or platform.machine()
    release = release or platform.release()
    errors: list[str] = []
    if system == "Darwin":
        return None, ["macOS is not a supported Slice 18B target."]
    if system == "Windows":
        return None, [
            "Run scripts/workstation/install.sh inside Linux or WSL2, not native Windows."
        ]
    if system != "Linux":
        return None, [f"Unsupported operating system: {system}."]
    if machine.lower() not in {"x86_64", "amd64"}:
        errors.append(f"Unsupported architecture {machine}; Slice 18B requires x86-64.")
    lower_release = release.lower()
    if "microsoft" in lower_release:
        if "wsl2" not in lower_release and "microsoft-standard" not in lower_release:
            errors.append("WSL1 is unsupported; use a WSL2 distribution.")
            return None, errors
        return ("wsl2" if not errors else None), errors
    return ("linux" if not errors else None), errors


def read_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    """Return available MemTotal/MemAvailable bytes from procfs."""
    values: dict[str, int] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        name, separator, rest = line.partition(":")
        if not separator or name not in {"MemTotal", "MemAvailable"}:
            continue
        parts = rest.split()
        if len(parts) >= 2 and parts[1] == "kB":
            values[name] = int(parts[0]) * 1024
    missing = {"MemTotal", "MemAvailable"} - values.keys()
    if missing:
        raise ValueError(f"missing memory values: {', '.join(sorted(missing))}")
    return values


def is_windows_mount_path(path: Path, fs_type: str | None) -> bool:
    """Identify common WSL Windows-mounted paths and filesystem types."""
    resolved = Path(os.path.abspath(path))
    if (
        len(resolved.parts) >= 3
        and resolved.parts[1].lower() == "mnt"
        and len(resolved.parts[2]) == 1
        and resolved.parts[2].isalpha()
    ):
        return True
    normalized = (fs_type or "").lower()
    return normalized in {"drvfs", "9p", "cifs", "smb3", "ntfs", "fuseblk"}


def _mount_type(path: Path) -> str | None:
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    result = subprocess.run(
        ["findmnt", "--noheadings", "--output", "FSTYPE", "--target", str(probe)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return (
        result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else None
    )


def validate_data_root(path: Path, *, target: str, fs_type: str | None = None) -> None:
    """Require WSL mutable state to be on a Linux filesystem."""
    if target == "wsl2" and is_windows_mount_path(path, fs_type):
        raise ValueError(
            "WSL mutable Seneca data must reside on the distro's Linux filesystem; "
            f"the configured path is on a Windows-mounted filesystem: {path}"
        )
    if target == "wsl2" and fs_type is None:
        raise ValueError(
            "Cannot verify the WSL data filesystem. Install util-linux (findmnt) "
            "or choose a path under the distro's Linux home filesystem."
        )


def _ollama_model_available(model: str) -> tuple[bool, str]:
    request = urllib.request.Request(OLLAMA_URL, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return (
            False,
            f"Ollama is not reachable at 127.0.0.1:11434 ({type(exc).__name__}).",
        )
    models = payload.get("models") if isinstance(payload, dict) else None
    names = {item.get("name") for item in models or [] if isinstance(item, dict)}
    if model not in names:
        return (
            False,
            f"Ollama model {model!r} is not present. Pull it explicitly with `ollama pull {model}`.",
        )
    return True, "Ollama endpoint and selected local model are ready."


def _user_linger_enabled() -> bool:
    try:
        result = subprocess.run(
            [
                "loginctl",
                "show-user",
                getpass.getuser(),
                "--property=Linger",
                "--value",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "yes"


def collect_preflight(
    *,
    app_dir: Path,
    data_dir: Path,
    models_dir: Path,
    model: str,
    check_services: bool = True,
) -> dict[str, Any]:
    """Collect host facts and fail-closed installation preconditions."""
    target, errors = detect_target()
    result: dict[str, Any] = {
        "target": target,
        "architecture": platform.machine(),
        "release": platform.release(),
        "errors": errors,
        "warnings": [],
        "memory_bytes": None,
        "large_pdf_path_available": None,
        "mount_types": {},
        "disk_available_bytes": {},
        "commands": {},
        "user_service_manager": None,
        "ollama": None,
    }
    if target is None:
        return result

    try:
        memory = read_meminfo()
        result["memory_bytes"] = memory
        if target == "wsl2":
            large_pdf = (
                memory["MemTotal"] >= LARGE_PDF_TOTAL_BYTES
                and memory["MemAvailable"] >= LARGE_PDF_AVAILABLE_BYTES
            )
            result["large_pdf_path_available"] = large_pdf
            if not large_pdf:
                result["warnings"].append(
                    "WSL-visible memory does not currently satisfy the accepted "
                    ">25 MiB PDF profile gate. Ordinary 25 MiB sources remain available; "
                    "WSL memory limits can be changed outside Seneca if needed."
                )
    except (OSError, ValueError) as exc:
        result["errors"].append(f"Could not read Linux memory information: {exc}")

    for label, path in (("app", app_dir), ("data", data_dir), ("models", models_dir)):
        resolved = path.expanduser().absolute()
        mount_type = _mount_type(resolved)
        result["mount_types"][label] = mount_type
        try:
            validate_data_root(resolved, target=target, fs_type=mount_type)
        except ValueError as exc:
            result["errors"].append(str(exc))
        ancestor = resolved
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        try:
            result["disk_available_bytes"][label] = shutil.disk_usage(ancestor).free
        except OSError:
            result["disk_available_bytes"][label] = None

    roots = [p.expanduser().absolute() for p in (app_dir, data_dir, models_dir)]
    for i, left in enumerate(roots):
        for right in roots[i + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                result["errors"].append(
                    "Application, data, and models roots must be separate directories."
                )

    required = [
        "bash",
        "curl",
        "tar",
        "sha256sum",
        "findmnt",
        "install",
        "mktemp",
        "systemctl",
        "loginctl",
        "journalctl",
        "git",
    ]
    for command in required:
        present = shutil.which(command) is not None
        result["commands"][command] = present
        if not present:
            result["errors"].append(f"Required command is missing: {command}.")
    if not shutil.which("python3"):
        result["errors"].append(
            "python3 is required for installer metadata and preflight."
        )
    if check_services:
        service = subprocess.run(
            ["systemctl", "--user", "show-environment"],
            check=False,
            capture_output=True,
            text=True,
        )
        ready = service.returncode == 0
        result["user_service_manager"] = ready
        if not ready:
            result["errors"].append(
                "systemd user manager is unavailable. Enable/start the distro's systemd user manager; "
                "Seneca will not fall back to nohup or PID-file service handling."
            )
        linger = _user_linger_enabled()
        result["user_manager_linger"] = linger
        if not linger:
            result["errors"].append(
                "systemd user-manager lingering is not enabled. Enable it with "
                f"`sudo loginctl enable-linger {getpass.getuser()}` so the "
                "enabled Seneca service can outlive the installing shell."
            )

    if not model.strip():
        result["errors"].append(
            "Select an Ollama model before workstation installation."
        )
    else:
        available, message = _ollama_model_available(model)
        result["ollama"] = {
            "ready": available,
            "message": message,
            "endpoint": OLLAMA_URL,
        }
        if not available:
            result["errors"].append(message)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--app-dir", type=Path, required=True)
    preflight.add_argument("--data-dir", type=Path, required=True)
    preflight.add_argument("--models-dir", type=Path, required=True)
    preflight.add_argument("--ollama-model", required=True)
    preflight.add_argument("--skip-service-check", action="store_true")
    preflight.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command != "preflight":
        parser.error("unknown command")
    result = collect_preflight(
        app_dir=args.app_dir,
        data_dir=args.data_dir,
        models_dir=args.models_dir,
        model=args.ollama_model,
        check_services=not args.skip_service_check,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
