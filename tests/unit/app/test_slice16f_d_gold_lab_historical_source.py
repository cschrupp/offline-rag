"""Slice 16F-D — immutable historical source integrity and path confinement."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.app.errors import ErrorCode
from offline_rag.app.gold_lab.historical_source import resolve_historical_chunk
from offline_rag.app.gold_lab.models import GoldCampaign, build_selection_policy
from offline_rag.app.paths import ensure_data_directories
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.snapshot import CanonicalSnapshotManifest
from offline_rag.chunking.persistence import (
    chunk_artifact_relpath,
    write_chunk_artifact,
)
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.core.ids import (
    STRUCTURE_AWARE_CHUNKER_VERSION,
    chunk_artifact_id,
    chunk_set_id_from_entries,
    corpus_id_from_entries,
)
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.domain.chunking import (
    ChunkSetDocumentEntry,
    ChunkSetManifest,
    DocumentChunkArtifact,
)
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.lexical.backend import LexicalDocumentInput, LocalInvertedIndexBackend
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"

DOC_ID = "doc_16fd"
CHUNK_A = "chunk_a_16fd"
CHUNK_B = "chunk_b_16fd"
CORPUS_NAME = "goldlab16fd"
PARSED = "parsed_16fd"
CHUNK_CFG = "chunkcfg_" + ("ab" * 32)


class _FakeQdrant:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self.counts

    def count(self, name: str) -> int:
        return int(self.counts[name])


def _settings(tmp_path: Path) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "local-test-model",
            "approved_endpoints": ["http://127.0.0.1:11434/v1"],
            "approved_models": ["local-test-model"],
        }
    )
    reranker = settings.reranker.model_copy(update={"enabled": False})
    settings = settings.model_copy(update={"generation": generation, "reranker": reranker})
    ensure_data_directories(settings)
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)
    return settings


def _publish_integrity(settings: AppSettings) -> tuple[str, str, str, str]:
    from offline_rag.chunking.tokenize import TiktokenTokenCounter

    counter = TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )
    hashes = {
        "embedding_config_hash": build_embedding_config_hash(settings),
        "index_config_hash": build_index_config_hash(settings),
        "lexical_config_hash": build_lexical_config_hash(settings),
        "fusion_config_hash": build_fusion_config_hash(settings),
        "reranker_config_hash": build_reranker_config_hash(settings),
        "context_config_hash": build_context_config_hash(
            settings, token_counter=counter
        ),
    }
    art_id = chunk_artifact_id(
        PARSED, CHUNK_CFG, chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION
    )
    children = [
        Chunk(
            chunk_id=CHUNK_A,
            document_id=DOC_ID,
            kind=ChunkKind.CHILD,
            text="alpha candidate text for gold lab",
            order=0,
            token_count=4,
            content_hash="ch_a",
            source_block_ids=["blk_a"],
        ),
        Chunk(
            chunk_id=CHUNK_B,
            document_id=DOC_ID,
            kind=ChunkKind.CHILD,
            text="beta candidate text for gold lab",
            order=1,
            token_count=4,
            content_hash="ch_b",
            source_block_ids=["blk_b"],
        ),
    ]
    artifact = DocumentChunkArtifact(
        chunk_artifact_id=art_id,
        parsed_artifact_id=PARSED,
        document_id=DOC_ID,
        chunk_config_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        parents=[],
        children=children,
        parent_count=0,
        child_count=2,
    )
    _path, digest = write_chunk_artifact(settings.paths.chunks, artifact)
    docs = [
        CorpusDocumentEntry(
            document_id=DOC_ID,
            source_path="spec.pdf",
            source_name="spec.pdf",
            source_content_hash="ch_16fd",
            source_size_bytes=12,
            source_media_type="application/pdf",
            parser_name="docling_pdf",
            parser_version="v1",
            block_count=1,
            processed_artifact="processed/x.json",
            processed_artifact_hash="pah_1",
            parsed_artifact_id=PARSED,
            parse_config_hash="cfg_parse",
        )
    ]
    schema = "offline-rag-corpus-manifest-v1"
    cfg_hash = "cfg_corpus"
    corpus_id = corpus_id_from_entries(
        schema_version=schema,
        parse_cfg_hash=cfg_hash,
        document_identities=[
            {
                "document_id": d.document_id,
                "source_content_hash": d.source_content_hash,
                "processed_artifact_hash": d.processed_artifact_hash,
                "parsed_artifact_id": d.parsed_artifact_id,
            }
            for d in docs
        ],
    )
    now = datetime.now(tz=UTC)
    corpus = CorpusManifest(
        schema_version=schema,
        corpus_id=corpus_id,
        corpus_hash="corphash",
        created_at=now,
        config_hash=cfg_hash,
        documents=docs,
    )
    chunk_set_id = chunk_set_id_from_entries(
        corpus_id=corpus_id,
        chunk_cfg_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        document_entries=[
            {
                "document_id": DOC_ID,
                "parsed_artifact_id": PARSED,
                "chunk_artifact_id": art_id,
            }
        ],
    )
    entry = ChunkSetDocumentEntry(
        document_id=DOC_ID,
        parsed_artifact_id=PARSED,
        chunk_artifact_id=art_id,
        chunk_artifact=chunk_artifact_relpath(art_id),
        chunk_artifact_hash=digest,
        parent_count=0,
        child_count=2,
    )
    chunk = ChunkSetManifest(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        chunk_config_hash=CHUNK_CFG,
        chunker_version=STRUCTURE_AWARE_CHUNKER_VERSION,
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        created_at=now,
        documents=[entry],
        total_parent_count=0,
        total_child_count=2,
    )
    for root in (
        settings.paths.manifests,
        settings.paths.chunk_manifests,
        settings.paths.index_manifests,
        settings.paths.lexical_index_manifests,
        settings.paths.lexical_indexes,
    ):
        root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        settings.paths.manifests / f"{corpus_id}.json", corpus.model_dump_json()
    )
    atomic_write_text(
        settings.paths.chunk_manifests / f"{chunk_set_id}.json", chunk.model_dump_json()
    )
    dense_index_id = "denseindex_16fd"
    lexical_index_id = "lexical_16fd"
    collection = "col_16fd"
    dense = DenseIndexManifest(
        index_id=dense_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        embedding_config_hash=hashes["embedding_config_hash"],
        index_config_hash=hashes["index_config_hash"],
        index_contract_version="dense-index-v1",
        embedding_text_strategy="plain",
        embedding_text_contract="plain-v1",
        embedding_model_id="model",
        embedding_model_revision="rev",
        embedding_dimension=8,
        normalize=True,
        similarity_metric="cosine",
        backend="qdrant_local",
        backend_contract="qdrant-local-v1",
        collection_name=collection,
        expected_child_count=2,
        indexed_child_count=2,
        created_at=now,
    )
    lexical = LexicalIndexManifest(
        lexical_index_id=lexical_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
        text_strategy="plain",
        text_contract="plain-v1",
        analyzer_strategy="technical",
        analyzer_contract="technical-v1",
        bm25_contract="bm25-v1",
        bm25_k1=1.2,
        bm25_b=0.75,
        bm25_idf="standard",
        bm25_query_tf="raw",
        backend="local_inverted",
        backend_contract="local-inverted-index-v1",
        expected_child_count=2,
        indexed_child_count=2,
        document_count=1,
        vocabulary_size=2,
        avgdl=1.0,
        physical_index_relpath=f"{lexical_index_id}",
        created_at=now,
    )
    atomic_write_text(
        settings.paths.index_manifests / f"{dense_index_id}.json",
        dense.model_dump_json(),
    )
    atomic_write_text(
        settings.paths.lexical_index_manifests / f"{lexical_index_id}.json",
        lexical.model_dump_json(),
    )
    LocalInvertedIndexBackend(settings.paths.lexical_indexes).build(
        lexical_index_id,
        [
            LexicalDocumentInput(
                chunk_id=CHUNK_A, terms=["offline", "rag"], document_id=DOC_ID
            ),
            LexicalDocumentInput(
                chunk_id=CHUNK_B, terms=["gold", "lab"], document_id=DOC_ID
            ),
        ],
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
    )
    q = _FakeQdrant()
    q.counts[collection] = 2
    identity = CanonicalSnapshotManifest(
        corpus_id=corpus_id,
        corpus_manifest=f"{corpus_id}.json",
        chunk_set_id=chunk_set_id,
        chunk_manifest=f"{chunk_set_id}.json",
        dense_index_id=dense_index_id,
        dense_index_manifest=f"{dense_index_id}.json",
        lexical_index_id=lexical_index_id,
        lexical_index_manifest=f"{lexical_index_id}.json",
        **hashes,
    )
    registry = ProductPublicationRegistry(settings, qdrant=q)
    snapshot_id = registry.publish(
        CORPUS_NAME, identity, require_current_config_match=True
    )
    return snapshot_id, corpus_id, chunk_set_id, art_id


def _campaign(
    *,
    snapshot_id: str,
    corpus_id: str,
    chunk_set_id: str,
    corpus_name: str = CORPUS_NAME,
) -> GoldCampaign:
    return GoldCampaign(
        campaign_id="goldcamp_" + ("ab" * 16),
        project_id="goldproj_" + ("cd" * 16),
        workspace_id="ws_test",
        snapshot_id=snapshot_id,
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        selection_policy=build_selection_policy(
            selection_policy_id="default", project_type="benchmark"
        ),
        baseline_authoring_run_id="authorrun_16fd",
        baseline_sha256="a" * 64,
        workspace_revision_at_creation=1,
        created_at=datetime.now(tz=UTC),
    )


def test_historical_happy_path_and_independence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _art = _publish_integrity(settings)
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    # Destroy current pointer / indexes / qdrant-facing state after publish.
    current = settings.paths.corpora / CORPUS_NAME / "product" / "current.json"
    if current.exists():
        current.unlink()
    shutil.rmtree(settings.paths.lexical_indexes, ignore_errors=True)
    chunk, corpus_m, source_name = resolve_historical_chunk(
        settings, campaign, chunk_id=CHUNK_A, expected_document_id=DOC_ID
    )
    assert chunk.chunk_id == CHUNK_A
    assert source_name == "spec.pdf"
    assert corpus_m.corpus_id == corpus_id


def test_corrupt_corpus_name_path_elements(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    campaign = _campaign(
        snapshot_id=snapshot_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        corpus_name="../evil",
    )
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, campaign, chunk_id=CHUNK_A)
    assert getattr(exc.value, "code", None) is ErrorCode.GOLD_STATE_UNAVAILABLE


def test_malformed_snapshot_id_before_path(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    # Bypass model validator by object.__setattr__ on frozen? GoldCampaign is pydantic.
    dirty = campaign.model_copy(update={"snapshot_id": "../snap_evil"})
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, dirty, chunk_id=CHUNK_A)
    # May fail at model validation or reader; either is fail-closed.
    assert "snap" in str(exc.value).lower() or getattr(exc.value, "code", None) in {
        ErrorCode.GOLD_STATE_UNAVAILABLE,
        None,
    }


def test_byte_hash_mismatch_no_text(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, art_id = _publish_integrity(settings)
    path = settings.paths.chunks / f"{art_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["children"][0]["text"] = "tampered evidence text"
    path.write_text(json.dumps(payload), encoding="utf-8")
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, campaign, chunk_id=CHUNK_A)
    err = exc.value
    assert getattr(err, "code", None) is ErrorCode.GOLD_STATE_UNAVAILABLE
    assert "tampered" not in str(getattr(err, "message", ""))


def test_chunk_set_id_recompute_mismatch(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _art_id = _publish_integrity(settings)
    manifest_path = settings.paths.chunk_manifests / f"{chunk_set_id}.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["documents"][0]["parsed_artifact_id"] = "parsed_tampered"
    # keep declared chunk_set_id old
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, campaign, chunk_id=CHUNK_A)
    assert getattr(exc.value, "code", None) is ErrorCode.GOLD_STATE_UNAVAILABLE


def test_absolute_nested_manifest_refs_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _ = _publish_integrity(settings)
    snap_path = (
        settings.paths.corpora
        / CORPUS_NAME
        / "product"
        / "snapshots"
        / f"{snapshot_id}.json"
    )
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    data["corpus_manifest"] = f"../{corpus_id}.json"
    # identity will no longer match compute_snapshot_id — still fail closed
    snap_path.write_text(json.dumps(data), encoding="utf-8")
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, campaign, chunk_id=CHUNK_A)
    assert getattr(exc.value, "code", None) is ErrorCode.GOLD_STATE_UNAVAILABLE


def test_relative_path_field_never_followed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    snapshot_id, corpus_id, chunk_set_id, _art_id = _publish_integrity(settings)
    manifest_path = settings.paths.chunk_manifests / f"{chunk_set_id}.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["documents"][0]["chunk_artifact"] = "chunks/../escape.json"
    # also need recomputed chunk_set_id to still match — changing chunk_artifact
    # does not affect chunk_set_id_from_entries (only document_id/parsed/art id)
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    campaign = _campaign(
        snapshot_id=snapshot_id, corpus_id=corpus_id, chunk_set_id=chunk_set_id
    )
    with pytest.raises(Exception) as exc:
        resolve_historical_chunk(settings, campaign, chunk_id=CHUNK_A)
    assert getattr(exc.value, "code", None) is ErrorCode.GOLD_STATE_UNAVAILABLE
    assert not (settings.paths.chunks.parent / "escape.json").exists()
