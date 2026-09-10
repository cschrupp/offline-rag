"""CLI chunk command tests."""

from __future__ import annotations

import json
from pathlib import Path

from offline_rag.cli import main
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest


def _prepare_workspace(tmp_path: Path) -> Path:
    for name in (
        "data/processed",
        "data/manifests",
        "data/corpora",
        "data/chunks",
        "data/chunk-manifests",
        "data/raw",
        "data/qdrant",
        "eval/results",
        "models",
        "models/docling",
        "models/tokenizers/tiktoken",
    ):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "models" / "docling" / "placeholder.bin").write_bytes(b"x")
    write_provisioning_manifest(tmp_path / "models" / "docling", docling_version="test")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("alpha beta gamma delta epsilon\n", encoding="utf-8")
    return docs


def test_chunk_json_and_inspect(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    docs = _prepare_workspace(tmp_path)
    # Use fake tokenizer via env-less overrides: write a local config overlay.
    cfg = tmp_path / "chunk.yaml"
    cfg.write_text(
        "project:\n  strict_offline: false\n"
        "chunking:\n  tokenizer:\n    implementation: fake\n",
        encoding="utf-8",
    )
    assert main(["ingest", str(docs), "--corpus", "cli", "--config", str(cfg)]) == 0
    capsys.readouterr()
    code = main(["chunk", "--corpus", "cli", "--json", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert code == 0
    report = json.loads(out.strip().splitlines()[-1])
    assert report["status"] in {"success", "no_op"}
    assert report["documents_total"] == 1
    document_id = report["documents"][0]["document_id"]
    chunk_artifact_id = report["documents"][0]["chunk_artifact_id"]
    assert chunk_artifact_id

    # Load a child id from artifact for inspect.
    from offline_rag.chunking.persistence import load_chunk_artifact

    artifact = load_chunk_artifact(tmp_path / "data" / "chunks" / f"{chunk_artifact_id}.json")
    child_id = artifact.children[0].chunk_id
    assert main(["chunk", "inspect", "--corpus", "cli", "--chunk", child_id, "--config", str(cfg)]) == 0
    inspect_out = capsys.readouterr().out
    assert child_id in inspect_out
    assert "source_block_ids" in inspect_out

    assert (
        main(["chunk", "inspect", "--corpus", "cli", "--document", document_id, "--config", str(cfg)])
        == 0
    )
    doc_out = capsys.readouterr().out
    assert document_id in doc_out
    assert "ordered children" in doc_out

    # Identical rerun should reuse.
    code = main(["chunk", "--corpus", "cli", "--json", "--config", str(cfg)])
    report2 = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert code == 0
    assert report2["status"] == "no_op"
    assert report2["documents_reused"] == 1
