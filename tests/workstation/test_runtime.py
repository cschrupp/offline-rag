"""Transactional workstation runtime-profile tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "workstation"
RUNTIME_PATH = SCRIPT_DIR / "runtime.py"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("workstation_runtime", RUNTIME_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime
SPEC.loader.exec_module(runtime)


def _write_package(package: Path, source_sha: str) -> None:
    payload = package / "payload"
    (payload / "src/offline_rag").mkdir(parents=True)
    (payload / "config").mkdir()
    (payload / "ui").mkdir()
    (payload / "scripts").mkdir()
    (payload / "src/offline_rag/__init__.py").write_text("\n", encoding="utf-8")
    (payload / "config/base.yaml").write_text("fixture: true\n", encoding="utf-8")
    (payload / "ui/index.html").write_text("fixture\n", encoding="utf-8")
    (payload / "scripts/runtime.py").write_text("fixture\n", encoding="utf-8")
    (payload / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (payload / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (payload / "README.md").write_text("fixture\n", encoding="utf-8")
    (package / "RELEASE.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_sha": source_sha,
                "ui_source_sha": source_sha,
                "project_version": "0.1.0",
                "dependency_profile": "cpu-release",
            }
        ),
        encoding="utf-8",
    )
    (package / "SHA256SUMS").write_text("package integrity checked\n", encoding="utf-8")


def _make_layout(tmp_path: Path, *, profile: str = "cpu-release"):
    source_sha = "a" * 40
    app_link = tmp_path / "seneca/app"
    releases = tmp_path / "seneca/releases"
    packages = tmp_path / "seneca/packages"
    data = tmp_path / "seneca/data"
    models = tmp_path / "seneca/models"
    env_file = tmp_path / "seneca/workstation.env"
    metadata_file = tmp_path / "seneca/installation.json"
    releases.mkdir(parents=True)
    packages.mkdir(parents=True)
    data.mkdir(parents=True)
    models.mkdir(parents=True)
    (data / "preserved.txt").write_text("data", encoding="utf-8")
    (models / "preserved.txt").write_text("models", encoding="utf-8")
    cpu = releases / f"{source_sha}-cpu"
    cpu.mkdir()
    runtime.write_release_marker(
        cpu / runtime.RELEASE_MARKER,
        source_sha=source_sha,
        project_version="0.1.0",
        dependency_profile="cpu-release",
    )
    active = cpu
    cuda_identity = None
    if profile == "cuda-dev":
        active = releases / f"{source_sha}-cuda"
        active.mkdir()
        runtime.write_release_marker(
            active / runtime.RELEASE_MARKER,
            source_sha=source_sha,
            project_version="0.1.0",
            dependency_profile="cuda-dev",
        )
        cuda_identity = active.name
    app_link.symlink_to(active.relative_to(app_link.parent))
    env_file.write_text('OFFLINE_RAG_DATA_DIR="/unused/data"\n', encoding="utf-8")

    package = tmp_path / "package"
    _write_package(package, source_sha)
    seed_root = packages / source_sha
    runtime.create_seed(
        package,
        seed_root,
        package_identity="seneca-workstation-fixture",
        source_sha=source_sha,
    )
    metadata = {
        "schema_version": 1,
        "source_sha": source_sha,
        "project_version": "0.1.0",
        "package_identity": "seneca-workstation-fixture",
        "active_dependency_profile": profile,
        "active_release_identity": active.name,
        "cpu_release_identity": cpu.name,
        "cuda_release_identity": cuda_identity,
        "cuda_enabled": profile == "cuda-dev",
        "package_seed_manifest_sha256": runtime._sha256(
            seed_root / runtime.SEED_MANIFEST
        ),
    }
    runtime._write_json(metadata_file, metadata)
    layout = runtime.WorkstationLayout(
        app_link=app_link,
        releases=releases,
        packages=packages,
        data=data,
        models=models,
        env_file=env_file,
        metadata_file=metadata_file,
    )
    return layout, cpu, seed_root


def _activate(layout, release: Path) -> None:
    temporary = layout.app_link.parent / ".app-link-test"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release.relative_to(layout.app_link.parent))
    temporary.replace(layout.app_link)


def test_seed_is_closed_source_bound_and_detects_payload_mutation(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    source_sha = "b" * 40
    _write_package(package, source_sha)
    seed = tmp_path / "packages" / source_sha
    runtime.create_seed(
        package,
        seed,
        package_identity="fixture-package",
        source_sha=source_sha,
    )
    trusted = runtime.verify_seed(seed, source_sha=source_sha)
    assert trusted["package_identity"] == "fixture-package"
    (seed / "payload/src/offline_rag/extra.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="file set|content hash"):
        runtime.verify_seed(seed, source_sha=source_sha)


def test_enable_cuda_requires_confirmation_before_seed_or_environment_work(
    tmp_path: Path,
) -> None:
    layout, cpu, _ = _make_layout(tmp_path)
    with pytest.raises(ValueError, match="explicit user confirmation"):
        runtime.enable_cuda(layout, confirmed=False)
    assert layout.app_link.resolve() == cpu.resolve()


@pytest.mark.parametrize(
    "failure_stage",
    ["dependency construction", "torch_st_v1 provisioning", "CUDA validation"],
)
def test_pre_activation_failure_keeps_cpu_data_and_models(
    tmp_path: Path, failure_stage: str
) -> None:
    layout, cpu, _ = _make_layout(tmp_path)

    def fail_prepare(*args, **kwargs):
        raise RuntimeError(failure_stage)

    with pytest.raises(RuntimeError, match=failure_stage):
        runtime.enable_cuda(
            layout,
            confirmed=True,
            prepare=fail_prepare,
        )
    assert layout.app_link.resolve() == cpu.resolve()
    assert (layout.data / "preserved.txt").read_text() == "data"
    assert (layout.models / "preserved.txt").read_text() == "models"


def test_corrupt_seed_fails_before_candidate_construction(tmp_path: Path) -> None:
    layout, cpu, seed = _make_layout(tmp_path)
    (seed / "payload/config/base.yaml").write_text("corrupt\n", encoding="utf-8")
    called = False

    def prepare(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("candidate construction must not run for a bad seed")

    with pytest.raises(ValueError, match="content hash|seed identity"):
        runtime.enable_cuda(layout, confirmed=True, prepare=prepare)
    assert called is False
    assert layout.app_link.resolve() == cpu.resolve()


@pytest.mark.parametrize(
    ("failure_stage", "matches"),
    [
        ("dependency construction", "sync"),
        ("torch_st_v1 provisioning", "provision"),
        ("candidate CUDA validation", "-c"),
    ],
)
def test_cuda_candidate_stage_failure_cleans_candidate_without_switching_cpu(
    monkeypatch, tmp_path: Path, failure_stage: str, matches: str
) -> None:
    layout, cpu, seed = _make_layout(tmp_path)
    uv = tmp_path / "uv"
    uv.write_text("fixture", encoding="utf-8")
    uv.chmod(0o755)
    metadata = json.loads(layout.metadata_file.read_text())
    metadata["uv_path"] = str(uv)

    commands: list[list[str]] = []

    def fail_at(command, *, env, timeout=1800):
        commands.append(command)
        if matches in command:
            raise RuntimeError(failure_stage)

    monkeypatch.setattr(runtime, "_run", fail_at)
    with pytest.raises(RuntimeError, match=failure_stage):
        runtime._prepare_cuda_release(
            layout,
            metadata,
            seed,
            runtime.verify_seed(
                seed,
                source_sha=metadata["source_sha"],
                expected_manifest_sha256=metadata["package_seed_manifest_sha256"],
                expected_package_identity=metadata["package_identity"],
            ),
        )
    assert layout.app_link.resolve() == cpu.resolve()
    assert list(layout.releases.iterdir()) == [cpu]
    assert (layout.data / "preserved.txt").read_text() == "data"
    assert (layout.models / "preserved.txt").read_text() == "models"
    if failure_stage == "candidate CUDA validation":
        assert not any("provision" in command for command in commands)


def test_activation_failure_keeps_cpu_release_active_and_persistent_roots(
    tmp_path: Path,
) -> None:
    layout, cpu, _ = _make_layout(tmp_path)

    def prepare(layout, metadata, seed_root, seed):
        candidate = layout.releases / f"{metadata['source_sha']}-cuda-test"
        candidate.mkdir()
        runtime.write_release_marker(
            candidate / runtime.RELEASE_MARKER,
            source_sha=metadata["source_sha"],
            project_version=metadata["project_version"],
            dependency_profile="cuda-dev",
        )
        return candidate

    def fail_activation(layout, release):
        raise RuntimeError("activation failure")

    with pytest.raises(RuntimeError, match="previous CPU release was restored"):
        runtime.enable_cuda(
            layout,
            confirmed=True,
            prepare=prepare,
            activate=fail_activation,
        )
    assert layout.app_link.resolve() == cpu.resolve()
    assert (layout.data / "preserved.txt").read_text() == "data"
    assert (layout.models / "preserved.txt").read_text() == "models"


def test_post_activation_health_failure_rolls_back_to_cpu(tmp_path: Path) -> None:
    layout, cpu, _ = _make_layout(tmp_path)
    restart_calls = 0
    health_calls = 0

    def prepare(layout, metadata, seed_root, seed):
        candidate = layout.releases / f"{metadata['source_sha']}-cuda-test"
        candidate.mkdir()
        runtime.write_release_marker(
            candidate / runtime.RELEASE_MARKER,
            source_sha=metadata["source_sha"],
            project_version=metadata["project_version"],
            dependency_profile="cuda-dev",
        )
        return candidate

    def restart():
        nonlocal restart_calls
        restart_calls += 1

    def fail_health_once():
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            raise RuntimeError("post-activation health failure")

    with pytest.raises(RuntimeError, match="previous CPU release was restored"):
        runtime.enable_cuda(
            layout,
            confirmed=True,
            prepare=prepare,
            activate=_activate,
            restart=restart,
            wait_ready=fail_health_once,
        )
    assert restart_calls == 2
    assert layout.app_link.resolve() == cpu.resolve()
    metadata = json.loads(layout.metadata_file.read_text())
    assert metadata["active_dependency_profile"] == "cpu-release"
    assert (layout.data / "preserved.txt").read_text() == "data"
    assert (layout.models / "preserved.txt").read_text() == "models"


def test_service_restart_failure_rolls_back_to_cpu(tmp_path: Path) -> None:
    layout, cpu, _ = _make_layout(tmp_path)
    restart_calls = 0

    def prepare(layout, metadata, seed_root, seed):
        candidate = layout.releases / f"{metadata['source_sha']}-cuda-test"
        candidate.mkdir()
        runtime.write_release_marker(
            candidate / runtime.RELEASE_MARKER,
            source_sha=metadata["source_sha"],
            project_version=metadata["project_version"],
            dependency_profile="cuda-dev",
        )
        return candidate

    def restart_once():
        nonlocal restart_calls
        restart_calls += 1
        if restart_calls == 1:
            raise RuntimeError("service restart failure")

    with pytest.raises(RuntimeError, match="previous CPU release was restored"):
        runtime.enable_cuda(
            layout,
            confirmed=True,
            prepare=prepare,
            activate=_activate,
            restart=restart_once,
            wait_ready=lambda: None,
        )
    assert restart_calls == 2
    assert layout.app_link.resolve() == cpu.resolve()
    assert (
        json.loads(layout.metadata_file.read_text())["active_dependency_profile"]
        == "cpu-release"
    )


def test_disable_cuda_restores_retained_cpu_without_deleting_torch_models(
    tmp_path: Path,
) -> None:
    layout, cpu, _ = _make_layout(tmp_path, profile="cuda-dev")
    (layout.models / "torch-st-model").mkdir()
    (layout.models / "torch-st-model/marker").write_text("retained", encoding="utf-8")
    release = runtime.disable_cuda(
        layout,
        activate=_activate,
        restart=lambda: None,
        wait_ready=lambda: None,
    )
    assert release == cpu
    assert layout.app_link.resolve() == cpu.resolve()
    assert (layout.models / "torch-st-model/marker").read_text() == "retained"
    metadata = json.loads(layout.metadata_file.read_text())
    assert metadata["active_dependency_profile"] == "cpu-release"
    assert metadata["cuda_enabled"] is False
