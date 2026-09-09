"""Docling artifact validation unit tests (no models required)."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.config import load_settings
from offline_rag.ingestion.docling_artifacts import (
    DoclingArtifactsUnavailableError,
    require_docling_artifacts,
    validate_docling_artifacts,
    write_provisioning_manifest,
)


def test_default_and_env_docling_path(tmp_path: Path) -> None:
    settings = load_settings(yaml_paths=[], environ={})
    assert settings.paths.docling_artifacts == Path("models/docling")
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_DOCLING_ARTIFACTS_PATH": str(tmp_path / "artifacts")},
    )
    assert settings.paths.docling_artifacts == tmp_path / "artifacts"


def test_artifact_validation_states(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    status = validate_docling_artifacts(missing)
    assert status.ready is False
    assert "missing" in status.reason

    empty = tmp_path / "empty"
    empty.mkdir()
    assert validate_docling_artifacts(empty).ready is False

    no_manifest = tmp_path / "no_manifest"
    no_manifest.mkdir()
    (no_manifest / "placeholder.bin").write_bytes(b"x")
    assert "manifest" in validate_docling_artifacts(no_manifest).reason

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "offline-rag-artifacts.json").write_text("{", encoding="utf-8")
    assert "malformed" in validate_docling_artifacts(bad).reason

    good = tmp_path / "good"
    good.mkdir()
    (good / "weights.bin").write_bytes(b"abc")
    write_provisioning_manifest(good, docling_version="test")
    status = validate_docling_artifacts(good)
    assert status.ready is True

    with pytest.raises(DoclingArtifactsUnavailableError) as exc:
        require_docling_artifacts(missing)
    message = str(exc.value)
    assert "Resolved path" in message
    assert "Runtime downloading is intentionally disabled" in message
    assert "provision_docling.py" in message


def test_ocr_setting_changes_parse_config_hash() -> None:
    from offline_rag.core.ids import parse_config_hash

    off = parse_config_hash(parser_name="docling_pdf", parser_version="v1", ocr_enabled=False)
    on = parse_config_hash(parser_name="docling_pdf", parser_version="v1", ocr_enabled=True)
    assert off != on
