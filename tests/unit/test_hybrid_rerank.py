"""Slice 6 hybrid-rerank unit tests."""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import MagicMock

import pytest

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_PINNED_REVISION,
    FAKE_RERANK_DIGEST_CONTRACT,
)
from offline_rag.domain.indexing import (
    FusionProvenance,
    HybridCandidate,
    HybridRetrievalResult,
)
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.evaluate import HybridRerankRetrievalEvaluator
from offline_rag.rerank.fake import (
    FakeReranker,
    FakeRerankerError,
    fake_rerank_digest_score,
)
from offline_rag.rerank.input_builder import PairInputError, PlainPairInputBuilder
from offline_rag.rerank.protocol import RerankerPair
from offline_rag.rerank.retrieve import (
    HybridRerankRetrievalError,
    HybridRerankRetriever,
)


def _hybrid_candidate(
    chunk_id: str,
    *,
    rank: int,
    text: str,
    rrf_score: float = 0.01,
) -> HybridCandidate:
    return HybridCandidate(
        rank=rank,
        score=rrf_score,
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=text,
        fusion=FusionProvenance(
            rrf_score=rrf_score,
            dense_rank=rank,
            dense_score=0.9,
            lexical_rank=None,
            lexical_score=None,
        ),
    )


def test_reranker_config_hash_payload_and_ignores_output_k() -> None:
    settings = AppSettings()
    h1 = build_reranker_config_hash(settings)
    assert h1.startswith("rrkcfg_")

    settings2 = settings.model_copy(
        update={"reranker": settings.reranker.model_copy(update={"output_k": 99})}
    )
    assert build_reranker_config_hash(settings2) == h1

    settings3 = settings.model_copy(
        update={"reranker": settings.reranker.model_copy(update={"input_k": 50})}
    )
    assert build_reranker_config_hash(settings3) != h1

    settings4 = settings.model_copy(
        update={
            "reranker": settings.reranker.model_copy(
                update={
                    "model": settings.reranker.model.model_copy(
                        update={"revision": "deadbeef" * 5}
                    )
                }
            )
        }
    )
    assert build_reranker_config_hash(settings4) != h1

    # Defaults match pinned production identity in hash payload.
    assert settings.reranker.model.model_id == BGE_RERANKER_MODEL_ID
    assert settings.reranker.model.revision == BGE_RERANKER_PINNED_REVISION


def test_plain_pair_input_builder() -> None:
    builder = PlainPairInputBuilder()
    spaced = HybridCandidate.model_construct(
        rank=2,
        score=0.01,
        chunk_id="c2",
        document_id="doc_c2",
        text="  keep spaces  ",
        section_path=[],
        token_count=0,
        fusion=FusionProvenance(rrf_score=0.01),
        metadata={},
    )
    candidates = [
        _hybrid_candidate("c1", rank=1, text="passage one"),
        spaced,
    ]
    pairs = builder.build(query="  hello world  ", candidates=candidates)
    assert len(pairs) == 2
    assert pairs[0] == RerankerPair(
        chunk_id="c1",
        query_text="hello world",
        passage_text="passage one",
    )
    assert pairs[1].passage_text == "  keep spaces  "

    with pytest.raises(PairInputError, match="non-empty"):
        builder.build(query="   ", candidates=candidates)

    blank = HybridCandidate.model_construct(
        rank=1,
        score=0.01,
        chunk_id="empty",
        document_id="doc_empty",
        text="   ",
        section_path=[],
        token_count=0,
        fusion=FusionProvenance(rrf_score=0.01),
        metadata={},
    )
    with pytest.raises(PairInputError, match="invariant failure"):
        builder.build(query="q", candidates=[blank])


def test_fake_rerank_digest_contract() -> None:
    assert FakeReranker.contract == FAKE_RERANK_DIGEST_CONTRACT
    score = fake_rerank_digest_score("q", "p")
    assert -10.0 <= score < 10.0
    assert math.isfinite(score)
    # Deterministic
    assert fake_rerank_digest_score("q", "p") == score
    assert FakeReranker().score_pairs([]) == []

    pairs = [
        RerankerPair(chunk_id="a", query_text="q", passage_text="same"),
        RerankerPair(chunk_id="b", query_text="q", passage_text="same"),
    ]
    scores = FakeReranker().score_pairs(pairs)
    assert scores[0] == scores[1]

    override = FakeReranker(score_map={("q", "a"): 3.5, ("q", "b"): -1.0})
    assert override.score_pairs(pairs) == [3.5, -1.0]

    with pytest.raises(FakeRerankerError, match="finite"):
        FakeReranker(score_map={("q", "a"): float("nan")})


def test_sort_raw_logit_desc_chunk_id_asc() -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"implementation": "fake", "input_k": 5, "output_k": 3}
            )
        }
    )
    pool = [
        _hybrid_candidate("c", rank=1, text="t1"),
        _hybrid_candidate("a", rank=2, text="t2"),
        _hybrid_candidate("b", rank=3, text="t3"),
    ]
    hybrid = MagicMock()
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="q",
        top_k=5,
        candidates=pool,
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        metadata={
            "chunk_set_id": "chunkset_x",
            "latency_ms": {"dense": 1, "lexical": 2, "fusion": 3, "total": 6},
        },
    )
    reranker = FakeReranker(
        score_map={
            ("q", "c"): 1.0,
            ("q", "a"): 1.0,
            ("q", "b"): 2.0,
        }
    )
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=reranker)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = retriever.retrieve(query="q", corpus_name="default", top_k=3)
    assert [c.chunk_id for c in result.candidates] == ["b", "a", "c"]
    assert result.candidates[0].score == 2.0
    assert result.candidates[1].score == 1.0
    assert result.candidates[1].hybrid_rerank.hybrid_rank == 2
    assert result.candidates[1].hybrid_rerank.rrf_score == pool[1].fusion.rrf_score
    assert result.method == "hybrid-rerank"
    assert result.reranker_config_hash.startswith("rrkcfg_")
    latency = result.metadata["latency_ms"]
    assert "hybrid" in latency
    assert "pair_build" in latency
    assert "rerank_infer" in latency
    assert "sort" in latency
    assert "total" in latency
    assert latency["hybrid_breakdown"]["dense"] == 1


def test_orchestrator_calls_hybrid_with_input_k_and_truncates() -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"implementation": "fake", "input_k": 4, "output_k": 2}
            )
        }
    )
    captured: dict[str, Any] = {}

    def hybrid_retrieve(**kwargs: Any) -> HybridRetrievalResult:
        captured.update(kwargs)
        return HybridRetrievalResult(
            query=kwargs["query"],
            top_k=kwargs["top_k"],
            candidates=[
                _hybrid_candidate(f"c{i}", rank=i, text=f"text-{i}") for i in range(1, 5)
            ],
            dense_index_id="d",
            lexical_index_id="l",
            fusion_config_hash="fuscfg_y",
            metadata={"chunk_set_id": "cs", "latency_ms": {}},
        )

    hybrid = MagicMock()
    hybrid.retrieve.side_effect = hybrid_retrieve
    reranker = FakeReranker(
        score_map={
            ("query", "c1"): 0.1,
            ("query", "c2"): 0.4,
            ("query", "c3"): 0.3,
            ("query", "c4"): 0.2,
        }
    )
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=reranker)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = retriever.retrieve(query="query", corpus_name="eng")
    assert captured["top_k"] == 4
    assert result.top_k == 2
    assert [c.chunk_id for c in result.candidates] == ["c2", "c3"]
    assert result.metadata["input_pool_size"] == 4
    assert result.metadata["input_pool_chunk_ids"] == ["c1", "c2", "c3", "c4"]


def test_top_k_greater_than_input_k_raises() -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"implementation": "fake", "input_k": 3, "output_k": 2}
            )
        }
    )
    retriever = HybridRerankRetriever(
        settings, hybrid=MagicMock(), reranker=FakeReranker()
    )
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(HybridRerankRetrievalError, match="cannot exceed"):
        retriever.retrieve(query="q", top_k=5)


def test_disabled_reranker_not_ready_and_retrieve_fails(monkeypatch) -> None:
    from offline_rag.rerank.status import hybrid_rerank_status_for_corpus

    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"enabled": False, "implementation": "fake"}
            )
        }
    )
    monkeypatch.setattr(
        "offline_rag.rerank.status.hybrid_status_for_corpus",
        lambda _settings, _name: "READY",
    )
    assert hybrid_rerank_status_for_corpus(settings, "default") == "NOT_READY"

    retriever = HybridRerankRetriever(
        settings, hybrid=MagicMock(), reranker=FakeReranker()
    )
    with pytest.raises(HybridRerankRetrievalError, match="disabled"):
        retriever.retrieve(query="q", corpus_name="default")


def test_empty_pool_skips_scoring() -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"implementation": "fake", "input_k": 5, "output_k": 3}
            )
        }
    )
    hybrid = MagicMock()
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="q",
        top_k=5,
        candidates=[],
        dense_index_id="d",
        lexical_index_id="l",
        fusion_config_hash="fuscfg_z",
        metadata={"chunk_set_id": "cs", "latency_ms": {"dense": 0}},
    )
    reranker = MagicMock()
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=reranker)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    result = retriever.retrieve(query="q")
    assert result.candidates == []
    assert result.metadata["input_pool_size"] == 0
    reranker.score_pairs.assert_not_called()
    assert result.metadata["latency_ms"]["rerank_infer"] == 0


def test_gold_in_rerank_pool_diagnostics(tmp_path) -> None:
    import json

    settings = AppSettings().model_copy(
        update={
            "paths": AppSettings().paths.model_copy(
                update={"eval_results": tmp_path / "eval"}
            ),
            "reranker": AppSettings().reranker.model_copy(
                update={"implementation": "fake", "input_k": 3, "output_k": 2}
            ),
        }
    )
    pool = [
        _hybrid_candidate("gold", rank=1, text="relevant"),
        _hybrid_candidate("other", rank=2, text="noise"),
        _hybrid_candidate("third", rank=3, text="more"),
    ]
    hybrid = MagicMock()
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="API pressure",
        top_k=3,
        candidates=pool,
        dense_index_id="d",
        lexical_index_id="l",
        fusion_config_hash="fuscfg_e",
        metadata={"chunk_set_id": "chunkset_eval", "latency_ms": {}},
    )
    reranker = FakeReranker(
        score_map={
            ("API pressure", "gold"): 0.5,
            ("API pressure", "other"): 2.0,
            ("API pressure", "third"): 1.0,
        }
    )
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=reranker)
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]

    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "meta.json").write_text(
        json.dumps({"schema_version": 1, "chunk_set_id": "chunkset_eval"}),
        encoding="utf-8",
    )
    (dataset_dir / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "query": "API pressure",
                "relevant_chunk_ids": ["gold"],
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "c2",
                "query": "API pressure",
                "relevant_chunk_ids": ["missing_gold"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    # Only one case at a time so we can swap pool membership for second case.
    # First evaluation with gold in pool.
    single = tmp_path / "single"
    single.mkdir()
    (single / "meta.json").write_text(
        (dataset_dir / "meta.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (single / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c1",
                "query": "API pressure",
                "relevant_chunk_ids": ["gold"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    evaluator = HybridRerankRetrievalEvaluator(settings, retriever=retriever)
    report = evaluator.evaluate(single, corpus_name="default", top_k=2, persist=True)
    assert report.method == "hybrid-rerank"
    assert report.cases[0].gold_in_rerank_pool is True
    assert report.cases[0].input_pool_size == 3
    assert report.reranker_config_hash.startswith("rrkcfg_")
    assert (settings.paths.eval_results / "hybrid-rerank-retrieval").exists()

    # Generation miss: gold not in hybrid prefix.
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="API pressure",
        top_k=3,
        candidates=pool[1:],  # no gold
        dense_index_id="d",
        lexical_index_id="l",
        fusion_config_hash="fuscfg_e",
        metadata={"chunk_set_id": "chunkset_eval", "latency_ms": {}},
    )
    miss = tmp_path / "miss"
    miss.mkdir()
    (miss / "meta.json").write_text(
        (dataset_dir / "meta.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (miss / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "c2",
                "query": "API pressure",
                "relevant_chunk_ids": ["gold"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    report2 = evaluator.evaluate(miss, corpus_name="default", top_k=2, persist=False)
    assert report2.cases[0].gold_in_rerank_pool is False
    assert report2.cases[0].input_pool_size == 2
