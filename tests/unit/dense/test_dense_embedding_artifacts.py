"""P1 Round-11 artifact / qualification trust tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from offline_rag.dense.embedding_artifacts import (
    BUNDLE_MANIFEST_NAME,
    BUNDLE_SCHEMA,
    INSTALLED_REPRESENTATION_SCHEMA,
    QUALIFICATION_SCHEMA,
    REPRESENTATION_MANIFEST_NAME,
    QualifiedEmbeddingRepresentationSpec,
    RepresentationReadiness,
    RepresentationReasonCode,
    inspect_representation,
    load_package_qualification_spec,
    parse_bundle_manifest,
    sha256_file,
)
from offline_rag.dense.provision import EMBEDDING_MANIFEST_NAME


def _write(path: Path, data: bytes | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _tiny_spec(files: dict[str, str]) -> QualifiedEmbeddingRepresentationSpec:
    return QualifiedEmbeddingRepresentationSpec(
        qualification_schema=QUALIFICATION_SCHEMA,
        representation_id="onnx_fp32_v1",
        model_id="Qwen/Qwen3-Embedding-0.6B",
        model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        expected_dimension=1024,
        runtime_family="sentence_transformers_onnx",
        source_kind="test",
        source_repo_id="Qwen/Qwen3-Embedding-0.6B",
        source_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        required_files=tuple(sorted(files)),
        expected_file_digests=dict(files),
        runtime_contract={
            "provider": "CPUExecutionProvider",
            "graph_file_name": "onnx/model.onnx",
            "ort_intra_op_threads": 8,
            "ort_inter_op_threads": 1,
        },
        qualification_evidence={"test": True},
        historical_qualification_tree_sha256=None,
    )


def test_package_owned_onnx_spec_parses() -> None:
    spec = load_package_qualification_spec("onnx_fp32_v1")
    assert spec.representation_id == "onnx_fp32_v1"
    assert spec.qualification_schema == QUALIFICATION_SCHEMA
    assert "onnx/model.onnx" in spec.expected_file_digests
    assert (
        spec.expected_file_digests["onnx/model.onnx"]
        == "6135c5388da771b2072db0698a4ff558f78f4479ab8160721d43c077767707e9"
    )
    assert (
        spec.expected_file_digests["onnx/model.onnx_data"]
        == "a585477de21c0a89e021dd64f4d3be34483eb4aaed7ae93fc047e3edf74545da"
    )
    assert (
        spec.historical_qualification_tree_sha256
        == "3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345"
    )
    assert len(spec.required_files) >= 10


def test_legacy_torch_ready_onnx_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "qwen"
    root.mkdir()
    # Minimal fake legacy validation via monkeypatch
    from offline_rag.dense import embedding_artifacts as art
    from offline_rag.dense.provision import EmbeddingArtifactStatus, EmbeddingReadiness

    def fake_validate(model_dir, **kwargs):  # type: ignore[no-untyped-def]
        return EmbeddingArtifactStatus(
            Path(model_dir), EmbeddingReadiness.READY, "ok", manifest=None
        )

    monkeypatch.setattr(art, "validate_embedding_artifacts", fake_validate)
    (root / EMBEDDING_MANIFEST_NAME).write_text("{}", encoding="utf-8")
    torch = inspect_representation(root, "torch_st_v1")
    onnx = inspect_representation(root, "onnx_fp32_v1")
    assert torch.readiness == RepresentationReadiness.READY
    assert torch.reason_code == RepresentationReasonCode.LEGACY_TORCH_READY
    assert onnx.readiness == RepresentationReadiness.ABSENT
    assert onnx.reason_code == RepresentationReasonCode.LEGACY_ONNX_ABSENT


def test_bundle_pointer_selects_instance_and_ignores_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "qwen"
    good = root / "representations" / "onnx_fp32_v1" / "inst-good"
    orphan = root / "representations" / "onnx_fp32_v1" / "inst-orphan"
    files = {
        "onnx/model.onnx": _write(good / "onnx/model.onnx", b"graph-bytes"),
        "config.json": _write(good / "config.json", b"{}"),
    }
    _write(orphan / "onnx/model.onnx", b"orphan-graph")
    _write(orphan / "config.json", b"{}")
    (root / BUNDLE_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "bundle_schema": BUNDLE_SCHEMA,
                "representations": {
                    "onnx_fp32_v1": "representations/onnx_fp32_v1/inst-good"
                },
            }
        ),
        encoding="utf-8",
    )
    (good / REPRESENTATION_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "installed_representation_schema": INSTALLED_REPRESENTATION_SCHEMA,
                "representation_id": "onnx_fp32_v1",
                "model_id": "Qwen/Qwen3-Embedding-0.6B",
                "model_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
                "runtime_family": "sentence_transformers_onnx",
                "file_digests": files,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.load_package_qualification_spec",
        lambda _rid: _tiny_spec(files),
    )
    result = inspect_representation(root, "onnx_fp32_v1")
    assert result.readiness == RepresentationReadiness.READY
    assert result.instance_path == good.resolve()
    assert orphan.exists()  # orphan remains on disk but unused


def test_qualification_mismatch_and_digest_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "qwen"
    inst = root / "representations" / "onnx_fp32_v1" / "inst"
    digest = _write(inst / "onnx/model.onnx", b"graph")
    _write(inst / "config.json", b"{}")
    files = {
        "onnx/model.onnx": digest,
        "config.json": sha256_file(inst / "config.json"),
    }
    (root / BUNDLE_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "bundle_schema": BUNDLE_SCHEMA,
                "representations": {"onnx_fp32_v1": str(inst.relative_to(root))},
            }
        ),
        encoding="utf-8",
    )
    (inst / REPRESENTATION_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "installed_representation_schema": INSTALLED_REPRESENTATION_SCHEMA,
                "representation_id": "onnx_fp32_v1",
                "model_id": "Qwen/Qwen3-Embedding-0.6B",
                "model_revision": "wrong-revision",
                "runtime_family": "sentence_transformers_onnx",
                "file_digests": files,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.load_package_qualification_spec",
        lambda _rid: _tiny_spec(files),
    )
    bad_rev = inspect_representation(root, "onnx_fp32_v1")
    assert bad_rev.readiness == RepresentationReadiness.INVALID
    assert bad_rev.reason_code == RepresentationReasonCode.QUALIFICATION_MISMATCH

    # Fix revision; break local digest vs package authority
    (inst / REPRESENTATION_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "installed_representation_schema": INSTALLED_REPRESENTATION_SCHEMA,
                "representation_id": "onnx_fp32_v1",
                "model_id": "Qwen/Qwen3-Embedding-0.6B",
                "model_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
                "runtime_family": "sentence_transformers_onnx",
                "file_digests": files,
            }
        ),
        encoding="utf-8",
    )
    wrong = dict(files)
    wrong["onnx/model.onnx"] = "0" * 64
    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.load_package_qualification_spec",
        lambda _rid: _tiny_spec(wrong),
    )
    bad_digest = inspect_representation(root, "onnx_fp32_v1")
    assert bad_digest.readiness == RepresentationReadiness.INVALID
    assert bad_digest.reason_code == RepresentationReasonCode.DIGEST_MISMATCH


def test_installed_manifest_cannot_self_authorize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "qwen"
    inst = root / "representations" / "onnx_fp32_v1" / "inst"
    digest = _write(inst / "onnx/model.onnx", b"graph")
    cfg = _write(inst / "config.json", b"{}")
    extra = _write(inst / "evil.bin", b"nope")
    files = {"onnx/model.onnx": digest, "config.json": cfg}
    (root / BUNDLE_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "bundle_schema": BUNDLE_SCHEMA,
                "representations": {"onnx_fp32_v1": str(inst.relative_to(root))},
            }
        ),
        encoding="utf-8",
    )
    (inst / REPRESENTATION_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "installed_representation_schema": INSTALLED_REPRESENTATION_SCHEMA,
                "representation_id": "onnx_fp32_v1",
                "model_id": "Qwen/Qwen3-Embedding-0.6B",
                "model_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
                "runtime_family": "sentence_transformers_onnx",
                "file_digests": {**files, "evil.bin": extra},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedding_artifacts.load_package_qualification_spec",
        lambda _rid: _tiny_spec(files),
    )
    result = inspect_representation(root, "onnx_fp32_v1")
    assert result.readiness == RepresentationReadiness.INVALID
    assert result.reason_code == RepresentationReasonCode.INSTALLED_DIGEST_DISAGREES


def test_parse_bundle_manifest() -> None:
    pointers = parse_bundle_manifest(
        {
            "bundle_schema": BUNDLE_SCHEMA,
            "representations": {
                "onnx_fp32_v1": {"path": "representations/onnx_fp32_v1/a"}
            },
        }
    )
    assert pointers["onnx_fp32_v1"] == "representations/onnx_fp32_v1/a"


def test_inspector_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "qwen"
    root.mkdir()
    before = {p.relative_to(root) for p in root.rglob("*")}
    inspect_representation(root, "onnx_fp32_v1")
    after = {p.relative_to(root) for p in root.rglob("*")}
    assert before == after
