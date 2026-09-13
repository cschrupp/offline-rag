"""Lexical indexing / retrieval / evaluation unit tests."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config import ConfigError, load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.evaluate import mean_reciprocal_rank, recall_at_k
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import IndexingStatus
from offline_rag.ingestion.pipeline import run_ingestion
from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer
from offline_rag.lexical.backend import LocalInvertedIndexBackend
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.evaluate import LexicalRetrievalEvaluator
from offline_rag.lexical.pipeline import run_lexical_indexing
from offline_rag.lexical.retrieve import LexicalRetrievalError, LexicalRetriever
from offline_rag.lexical.scoring import BM25OkapiV1Scorer, idf, score_term_contribution
from offline_rag.lexical.status import lexical_indexing_status_for_corpus
from offline_rag.lexical.text import PlainLexicalTextBuilder


def _settings(tmp_path: Path) -> AppSettings:
    settings = AppSettings()
    return settings.model_copy(
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
        }
    )


def _prepare_corpus(settings: AppSettings, docs: dict[str, str], *, corpus_name: str = "default") -> None:
    raw = settings.paths.raw_data
    raw.mkdir(parents=True, exist_ok=True)
    for name, text in docs.items():
        (raw / name).write_text(text, encoding="utf-8")
    for path in (
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.lexical_indexes,
        settings.paths.lexical_index_manifests,
        settings.paths.eval_results,
        settings.paths.tokenizer_artifacts,
    ):
        path.mkdir(parents=True, exist_ok=True)
    ingest = run_ingestion(
        settings=settings,
        inputs=[raw],
        corpus_name=corpus_name,
        recursive=False,
        root=raw,
    )
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(
        settings=settings,
        corpus_name=corpus_name,
        token_counter=FakeTokenCounter(),
    )
    assert chunk.status.value in {"success", "no_op"}


def test_plain_lexical_text_builder_is_exact() -> None:
    from offline_rag.retrieval.ranking_text import RankingTextInputs

    chunk = Chunk(
        chunk_id="chunk_a",
        document_id="doc_a",
        kind=ChunkKind.CHILD,
        text="API-12 pressure",
        order=0,
        token_count=2,
        content_hash="hash_a",
        source_block_ids=["block_a"],
    )
    builder = PlainLexicalTextBuilder()
    inputs = RankingTextInputs(
        document_title=None,
        section_path=(),
        chunk_text=chunk.text,
    )
    assert builder.build(inputs) == chunk.text
    blank = RankingTextInputs(
        document_title=None,
        section_path=(),
        chunk_text="   \n\t",
    )
    with pytest.raises(ValueError):
        builder.build(blank)


def test_technical_v1_identifier_fixtures() -> None:
    analyzer = TechnicalLexicalAnalyzer()
    cases = {
        "API-12 maximum pressure": ["api-12", "maximum", "pressure"],
        "Firmware v1.2": ["firmware", "v1.2"],
        "part_no AB-104": ["part_no", "ab-104"],
        "C++ parser": ["c++", "parser"],
        "C# client": ["c#", "client"],
        ".NET runtime": [".net", "runtime"],
        "HPHT MDT C5-C6": ["hpht", "mdt", "c5-c6"],
        "Qwen3-Embedding-0.6B": ["qwen3-embedding-0.6b"],
        "api/v1 parent_chunk_id": ["api/v1", "parent_chunk_id"],
    }
    for text, expected in cases.items():
        assert analyzer.analyze(text) == expected, text
    assert analyzer.analyze_query_terms("pressure pressure API-12") == ["pressure", "api-12"]


def test_bm25_okapi_hand_calculation() -> None:
    # N=3, docs: d1 len=2 [a,a], d2 len=1 [a], d3 len=1 [b]
    n = 3
    avgdl = (2 + 1 + 1) / 3
    df_a = 2
    idf_a = idf(n=n, df=df_a)
    expected_idf = math.log(1.0 + (n - df_a + 0.5) / (df_a + 0.5))
    assert idf_a == pytest.approx(expected_idf)

    contrib_d1 = score_term_contribution(tf=2, doc_length=2, avgdl=avgdl, idf_value=idf_a)
    contrib_d2 = score_term_contribution(tf=1, doc_length=1, avgdl=avgdl, idf_value=idf_a)
    assert contrib_d1 != pytest.approx(2 * contrib_d2)  # saturation

    scorer = BM25OkapiV1Scorer()
    scores = scorer.accumulate(
        query_terms=["a", "a"],
        postings_by_term={"a": [("chunk_b", 1.0), ("chunk_a", 2.0)]},
        doc_lengths={"chunk_a": 2.0, "chunk_b": 1.0, "chunk_c": 1.0},
        avgdl=avgdl,
        n=n,
        dfs={"a": 2},
    )
    # unique query terms — repeated "a" does not double
    once = scorer.accumulate(
        query_terms=["a"],
        postings_by_term={"a": [("chunk_b", 1.0), ("chunk_a", 2.0)]},
        doc_lengths={"chunk_a": 2.0, "chunk_b": 1.0, "chunk_c": 1.0},
        avgdl=avgdl,
        n=n,
        dfs={"a": 2},
    )
    assert scores == once
    assert "chunk_c" not in scores


def test_lexical_index_noop_persist_and_retrieve(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {
            "alpha.txt": "Alpha well uses API-12 for maximum operating pressure control.\n",
            "beta.txt": "Beta system documents C++ tooling and .NET runtime notes.\n",
        },
    )
    first = run_lexical_indexing(settings=settings, corpus_name="default")
    assert first.status == IndexingStatus.SUCCESS
    assert first.lexical_index_id is not None
    assert lexical_indexing_status_for_corpus(settings, "default") == "CURRENT"

    second = run_lexical_indexing(settings=settings, corpus_name="default")
    assert second.status == IndexingStatus.NO_OP
    assert second.lexical_index_id == first.lexical_index_id

    backend = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
    backend.open(first.lexical_index_id)
    hits = backend.search(["api-12"], top_k=5)
    backend.close()
    assert hits
    assert hits[0].chunk_id

    # reopen persistence
    backend2 = LocalInvertedIndexBackend(settings.paths.lexical_indexes)
    backend2.open(first.lexical_index_id)
    hits2 = backend2.search(["api-12"], top_k=5)
    backend2.close()
    assert [(h.chunk_id, h.score) for h in hits2] == [(h.chunk_id, h.score) for h in hits]

    retriever = LexicalRetriever(settings)
    try:
        result = retriever.retrieve(query="API-12 pressure", corpus_name="default", top_k=5)
    finally:
        retriever.close()
    assert result.method == "lexical"
    assert result.candidates
    assert result.candidates[0].text
    assert "api-12" in " ".join(result.metadata["query_terms"])


def test_top_k_not_in_lexical_identity(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    h1 = build_lexical_config_hash(settings)
    settings2 = settings.model_copy(
        update={"lexical": settings.lexical.model_copy(update={"top_k": 99})}
    )
    assert build_lexical_config_hash(settings2) == h1
    settings3 = settings.model_copy(
        update={
            "lexical": settings.lexical.model_copy(
                update={"bm25": settings.lexical.bm25.model_copy(update={"k1": 1.5})}
            )
        }
    )
    assert build_lexical_config_hash(settings3) != h1


def test_zero_term_query_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(settings, {"doc.txt": "pressure valve API-12\n"})
    assert run_lexical_indexing(settings=settings, corpus_name="default").status == IndexingStatus.SUCCESS
    retriever = LexicalRetriever(settings)
    try:
        with pytest.raises(LexicalRetrievalError, match="zero analyzed"):
            retriever.retrieve(query="!!! ???", corpus_name="default")
    finally:
        retriever.close()


def test_lexical_eval_smoke(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _prepare_corpus(
        settings,
        {"doc.txt": "Maximum operating pressure uses API-12 guidelines for wells.\n"},
    )
    report = run_lexical_indexing(settings=settings, corpus_name="default")
    assert report.status == IndexingStatus.SUCCESS

    retriever = LexicalRetriever(settings)
    try:
        hit = retriever.retrieve(query="API-12 pressure", corpus_name="default", top_k=3)
    finally:
        retriever.close()
    assert hit.candidates
    relevant = hit.candidates[0].chunk_id

    from offline_rag.lexical.persistence import (
        lexical_index_state_path,
        load_lexical_index_state,
    )

    state = load_lexical_index_state(lexical_index_state_path(settings.paths.corpora, "default"))
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "meta.json").write_text(
        f'{{"schema_version":1,"chunk_set_id":"{state.source_chunk_set_id}","metadata":{{}}}}',
        encoding="utf-8",
    )
    (dataset / "cases.jsonl").write_text(
        f'{{"id":"c1","query":"API-12 pressure","relevant_chunk_ids":["{relevant}"]}}\n',
        encoding="utf-8",
    )

    evaluator = LexicalRetrievalEvaluator(settings)
    try:
        eval_report = evaluator.evaluate(dataset, corpus_name="default", top_k=5)
    finally:
        evaluator.retriever.close()
    assert eval_report.method == "lexical"
    assert eval_report.aggregates.recall_at_1.value == pytest.approx(1.0)
    assert eval_report.aggregates.mrr.value == pytest.approx(1.0)
    assert recall_at_k([relevant], [relevant], 1) == 1.0
    assert mean_reciprocal_rank([relevant], [relevant]) == 1.0


def test_sparse_config_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "sparse.yaml"
    bad.write_text("sparse:\n  enabled: true\n  method: bm25\n  top_k: 10\n", encoding="utf-8")
    with pytest.raises(ConfigError, match='renamed to "lexical"'):
        load_settings(yaml_paths=[bad], environ={})

    both = tmp_path / "both.yaml"
    both.write_text(
        "sparse:\n  enabled: true\nlexical:\n  enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="must not both"):
        load_settings(yaml_paths=[both], environ={})
