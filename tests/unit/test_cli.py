"""CLI shell tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.cli import NOT_IMPLEMENTED_EXIT, main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("argv", "label"),
    [
        (["ingest", "--help"], "ingest"),
        (["chunk", "--help"], "chunk"),
        (["chunk", "inspect", "--help"], "chunk inspect"),
        (["provision", "embedding", "--help"], "provision embedding"),
        (["index", "--help"], "index"),
        (["index", "inspect", "--help"], "index inspect"),
        (["retrieve", "--help"], "retrieve"),
        (["query", "--help"], "query"),
        (["eval", "run", "--help"], "eval run"),
        (["eval", "compare", "--help"], "eval compare"),
        (["eval", "retrieve", "--help"], "eval retrieve"),
        (["doctor", "--help"], "doctor"),
    ],
)
def test_subcommand_help(argv: list[str], label: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 0, label


@pytest.mark.parametrize(
    "argv",
    [
        ["query"],
        ["eval", "run"],
        ["eval", "compare"],
    ],
)
def test_placeholders_terminate_cleanly(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv)
    assert code == NOT_IMPLEMENTED_EXIT
    err = capsys.readouterr().err
    assert "not implemented" in err
    if argv == ["query"]:
        assert "retrieve" in err


def test_doctor_ok_with_base_config(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    # Doctor may FAIL if Docling/tokenizer/embedding artifacts are missing under strict offline.
    artifacts = REPO_ROOT / "models" / "docling"
    from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

    if not (artifacts / "offline-rag-artifacts.json").exists():
        (artifacts / "placeholder.bin").write_bytes(b"unit")
        write_provisioning_manifest(artifacts, docling_version="test")
    tok = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
    if not (tok / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    from offline_rag.dense.provision import (
        EmbeddingReadiness,
        validate_embedding_artifacts,
    )

    emb = REPO_ROOT / "models" / "embeddings" / "qwen3-embedding-0.6b"
    emb_status = validate_embedding_artifacts(emb)
    if emb_status.readiness != EmbeddingReadiness.READY:
        pytest.skip("embedding artifacts not provisioned")
    code = main(["doctor", "--config", str(REPO_ROOT / "config" / "base.yaml")])
    captured = capsys.readouterr()
    assert code == 0
    assert "doctor: OK" in captured.out
    assert "Tokenizer artifacts" in captured.out
    assert "Embedding model artifacts" in captured.out
    assert "Indexing status" in captured.out


def test_ingest_json_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("hello\n\nworld\n", encoding="utf-8")
    # Minimal config via env overrides using default settings and local paths.
    # Create required sibling dirs used by doctor/ingest defaults when resolving relative paths.
    for name in ("data/processed", "data/manifests", "data/corpora", "models/docling", "data/raw", "data/qdrant", "eval/results", "models"):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest

    (tmp_path / "models" / "docling" / "placeholder.bin").write_bytes(b"x")
    write_provisioning_manifest(tmp_path / "models" / "docling", docling_version="test")

    code = main(["ingest", str(docs), "--json", "--corpus", "default"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"status":' in out
    assert "corpus_" in out
