"""Tests for generated workstation configuration and metadata."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tomllib
import venv
from pathlib import Path
from types import SimpleNamespace

import pytest

from offline_rag.config import load_settings

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "workstation" / "configure.py"
)
SPEC = importlib.util.spec_from_file_location("workstation_configure", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)


def test_environment_binds_loopback_local_models_and_strict_offline(
    tmp_path: Path,
) -> None:
    values = configure.environment_values(
        app_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        model="qwen3.5:14b",
    )
    assert values["OFFLINE_RAG_HTTP_HOST"] == "127.0.0.1"
    assert values["OFFLINE_RAG_STRICT_OFFLINE"] == "true"
    assert values["OFFLINE_RAG_ALLOW_NON_LOOPBACK"] == "false"
    assert values["OFFLINE_RAG_LLM_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert (
        values["OFFLINE_RAG_APPROVED_LLM_ENDPOINTS"]
        == values["OFFLINE_RAG_LLM_BASE_URL"]
    )
    assert values["OFFLINE_RAG_APPROVED_LLM_MODELS"] == "qwen3.5:14b"
    assert values["HF_HUB_OFFLINE"] == "1"


def test_custom_roots_rebase_existing_model_provisioning_paths(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    data_root = tmp_path / "custom state" / "data"
    models_root = tmp_path / "custom state" / "models"
    settings = load_settings(
        yaml_paths=[repository_root / "config" / "base.yaml"],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(data_root),
            "OFFLINE_RAG_MODELS_DIR": str(models_root),
        },
    )
    assert settings.paths.raw_data == data_root / "raw"
    assert settings.paths.workspaces == data_root / "workspaces"
    assert settings.paths.embedding_artifacts == models_root / "embeddings"
    assert settings.paths.reranker_artifacts == models_root / "rerankers"
    assert settings.paths.docling_artifacts == models_root / "docling"
    assert settings.paths.tokenizer_artifacts == models_root / "tokenizers" / "tiktoken"
    assert settings.indexing.embedding.device == "auto"


def test_installer_selects_locked_cpu_release_without_cuda_extra() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads((repository_root / "pyproject.toml").read_text())
    installer = (repository_root / "scripts" / "workstation" / "install.sh").read_text()
    assert "cpu-release" in pyproject["project"]["optional-dependencies"]
    assert "--extra cpu-release" in installer
    assert "--no-dev" in installer
    assert "cuda-dev" not in installer


def test_install_rerun_only_replaces_application_and_keeps_persistent_roots() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    installer = (repository_root / "scripts" / "workstation" / "install.sh").read_text()
    builder = (
        repository_root / "scripts" / "workstation" / "build_package.sh"
    ).read_text()
    assert '"$UV_BIN" sync --project "$RELEASE_DIR"' in installer
    assert 'UV_PROJECT_ENVIRONMENT="$RELEASE_DIR/.venv"' in installer
    assert 'activate-release --app-link "$APP_DIR"' in installer
    assert '"$APP_DIR/.venv/bin/offline-rag" --help' in installer
    assert "git archive" in builder
    assert "npm ci && npm run build" in builder
    assert "RELEASE.json" in builder
    assert "sha256sum" in builder
    assert "git " not in installer
    assert "node" not in installer
    assert "npm" not in installer
    assert 'rm -rf -- "$DATA_DIR"' not in installer
    assert 'rm -rf -- "$MODELS_DIR"' not in installer


def test_activated_release_runs_its_final_path_venv_entrypoint(
    tmp_path: Path,
) -> None:
    seneca_root = tmp_path / "seneca"
    releases = seneca_root / "releases"
    app_link = seneca_root / "app"

    def create_release(name: str) -> Path:
        release = releases / name
        venv.EnvBuilder(with_pip=False).create(release / ".venv")
        python = release / ".venv" / "bin" / "python"
        executable = release / ".venv" / "bin" / "offline-rag"
        executable.write_text(
            f"#!{python}\nimport sys\nprint(sys.prefix)\n", encoding="utf-8"
        )
        executable.chmod(0o755)
        return release

    first = create_release("first")
    configure.activate_release_link(app_link, first)
    first_result = subprocess.run(
        [str(app_link / ".venv" / "bin" / "offline-rag")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(first_result.stdout.strip()) == (first / ".venv").resolve()

    second = create_release("second")
    configure.activate_release_link(app_link, second)
    second_result = subprocess.run(
        [str(app_link / ".venv" / "bin" / "offline-rag")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert Path(second_result.stdout.strip()) == (second / ".venv").resolve()
    assert first.exists(), "previous releases remain available for recovery"


def test_workstation_provisioning_uses_direct_configured_cli_and_defers_doctor() -> (
    None
):
    repository_root = Path(__file__).resolve().parents[2]
    provision = (
        repository_root / "scripts" / "workstation" / "provision.sh"
    ).read_text()
    wrapper = (repository_root / "scripts" / "workstation" / "seneca").read_text()
    assert "systemd-run" not in provision
    assert '--config "$APP_DIR/config/base.yaml"' in provision
    assert (
        "systemd-run"
        not in (repository_root / "scripts" / "workstation" / "host.py").read_text()
    )
    assert 'run_provision "post-provision doctor"' not in provision
    assert "seneca start" in provision
    assert '--config "$APP_DIR/config/base.yaml"' in wrapper
    assert "systemd-run" not in wrapper


def test_environment_file_is_private_and_rerun_preserves_exact_configuration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config" / "workstation.env"
    arguments = {
        "app_dir": tmp_path / "app",
        "data_dir": tmp_path / "data",
        "models_dir": tmp_path / "models",
        "model": "qwen3.5:14b",
    }
    configure.write_environment_file(path, **arguments)
    original = path.read_text(encoding="utf-8")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    configure.write_environment_file(path, **arguments)
    assert path.read_text(encoding="utf-8") == original


def test_environment_file_rejects_changed_install_bindings_without_overwrite(
    tmp_path: Path,
) -> None:
    path = tmp_path / "workstation.env"
    arguments = {
        "app_dir": tmp_path / "app",
        "data_dir": tmp_path / "data",
        "models_dir": tmp_path / "models",
        "model": "qwen3.5:14b",
    }
    configure.write_environment_file(path, **arguments)
    original = path.read_bytes()
    try:
        configure.write_environment_file(path, **{**arguments, "model": "other:latest"})
    except ValueError as exc:
        assert "explicitly" in str(exc)
    else:
        raise AssertionError("changed configuration must be reviewed, not overwritten")
    assert path.read_bytes() == original


def test_read_root_resolves_custom_data_and_model_directories(tmp_path: Path) -> None:
    path = tmp_path / "workstation.env"
    data_dir = tmp_path / "custom state" / "data"
    models_dir = tmp_path / "custom state" / "models"
    configure.write_environment_file(
        path,
        app_dir=tmp_path / "app",
        data_dir=data_dir,
        models_dir=models_dir,
        model="qwen3.5:14b",
    )

    data_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "read-root",
            "--path",
            str(path),
            "--name",
            "data",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    models_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "read-root",
            "--path",
            str(path),
            "--name",
            "models",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert data_result.stdout.strip() == str(data_dir)
    assert models_result.stdout.strip() == str(models_dir)


def test_child_environment_parses_values_without_shell_evaluation(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "workstation.env"
    path.write_text('MODEL="$(touch /tmp/should-not-run) qwen"\n', encoding="utf-8")
    monkeypatch.setenv("BASE_SETTING", "kept")
    result = configure._child_environment(path, ["HF_HUB_OFFLINE=0"])
    assert result["MODEL"] == "$(touch /tmp/should-not-run) qwen"
    assert result["BASE_SETTING"] == "kept"
    assert result["HF_HUB_OFFLINE"] == "0"


def test_user_service_uses_installed_entrypoint_and_preserves_shutdown_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "systemd" / "seneca.service"
    configure.write_user_service(
        path,
        app_dir=tmp_path / "seneca app",
        env_file=tmp_path / "config" / "workstation.env",
    )
    unit = path.read_text(encoding="utf-8")
    assert "Type=simple" in unit
    assert f'EnvironmentFile="{tmp_path / "config" / "workstation.env"}"' in unit
    assert str(tmp_path / "seneca app" / ".venv" / "bin" / "python") in unit
    assert "-m offline_rag.api.server" in unit
    assert unit.count("ExecStart=") == 1
    assert "Restart=on-failure" in unit
    assert "KillSignal=SIGTERM" in unit
    assert "TimeoutStopSec=45s" in unit
    assert "Workers=" not in unit


def test_installation_metadata_is_bounded_and_excludes_environment_dump(
    monkeypatch, tmp_path: Path
) -> None:
    app = tmp_path / "app"
    python = app / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    uv = tmp_path / "uv"
    uv.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        configure.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="uv 0.11.18\n"),
    )
    path = tmp_path / "installation.json"
    release_json = tmp_path / "RELEASE.json"
    source_sha = "a" * 40
    release_json.write_text(
        json.dumps(
            {"schema_version": 1, "source_sha": source_sha, "project_version": "0.1.0"}
        ),
        encoding="utf-8",
    )
    configure.write_installation_metadata(
        path,
        source_sha=source_sha,
        project_version="0.1.0",
        package_identity="seneca-workstation-test",
        release_json=release_json,
        target="wsl2",
        app_dir=app,
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "models",
        ui_dir=app / "ui",
        uv_path=uv,
        model="qwen3.5:14b",
        visible_memory={"MemTotal": 30_000_000_000, "MemAvailable": 20_000_000_000},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["service_mechanism"] == "systemd-user"
    assert payload["source_sha"] == source_sha
    assert payload["package_identity"] == "seneca-workstation-test"
    assert payload["wsl_visible_memory_bytes"]["MemAvailable"] == 20_000_000_000
    assert "environment" not in payload
    assert "api_key" not in json.dumps(payload).lower()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    with pytest.raises(ValueError, match="source SHA does not match RELEASE.json"):
        configure.write_installation_metadata(
            path,
            source_sha="b" * 40,
            project_version="0.1.0",
            package_identity="seneca-workstation-test",
            release_json=release_json,
            target="wsl2",
            app_dir=app,
            data_dir=tmp_path / "data",
            models_dir=tmp_path / "models",
            ui_dir=app / "ui",
            uv_path=uv,
            model="qwen3.5:14b",
            visible_memory=None,
        )
