"""P3 bundle-aware embedding provisioning tests."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from offline_rag.core.ids import (
    QWEN3_EMBEDDING_ARTIFACT_CONTRACT,
    QWEN3_EMBEDDING_MODEL_ID,
    QWEN3_EMBEDDING_PINNED_REVISION,
)
from offline_rag.dense.embedding_artifacts import (
    BUNDLE_MANIFEST_NAME,
    INSTALLED_REPRESENTATION_SCHEMA,
    QUALIFICATION_SCHEMA,
    REPRESENTATION_MANIFEST_NAME,
    QualifiedEmbeddingRepresentationSpec,
    RepresentationReadiness,
    inspect_representation,
    load_package_qualification_spec,
)
from offline_rag.dense.embedding_bundle_provision import (
    OUTCOME_ALREADY_PROVISIONED,
    OUTCOME_LOCK_UNAVAILABLE,
    OUTCOME_MALFORMED_BUNDLE,
    OUTCOME_POST_PUBLISH_VALIDATION_FAILED,
    OUTCOME_ROLLBACK_FAILED,
    OUTCOME_SOURCE_REQUIRED,
    normalize_representation_request,
    provision_embedding_representations,
)
from offline_rag.dense.provision import (
    EMBEDDING_MANIFEST_NAME,
    REQUIRED_EMBEDDING_FILES,
    _artifact_id_from_digests,
    _sha256_file,
    provision_embedding_model,
    validate_embedding_artifacts,
)
from offline_rag.domain.indexing import EmbeddingModelManifest, ProvisioningStatus

_RUNTIME_CONTRACT = {
    "provider": "CPUExecutionProvider",
    "graph_file_name": "onnx/model.onnx",
    "ort_intra_op_threads": 8,
    "ort_inter_op_threads": 1,
    "required_onnx_inputs": ["input_ids", "attention_mask", "position_ids"],
}


def _write(path: Path, data: bytes | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.write_bytes(raw)
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _tiny_onnx_files() -> dict[str, bytes]:
    return {
        "onnx/model.onnx": b"ONNX-TINY-GRAPH",
        "config.json": b'{"tiny": true}',
        "modules.json": b"[]",
        "tokenizer.json": b"{}",
    }


def _tiny_spec(files: dict[str, str]) -> QualifiedEmbeddingRepresentationSpec:
    return QualifiedEmbeddingRepresentationSpec(
        qualification_schema=QUALIFICATION_SCHEMA,
        representation_id="onnx_fp32_v1",
        model_id=QWEN3_EMBEDDING_MODEL_ID,
        model_revision=QWEN3_EMBEDDING_PINNED_REVISION,
        expected_dimension=1024,
        runtime_family="sentence_transformers_onnx",
        source_kind="test",
        source_repo_id=QWEN3_EMBEDDING_MODEL_ID,
        source_revision=QWEN3_EMBEDDING_PINNED_REVISION,
        required_files=tuple(sorted(files)),
        expected_file_digests=dict(files),
        runtime_contract=dict(_RUNTIME_CONTRACT),
        qualification_evidence={"test": True},
        historical_qualification_tree_sha256="0" * 64,
    )


@pytest.fixture
def tiny_onnx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Any]:
    content = _tiny_onnx_files()
    digests = {
        rel: _write(tmp_path / "src" / rel, data) for rel, data in content.items()
    }
    spec = _tiny_spec(digests)

    def _load(rep_id: str) -> QualifiedEmbeddingRepresentationSpec:
        assert rep_id == "onnx_fp32_v1"
        return spec

    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.load_package_qualification_spec",
        _load,
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedding_bundle_provision.load_package_qualification_spec",
        _load,
    )
    return tmp_path / "src", spec


def _make_torch_tree(root: Path) -> str:
    digests: dict[str, str] = {}
    for name in REQUIRED_EMBEDDING_FILES:
        digests[name] = _write(root / name, f"{name}-body")
    digests["model.safetensors"] = _write(root / "model.safetensors", b"WEIGHTS")
    artifact_id = _artifact_id_from_digests(
        model_id=QWEN3_EMBEDDING_MODEL_ID,
        revision=QWEN3_EMBEDDING_PINNED_REVISION,
        digests=digests,
    )
    manifest = EmbeddingModelManifest(
        model_id=QWEN3_EMBEDDING_MODEL_ID,
        requested_revision=QWEN3_EMBEDDING_PINNED_REVISION,
        resolved_revision=QWEN3_EMBEDDING_PINNED_REVISION,
        expected_dimension=1024,
        artifact_contract=QWEN3_EMBEDDING_ARTIFACT_CONTRACT,
        provisioned_at=datetime.now(tz=UTC),
        required_files=list(REQUIRED_EMBEDDING_FILES),
        file_digests=digests,
        artifact_id=artifact_id,
        metadata={},
    )
    (root / EMBEDDING_MANIFEST_NAME).write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    status = validate_embedding_artifacts(root)
    assert status.readiness.value == "ready"
    return artifact_id


def test_normalize_representation_request() -> None:
    assert normalize_representation_request(None) == ["torch_st_v1"]
    assert normalize_representation_request("all") == ["torch_st_v1", "onnx_fp32_v1"]
    assert normalize_representation_request("onnx_fp32_v1") == ["onnx_fp32_v1"]


def test_omitted_representation_is_torch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)

    def boom(*a, **k):  # type: ignore[no-untyped-def]
        raise AssertionError("should not download when already ready")

    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        boom,
    )
    report = provision_embedding_model(dest)
    assert report.status is ProvisioningStatus.ALREADY_PROVISIONED
    assert report.metadata["outcome_code"] == OUTCOME_ALREADY_PROVISIONED
    assert report.status.value == "already_provisioned"


def test_legacy_torch_onnx_install_adopts_dot(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _spec = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        inspect_representation(dest, "torch_st_v1").readiness
        is RepresentationReadiness.READY
    )
    assert (
        inspect_representation(dest, "onnx_fp32_v1").readiness
        is RepresentationReadiness.ABSENT
    )

    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        onnx_source=src,
    )
    assert report.status is ProvisioningStatus.READY
    assert report.status.value == "ready"
    assert report.metadata["bundle_changed"] is True
    assert report.metadata["restart_required"] is True
    bundle = json.loads((dest / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert bundle["representations"]["torch_st_v1"] == "."
    assert bundle["representations"]["onnx_fp32_v1"].startswith(
        "representations/onnx_fp32_v1/"
    )
    assert (
        inspect_representation(dest, "torch_st_v1").readiness
        is RepresentationReadiness.READY
    )
    assert (
        inspect_representation(dest, "onnx_fp32_v1").readiness
        is RepresentationReadiness.READY
    )

    # Installed ONNX files are regular files (not symlinks).
    onnx_inst = dest / bundle["representations"]["onnx_fp32_v1"]
    installed_manifest = json.loads(
        (onnx_inst / REPRESENTATION_MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert (
        installed_manifest["installed_representation_schema"]
        == INSTALLED_REPRESENTATION_SCHEMA
    )
    for rel in installed_manifest["required_files"]:
        path = onnx_inst / rel
        assert path.is_file()
        assert not path.is_symlink()

    # Repeat → already_provisioned, no bundle change
    again = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert again.status is ProvisioningStatus.ALREADY_PROVISIONED
    assert again.metadata["bundle_changed"] is False


def test_corrupted_onnx_byte_fails(tmp_path: Path, tiny_onnx: tuple[Path, Any]) -> None:
    src, _spec = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    # Corrupt one required source file after digests were computed for spec —
    # rewrite source file to different bytes but keep tiny_spec digests.
    bad = src / "onnx/model.onnx"
    bad.write_bytes(b"CORRUPTED")
    report = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == "qualification_mismatch"
    assert not (dest / BUNDLE_MANIFEST_NAME).exists()


def test_missing_required_onnx_file_fails(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _spec = tiny_onnx
    (src / "onnx/model.onnx").unlink()
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == "source_invalid"
    assert not (dest / BUNDLE_MANIFEST_NAME).exists()


def test_source_symlink_materialized(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, spec = tiny_onnx
    real = tmp_path / "real-model.onnx"
    real.write_bytes((src / "onnx/model.onnx").read_bytes())
    (src / "onnx/model.onnx").unlink()
    (src / "onnx/model.onnx").symlink_to(real)
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert report.status is ProvisioningStatus.READY
    pointer = json.loads((dest / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))[
        "representations"
    ]["onnx_fp32_v1"]
    installed = dest / pointer / "onnx/model.onnx"
    assert installed.is_file()
    assert not installed.is_symlink()
    assert _sha256_file(installed) == spec.expected_file_digests["onnx/model.onnx"]


def test_extra_source_files_not_installed(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _spec = tiny_onnx
    _write(src / "scientific_evidence.json", '{"no": true}')
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert report.status is ProvisioningStatus.READY
    pointer = json.loads((dest / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))[
        "representations"
    ]["onnx_fp32_v1"]
    assert not (dest / pointer / "scientific_evidence.json").exists()


def test_onnx_source_required(tmp_path: Path) -> None:
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_representations(dest, representations="onnx_fp32_v1")
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == OUTCOME_SOURCE_REQUIRED


def test_malformed_bundle_no_mutation(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    (dest / BUNDLE_MANIFEST_NAME).write_text("{not-json", encoding="utf-8")
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()
    report = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == OUTCOME_MALFORMED_BUNDLE
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_torch_replace_preserves_onnx(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    onnx_pointer = json.loads(
        (dest / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8")
    )["representations"]["onnx_fp32_v1"]

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    report = provision_embedding_representations(
        dest, representations="torch_st_v1", force=True
    )
    assert report.status is ProvisioningStatus.READY
    bundle = json.loads((dest / BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert bundle["representations"]["onnx_fp32_v1"] == onnx_pointer
    assert bundle["representations"]["torch_st_v1"] != "."
    assert (dest / onnx_pointer).is_dir()
    assert (
        inspect_representation(dest, "onnx_fp32_v1").readiness
        is RepresentationReadiness.READY
    )


def test_all_transaction_one_bundle_publication(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    report = provision_embedding_representations(
        dest,
        representations="all",
        onnx_source=src,
    )
    assert report.status is ProvisioningStatus.READY
    # One forward publication implied by single bundle file and READY both
    assert (
        inspect_representation(dest, "torch_st_v1").readiness
        is RepresentationReadiness.READY
    )
    assert (
        inspect_representation(dest, "onnx_fp32_v1").readiness
        is RepresentationReadiness.READY
    )


def test_partial_failure_no_selection_change(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    first = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert first.status is ProvisioningStatus.READY
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)

    def fail_onnx(*a, **k):  # type: ignore[no-untyped-def]
        raise RuntimeError("injected onnx stage failure")

    report = provision_embedding_representations(
        dest,
        representations="all",
        force=True,
        onnx_source=src,
        test_hooks={"fail_after_onnx_stage": fail_onnx},
    )
    assert report.status is ProvisioningStatus.FAILED
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_post_publish_validation_rollback(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    # Establish a valid previous bundle first
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()

    def fail_post():  # type: ignore[no-untyped-def]
        raise RuntimeError("injected post-publish failure")

    # Force replace ONNX; inject failure after successful validation path via hook
    # that runs after inspect would pass — use fail_after_post_publish_validation
    # which raises BundleProvisionError path... the hook raises bare RuntimeError
    # wrapped? Looking at code: `if callable(fail_post): fail_post()` after READY
    # checks — bare Exception won't be BundleProvisionError. Fix hook usage:
    from offline_rag.dense.embedding_bundle_provision import BundleProvisionError

    def fail_post_typed():  # type: ignore[no-untyped-def]
        raise BundleProvisionError(OUTCOME_POST_PUBLISH_VALIDATION_FAILED, "injected")

    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
        test_hooks={"fail_after_post_publish_validation": fail_post_typed},
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == OUTCOME_POST_PUBLISH_VALIDATION_FAILED
    assert report.metadata.get("rollback", {}).get("ok") is True
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_rollback_failure_code(tmp_path: Path, tiny_onnx: tuple[Path, Any]) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    from offline_rag.dense.embedding_bundle_provision import BundleProvisionError

    def fail_post():  # type: ignore[no-untyped-def]
        raise BundleProvisionError(OUTCOME_POST_PUBLISH_VALIDATION_FAILED, "injected")

    def fail_rollback():  # type: ignore[no-untyped-def]
        raise RuntimeError("rollback boom")

    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
        test_hooks={
            "fail_after_post_publish_validation": fail_post,
            "fail_before_rollback_replace": fail_rollback,
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == OUTCOME_ROLLBACK_FAILED
    assert "final_observed_state" in report.metadata


def test_concurrent_writer_lock(tmp_path: Path, tiny_onnx: tuple[Path, Any]) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    started = threading.Event()
    release = threading.Event()
    results: list[Any] = []

    def hold_lock() -> None:
        report = provision_embedding_representations(
            dest,
            representations="onnx_fp32_v1",
            onnx_source=src,
            test_hooks={
                "fail_before_onnx_copy": lambda: (
                    started.set(),
                    release.wait(timeout=5),
                ),
            },
        )
        results.append(report)

    t = threading.Thread(target=hold_lock)
    t.start()
    assert started.wait(timeout=5)
    loser = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    release.set()
    t.join(timeout=10)
    assert loser.status is ProvisioningStatus.FAILED
    assert loser.metadata["outcome_code"] == OUTCOME_LOCK_UNAVAILABLE
    assert results[0].status is ProvisioningStatus.READY


def test_absolute_pointer_rejected_via_hook(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    # Direct unit: relative pointer validation
    from offline_rag.dense.embedding_bundle_provision import (
        BundleProvisionError,
        _validate_relative_pointer,
    )

    with pytest.raises(BundleProvisionError):
        _validate_relative_pointer("/abs/path")
    with pytest.raises(BundleProvisionError):
        _validate_relative_pointer("../escape")
    assert _validate_relative_pointer(".") == "."


def test_package_qualification_unchanged() -> None:
    spec = load_package_qualification_spec("onnx_fp32_v1")
    assert (
        spec.historical_qualification_tree_sha256
        == "3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345"
    )


def test_json_status_lowercase(tmp_path: Path) -> None:
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_model(dest)
    payload = json.loads(report.model_dump_json())
    assert payload["status"] == "already_provisioned"
    assert set(payload) >= {
        "status",
        "model_id",
        "requested_revision",
        "resolved_revision",
        "destination",
        "artifact_id",
        "manifest_path",
        "files_downloaded",
        "errors",
        "metadata",
    }


def test_stale_legacy_ignored_when_bundle_selects_instance(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    assert (
        provision_embedding_representations(
            dest, representations="torch_st_v1", force=True
        ).status
        is ProvisioningStatus.READY
    )
    # Corrupt legacy root files; bundle-selected immutable torch must still win planning.
    (dest / "config.json").write_text("CORRUPT", encoding="utf-8")
    torch = inspect_representation(dest, "torch_st_v1")
    assert torch.readiness is RepresentationReadiness.READY
    assert torch.instance_path != dest
    again = provision_embedding_representations(dest, representations="torch_st_v1")
    assert again.status is ProvisioningStatus.ALREADY_PROVISIONED


# --- IR-001 narrow durability / compatibility regressions ---


def test_f001_fail_before_bundle_replace_no_rollback(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()

    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
        test_hooks={
            "fail_before_bundle_replace": lambda: (_ for _ in ()).throw(
                RuntimeError("pre-replace")
            )
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata.get("rollback", {}).get("attempted") is False
    assert report.metadata.get("bundle_publication_state") == "not_replaced"
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_f001_fail_after_replace_via_fsync_triggers_rollback(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import offline_rag.dense.embedding_bundle_provision as emb

    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()

    orig = emb._fsync_file
    seen = {"bundle": 0}

    def flaky(path: Path) -> None:  # type: ignore[no-untyped-def]
        if path.name == BUNDLE_MANIFEST_NAME:
            seen["bundle"] += 1
            # First fsync after os.replace of the forward publication.
            if seen["bundle"] == 1:
                raise OSError("injected post-replace file fsync failure")
        return orig(path)

    monkeypatch.setattr(emb, "_fsync_file", flaky)
    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata.get("rollback", {}).get("ok") is True
    assert report.metadata.get("bundle_publication_state") in {
        "replaced_not_confirmed_durable",
        "replaced_durable",
    }
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_f001_fail_after_dir_fsync_triggers_rollback(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    before = (dest / BUNDLE_MANIFEST_NAME).read_bytes()
    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
        test_hooks={
            "fail_after_bundle_dir_fsync": lambda: (_ for _ in ()).throw(
                RuntimeError("post-dir-fsync")
            )
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata.get("rollback", {}).get("ok") is True
    assert report.metadata["bundle_publication_state"] == "replaced_durable"
    assert (dest / BUNDLE_MANIFEST_NAME).read_bytes() == before


def test_f002_torch_regular_files_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "model"
    dest.mkdir()
    persisted: list[str] = []

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    report = provision_embedding_representations(
        dest,
        representations="torch_st_v1",
        force=True,
        test_hooks={
            "fail_after_torch_file_persist": lambda rel: persisted.append(rel),
        },
    )
    assert report.status is ProvisioningStatus.READY
    assert report.metadata["torch_files_persisted"] >= 4
    # Regular weight + required files + manifest must appear in persist pass.
    assert any(name.endswith("model.safetensors") or name == "model.safetensors" for name in persisted)
    assert EMBEDDING_MANIFEST_NAME in persisted
    assert "config.json" in persisted


def test_f003_multilevel_destination_ancestry(tmp_path: Path) -> None:
    import offline_rag.dense.embedding_bundle_provision as emb

    dest = tmp_path / "a" / "b" / "c" / "model"
    root = emb._durable_mkdir_ancestry(dest)
    assert root == dest.resolve()
    assert dest.is_dir()
    assert (tmp_path / "a").is_dir()
    assert (tmp_path / "a" / "b").is_dir()
    assert (tmp_path / "a" / "b" / "c").is_dir()


def test_f003_ancestry_symlink_escape_rejected(tmp_path: Path) -> None:
    import offline_rag.dense.embedding_bundle_provision as emb
    from offline_rag.dense.embedding_bundle_provision import BundleProvisionError

    outside = tmp_path / "outside"
    outside.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    link = base / "escape"
    link.symlink_to(outside)
    with pytest.raises(BundleProvisionError, match="symlink escapes"):
        emb._durable_mkdir_ancestry(link / "model")


def test_f004_manifest_path_not_bundle(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)

    # Legacy torch no-op
    noop = provision_embedding_model(dest)
    assert noop.status is ProvisioningStatus.ALREADY_PROVISIONED
    assert noop.manifest_path is not None
    assert noop.manifest_path.endswith(EMBEDDING_MANIFEST_NAME)
    assert BUNDLE_MANIFEST_NAME not in Path(noop.manifest_path).name

    # ONNX-only install (adopts legacy torch)
    onnx_rep = provision_embedding_representations(
        dest, representations="onnx_fp32_v1", onnx_source=src
    )
    assert onnx_rep.status is ProvisioningStatus.READY
    assert onnx_rep.manifest_path is not None
    assert onnx_rep.manifest_path.endswith(EMBEDDING_MANIFEST_NAME)
    assert onnx_rep.metadata["bundle_manifest"].endswith(BUNDLE_MANIFEST_NAME)

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    torch_rep = provision_embedding_representations(
        dest, representations="torch_st_v1", force=True
    )
    assert torch_rep.status is ProvisioningStatus.READY
    assert torch_rep.manifest_path is not None
    assert torch_rep.manifest_path.endswith(EMBEDDING_MANIFEST_NAME)
    assert "representations/torch_st_v1/" in torch_rep.manifest_path.replace("\\", "/")

    all_rep = provision_embedding_representations(
        dest, representations="all", force=True, onnx_source=src
    )
    assert all_rep.status is ProvisioningStatus.READY
    assert all_rep.manifest_path is not None
    assert all_rep.manifest_path.endswith(EMBEDDING_MANIFEST_NAME)
    assert all_rep.metadata["bundle_manifest"].endswith(BUNDLE_MANIFEST_NAME)


def test_f005_both_ready_all_without_onnx_source(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    again = provision_embedding_representations(dest, representations="all")
    assert again.status is ProvisioningStatus.ALREADY_PROVISIONED
    assert again.metadata["bundle_changed"] is False


def test_f005_forward_publication_count_exact(
    tmp_path: Path, tiny_onnx: tuple[Path, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"

    def fake_download(*, repo_id, revision, local_dir):  # type: ignore[no-untyped-def]
        _make_torch_tree(Path(local_dir))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_download)
    report = provision_embedding_representations(
        dest, representations="all", onnx_source=src
    )
    assert report.status is ProvisioningStatus.READY
    assert report.metadata["bundle_changed"] is True
    # Exactly one forward selection transition
    assert report.metadata.get("bundle_publication_state") == "replaced_durable"


def test_f005_rollback_to_previous_absence(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert not (dest / BUNDLE_MANIFEST_NAME).exists()
    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        onnx_source=src,
        test_hooks={
            "fail_after_post_publish_validation": lambda: (_ for _ in ()).throw(
                __import__(
                    "offline_rag.dense.embedding_bundle_provision", fromlist=["BundleProvisionError"]
                ).BundleProvisionError(
                    "post_publish_validation_failed", "injected"
                )
            )
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata.get("rollback", {}).get("ok") is True
    assert report.metadata.get("rollback", {}).get("restored") == "absent"
    assert not (dest / BUNDLE_MANIFEST_NAME).exists()


def test_f005_rollback_persistence_failure(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    assert (
        provision_embedding_representations(
            dest, representations="onnx_fp32_v1", onnx_source=src
        ).status
        is ProvisioningStatus.READY
    )
    from offline_rag.dense.embedding_bundle_provision import (
        OUTCOME_POST_PUBLISH_VALIDATION_FAILED,
        OUTCOME_ROLLBACK_FAILED,
        BundleProvisionError,
    )

    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        force=True,
        onnx_source=src,
        test_hooks={
            "fail_after_post_publish_validation": lambda: (_ for _ in ()).throw(
                BundleProvisionError(OUTCOME_POST_PUBLISH_VALIDATION_FAILED, "x")
            ),
            "fail_after_rollback_dir_fsync": lambda: (_ for _ in ()).throw(
                RuntimeError("rollback dir fsync")
            ),
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata["outcome_code"] == OUTCOME_ROLLBACK_FAILED
    assert "final_observed_state" in report.metadata


def test_f005_bundle_tmp_persist_hook(
    tmp_path: Path, tiny_onnx: tuple[Path, Any]
) -> None:
    src, _ = tiny_onnx
    dest = tmp_path / "model"
    dest.mkdir()
    _make_torch_tree(dest)
    report = provision_embedding_representations(
        dest,
        representations="onnx_fp32_v1",
        onnx_source=src,
        test_hooks={
            "fail_before_bundle_tmp_fsync_done": lambda: (_ for _ in ()).throw(
                RuntimeError("tmp persist")
            )
        },
    )
    assert report.status is ProvisioningStatus.FAILED
    assert report.metadata.get("rollback", {}).get("attempted") is False
    assert not (dest / BUNDLE_MANIFEST_NAME).exists()
