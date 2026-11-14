#!/usr/bin/env python3
"""Write bounded workstation environment, service, and installation metadata."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import tempfile
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _env_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("workstation environment values cannot contain newlines")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unit_quote(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("systemd unit values cannot contain newlines")
    escaped = value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def _unit_path(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("systemd unit paths cannot contain newlines")
    return value.replace("\\", "\\\\").replace("%", "%%").replace(" ", "\\x20")


def environment_values(
    *, app_dir: Path, data_dir: Path, models_dir: Path, model: str
) -> dict[str, str]:
    app = str(app_dir.expanduser().absolute())
    data = str(data_dir.expanduser().absolute())
    models = str(models_dir.expanduser().absolute())
    return {
        "OFFLINE_RAG_CONFIG": f"{app}/config/base.yaml",
        "OFFLINE_RAG_DATA_DIR": data,
        "OFFLINE_RAG_MODELS_DIR": models,
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        "OFFLINE_RAG_HTTP_HOST": "127.0.0.1",
        "OFFLINE_RAG_HTTP_PORT": "8080",
        "OFFLINE_RAG_ALLOW_NON_LOOPBACK": "false",
        "OFFLINE_RAG_UI_DIR": f"{app}/ui",
        "OFFLINE_RAG_LLM_BASE_URL": "http://127.0.0.1:11434/v1",
        "OFFLINE_RAG_LLM_MODEL": model,
        "OFFLINE_RAG_APPROVED_LLM_ENDPOINTS": "http://127.0.0.1:11434/v1",
        "OFFLINE_RAG_APPROVED_LLM_MODELS": model,
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, raw_value = line.partition("=")
        if not sep or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid workstation.env entry on line {number}")
        parsed = shlex.split(raw_value, posix=True)
        if len(parsed) != 1:
            raise ValueError(f"invalid workstation.env value on line {number}")
        values[key] = parsed[0]
    return values


def _child_environment(path: Path, overrides: list[str]) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(_read_env_file(path))
    for assignment in overrides:
        key, separator, value = assignment.partition("=")
        if not separator or not key.replace("_", "").isalnum():
            raise ValueError("environment overrides must use KEY=VALUE syntax")
        environment[key] = value
    return environment


def write_environment_file(
    path: Path, *, app_dir: Path, data_dir: Path, models_dir: Path, model: str
) -> None:
    expected = environment_values(
        app_dir=app_dir, data_dir=data_dir, models_dir=models_dir, model=model
    )
    if path.exists():
        existing = _read_env_file(path)
        mismatches = [
            key for key, value in expected.items() if existing.get(key) != value
        ]
        if mismatches:
            raise ValueError(
                "existing workstation.env has different installation bindings "
                f"({', '.join(mismatches)}); review and update it explicitly"
            )
        return
    lines = [
        "# Seneca workstation installation settings. Local edits are preserved by reinstall.",
        *(f"{key}={_env_quote(value)}" for key, value in expected.items()),
    ]
    _atomic_write(path, "\n".join(lines) + "\n", 0o600)


def write_user_service(path: Path, *, app_dir: Path, env_file: Path) -> None:
    app = app_dir.expanduser().absolute()
    python = app / ".venv" / "bin" / "python"
    lines = [
        "[Unit]",
        "Description=Seneca local workstation service",
        "After=default.target",
        "",
        "[Service]",
        "Type=simple",
        f"EnvironmentFile={_unit_path(str(env_file.expanduser().absolute()))}",
        f"WorkingDirectory={_unit_path(str(app))}",
        f"ExecStart={_unit_quote(str(python))} -m offline_rag.api.server",
        "Restart=on-failure",
        "RestartSec=3s",
        "KillSignal=SIGTERM",
        "TimeoutStopSec=45s",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    _atomic_write(path, "\n".join(lines), 0o644)


def write_installation_metadata(
    path: Path,
    *,
    source_sha: str,
    project_version: str,
    package_identity: str,
    release_json: Path,
    target: str,
    app_dir: Path,
    data_dir: Path,
    models_dir: Path,
    ui_dir: Path,
    uv_path: Path,
    model: str,
    active_profile: str = "cpu-release",
    active_release_identity: str = "",
    cpu_release_identity: str = "",
    cuda_release_identity: str | None = None,
    seed_manifest_sha256: str = "",
    visible_memory: Mapping[str, int] | None = None,
) -> None:
    release = json.loads(release_json.read_text(encoding="utf-8"))
    if release.get("source_sha") != source_sha:
        raise ValueError("package source SHA does not match RELEASE.json")
    if release.get("project_version") != project_version:
        raise ValueError("project version does not match RELEASE.json")
    if active_profile not in {"cpu-release", "cuda-dev"}:
        raise ValueError("unsupported active workstation dependency profile")
    if not active_release_identity or not cpu_release_identity:
        raise ValueError("active and CPU release identities are required")
    if (
        active_profile == "cpu-release"
        and active_release_identity != cpu_release_identity
    ):
        raise ValueError("CPU installation must activate its CPU release identity")
    if not re.fullmatch(r"[0-9a-f]{64}", seed_manifest_sha256):
        raise ValueError("invalid package seed manifest SHA-256")
    uv_version = subprocess.run(
        [str(uv_path), "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    python_version = subprocess.run(
        [
            str(app_dir.expanduser().absolute() / ".venv" / "bin" / "python"),
            "--version",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    payload = {
        "schema_version": 1,
        "package_schema_version": release["schema_version"],
        "project_version": project_version,
        "package_identity": package_identity,
        "package_source_sha": source_sha,
        "source_sha": source_sha,
        "installed_at": datetime.now(tz=UTC).isoformat(),
        "target": target,
        "architecture": platform.machine(),
        "python_version": python_version,
        "uv_version": uv_version,
        "uv_path": str(uv_path.expanduser().resolve()),
        "application_root": str(app_dir.expanduser().absolute()),
        "data_root": str(data_dir.expanduser().absolute()),
        "models_root": str(models_dir.expanduser().absolute()),
        "ui_root": str(ui_dir.expanduser().absolute()),
        "service_mechanism": "systemd-user",
        "active_dependency_profile": active_profile,
        "active_release_identity": active_release_identity,
        "cpu_release_identity": cpu_release_identity,
        "cuda_release_identity": cuda_release_identity,
        "cuda_enabled": active_profile == "cuda-dev",
        "package_seed_identity": source_sha,
        "package_seed_manifest_sha256": seed_manifest_sha256,
        "generator_endpoint": "http://127.0.0.1:11434/v1",
        "generator_model": model,
        "wsl_visible_memory_bytes": dict(visible_memory) if target == "wsl2" else None,
    }
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", 0o600)


def activate_release_link(app_link: Path, release_dir: Path) -> None:
    """Atomically point the stable app path at a completed release directory."""
    app_link = app_link.expanduser().absolute()
    parent = app_link.parent.resolve()
    release = release_dir.expanduser().resolve(strict=True)
    releases_root = (parent / "releases").resolve()
    if releases_root not in release.parents:
        raise ValueError(
            "release directory must be below the app root's releases directory"
        )
    if app_link.exists() and not app_link.is_symlink():
        raise ValueError("app path exists and is not a release symlink")

    temporary = parent / f".{app_link.name}.link-{uuid.uuid4().hex}"
    relative_target = os.path.relpath(release, parent)
    try:
        os.symlink(relative_target, temporary)
        os.replace(temporary, app_link)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    env = sub.add_parser("write-env")
    env.add_argument("--path", type=Path, required=True)
    env.add_argument("--app-dir", type=Path, required=True)
    env.add_argument("--data-dir", type=Path, required=True)
    env.add_argument("--models-dir", type=Path, required=True)
    env.add_argument("--model", required=True)
    service = sub.add_parser("write-service")
    service.add_argument("--path", type=Path, required=True)
    service.add_argument("--app-dir", type=Path, required=True)
    service.add_argument("--env-file", type=Path, required=True)
    metadata = sub.add_parser("write-metadata")
    metadata.add_argument("--path", type=Path, required=True)
    metadata.add_argument("--source-sha", required=True)
    metadata.add_argument("--project-version", required=True)
    metadata.add_argument("--package-identity", required=True)
    metadata.add_argument("--release-json", type=Path, required=True)
    metadata.add_argument("--target", choices=("linux", "wsl2"), required=True)
    metadata.add_argument("--app-dir", type=Path, required=True)
    metadata.add_argument("--data-dir", type=Path, required=True)
    metadata.add_argument("--models-dir", type=Path, required=True)
    metadata.add_argument("--ui-dir", type=Path, required=True)
    metadata.add_argument("--uv-path", type=Path, required=True)
    metadata.add_argument("--model", required=True)
    metadata.add_argument(
        "--active-profile", choices=("cpu-release", "cuda-dev"), default="cpu-release"
    )
    metadata.add_argument("--active-release-identity", required=True)
    metadata.add_argument("--cpu-release-identity", required=True)
    metadata.add_argument("--seed-manifest-sha256", required=True)
    metadata.add_argument("--mem-total", type=int)
    metadata.add_argument("--mem-available", type=int)
    exec_env = sub.add_parser(
        "exec-env", help="Run a child with workstation.env applied"
    )
    exec_env.add_argument("--path", type=Path, required=True)
    exec_env.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    exec_env.add_argument("exec_args", nargs=argparse.REMAINDER)
    roots = sub.add_parser("read-root", help="Read a persisted Seneca data root")
    roots.add_argument("--path", type=Path, required=True)
    roots.add_argument("--name", choices=("data", "models"), required=True)
    activate = sub.add_parser(
        "activate-release", help="Atomically update the installed app release link"
    )
    activate.add_argument("--app-link", type=Path, required=True)
    activate.add_argument("--release-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "write-env":
        write_environment_file(
            args.path,
            app_dir=args.app_dir,
            data_dir=args.data_dir,
            models_dir=args.models_dir,
            model=args.model,
        )
    elif args.command == "write-service":
        write_user_service(args.path, app_dir=args.app_dir, env_file=args.env_file)
    elif args.command == "write-metadata":
        memory = None
        if args.target == "wsl2":
            if args.mem_total is None or args.mem_available is None:
                parser.error("WSL metadata needs both visible memory values")
            memory = {"MemTotal": args.mem_total, "MemAvailable": args.mem_available}
        write_installation_metadata(
            args.path,
            source_sha=args.source_sha,
            project_version=args.project_version,
            package_identity=args.package_identity,
            release_json=args.release_json,
            target=args.target,
            app_dir=args.app_dir,
            data_dir=args.data_dir,
            models_dir=args.models_dir,
            ui_dir=args.ui_dir,
            uv_path=args.uv_path,
            model=args.model,
            active_profile=args.active_profile,
            active_release_identity=args.active_release_identity,
            cpu_release_identity=args.cpu_release_identity,
            seed_manifest_sha256=args.seed_manifest_sha256,
            visible_memory=memory,
        )
    elif args.command == "exec-env":
        command = args.exec_args
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            parser.error("exec-env requires a command after --")
        try:
            child_environment = _child_environment(args.path, args.set)
        except ValueError as exc:
            parser.error(str(exc))
        os.execvpe(command[0], command, child_environment)
    elif args.command == "read-root":
        values = _read_env_file(args.path)
        key = (
            "OFFLINE_RAG_DATA_DIR" if args.name == "data" else "OFFLINE_RAG_MODELS_DIR"
        )
        value = values.get(key)
        if not value or not Path(value).is_absolute():
            parser.error(f"{key} must be an absolute path in workstation.env")
        print(value)
    elif args.command == "activate-release":
        try:
            activate_release_link(args.app_link, args.release_dir)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
