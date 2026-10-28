#!/usr/bin/env python3
"""Observation-only Seneca process and GPU preflight for R04."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_SECRET_FLAG = re.compile(r"(?:api[-_]?key|token|secret|password|credential)", re.IGNORECASE)
_GENERATION_MARKERS = ("llama-server", "llama.cpp", "llama_cpp", "ollama", "vllm")
_API_MARKERS = ("offline_rag.api", "uvicorn", "api.server")


def _is_within(path_text: str | None, root: Path) -> bool:
    if not path_text:
        return False
    try:
        Path(path_text).resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _sanitize_argv(argv: list[str]) -> list[str]:
    """Redact common secret-valued options before any command line is emitted."""
    safe: list[str] = []
    redact_next = False
    for argument in argv:
        if redact_next:
            safe.append("<redacted>")
            redact_next = False
            continue
        if _SECRET_FLAG.search(argument):
            if "=" in argument:
                safe.append(f"{argument.split('=', 1)[0]}=<redacted>")
            elif " " in argument or ":" in argument:
                safe.append("<redacted>")
            else:
                safe.append(argument)
                redact_next = True
            continue
        argument = re.sub(
            r"(?i)\bBearer\s+\S+",
            "Bearer <redacted>",
            argument,
        )
        argument = re.sub(
            r"(?i)(https?://)[^/@\s]+:[^/@\s]+@",
            r"\1<redacted>@",
            argument,
        )
        safe.append(argument)
    return safe


def _read_process(pid: int, proc_root: Path, repo_root: Path) -> dict[str, Any] | None:
    process_dir = proc_root / str(pid)
    try:
        argv = [
            item.decode("utf-8", errors="replace")
            for item in (process_dir / "cmdline").read_bytes().split(b"\0")
            if item
        ]
    except (OSError, PermissionError):
        return None
    if not argv:
        return None

    ppid: int | None = None
    try:
        for line in (process_dir / "status").read_text(errors="replace").splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split(":", 1)[1].strip())
                break
    except (OSError, ValueError):
        pass
    try:
        cwd = os.readlink(process_dir / "cwd")
    except OSError:
        cwd = None

    command_lower = " ".join(argv).lower()
    executable = Path(argv[0]).name
    is_python_process = executable.lower().startswith("python")
    is_api_executable = is_python_process or executable.lower() == "uvicorn"
    repo_local = _is_within(cwd, repo_root) or any(
        Path(argument).is_absolute() and _is_within(argument, repo_root)
        for argument in argv[1:]
    )
    seneca_server = (
        is_api_executable and "offline_rag.api.server" in command_lower
    )
    repo_api = (
        repo_local
        and is_api_executable
        and any(marker in command_lower for marker in _API_MARKERS)
    )
    generation_server = (
        any(marker in executable.lower() for marker in _GENERATION_MARKERS)
        or (
            is_python_process
            and any(marker in command_lower for marker in _GENERATION_MARKERS)
        )
    )
    keep_command_line = seneca_server or repo_api or generation_server
    return {
        "pid": pid,
        "ppid": ppid,
        "executable": executable,
        "command_line": _sanitize_argv(argv) if keep_command_line else None,
        "cwd": cwd,
        "repo_local": repo_local,
        "seneca_server": seneca_server,
        "repo_api": repo_api,
        "generation_server": generation_server,
    }


def collect_processes(
    *, proc_root: Path = Path("/proc"), repo_root: Path = REPO_ROOT
) -> list[dict[str, Any]]:
    processes: list[dict[str, Any]] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return processes
    for entry in entries:
        if not entry.name.isdecimal():
            continue
        process = _read_process(int(entry.name), proc_root, repo_root)
        if process is not None:
            processes.append(process)
    return sorted(processes, key=lambda process: process["pid"])


def _decode_local_address(hex_address: str, *, ipv6: bool) -> str | None:
    try:
        raw = bytes.fromhex(hex_address)
        if ipv6:
            raw = b"".join(raw[index : index + 4][::-1] for index in range(0, 16, 4))
            return socket.inet_ntop(socket.AF_INET6, raw)
        return socket.inet_ntop(socket.AF_INET, raw[::-1])
    except (ValueError, OSError):
        return None


def _listening_sockets(proc_root: Path) -> list[dict[str, Any]]:
    sockets: list[dict[str, Any]] = []
    for table_name, ipv6 in (("net/tcp", False), ("net/tcp6", True)):
        try:
            lines = (proc_root / table_name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[3] != "0A":
                continue
            address_hex, port_hex = fields[1].split(":", 1)
            address = _decode_local_address(address_hex, ipv6=ipv6)
            if address is None:
                continue
            try:
                port = int(port_hex, 16)
                inode = fields[9]
            except ValueError:
                continue
            sockets.append({"address": address, "port": port, "inode": inode})

    inode_owners: dict[str, list[int]] = {}
    try:
        pids = [entry.name for entry in proc_root.iterdir() if entry.name.isdecimal()]
    except OSError:
        pids = []
    for pid_text in pids:
        fd_dir = proc_root / pid_text / "fd"
        try:
            descriptors = list(fd_dir.iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match:
                inode_owners.setdefault(match.group(1), []).append(int(pid_text))

    for item in sockets:
        item["pids"] = sorted(set(inode_owners.get(item.pop("inode"), [])))
    return sorted(sockets, key=lambda item: (item["port"], item["address"]))


def _run_nvidia_smi(
    runner: Callable[..., subprocess.CompletedProcess[str]], arguments: list[str]
) -> subprocess.CompletedProcess[str] | None:
    try:
        return runner(
            ["nvidia-smi", *arguments],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def collect_gpu(
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
) -> dict[str, Any]:
    memory_result = _run_nvidia_smi(
        runner,
        ["--query-gpu=memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
    )
    devices: list[dict[str, int | None]] = []
    if memory_result is not None and memory_result.returncode == 0:
        for row in csv.reader(memory_result.stdout.splitlines()):
            values: list[int | None] = []
            for value in row[:3]:
                try:
                    values.append(int(value.strip()))
                except ValueError:
                    values.append(None)
            if values:
                values.extend([None] * (3 - len(values)))
                devices.append(
                    {"total_mib": values[0], "used_mib": values[1], "free_mib": values[2]}
                )

    process_result = _run_nvidia_smi(
        runner,
        [
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
    )
    gpu_processes: list[dict[str, Any]] = []
    if process_result is not None and process_result.returncode == 0:
        for row in csv.reader(process_result.stdout.splitlines()):
            if len(row) < 3:
                continue
            try:
                pid = int(row[0].strip())
            except ValueError:
                continue
            memory_text = row[2].strip()
            try:
                used_memory_mib = int(memory_text)
            except ValueError:
                used_memory_mib = None
            gpu_processes.append(
                {
                    "pid": pid,
                    "process_name": row[1].strip(),
                    "used_memory_mib": used_memory_mib,
                }
            )

    attribution = "OBSERVED" if gpu_processes else "NOT_OBSERVABLE"
    return {
        "status": "OBSERVED" if devices else "UNAVAILABLE",
        "devices": devices,
        "process_attribution": attribution,
        "processes": gpu_processes,
        "memory_error": (
            None
            if memory_result is not None and memory_result.returncode == 0
            else "nvidia_smi_unavailable"
        ),
    }


def build_report(
    *,
    processes: list[dict[str, Any]],
    listeners: list[dict[str, Any]],
    gpu: dict[str, Any],
    captured_at: str,
) -> dict[str, Any]:
    seneca_processes = [item for item in processes if item["seneca_server"]]
    repo_api_processes = [item for item in processes if item["repo_api"]]
    generation_processes = [item for item in processes if item["generation_server"]]
    flags: list[str] = []
    if len(seneca_processes) > 1:
        flags.append("POSSIBLE_DUPLICATE_SENECA_PROCESS")
    if len(repo_api_processes) > 1:
        flags.append("MULTIPLE_REPO_API_PROCESSES")
    if gpu.get("process_attribution") != "OBSERVED":
        flags.append("GPU_PROCESS_ATTRIBUTION_UNAVAILABLE")
    for device in gpu.get("devices", []):
        total = device.get("total_mib")
        used = device.get("used_mib")
        if (
            isinstance(total, int)
            and isinstance(used, int)
            and total > 0
            and used / total >= 0.85
        ):
            flags.append("HIGH_GPU_OCCUPANCY")
            break

    return {
        "schema": "s16k-r04-cuda-preflight-v1",
        "captured_at": captured_at,
        "observation_only": True,
        "flags": flags,
        "counts": {
            "seneca_processes": len(seneca_processes),
            "repo_api_processes": len(repo_api_processes),
            "generation_servers": len(generation_processes),
        },
        "seneca_processes": seneca_processes,
        "repo_api_processes": repo_api_processes,
        "generation_servers": generation_processes,
        "listeners": listeners,
        "gpu": gpu,
        "all_processes": processes,
        "actions_taken": [],
    }


def run_preflight(
    *,
    proc_root: Path = Path("/proc"),
    repo_root: Path = REPO_ROOT,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    processes = collect_processes(proc_root=proc_root, repo_root=repo_root)
    listeners = _listening_sockets(proc_root)
    gpu = collect_gpu(runner=runner)
    return build_report(
        processes=processes,
        listeners=listeners,
        gpu=gpu,
        captured_at=dt.datetime.now(dt.UTC).isoformat(),
    )


def _summary(report: dict[str, Any]) -> str:
    counts = report["counts"]
    devices = report["gpu"].get("devices", [])
    gpu_summary = "unavailable"
    if devices:
        gpu_summary = ", ".join(
            f"{item['used_mib']}/{item['total_mib']} MiB"
            for item in devices
        )
    flags = ", ".join(report["flags"]) if report["flags"] else "none"
    return (
        "R04 preflight (observation only): "
        f"Seneca={counts['seneca_processes']}, repo API={counts['repo_api_processes']}, "
        f"generation servers={counts['generation_servers']}, GPU={gpu_summary}, "
        f"attribution={report['gpu']['process_attribution']}, flags={flags}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    report = run_preflight()
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    print(_summary(report))
    if args.json_out is not None:
        print(f"JSON: {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
