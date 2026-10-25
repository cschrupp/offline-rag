"""L3 parser and ingestion identity path-contract checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from offline_rag.app.ingest import _validate_document_identities
from offline_rag.app.ingest_upload import SpooledIngestUpload, SpooledUploadFile
from offline_rag.config import load_settings
from offline_rag.core.ids import document_id_from_bytes
from offline_rag.domain.ingestion import IngestionStatus
from offline_rag.ingestion import pipeline


def _upload(path: Path, document_id: str) -> SpooledIngestUpload:
    return SpooledIngestUpload(
        upload_id="l3",
        corpus_name="docs",
        staging_root=path.parent,
        files_root=path.parent,
        files=[
            SpooledUploadFile(
                absolute_path=path,
                storage_name=path.name,
                client_filename=path.name,
                source_name=path.name,
                document_id=document_id,
                size_bytes=path.stat().st_size,
                media_type="text/plain",
            )
        ],
    )


def test_product_identity_validation_uses_spooled_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"spooled identity"
    path = tmp_path / "doc.txt"
    path.write_bytes(payload)
    document_id = document_id_from_bytes(payload)

    def fail_read_bytes(_path: Path) -> bytes:
        raise AssertionError("product validation must not reread the source")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    identities = _validate_document_identities(_upload(path, document_id))
    assert identities[path.name].document_id == document_id
    assert identities[path.name].content_hash == hashlib.sha256(payload).hexdigest()


def test_trusted_pipeline_identity_skips_path_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.txt"
    payload = b"trusted pipeline identity\n"
    source.write_bytes(payload)
    settings = load_settings(yaml_paths=[], environ={}).model_copy(
        update={
            "paths": load_settings(yaml_paths=[], environ={}).paths.model_copy(
                update={
                    "processed": tmp_path / "processed",
                    "manifests": tmp_path / "manifests",
                    "corpora": tmp_path / "corpora",
                }
            )
        }
    )
    digest = hashlib.sha256(payload).hexdigest()

    def fail_hash(_path: Path) -> str:
        raise AssertionError("trusted identity must not rehash the path")

    monkeypatch.setattr(pipeline, "content_hash_from_path", fail_hash)
    report = pipeline.run_ingestion(
        settings=settings,
        inputs=[source],
        corpus_name="docs",
        trusted_identities={
            source.name: pipeline.SourceIdentity(
                document_id=f"doc_{digest}", content_hash=digest
            )
        },
    )
    assert report.status == IngestionStatus.SUCCESS
    assert report.files_parsed == 1
    assert report.files[0].document_id == f"doc_{digest}"


@pytest.mark.parametrize(
    ("document_id", "content_hash"),
    [
        ("doc_" + "a" * 64, "b" * 64),
        ("doc_" + "a" * 63 + "G", "a" * 64),
    ],
)
def test_trusted_identity_inconsistency_fails_closed(
    tmp_path: Path, document_id: str, content_hash: str
) -> None:
    source = tmp_path / "source.txt"
    source.write_text("trusted identity failure\n", encoding="utf-8")
    settings = load_settings(yaml_paths=[], environ={}).model_copy(
        update={
            "paths": load_settings(yaml_paths=[], environ={}).paths.model_copy(
                update={
                    "processed": tmp_path / "processed",
                    "manifests": tmp_path / "manifests",
                    "corpora": tmp_path / "corpora",
                }
            )
        }
    )
    report = pipeline.run_ingestion(
        settings=settings,
        inputs=[source],
        corpus_name="docs",
        trusted_identities={
            source.name: pipeline.SourceIdentity(
                document_id=document_id, content_hash=content_hash
            )
        },
    )
    assert report.status == IngestionStatus.FAILED
    assert report.metadata["failure_class"] == "internal"
    assert not (tmp_path / "corpora" / "docs" / "state.json").exists()
