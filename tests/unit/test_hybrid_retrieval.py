"""Hybrid RRF fusion and HybridRetriever unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.cli import main
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.pipeline import run_indexing
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.indexing import (
    DenseCandidate,
    DenseRetrievalResult,
    IndexingStatus,
    LexicalCandidate,
    LexicalRetrievalResult,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.evaluate import HybridRetrievalEvaluator
from offline_rag.hybrid.fusion import RankedBranchHit, ReciprocalRankFusion
from offline_rag.hybrid.retrieve import HybridRetrievalError, HybridRetriever
from offline_rag.hybrid.status import hybrid_status_for_corpus
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.lexical.pipeline import run_lexical_indexing
from offline_rag.lexical.retrieve import LexicalRetriever


def test_rrf_v1_both_branches_and_tie_break() -> None:
    fusion = ReciprocalRankFusion(rrf_k=60)
    dense = [
        RankedBranchHit("A", 1, 0.9),
        RankedBranchHit("B", 2, 0.8),
        RankedBranchHit("C", 3, 0.7),
    ]
    lexical = [
        RankedBranchHit("B", 1, 5.0),
        RankedBranchHit("A", 2, 4.0),
        RankedBranchHit("D", 3, 3.0),
    ]
    fused = fusion.fuse(dense=dense, lexical=lexical)
    by_id = {hit.chunk_id: hit for hit in fused}
    assert by_id["A"].rrf_score == pytest.approx(1 / 61 + 1 / 62)
    assert by_id["B"].rrf_score == pytest.approx(1 / 62 + 1 / 61)
    assert by_id["C"].rrf_score == pytest.approx(1 / 63)
    assert by_id["D"].rrf_score == pytest.approx(1 / 63)
    assert by_id["A"].dense_rank == 1
    assert by_id["A"].lexical_rank == 2
    assert by_id["C"].lexical_rank is None
    assert by_id["D"].dense_rank is None
    # A and B equal RRF; chunk_id ASC => A before B
    assert [hit.chunk_id for hit in fused[:2]] == ["A", "B"]


def test_rrf_dense_only_and_lexical_only() -> None:
    fusion = ReciprocalRankFusion(rrf_k=60)
    fused = fusion.fuse(
        dense=[RankedBranchHit("X", 1, 0.5)],
        lexical=[RankedBranchHit("Y", 1, 2.0)],
    )
    assert [hit.chunk_id for hit in fused] == ["X", "Y"]
    assert fused[0].rrf_score == pytest.approx(1 / 61)
    assert fused[0].lexical_rank is None
    assert fused[1].dense_rank is None


def test_rrf_equal_ranks_one_based_k60() -> None:
    fusion = ReciprocalRankFusion(rrf_k=60)
    fused = fusion.fuse(
        dense=[RankedBranchHit("p", 1, 1.0)],
        lexical=[RankedBranchHit("p", 1, 9.0)],
    )
    assert len(fused) == 1
    assert fused[0].rrf_score == pytest.approx(2 / 61)


def test_rrf_duplicate_branch_keeps_best_rank() -> None:
    fusion = ReciprocalRankFusion(rrf_k=60)
    dense = [
        RankedBranchHit("A", 5, 0.1),
        RankedBranchHit("A", 1, 0.9),
    ]
    fused = fusion.fuse(dense=dense, lexical=[])
    assert len(fused) == 1
    assert fused[0].dense_rank == 1
    assert fused[0].rrf_score == pytest.approx(1 / 61)


def test_rrf_rejects_zero_based_rank() -> None:
    fusion = ReciprocalRankFusion(rrf_k=60)
    with pytest.raises(ValueError, match="1-based"):
        fusion.fuse(dense=[RankedBranchHit("A", 0, 1.0)], lexical=[])


def test_fusion_config_hash_ignores_output_top_k() -> None:
    settings = AppSettings()
    h1 = build_fusion_config_hash(settings)
    settings2 = settings.model_copy(
        update={"fusion": settings.fusion.model_copy(update={"output_top_k": 99})}
    )
    assert build_fusion_config_hash(settings2) == h1
    settings3 = settings.model_copy(
        update={"fusion": settings.fusion.model_copy(update={"dense_top_k": 20})}
    )
    assert build_fusion_config_hash(settings3) != h1


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
                    "lexical_indexes": tmp_path / "lexical-indexes",
                    "lexical_index_manifests": tmp_path / "lexical-index-manifests",
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
            "fusion": settings.fusion.model_copy(
                update={
                    "dense_top_k": 5,
                    "lexical_top_k": 5,
                    "output_top_k": 3,
                }
            ),
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
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.eval_results,
        settings.paths.docling_artifacts,
        settings.paths.tokenizer_artifacts,
        settings.paths.embedding_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _prepare(settings: AppSettings) -> None:
    raw = settings.paths.raw_data
    (raw / "a.txt").write_text(
        "Beta tool maximum pressure is 15000 psi for continuous API-12 operation.\n",
        encoding="utf-8",
    )
    (raw / "b.txt").write_text(
        "Alpha sensor temperature rating is 175 deg C under load.\n",
        encoding="utf-8",
    )
    ingest = run_ingestion(settings=settings, inputs=[raw], corpus_name="eng", recursive=False)
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(settings=settings, corpus_name="eng", token_counter=FakeTokenCounter())
    assert chunk.status.value in {"success", "no_op"}
    dense = run_indexing(
        settings=settings,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8, normalize=True),
    )
    assert dense.status in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}
    lexical = run_lexical_indexing(settings=settings, corpus_name="eng")
    assert lexical.status in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}


def _dense_candidate(chunk_id: str, rank: int, score: float) -> DenseCandidate:
    return DenseCandidate(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"text-{chunk_id}",
    )


def _lexical_candidate(chunk_id: str, rank: int, score: float) -> LexicalCandidate:
    return LexicalCandidate(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"text-{chunk_id}",
    )


def test_hybrid_sequential_branch_depths_and_truncation() -> None:
    settings = AppSettings().model_copy(
        update={
            "fusion": AppSettings().fusion.model_copy(
                update={"dense_top_k": 30, "lexical_top_k": 30, "output_top_k": 10}
            )
        }
    )
    order: list[str] = []
    dense_kwargs: dict[str, Any] = {}
    lexical_kwargs: dict[str, Any] = {}

    def dense_retrieve(**kwargs: Any) -> DenseRetrievalResult:
        order.append("dense")
        dense_kwargs.update(kwargs)
        return DenseRetrievalResult(
            query=kwargs["query"],
            index_id="idx_dense",
            top_k=kwargs["top_k"],
            candidates=[
                _dense_candidate(f"c{i}", i, 1.0 - i * 0.01) for i in range(1, kwargs["top_k"] + 1)
            ],
            metadata={"chunk_set_id": "chunkset_x"},
        )

    def lexical_retrieve(**kwargs: Any) -> LexicalRetrievalResult:
        order.append("lexical")
        lexical_kwargs.update(kwargs)
        return LexicalRetrievalResult(
            query=kwargs["query"],
            index_id="idx_lex",
            top_k=kwargs["top_k"],
            candidates=[
                _lexical_candidate(f"c{i}", i, 10.0 - i)
                for i in range(1, min(5, kwargs["top_k"]) + 1)
            ],
            metadata={"chunk_set_id": "chunkset_x"},
        )

    dense = MagicMock()
    dense.retrieve.side_effect = dense_retrieve
    lexical = MagicMock()
    lexical.retrieve.side_effect = lexical_retrieve

    fusion = ReciprocalRankFusion(rrf_k=60)
    real_fuse = fusion.fuse

    def tracked_fuse(**kwargs: Any) -> Any:
        order.append("fusion")
        return real_fuse(**kwargs)

    fusion.fuse = tracked_fuse  # type: ignore[method-assign]

    retriever = HybridRetriever(settings, dense=dense, lexical=lexical, fusion=fusion)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = retriever.retrieve(query="q", corpus_name="default", top_k=2)

    assert order == ["dense", "lexical", "fusion"]
    assert dense_kwargs["top_k"] == 30
    assert lexical_kwargs["top_k"] == 30
    assert result.top_k == 2
    assert len(result.candidates) == 2
    assert result.dense_index_id == "idx_dense"
    assert result.lexical_index_id == "idx_lex"
    assert result.fusion_config_hash.startswith("fuscfg_")
    assert result.metadata["latency_ms"]["dense"] >= 0
    assert result.metadata["latency_ms"]["lexical"] >= 0
    assert result.metadata["latency_ms"]["fusion"] >= 0
    assert result.metadata["latency_ms"]["total"] >= 0


def test_hybrid_valid_empty_branches() -> None:
    settings = AppSettings()
    dense = MagicMock()
    dense.retrieve.return_value = DenseRetrievalResult(
        query="q",
        index_id="idx_dense",
        top_k=30,
        candidates=[],
        metadata={"chunk_set_id": "cs"},
    )
    lexical = MagicMock()
    lexical.retrieve.return_value = LexicalRetrievalResult(
        query="q",
        index_id="idx_lex",
        top_k=30,
        candidates=[_lexical_candidate("only", 1, 3.0)],
        metadata={"chunk_set_id": "cs"},
    )
    retriever = HybridRetriever(settings, dense=dense, lexical=lexical)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = retriever.retrieve(query="q", corpus_name="default", top_k=5)
    assert [c.chunk_id for c in result.candidates] == ["only"]
    assert result.candidates[0].fusion.dense_rank is None
    assert result.candidates[0].fusion.lexical_rank == 1

    dense.retrieve.return_value = DenseRetrievalResult(
        query="q",
        index_id="idx_dense",
        top_k=30,
        candidates=[_dense_candidate("d1", 1, 0.9)],
        metadata={"chunk_set_id": "cs"},
    )
    lexical.retrieve.return_value = LexicalRetrievalResult(
        query="q",
        index_id="idx_lex",
        top_k=30,
        candidates=[],
        metadata={"chunk_set_id": "cs"},
    )
    result2 = retriever.retrieve(query="q", corpus_name="default", top_k=5)
    assert [c.chunk_id for c in result2.candidates] == ["d1"]

    dense.retrieve.return_value = DenseRetrievalResult(
        query="q",
        index_id="idx_dense",
        top_k=30,
        candidates=[],
        metadata={"chunk_set_id": "cs"},
    )
    result3 = retriever.retrieve(query="q", corpus_name="default", top_k=5)
    assert result3.candidates == []


def test_hybrid_retrieve_integration_and_doctor(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert hybrid_status_for_corpus(settings, "eng") == "NOT_READY"
    _prepare(settings)
    assert hybrid_status_for_corpus(settings, "eng") == "READY"

    dense = DenseRetriever(settings, embedder=FakeEmbedder(dimension=8, normalize=True))
    retriever = HybridRetriever(settings, dense=dense)
    try:
        result = retriever.retrieve(query="API-12 pressure", corpus_name="eng", top_k=3)
    finally:
        retriever.close()
    assert result.method == "hybrid"
    assert result.candidates
    assert result.fusion_config_hash.startswith("fuscfg_")
    assert result.metadata["dense_top_k"] == 5
    assert result.metadata["lexical_top_k"] == 5
    for candidate in result.candidates:
        assert candidate.score == candidate.fusion.rrf_score
    assert not (settings.paths.corpora / "eng" / "hybrid").exists()


def test_hybrid_refuses_without_lexical(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = settings.paths.raw_data
    (raw / "a.txt").write_text("pressure API-12\n", encoding="utf-8")
    assert run_ingestion(settings=settings, inputs=[raw], corpus_name="eng").status.value in {
        "success",
        "no_op",
    }
    assert run_chunking(
        settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
    ).status.value in {"success", "no_op"}
    assert run_indexing(
        settings=settings,
        corpus_name="eng",
        embedder=FakeEmbedder(dimension=8, normalize=True),
    ).status in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}
    assert hybrid_status_for_corpus(settings, "eng") == "NOT_READY"
    dense = DenseRetriever(settings, embedder=FakeEmbedder(dimension=8, normalize=True))
    retriever = HybridRetriever(settings, dense=dense)
    try:
        with pytest.raises(HybridRetrievalError, match="unavailable"):
            retriever.retrieve(query="pressure", corpus_name="eng")
    finally:
        retriever.close()


def test_hybrid_refuses_without_dense(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = settings.paths.raw_data
    (raw / "a.txt").write_text("pressure API-12\n", encoding="utf-8")
    assert run_ingestion(settings=settings, inputs=[raw], corpus_name="eng").status.value in {
        "success",
        "no_op",
    }
    assert run_chunking(
        settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
    ).status.value in {"success", "no_op"}
    assert run_lexical_indexing(settings=settings, corpus_name="eng").status in {
        IndexingStatus.SUCCESS,
        IndexingStatus.NO_OP,
    }
    assert hybrid_status_for_corpus(settings, "eng") == "NOT_READY"
    retriever = HybridRetriever(settings, dense=MagicMock(), lexical=LexicalRetriever(settings))
    try:
        with pytest.raises(HybridRetrievalError, match="unavailable"):
            retriever.retrieve(query="pressure", corpus_name="eng")
    finally:
        retriever.close()


def test_hybrid_eval_reuses_metrics(tmp_path: Path) -> None:
    import json

    settings = _settings(tmp_path)
    _prepare(settings)
    dense = DenseRetriever(settings, embedder=FakeEmbedder(dimension=8, normalize=True))
    hybrid = HybridRetriever(settings, dense=dense)
    result = hybrid.retrieve(query="API-12 pressure", corpus_name="eng", top_k=5)
    gold_chunk = result.candidates[0].chunk_id
    chunk_set_id = str(result.metadata["chunk_set_id"])
    corpus_id = str(result.metadata.get("corpus_id") or "corpus_x")
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": corpus_id,
                "chunk_set_id": chunk_set_id,
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "query": "API-12 pressure",
                "relevant_chunk_ids": [gold_chunk],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evaluator = HybridRetrievalEvaluator(settings, retriever=hybrid)
    try:
        report = evaluator.evaluate(
            dataset_dir,
            corpus_name="eng",
            top_k=5,
            persist=True,
        )
    finally:
        hybrid.close()
    assert report.method == "hybrid"
    assert str(report.semantic_provenance["fusion_config_hash"]).startswith("fuscfg_")
    assert report.semantic_provenance["dense_index_id"]
    assert report.semantic_provenance["lexical_index_id"]
    assert report.aggregates.recall_at_1.value == 1.0
    assert report.aggregates.mrr.value == 1.0
    assert (settings.paths.eval_results / "hybrid-retrieval").exists()


def test_cli_retrieve_hybrid_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["retrieve", "hybrid", "--help"])
    assert exc.value.code == 0
