"""Tests for generated workstation configuration and metadata."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

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
    assert 'mv -- "$APP_DIR" "$BACKUP"' in installer
    assert 'mv -- "$STAGE" "$APP_DIR"' in installer
    assert 'rm -rf -- "$DATA_DIR"' not in installer
    assert 'rm -rf -- "$MODELS_DIR"' not in installer


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
    configure.write_installation_metadata(
        path,
        source_root=tmp_path,
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
    assert payload["wsl_visible_memory_bytes"]["MemAvailable"] == 20_000_000_000
    assert "environment" not in payload
    assert "api_key" not in json.dumps(payload).lower()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
