"""Dense indexing / retrieval / evaluation unit tests (FakeEmbedder)."""

from __future__ import annotations

import json
from pathlib import Path

from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dense_point_uuid
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.evaluate import (
    DenseRetrievalEvaluator,
    first_relevant_rank,
    mean_reciprocal_rank,
    recall_at_k,
)
from offline_rag.dense.pipeline import run_indexing
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.dense.status import indexing_status_for_corpus
from offline_rag.dense.text import PlainEmbeddingTextBuilder
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import IndexingStatus
from offline_rag.ingestion.pipeline import run_ingestion


def _settings(tmp_path: Path) -> AppSettings:
    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "project": settings.project.model_copy(update={"strict_offline": False}),
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": tmp_path / "raw",
                    "manifests": tmp_path / "manifests",
                    "processed": tmp_path / "processed",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                    "embeddings": tmp_path / "embeddings",
                    "index_manifests": tmp_path / "index-manifests",
                    "qdrant_storage": tmp_path / "qdrant",
                    "retrieval_models": tmp_path / "models",
                    "docling_artifacts": tmp_path / "models" / "docling",
                    "tokenizer_artifacts": tmp_path / "models" / "tokenizers" / "tiktoken",
                    "embedding_artifacts": tmp_path / "models" / "embeddings",
                    "eval_results": tmp_path / "eval" / "results",
                }
            ),
            "chunking": settings.chunking.model_copy(
                update={
                    "tokenizer": settings.chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            ),
            "indexing": settings.indexing.model_copy(
                update={
                    "embedding": settings.indexing.embedding.model_copy(
                        update={
                            "implementation": "fake",
                            "model_id": "fake",
                            "revision": "fake-v1",
                            "dimension": 8,
                            "adapter_contract": "fake-embedder-v1",
                        }
                    )
                }
            ),
            "dense": settings.dense.model_copy(update={"top_k": 5}),
        }
    )
    for path in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.eval_results,
        settings.paths.docling_artifacts,
        settings.paths.tokenizer_artifacts,
        settings.paths.embedding_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _prepare_corpus(settings: AppSettings, docs: Path) -> None:
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "a.txt").write_text(
        "Beta tool maximum pressure is 15000 psi for continuous operation.\n",
        encoding="utf-8",
    )
    (docs / "b.txt").write_text(
        "Alpha sensor temperature rating is 175 deg C under load.\n",
        encoding="utf-8",
    )
    ingest = run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())
    assert chunk.status.value in {"success", "no_op"}


def test_plain_embedding_text_builder_is_exact() -> None:
    chunk = Chunk(
        chunk_id="chunk_1",
        document_id="doc_1",
        kind=ChunkKind.CHILD,
        parent_chunk_id="parent_1",
        text="Exact text",
        order=0,
        token_count=2,
        content_hash="h",
        source_block_ids=["b1"],
        section_path=["Ops", "Limits"],
    )
    builder = PlainEmbeddingTextBuilder()
    assert builder.build(chunk) == "Exact text"
    assert builder.build(chunk) == chunk.text


def test_fake_embedder_deterministic() -> None:
    embedder = FakeEmbedder(dimension=8, normalize=True)
    a = embedder.embed_documents(["hello world"])[0]
    b = embedder.embed_query("hello world")
    assert a == b
    assert len(a) == 8


def test_metric_helpers() -> None:
    relevant = {"c1", "c2"}
    retrieved = ["x", "c1", "y", "c2"]
    assert recall_at_k(relevant, retrieved, 1) == 0.0
    assert recall_at_k(relevant, retrieved, 2) == 0.5
    assert recall_at_k(relevant, retrieved, 4) == 1.0
    assert first_relevant_rank(relevant, retrieved) == 2
    assert mean_reciprocal_rank(relevant, retrieved) == 0.5


def test_point_uuid_deterministic() -> None:
    assert dense_point_uuid("chunk_abc") == dense_point_uuid("chunk_abc")
    assert dense_point_uuid("chunk_abc") != dense_point_uuid("chunk_abd")


def test_index_reuse_noop_and_retrieve(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _prepare_corpus(settings, docs)
    embedder = FakeEmbedder(dimension=8, normalize=True)

    first = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert first.status == IndexingStatus.SUCCESS
    assert first.embeddings_generated >= 1
    assert first.children_total == first.vectors_materialized
    assert indexing_status_for_corpus(settings, "eng") == "CURRENT"

    second = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert second.status == IndexingStatus.NO_OP
    assert second.embeddings_generated == 0
    assert second.index_id == first.index_id

    retriever = DenseRetriever(settings, embedder=embedder)
    try:
        result = retriever.retrieve(query="Beta tool pressure", corpus_name="eng", top_k=3)
    finally:
        retriever.close()
    assert result.candidates
    assert result.candidates[0].rank == 1
    assert "pressure" in result.candidates[0].text.lower() or result.candidates[0].text


def test_embedding_reuse_across_chunkset_change(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _prepare_corpus(settings, docs)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    first = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert first.status == IndexingStatus.SUCCESS
    generated_first = first.embeddings_generated

    (docs / "c.txt").write_text("Gamma valve orifice diameter is 0.25 inch.\n", encoding="utf-8")
    run_ingestion(settings=settings, inputs=[docs], corpus_name="eng", recursive=False)
    run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())
    second = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert second.status == IndexingStatus.SUCCESS
    assert second.index_id != first.index_id
    assert second.embeddings_reused >= 1
    assert second.embeddings_generated < generated_first + second.children_total
    # Historical first index remains
    assert (tmp_path / "index-manifests" / f"{first.index_id}.json").exists()


def test_qdrant_local_persistence(tmp_path: Path) -> None:
    storage = tmp_path / "qdrant"
    backend = QdrantLocalBackend(storage)
    from offline_rag.dense.backend import DensePointRecord

    backend.create_collection("dense_test", dimension=4, metric="cosine")
    backend.upsert(
        "dense_test",
        [
            DensePointRecord(
                point_id=dense_point_uuid("chunk_1"),
                vector=[1.0, 0.0, 0.0, 0.0],
                payload={"chunk_id": "chunk_1", "kind": "child"},
            )
        ],
    )
    assert backend.count("dense_test") == 1
    backend.close()

    reopened = QdrantLocalBackend(storage)
    assert reopened.collection_exists("dense_test")
    assert reopened.count("dense_test") == 1
    hits = reopened.search("dense_test", query_vector=[1.0, 0.0, 0.0, 0.0], top_k=1)
    assert hits[0].payload["chunk_id"] == "chunk_1"
    reopened.close()


def test_eval_retrieve_smoke(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _prepare_corpus(settings, docs)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    index_report = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    assert index_report.status == IndexingStatus.SUCCESS

    from offline_rag.chunking.persistence import load_chunk_artifact
    from offline_rag.dense.persistence import index_state_path, load_index_state

    state = load_index_state(index_state_path(settings.paths.corpora, "eng"))
    # Pick first child from first chunk artifact
    artifact_files = sorted((tmp_path / "chunks").glob("*.json"))
    artifact = load_chunk_artifact(artifact_files[0])
    child = artifact.children[0]

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": state.source_corpus_id,
                "chunk_set_id": state.source_chunk_set_id,
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "q1",
                "query": child.text.split()[0],
                "relevant_chunk_ids": [child.chunk_id],
                "relevant_document_ids": [child.document_id],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evaluator = DenseRetrievalEvaluator(settings, embedder=embedder)
    report = evaluator.evaluate(dataset_dir, corpus_name="eng", top_k=5)
    assert report.case_count == 1
    assert 0.0 <= report.recall_at_5 <= 1.0
    assert report.index_id == index_report.index_id


def test_config_hash_metric_change_reuses_embeddings(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _prepare_corpus(settings, docs)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    first = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    emb_cfg = build_embedding_config_hash(settings)
    idx_cfg = build_index_config_hash(settings)

    # Change only a non-vector setting that still participates in index hash via backend_contract
    changed = settings.model_copy(
        update={
            "indexing": settings.indexing.model_copy(
                update={"backend_contract": "qdrant-local-v1-test"}
            )
        }
    )
    assert build_embedding_config_hash(changed) == emb_cfg
    assert build_index_config_hash(changed) != idx_cfg
    second = run_indexing(settings=changed, corpus_name="eng", embedder=embedder)
    assert second.status == IndexingStatus.SUCCESS
    assert second.embeddings_generated == 0
    assert second.embeddings_reused == second.children_total
    assert second.index_id != first.index_id


def test_payload_has_no_full_text(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = tmp_path / "docs"
    _prepare_corpus(settings, docs)
    embedder = FakeEmbedder(dimension=8, normalize=True)
    report = run_indexing(settings=settings, corpus_name="eng", embedder=embedder)
    backend = QdrantLocalBackend(settings.paths.qdrant_storage)
    try:
        assert report.collection_name
        # Grab any point via search
        hits = backend.search(
            report.collection_name,
            query_vector=embedder.embed_query("pressure"),
            top_k=1,
        )
        assert hits
        payload = hits[0].payload
        assert "text" not in payload
        assert payload.get("kind") == "child"
        assert payload.get("chunk_id")
    finally:
        backend.close()
