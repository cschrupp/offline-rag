"""Deterministic workstation host-preflight tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "workstation" / "host.py"


def _load_host():
    spec = importlib.util.spec_from_file_location("workstation_host", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host = _load_host()


def test_detects_linux_and_wsl2_and_rejects_unsupported_targets() -> None:
    assert host.detect_target(system="Linux", machine="x86_64", release="6.8.0") == (
        "linux",
        [],
    )
    assert host.detect_target(
        system="Linux",
        machine="x86_64",
        release="6.8.0-microsoft-standard-WSL2",
    ) == ("wsl2", [])
    assert (
        host.detect_target(system="Linux", machine="x86_64", release="4.4.0-Microsoft")[
            0
        ]
        is None
    )
    assert (
        "WSL1"
        in host.detect_target(
            system="Linux", machine="x86_64", release="4.4.0-Microsoft"
        )[1][0]
    )
    assert (
        "x86-64"
        in host.detect_target(system="Linux", machine="aarch64", release="6.8.0")[1][0]
    )
    assert (
        "native Windows"
        in host.detect_target(system="Windows", machine="AMD64", release="Windows-11")[
            1
        ][0]
    )
    assert (
        "macOS"
        in host.detect_target(system="Darwin", machine="x86_64", release="Darwin")[1][0]
    )


def test_identifies_windows_mounted_data_paths() -> None:
    assert host.is_windows_mount_path(Path("/mnt/c/Users/test/seneca"), "drvfs")
    assert host.is_windows_mount_path(Path("/home/test/seneca"), "9p")
    assert not host.is_windows_mount_path(Path("/home/test/seneca"), "ext4")


def test_wsl_data_root_fails_closed_without_linux_filesystem_evidence() -> None:
    host.validate_data_root(
        Path("/home/test/seneca/data"), target="wsl2", fs_type="ext4"
    )
    for fs_type in (None, "drvfs", "9p"):
        try:
            host.validate_data_root(
                Path("/home/test/seneca/data"), target="wsl2", fs_type=fs_type
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected WSL path validation to reject {fs_type!r}")
    try:
        host.validate_data_root(
            Path("/mnt/c/seneca/data"), target="wsl2", fs_type="ext4"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected drive-mounted path rejection")


def test_reads_linux_memory_without_fabricating_missing_values(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal: 32000000 kB\nMemAvailable: 20000000 kB\n", encoding="ascii"
    )
    assert host.read_meminfo(meminfo) == {
        "MemTotal": 32_768_000_000,
        "MemAvailable": 20_480_000_000,
    }
    meminfo.write_text("MemTotal: 1000 kB\n", encoding="ascii")
    try:
        host.read_meminfo(meminfo)
    except ValueError as exc:
        assert "MemAvailable" in str(exc)
    else:
        raise AssertionError("missing memory fields must remain unavailable")


def test_preflight_reports_wsl_memory_warning_without_changing_policy(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "detect_target", lambda: ("wsl2", []))
    monkeypatch.setattr(
        host,
        "read_meminfo",
        lambda: {"MemTotal": 16_000_000_000, "MemAvailable": 8_000_000_000},
    )
    monkeypatch.setattr(host, "_mount_type", lambda path: "ext4")
    monkeypatch.setattr(host.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(host, "_ollama_model_available", lambda model: (True, "ready"))
    monkeypatch.setattr(host, "_user_linger_enabled", lambda: True)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    roots = [tmp_path / name for name in ("app", "data", "models")]
    result = host.collect_preflight(
        app_dir=roots[0],
        data_dir=roots[1],
        models_dir=roots[2],
        model="qwen3.5:14b",
    )
    assert result["target"] == "wsl2"
    assert result["large_pdf_path_available"] is False
    assert any("Ordinary 25 MiB" in warning for warning in result["warnings"])
    assert result["errors"] == []


def test_preflight_rejects_windows_mounted_wsl_data_before_install(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "detect_target", lambda: ("wsl2", []))
    monkeypatch.setattr(
        host,
        "read_meminfo",
        lambda: {"MemTotal": 32_000_000_000, "MemAvailable": 20_000_000_000},
    )
    monkeypatch.setattr(
        host,
        "_mount_type",
        lambda path: "drvfs" if path == Path("/mnt/c/seneca/data") else "ext4",
    )
    monkeypatch.setattr(host.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(host, "_ollama_model_available", lambda model: (True, "ready"))
    monkeypatch.setattr(host, "_user_linger_enabled", lambda: True)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    result = host.collect_preflight(
        app_dir=tmp_path / "app",
        data_dir=Path("/mnt/c/seneca/data"),
        models_dir=tmp_path / "models",
        model="qwen3.5:14b",
    )
    assert any("Windows-mounted filesystem" in error for error in result["errors"])


def test_preflight_requires_user_manager_linger_for_shell_independent_service(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "detect_target", lambda: ("linux", []))
    monkeypatch.setattr(
        host,
        "read_meminfo",
        lambda: {"MemTotal": 32_000_000_000, "MemAvailable": 20_000_000_000},
    )
    monkeypatch.setattr(host, "_mount_type", lambda path: "ext4")
    monkeypatch.setattr(host.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(host, "_ollama_model_available", lambda model: (True, "ready"))
    monkeypatch.setattr(host, "_user_linger_enabled", lambda: False)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    roots = [tmp_path / name for name in ("app", "data", "models")]
    result = host.collect_preflight(
        app_dir=roots[0],
        data_dir=roots[1],
        models_dir=roots[2],
        model="qwen3.5:14b",
    )
    assert result["user_manager_linger"] is False
    assert any("enable-linger" in error for error in result["errors"])
