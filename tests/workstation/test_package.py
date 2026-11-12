"""Tests for the self-contained workstation release package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPOSITORY_ROOT / "scripts/workstation/build_package.sh"
INSTALLER = REPOSITORY_ROOT / "scripts/workstation/install.sh"


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _create_integrity_fixture(package_root: Path) -> tuple[Path, dict[str, str]]:
    """Create a small package whose host preflight stops before mutation."""
    (package_root / "payload/config").mkdir(parents=True)
    (package_root / "payload/scripts/workstation").mkdir(parents=True)
    (package_root / "payload/src/offline_rag").mkdir(parents=True)
    installer = package_root / "install.sh"
    shutil.copy2(INSTALLER, installer)
    release = {
        "schema_version": 1,
        "product": "Seneca",
        "project": "offline-rag",
        "project_version": "0.1.0",
        "source_sha": "a" * 40,
        "target": "linux-x86_64",
        "python": "3.14",
        "uv_version": "0.11.18",
        "dependency_profile": "cpu-release",
        "ui_source_sha": "a" * 40,
    }
    (package_root / "RELEASE.json").write_text(json.dumps(release))
    config = package_root / "payload/config/base.yaml"
    config.write_text("original: true\n")
    (package_root / "payload/src/offline_rag/__init__.py").write_text("\n")
    host_tool = package_root / "payload/scripts/workstation/host.py"
    host_tool.write_text("raise SystemExit(1)\n")

    files = [installer, package_root / "RELEASE.json"]
    files.extend(
        path for path in (package_root / "payload").rglob("*") if path.is_file()
    )
    manifest = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  "
        f"{path.relative_to(package_root).as_posix()}\n"
        for path in sorted(files)
    )
    (package_root / "SHA256SUMS").write_text(manifest)

    home = package_root.parent / "home"
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_BIN_HOME": str(home / ".local/bin"),
    }
    return config, env


def _run_installer(package_root: Path, env: dict[str, str]):
    return subprocess.run(
        ["bash", str(package_root / "install.sh"), "--ollama-model", "fixture"],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _create_builder_fixture(root: Path) -> tuple[Path, Path]:
    """Create a tiny committed project and fake only the UI build tools."""
    (root / "scripts/workstation").mkdir(parents=True)
    (root / "scripts").mkdir(exist_ok=True)
    shutil.copy2(BUILDER, root / "scripts/workstation/build_package.sh")
    shutil.copy2(INSTALLER, root / "scripts/workstation/install.sh")
    for name in ("configure.py", "host.py", "provision.sh", "seneca"):
        (root / "scripts/workstation" / name).write_text("support\n")
    for name in ("provision_docling.py", "provision_tiktoken.py"):
        (root / "scripts" / name).write_text("support\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="offline-rag"\nversion="9.8.7"\n'
    )
    (root / "uv.lock").write_text("version = 1\n")
    (root / "README.md").write_text("fixture\n")
    (root / "src/offline_rag").mkdir(parents=True)
    (root / "src/offline_rag/__init__.py").write_text("\n")
    (root / "config").mkdir()
    (root / "config/base.yaml").write_text("fixture: true\n")
    (root / "ui").mkdir()
    (root / "ui/package-lock.json").write_text("{}\n")

    tool_bin = root / "test-bin"
    tool_bin.mkdir()
    node = tool_bin / "node"
    node.write_text("#!/bin/sh\nprintf '22\\n'\n")
    node.chmod(0o755)
    npm = tool_bin / "npm"
    npm.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = ci ]; then exit 0; fi\n'
        'if [ "$1" = run ] && [ "$2" = build ]; then\n'
        "  mkdir -p dist\n"
        "  printf '<html>built</html>\\n' > dist/index.html\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n"
    )
    npm.chmod(0o755)

    _run(["git", "init", "-q"], cwd=root)
    _run(["git", "config", "user.email", "test@example.invalid"], cwd=root)
    _run(["git", "config", "user.name", "Package Test"], cwd=root)
    _run(["git", "add", "."], cwd=root)
    _run(["git", "commit", "-qm", "fixture"], cwd=root)
    return tool_bin, root


def test_builder_creates_provenance_bound_integrity_checked_archive(
    tmp_path: Path,
) -> None:
    tool_bin, project = _create_builder_fixture(tmp_path / "project")
    env = {**os.environ, "PATH": f"{tool_bin}:{os.environ['PATH']}"}

    build = subprocess.run(
        ["bash", "scripts/workstation/build_package.sh"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    archive_dir = project / "dist/workstation"
    archives = list(archive_dir.glob("seneca-workstation-*.tar.gz"))
    assert len(archives) == 1
    archive = archives[0]
    assert (
        archive.name
        == "seneca-workstation-9.8.7-linux-x86_64-"
        + _run(["git", "rev-parse", "--short=12", "HEAD"], cwd=project).stdout.strip()
        + ".tar.gz"
    )
    assert "SHA-256:" in build.stdout
    _run(["sha256sum", "--check", archive.name + ".sha256"], cwd=archive_dir)

    extract_root = tmp_path / "extracted"
    extract_root.mkdir()
    with tarfile.open(archive, "r:gz") as package:
        package.extractall(extract_root, filter="data")
    package_root = next(extract_root.iterdir())
    manifest = json.loads((package_root / "RELEASE.json").read_text())
    assert manifest["project_version"] == "9.8.7"
    assert (
        manifest["source_sha"]
        == _run(["git", "rev-parse", "HEAD"], cwd=project).stdout.strip()
    )
    assert manifest["ui_source_sha"] == manifest["source_sha"]
    assert (package_root / "payload/ui/index.html").is_file()
    assert (package_root / "payload/src/offline_rag/__init__.py").is_file()
    assert (package_root / "payload/uv.lock").is_file()
    assert not any(
        path.name in {".git", "node_modules"} for path in package_root.rglob("*")
    )
    assert not (package_root / "payload/ui/package-lock.json").exists()
    assert not (package_root / "payload/ui/node_modules").exists()
    assert not (package_root / "payload/.env").exists()
    assert not (package_root / "payload/models").exists()
    assert not (package_root / "payload/data").exists()
    _run(["sha256sum", "--check", "--status", "SHA256SUMS"], cwd=package_root)


def test_tampered_package_fails_before_installation_mutation(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    config, env = _create_integrity_fixture(package_root)
    config.write_text("tampered: true\n")
    result = _run_installer(package_root, env)
    assert result.returncode != 0
    assert "Package integrity verification failed" in result.stderr
    home = Path(env["HOME"])
    assert not (home / ".local/share/seneca").exists()
    assert not (home / ".config/seneca").exists()


def test_added_unlisted_file_fails_before_installation_mutation(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "package"
    _, env = _create_integrity_fixture(package_root)
    (package_root / "payload/src/offline_rag/extra_file.py").write_text(
        "unexpected = True\n"
    )

    result = _run_installer(package_root, env)

    assert result.returncode != 0
    assert "Package integrity verification failed" in result.stderr
    home = Path(env["HOME"])
    assert not (home / ".local/share/seneca").exists()
    assert not (home / ".config/seneca").exists()


def test_added_unlisted_symlink_fails_before_installation_mutation(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "package"
    _, env = _create_integrity_fixture(package_root)
    link = package_root / "payload/src/offline_rag/extra_link.py"
    link.symlink_to("../../config/base.yaml")

    result = _run_installer(package_root, env)

    assert result.returncode != 0
    assert "Package integrity verification failed" in result.stderr
    home = Path(env["HOME"])
    assert not (home / ".local/share/seneca").exists()
    assert not (home / ".config/seneca").exists()


def test_missing_manifest_file_fails_before_installation_mutation(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "package"
    config, env = _create_integrity_fixture(package_root)
    config.unlink()

    result = _run_installer(package_root, env)

    assert result.returncode != 0
    assert "Package integrity verification failed" in result.stderr
    home = Path(env["HOME"])
    assert not (home / ".local/share/seneca").exists()
    assert not (home / ".config/seneca").exists()


def test_pristine_package_passes_integrity_before_host_preflight(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "package"
    _, env = _create_integrity_fixture(package_root)

    result = _run_installer(package_root, env)

    assert result.returncode != 0
    assert "Package integrity verification failed" not in result.stderr
    assert "Preflight failed" in result.stderr
    home = Path(env["HOME"])
    assert not (home / ".local/share/seneca").exists()
    assert not (home / ".config/seneca").exists()
