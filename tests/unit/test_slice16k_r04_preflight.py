from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_16k_r04_cuda_oom import preflight


def _write_process(
    proc_root: Path,
    *,
    pid: int,
    ppid: int,
    argv: list[str],
    cwd: Path,
) -> Path:
    process_dir = proc_root / str(pid)
    (process_dir / "fd").mkdir(parents=True)
    (process_dir / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in argv) + b"\0")
    (process_dir / "status").write_text(f"Name:\ttest\nPPid:\t{ppid}\n")
    (process_dir / "cwd").symlink_to(cwd, target_is_directory=True)
    return process_dir


def _proc_fixture(tmp_path: Path, *, seneca_count: int = 1) -> tuple[Path, Path]:
    proc_root = tmp_path / "proc"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (proc_root / "net").mkdir(parents=True)
    (proc_root / "net" / "tcp").write_text(
        "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
        "0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 778899\n"
    )
    (proc_root / "net" / "tcp6").write_text(
        "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n"
    )
    for offset in range(seneca_count):
        _write_process(
            proc_root,
            pid=101 + offset,
            ppid=90,
            argv=["/venv/bin/python", "-m", "offline_rag.api.server", "--port", str(8080 + offset)],
            cwd=repo_root,
        )
    _write_process(
        proc_root,
        pid=201,
        ppid=1,
        argv=["/usr/bin/python3", "/tmp/unrelated.py"],
        cwd=tmp_path,
    )
    _write_process(
        proc_root,
        pid=301,
        ppid=1,
            argv=[
                "/opt/llama.cpp/llama-server",
                "--model",
                "/models/local.gguf",
                "--api-key=private",
                "-H",
                "Authorization: Bearer supersecret",
            ],
        cwd=tmp_path,
    )
    (proc_root / "101" / "fd" / "9").symlink_to("socket:[778899]")
    return proc_root, repo_root


def _gpu_runner(*, process_output: str = ""):
    def runner(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if any(argument.startswith("--query-gpu=") for argument in args):
            return subprocess.CompletedProcess(args, 0, "8192, 7200, 992\n", "")
        if any(argument.startswith("--query-compute-apps=") for argument in args):
            return subprocess.CompletedProcess(args, 0, process_output, "")
        raise AssertionError(f"unexpected command: {args}")

    return runner


def test_one_seneca_process_has_no_duplicate_warning_and_reports_listener(
    tmp_path: Path,
) -> None:
    proc_root, repo_root = _proc_fixture(tmp_path)
    report = preflight.run_preflight(
        proc_root=proc_root,
        repo_root=repo_root,
        runner=_gpu_runner(),
    )

    assert report["counts"]["seneca_processes"] == 1
    assert "POSSIBLE_DUPLICATE_SENECA_PROCESS" not in report["flags"]
    assert report["listeners"] == [{"address": "127.0.0.1", "port": 8080, "pids": [101]}]
    assert report["gpu"]["process_attribution"] == "NOT_OBSERVABLE"
    assert "HIGH_GPU_OCCUPANCY" in report["flags"]


def test_multiple_repo_apis_and_other_python_are_classified_separately(
    tmp_path: Path,
) -> None:
    proc_root, repo_root = _proc_fixture(tmp_path, seneca_count=2)
    report = preflight.run_preflight(
        proc_root=proc_root,
        repo_root=repo_root,
        runner=_gpu_runner(process_output="444, /usr/bin/llama-server, 4096\n"),
    )

    assert report["counts"]["seneca_processes"] == 2
    assert report["counts"]["repo_api_processes"] == 2
    assert report["counts"]["generation_servers"] == 1
    assert "POSSIBLE_DUPLICATE_SENECA_PROCESS" in report["flags"]
    assert "MULTIPLE_REPO_API_PROCESSES" in report["flags"]
    assert all(process["pid"] != 201 for process in report["seneca_processes"])
    llama = report["generation_servers"][0]
    assert "--api-key=<redacted>" in llama["command_line"]
    assert llama["command_line"][-1] == "<redacted>"
    assert "supersecret" not in repr(llama["command_line"])
    assert report["gpu"]["process_attribution"] == "OBSERVED"


def test_uv_launcher_and_its_api_child_count_as_one_server(tmp_path: Path) -> None:
    proc_root, repo_root = _proc_fixture(tmp_path)
    _write_process(
        proc_root,
        pid=90,
        ppid=1,
        argv=["/home/user/.local/bin/uv", "run", "python", "-m", "offline_rag.api.server"],
        cwd=repo_root,
    )
    (proc_root / "101" / "status").write_text("Name:\ttest\nPPid:\t90\n")

    report = preflight.run_preflight(
        proc_root=proc_root,
        repo_root=repo_root,
        runner=_gpu_runner(),
    )

    assert report["counts"]["seneca_processes"] == 1
    assert report["counts"]["repo_api_processes"] == 1
    assert "POSSIBLE_DUPLICATE_SENECA_PROCESS" not in report["flags"]
    assert report["seneca_processes"][0]["pid"] == 101


def test_nvidia_smi_unavailable_is_bounded_and_tool_never_signals_processes(
    tmp_path: Path, monkeypatch
) -> None:
    proc_root, repo_root = _proc_fixture(tmp_path)
    signal_calls: list[int] = []
    monkeypatch.setattr("os.kill", lambda pid, sig: signal_calls.append(pid))

    def unavailable_runner(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("nvidia-smi unavailable")

    report = preflight.run_preflight(
        proc_root=proc_root,
        repo_root=repo_root,
        runner=unavailable_runner,
    )

    assert report["gpu"]["status"] == "UNAVAILABLE"
    assert report["gpu"]["process_attribution"] == "NOT_OBSERVABLE"
    assert report["gpu"]["memory_error"] == "nvidia_smi_unavailable"
    assert report["actions_taken"] == []
    assert signal_calls == []


def test_preflight_does_not_import_torch(tmp_path: Path, monkeypatch) -> None:
    proc_root, repo_root = _proc_fixture(tmp_path)
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any):
        if name == "torch" or name.startswith("torch."):
            raise AssertionError("preflight must not import torch")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    report = preflight.run_preflight(
        proc_root=proc_root,
        repo_root=repo_root,
        runner=_gpu_runner(),
    )
    assert report["observation_only"] is True
