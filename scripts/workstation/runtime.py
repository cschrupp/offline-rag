#!/usr/bin/env python3
"""Build and transactionally activate workstation runtime profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

SEED_SCHEMA_VERSION = 1
SEED_MANIFEST = "SEED_SHA256SUMS"
RELEASE_MARKER = ".seneca-release.json"
HEALTH_URL = "http://127.0.0.1:8080/health/ready"


@dataclass(frozen=True)
class WorkstationLayout:
    """Paths owned by one user's workstation installation."""

    app_link: Path
    releases: Path
    packages: Path
    data: Path
    models: Path
    env_file: Path
    metadata_file: Path

    @classmethod
    def from_environment(cls) -> WorkstationLayout:
        data_home = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
        root = data_home / "seneca"
        return cls(
            app_link=root / "app",
            releases=root / "releases",
            packages=root / "packages",
            data=root / "data",
            models=root / "models",
            env_file=config_home / "seneca" / "workstation.env",
            metadata_file=config_home / "seneca" / "installation.json",
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _file_inventory(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    for current, names, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in names:
            path = current_path / name
            if path.is_symlink() or not path.is_dir():
                raise ValueError("seed contains an unsupported filesystem object")
            directories.add(path.relative_to(root).as_posix())
        for name in filenames:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("seed contains an unsupported filesystem object")
            files.add(path.relative_to(root).as_posix())
    return files, directories


def _write_seed_manifest(root: Path) -> None:
    files, _ = _file_inventory(root)
    files.discard(SEED_MANIFEST)
    lines = [f"{_sha256(root / name)}  {name}\n" for name in sorted(files)]
    (root / SEED_MANIFEST).write_text("".join(lines), encoding="utf-8")


def verify_seed(
    seed_root: Path,
    *,
    source_sha: str,
    expected_manifest_sha256: str | None = None,
    expected_package_identity: str | None = None,
) -> dict[str, Any]:
    """Verify exact seed membership, content hashes, and source identity."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("installation source SHA is invalid")
    if seed_root.is_symlink() or not seed_root.is_dir():
        raise ValueError("trusted CUDA reconstruction seed is missing or unsafe")
    actual_files, actual_directories = _file_inventory(seed_root)
    manifest_path = seed_root / SEED_MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("CUDA reconstruction seed manifest is missing")

    try:
        seed = json.loads((seed_root / "SEED.json").read_text(encoding="utf-8"))
        release = json.loads((seed_root / "RELEASE.json").read_text(encoding="utf-8"))
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("CUDA reconstruction seed metadata is unreadable") from exc

    expected_files: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        relative = PurePosixPath(name)
        if (
            not separator
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not name
            or "\\" in name
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != name
            or name == SEED_MANIFEST
            or name in expected_files
        ):
            raise ValueError("CUDA reconstruction seed manifest is invalid")
        expected_files[name] = digest

    if not {"RELEASE.json", "SEED.json", "PACKAGE_SHA256SUMS"}.issubset(expected_files):
        raise ValueError("CUDA reconstruction seed is incomplete")

    expected_directories = {"payload"}
    for name in expected_files:
        if name not in {
            "RELEASE.json",
            "SEED.json",
            "PACKAGE_SHA256SUMS",
        } and not name.startswith("payload/"):
            raise ValueError("CUDA reconstruction seed contains an unexpected path")
        for index in range(1, len(PurePosixPath(name).parts)):
            parent = "/".join(PurePosixPath(name).parts[:index])
            if parent == "payload" or parent.startswith("payload/"):
                expected_directories.add(parent)
    if actual_files != set(expected_files) | {SEED_MANIFEST}:
        raise ValueError("CUDA reconstruction seed file set differs from its manifest")
    if actual_directories != expected_directories:
        raise ValueError("CUDA reconstruction seed directory set is invalid")
    for name, expected_digest in expected_files.items():
        if _sha256(seed_root / name) != expected_digest:
            raise ValueError("CUDA reconstruction seed content hash mismatch")

    if (
        seed.get("schema_version") != SEED_SCHEMA_VERSION
        or seed.get("source_sha") != source_sha
        or release.get("source_sha") != source_sha
        or seed.get("project_version") != release.get("project_version")
        or release.get("ui_source_sha") != source_sha
        or release.get("dependency_profile") != "cpu-release"
        or seed.get("source_manifest_sha256")
        != _sha256(seed_root / "PACKAGE_SHA256SUMS")
    ):
        raise ValueError(
            "CUDA reconstruction seed provenance does not match installation"
        )
    if (
        expected_manifest_sha256 is not None
        and _sha256(manifest_path) != expected_manifest_sha256
    ):
        raise ValueError(
            "CUDA reconstruction seed identity differs from installation metadata"
        )
    if (
        expected_package_identity is not None
        and seed.get("package_identity") != expected_package_identity
    ):
        raise ValueError(
            "CUDA reconstruction seed package identity differs from installation"
        )
    if (seed_root / "payload/data").exists() or (seed_root / "payload/models").exists():
        raise ValueError(
            "CUDA reconstruction seed must not contain user data or models"
        )
    return seed


def create_seed(
    package_root: Path,
    seed_root: Path,
    *,
    package_identity: str,
    source_sha: str,
) -> None:
    """Preserve verified package inputs in a closed, immutable seed directory."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("package source SHA is invalid")
    if seed_root.exists() or seed_root.is_symlink():
        existing = verify_seed(seed_root, source_sha=source_sha)
        if existing.get("package_identity") != package_identity:
            raise ValueError(
                "existing CUDA reconstruction seed has a different package identity"
            )
        return
    seed_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{source_sha}.", dir=seed_root.parent))
    try:
        shutil.copy2(package_root / "RELEASE.json", stage / "RELEASE.json")
        shutil.copy2(package_root / "SHA256SUMS", stage / "PACKAGE_SHA256SUMS")
        shutil.copytree(package_root / "payload", stage / "payload", symlinks=False)
        release = json.loads((stage / "RELEASE.json").read_text(encoding="utf-8"))
        if release.get("source_sha") != source_sha:
            raise ValueError("verified package source SHA differs from seed request")
        seed = {
            "schema_version": SEED_SCHEMA_VERSION,
            "source_sha": source_sha,
            "project_version": release.get("project_version"),
            "package_identity": package_identity,
            "source_manifest_sha256": _sha256(stage / "PACKAGE_SHA256SUMS"),
        }
        (stage / "SEED.json").write_text(
            json.dumps(seed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_seed_manifest(stage)
        verify_seed(stage, source_sha=source_sha)
        os.replace(stage, seed_root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def write_release_marker(
    path: Path, *, source_sha: str, project_version: str, dependency_profile: str
) -> None:
    if dependency_profile not in {"cpu-release", "cuda-dev"}:
        raise ValueError("unsupported workstation dependency profile")
    _write_json(
        path,
        {
            "schema_version": 1,
            "source_sha": source_sha,
            "project_version": project_version,
            "dependency_profile": dependency_profile,
        },
    )


def _load_metadata(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Seneca installation metadata is unavailable or invalid"
        ) from exc
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported Seneca installation metadata schema")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_sha", ""))):
        raise ValueError("installation metadata has an invalid source SHA")
    return payload


def _managed_release(
    layout: WorkstationLayout,
    identity: str,
    source_sha: str,
    *,
    expected_profile: str,
    project_version: str,
) -> Path:
    if not identity or Path(identity).name != identity:
        raise ValueError("installation metadata contains an invalid release identity")
    release = layout.releases / identity
    if release.is_symlink() or not release.is_dir():
        raise ValueError("recorded workstation release is missing or unsafe")
    try:
        release.resolve(strict=True).relative_to(layout.releases.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError(
            "recorded workstation release escapes the managed root"
        ) from exc
    marker_path = release / RELEASE_MARKER
    if marker_path.is_symlink() or not marker_path.is_file():
        raise ValueError("recorded workstation release identity is unavailable")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "recorded workstation release identity is unavailable"
        ) from exc
    if (
        marker.get("source_sha") != source_sha
        or marker.get("project_version") != project_version
        or marker.get("dependency_profile") != expected_profile
    ):
        raise ValueError("recorded workstation release provenance is invalid")
    return release


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("workstation environment file is malformed")
        parsed = shlex.split(value, posix=True)
        if len(parsed) != 1:
            raise ValueError("workstation environment file is malformed")
        values[key] = parsed[0]
    return values


def _run(command: list[str], *, env: dict[str, str], timeout: int = 1800) -> None:
    result = subprocess.run(
        command,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed at {Path(command[0]).name} (exit {result.returncode})"
        )


def _prepare_cuda_release(
    layout: WorkstationLayout,
    metadata: dict[str, Any],
    seed_root: Path,
    seed: dict[str, Any],
) -> Path:
    uv_path = Path(str(metadata.get("uv_path", "")))
    if (
        not uv_path.is_absolute()
        or not uv_path.is_file()
        or not os.access(uv_path, os.X_OK)
    ):
        raise ValueError(
            "the recorded uv executable is unavailable; reinstall the CPU package"
        )
    source_sha = str(metadata["source_sha"])
    release_id = f"{source_sha}-cuda-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
    candidate = layout.releases / release_id
    candidate.mkdir(parents=True, exist_ok=False)
    payload = seed_root / "payload"
    try:
        for name in ("pyproject.toml", "uv.lock", "README.md"):
            shutil.copy2(payload / name, candidate / name)
        for name in ("src", "config", "ui", "scripts"):
            shutil.copytree(payload / name, candidate / name, symlinks=False)
        write_release_marker(
            candidate / RELEASE_MARKER,
            source_sha=source_sha,
            project_version=str(metadata["project_version"]),
            dependency_profile="cuda-dev",
        )

        environment = os.environ.copy()
        environment.update(_read_env(layout.env_file))
        environment["UV_PROJECT_ENVIRONMENT"] = str(candidate / ".venv")
        environment["UV_PYTHON_DOWNLOADS"] = "0"
        _run([str(uv_path), "python", "install", "3.14"], env=environment)
        _run(
            [
                str(uv_path),
                "sync",
                "--project",
                str(candidate),
                "--locked",
                "--no-dev",
                "--extra",
                "cuda-dev",
                "--no-editable",
            ],
            env=environment,
        )

        candidate_python = candidate / ".venv/bin/python"
        candidate_cli = candidate / ".venv/bin/offline-rag"
        _run([str(candidate_cli), "--help"], env=environment)
        preflight = """\
from offline_rag.dense.device import probe_torch_cuda
from offline_rag.dense.execution_profile import resolve_qualified_embedding_profile

available, build, failed = probe_torch_cuda()
if failed or not available or build is None:
    raise SystemExit("CUDA is not usable by the candidate PyTorch runtime")
resolved = resolve_qualified_embedding_profile("auto", "native")
if resolved.profile.profile_id != "cuda_fp16_v1":
    raise SystemExit("AUTO did not resolve to the qualified CUDA profile")
"""
        _run(
            [str(candidate_python), "-c", preflight],
            env=environment,
        )
        provision_environment = environment.copy()
        provision_environment.update(
            {"HF_HUB_OFFLINE": "0", "TRANSFORMERS_OFFLINE": "0"}
        )
        _run(
            [
                str(candidate_cli),
                "provision",
                "embedding",
                "--config",
                str(candidate / "config/base.yaml"),
                "--representation",
                "torch_st_v1",
                "--json",
            ],
            env=provision_environment,
        )
        validation = """\
from offline_rag.config import load_settings
from offline_rag.dense.embedding_artifacts import inspect_representation
from offline_rag.dense.provision import resolve_embedding_model_dir
import sys

settings = load_settings(yaml_paths=[sys.argv[1]])
model_dir = resolve_embedding_model_dir(
    embedding_artifacts_root=settings.paths.embedding_artifacts,
    model_path=settings.dense.model_path,
)
inspection = inspect_representation(
    model_dir, "torch_st_v1",
    expected_model_id=settings.indexing.embedding.model_id,
    expected_revision=settings.indexing.embedding.revision,
    expected_dimension=settings.indexing.embedding.dimension,
)
if str(getattr(inspection.readiness, "value", inspection.readiness)).upper() != "READY":
    raise SystemExit("qualified torch_st_v1 representation is not READY")
"""
        _run(
            [
                str(candidate_python),
                "-c",
                validation,
                str(candidate / "config/base.yaml"),
            ],
            env=environment,
        )
        _run(
            [
                str(candidate_cli),
                "doctor",
                "--config",
                str(candidate / "config/base.yaml"),
            ],
            env=environment,
        )
        shutil.rmtree(candidate / "src")
        _run([str(candidate_cli), "--help"], env=environment)
        _run([str(candidate_python), "-c", "import offline_rag"], env=environment)
        return candidate
    except BaseException:
        shutil.rmtree(candidate, ignore_errors=True)
        raise


def _activate(layout: WorkstationLayout, release: Path) -> None:
    from configure import activate_release_link

    activate_release_link(layout.app_link, release)


def _restart_service() -> None:
    result = subprocess.run(
        ["systemctl", "--user", "restart", "seneca.service"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError("systemd-user could not restart Seneca")


def _wait_ready(timeout_seconds: int = 75) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2.0) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError, TimeoutError):
            time.sleep(1.0)
    raise RuntimeError("Seneca readiness check did not pass after service restart")


def _update_profile_metadata(
    path: Path,
    *,
    active_profile: str,
    active_release_identity: str,
    cpu_release_identity: str,
    cuda_release_identity: str | None,
) -> None:
    metadata = _load_metadata(path)
    metadata.update(
        {
            "active_dependency_profile": active_profile,
            "active_release_identity": active_release_identity,
            "cpu_release_identity": cpu_release_identity,
            "cuda_release_identity": cuda_release_identity,
            "cuda_enabled": active_profile == "cuda-dev",
            "runtime_state_updated_at": datetime.now(tz=UTC).isoformat(),
        }
    )
    _write_json(path, metadata)


def enable_cuda(
    layout: WorkstationLayout,
    *,
    confirmed: bool,
    seed_validator: Callable[..., dict[str, Any]] = verify_seed,
    prepare: Callable[..., Path] = _prepare_cuda_release,
    activate: Callable[..., None] = _activate,
    restart: Callable[[], None] = _restart_service,
    wait_ready: Callable[[], None] = _wait_ready,
    update_metadata: Callable[..., None] = _update_profile_metadata,
) -> Path:
    """Construct, validate, and atomically activate a CUDA release."""
    if not confirmed:
        raise ValueError("CUDA enablement requires explicit user confirmation")
    metadata = _load_metadata(layout.metadata_file)
    if metadata.get("active_dependency_profile") == "cuda-dev":
        return layout.app_link.resolve(strict=True)
    if metadata.get("active_dependency_profile") != "cpu-release":
        raise ValueError(
            "active workstation dependency profile is not a managed CPU release"
        )
    source_sha = str(metadata["source_sha"])
    cpu_identity = str(metadata.get("cpu_release_identity", ""))
    previous = _managed_release(
        layout,
        cpu_identity,
        source_sha,
        expected_profile="cpu-release",
        project_version=str(metadata["project_version"]),
    )
    if previous != layout.app_link.resolve(strict=True):
        raise ValueError("active app link differs from recorded CPU release")
    seed_root = layout.packages / source_sha
    seed = seed_validator(
        seed_root,
        source_sha=source_sha,
        expected_manifest_sha256=str(metadata.get("package_seed_manifest_sha256", "")),
        expected_package_identity=str(metadata.get("package_identity", "")),
    )
    candidate = prepare(layout, metadata, seed_root, seed)
    activated = False
    try:
        activate(layout, candidate)
        activated = True
        restart()
        wait_ready()
        update_metadata(
            layout.metadata_file,
            active_profile="cuda-dev",
            active_release_identity=candidate.name,
            cpu_release_identity=cpu_identity,
            cuda_release_identity=candidate.name,
        )
        return candidate
    except BaseException as exc:
        if activated:
            try:
                activate(layout, previous)
                restart()
                wait_ready()
            except BaseException as rollback_exc:
                raise RuntimeError(
                    "CUDA activation failed and CPU rollback needs operator attention; "
                    "both immutable releases were retained"
                ) from rollback_exc
        shutil.rmtree(candidate, ignore_errors=True)
        raise RuntimeError(
            "CUDA enablement failed; the previous CPU release was restored"
        ) from exc


def disable_cuda(
    layout: WorkstationLayout,
    *,
    activate: Callable[..., None] = _activate,
    restart: Callable[[], None] = _restart_service,
    wait_ready: Callable[[], None] = _wait_ready,
    update_metadata: Callable[..., None] = _update_profile_metadata,
) -> Path:
    """Restore the retained CPU release without modifying data or model assets."""
    metadata = _load_metadata(layout.metadata_file)
    if metadata.get("active_dependency_profile") == "cpu-release":
        return layout.app_link.resolve(strict=True)
    if metadata.get("active_dependency_profile") != "cuda-dev":
        raise ValueError("active workstation dependency profile is not managed")
    source_sha = str(metadata["source_sha"])
    cpu_identity = str(metadata.get("cpu_release_identity", ""))
    cuda_identity = str(metadata.get("active_release_identity", ""))
    cpu_release = _managed_release(
        layout,
        cpu_identity,
        source_sha,
        expected_profile="cpu-release",
        project_version=str(metadata["project_version"]),
    )
    previous = _managed_release(
        layout,
        cuda_identity,
        source_sha,
        expected_profile="cuda-dev",
        project_version=str(metadata["project_version"]),
    )
    if previous != layout.app_link.resolve(strict=True):
        raise ValueError("active app link differs from recorded CUDA release")
    try:
        activate(layout, cpu_release)
        restart()
        wait_ready()
        update_metadata(
            layout.metadata_file,
            active_profile="cpu-release",
            active_release_identity=cpu_identity,
            cpu_release_identity=cpu_identity,
            cuda_release_identity=cuda_identity,
        )
    except BaseException as exc:
        try:
            activate(layout, previous)
            restart()
            wait_ready()
        except BaseException as rollback_exc:
            raise RuntimeError(
                "CPU restoration failed and CUDA rollback needs operator attention; "
                "both immutable releases were retained"
            ) from rollback_exc
        raise RuntimeError(
            "CPU restoration failed; the previous CUDA release was restored"
        ) from exc
    return cpu_release


def _confirm_cuda(probe_status: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    if probe_status == "observed":
        prompt = "NVIDIA GPU support appears available. Enable optional CUDA acceleration? [y/N] "
    else:
        prompt = f"NVIDIA capability probe is {probe_status}. Attempt CUDA setup anyway? [y/N] "
    try:
        return input(prompt).strip().lower() in {"y", "yes"}
    except EOFError:
        return False


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    enable = subparsers.add_parser("enable-cuda")
    enable.add_argument(
        "--yes", action="store_true", help="Confirm explicit CUDA enablement"
    )
    subparsers.add_parser("disable-cuda")
    seed = subparsers.add_parser("create-seed")
    seed.add_argument("--package-root", type=Path, required=True)
    seed.add_argument("--seed-root", type=Path, required=True)
    seed.add_argument("--package-identity", required=True)
    seed.add_argument("--source-sha", required=True)
    marker = subparsers.add_parser("record-release")
    marker.add_argument("--path", type=Path, required=True)
    marker.add_argument("--source-sha", required=True)
    marker.add_argument("--project-version", required=True)
    marker.add_argument(
        "--dependency-profile", choices=("cpu-release", "cuda-dev"), required=True
    )
    args = parser.parse_args()

    if args.command == "create-seed":
        create_seed(
            args.package_root,
            args.seed_root,
            package_identity=args.package_identity,
            source_sha=args.source_sha,
        )
        return 0
    if args.command == "record-release":
        write_release_marker(
            args.path,
            source_sha=args.source_sha,
            project_version=args.project_version,
            dependency_profile=args.dependency_profile,
        )
        return 0

    layout = WorkstationLayout.from_environment()
    if args.command == "enable-cuda":
        from host import probe_nvidia_capability

        status = str(probe_nvidia_capability()["status"])
        if not _confirm_cuda(status, assume_yes=args.yes):
            print("CUDA enablement declined; the active CPU release is unchanged.")
            return 0
        release = enable_cuda(layout, confirmed=True)
        print(f"CUDA runtime activated from immutable release: {release.name}")
        return 0
    release = disable_cuda(layout)
    print(f"CPU runtime restored from immutable release: {release.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_cli())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Seneca workstation runtime change failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
