import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch
from pydantic import ValidationError
from test_context_expansion import _chunk

from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.loader import load_settings
from offline_rag.config.models import RerankerSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.store import ChunkStructureStore
from offline_rag.domain.indexing import (
    FusionProvenance,
    HybridCandidate,
    HybridRetrievalResult,
)
from offline_rag.rerank import cross_encoder
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.protocol import RerankerPair
from offline_rag.rerank.retrieve import (
    HybridRerankRetrievalError,
    HybridRerankRetriever,
)


class Tokenizer:
    def encode(self, text, *, add_special_tokens):
        assert not add_special_tokens
        return text.split()

    def __call__(self, *, text, text_pair, truncation, max_length, padding, **kwargs):
        assert truncation == "only_second"
        assert max_length == 1024
        rows = []
        for query, passage in zip(text, text_pair, strict=True):
            prefix = [1] + [2] * len(query.split()) + [3]
            ordinal, length = map(int, passage.split())
            rows.append(
                prefix
                + [ordinal + 10] * min(length, max_length - len(prefix) - 1)
                + [4]
            )
        if not padding:
            return {"input_ids": rows}
        assert kwargs["return_tensors"] == "pt"
        width = max(map(len, rows))
        ids = torch.tensor([row + [0] * (width - len(row)) for row in rows])
        mask = (ids != 0).long()
        return {
            "input_ids": ids,
            "attention_mask": mask,
            "position_ids": mask.cumsum(1) * mask,
        }


@pytest.fixture
def scorer(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cross_encoder, "require_reranker_artifacts", lambda *args, **kwargs: None
    )
    settings = RerankerSettings()
    scorer = cross_encoder.CrossEncoderReranker(
        model_path=tmp_path,
        model_id=settings.model.model_id,
        model_revision=settings.model.revision,
        adapter_contract=settings.model.adapter_contract,
        device="cpu",
    )
    return scorer


@pytest.mark.parametrize("count", [0, 1, 2, 5, 8, 10, 15, 16, 30, 35])
@pytest.mark.parametrize("lengths", [[10], [1100, 4, 28, 4, 500]])
def test_sorted_batching_preserves_encoded_pairs_and_raw_scores(scorer, count, lengths):
    pairs = [
        RerankerPair(str(i), "query text", f"{i} {lengths[i % len(lengths)]}")
        for i in range(count)
    ]
    seen = []
    batches = []

    def model(**encoded):
        assert torch.is_inference_mode_enabled()
        batch = []
        for ids, mask, positions in zip(*encoded.values(), strict=True):
            active = mask.bool()
            ordinal = int(ids[4]) - 10
            seen.append((ordinal, ids[active].tolist(), positions[active].tolist()))
            batch.append(ordinal)
        batches.append(batch)
        # Includes exact ties and near ties without changing score precision.
        return SimpleNamespace(
            logits=torch.tensor([[1 + (i % 3) * 2e-6] for i in batch])
        )

    scorer._loaded = (Tokenizer(), model)
    reference = scorer.score_pairs(pairs)
    baseline_rows = sorted(seen)
    seen.clear()
    batches.clear()
    scorer.batching_strategy = "length_sorted_8"
    actual = scorer.score_pairs(pairs)
    torch.testing.assert_close(
        torch.tensor(actual), torch.tensor(reference), atol=1e-4, rtol=1e-5
    )
    assert actual == reference
    assert sorted(seen) == baseline_rows
    expected = sorted(
        range(count), key=lambda i: (min(lengths[i % len(lengths)], 1019), i)
    )
    assert batches == [expected[i : i + 8] for i in range(0, count, 8)]
    assert all(
        len(row) == min(lengths[i % len(lengths)] + 5, 1024)
        for i, row, _ in baseline_rows
    )
    assert sorted(
        range(count), key=lambda i: (-actual[i], pairs[i].chunk_id)
    ) == sorted(range(count), key=lambda i: (-reference[i], pairs[i].chunk_id))


@pytest.mark.parametrize("strategy", ["consecutive", "length_sorted_8"])
@pytest.mark.parametrize(
    "logits,reason",
    [
        (torch.ones(2, 1), "single raw logit"),
        (torch.tensor([[float("nan")]]), "non-finite"),
    ],
)
def test_bad_logits_fail_closed(scorer, strategy, logits, reason):
    scorer.batching_strategy = strategy
    scorer._loaded = (Tokenizer(), lambda **_: SimpleNamespace(logits=logits))
    with pytest.raises(cross_encoder.CrossEncoderRerankerError, match=reason):
        scorer.score_pairs([RerankerPair("id", "query", "0 1")])


def test_invalid_pair_rejected_before_loading(scorer):
    with pytest.raises(
        cross_encoder.CrossEncoderRerankerError, match="invalid reranker pair"
    ):
        scorer.score_pairs([RerankerPair("id", "query", "")])


def test_execution_strategy_keeps_scientific_hash():
    baseline = RerankerSettings()
    assert baseline.batching_strategy == "consecutive"
    candidate = RerankerSettings(batching_strategy="length_sorted_8")
    assert baseline.input_k == candidate.input_k == 30
    assert build_reranker_config_hash(baseline) == build_reranker_config_hash(candidate)
    with pytest.raises(ValidationError):
        RerankerSettings(batching_strategy="other")


def test_sorted_strategy_preserves_canonical_ranking_and_packed_evidence(
    scorer, caplog
):
    caplog.set_level(logging.INFO)
    settings = load_settings(
        environ={"OFFLINE_RAG_RERANKER_BATCHING_STRATEGY": "length_sorted_8"},
        overrides={"context": {"strategy": "child-only"}},
    )
    assert settings.reranker.batching_strategy == "length_sorted_8"
    children = {f"id{i}": _chunk(f"id{i}", f"{i} {20 - i}") for i in range(10)}
    store = ChunkStructureStore(
        children=children, parents={}, chunk_set_id="chunks", corpus_id="corpus"
    )
    fused = HybridRetrievalResult(
        query="query",
        top_k=30,
        candidates=[
            HybridCandidate(
                rank=i,
                score=0.01,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                fusion=FusionProvenance(rrf_score=0.01, dense_rank=i, dense_score=0.9),
            )
            for i, chunk in enumerate(children.values(), 1)
        ],
        dense_index_id="dense",
        lexical_index_id="lexical",
        fusion_config_hash="fusion",
        metadata={"corpus_id": "corpus", "chunk_set_id": "chunks"},
    )

    def model(input_ids, **_):
        return SimpleNamespace(logits=(input_ids[:, 3:4] % 3).float())

    scorer._loaded = (Tokenizer(), model)
    scorer.configured_batching_strategy = settings.reranker.batching_strategy
    scorer.batching_strategy = settings.reranker.batching_strategy
    hybrid = Mock()
    hybrid.retrieve.return_value = fused
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=scorer)
    assembler = HybridRerankContextAssembler(
        settings, retriever=retriever, store=store, token_counter=FakeTokenCounter()
    )
    baseline_rank = retriever.retrieve(query="query", check_ready=False)
    baseline = assembler.assemble(query="query", check_ready=False)
    actual_rank = retriever.retrieve(query="query", check_ready=False)
    actual = assembler.assemble(query="query", check_ready=False)
    assert len(actual_rank.candidates) == 10
    assert actual_rank.candidates == baseline_rank.candidates
    assert actual.anchors == baseline.anchors
    assert actual.evidence_units == baseline.evidence_units
    assert actual.assembled_text == baseline.assembled_text
    assert actual.reranker_config_hash == baseline.reranker_config_hash
    assert actual.metadata["input_pool_chunk_ids"] == list(children)
    execution = actual.metadata["reranker_execution"]
    assert execution["batching_strategy"] == "length_sorted_8"
    assert execution["configured_batching_strategy"] == "length_sorted_8"
    assert execution["device"] == "cpu"
    assert execution["input_candidate_count"] == 10
    assert execution["output_candidate_count"] == 5
    assert execution["rss_scope"] == "process_lifetime_high_water"
    assert execution["process_peak_rss_bytes"] is None or isinstance(
        execution["process_peak_rss_bytes"], int
    )
    completed = [
        record for record in caplog.records if record.event == "reranker_completed"
    ]
    assert completed
    metrics = completed[-1].metrics
    assert metrics["batching_strategy"] == "length_sorted_8"
    assert metrics["configured_batching_strategy"] == "length_sorted_8"
    assert metrics["device"] == "cpu"
    assert metrics["candidate_count"] == 10
    assert metrics["returned_candidate_count"] == 5
    assert metrics["retrieval_latency_ms"] >= metrics["scorer_latency_ms"] >= 0
    assert metrics["rss_scope"] == "process_lifetime_high_water"


@pytest.mark.parametrize(
    ("resolved_device", "expected_strategy"),
    [("cpu", "length_sorted_8"), ("cuda", "consecutive")],
)
def test_configured_sorted_strategy_is_effective_only_on_cpu(
    monkeypatch, tmp_path, resolved_device, expected_strategy
):
    monkeypatch.setattr(cross_encoder, "_resolve_device", lambda _: resolved_device)
    monkeypatch.setattr(
        cross_encoder, "require_reranker_artifacts", lambda *args, **kwargs: None
    )
    settings = RerankerSettings(batching_strategy="length_sorted_8")
    scorer = cross_encoder.CrossEncoderReranker(
        model_path=tmp_path,
        model_id=settings.model.model_id,
        model_revision=settings.model.revision,
        adapter_contract=settings.model.adapter_contract,
        device="auto",
        batching_strategy=settings.batching_strategy,
    )
    assert scorer.configured_batching_strategy == "length_sorted_8"
    assert scorer.batching_strategy == expected_strategy


def test_failed_scorer_emits_failure_telemetry(scorer, caplog):
    settings = load_settings(yaml_paths=[], environ={})
    chunk = _chunk("failure", "1 4")
    fused = HybridRetrievalResult(
        query="query",
        top_k=30,
        candidates=[
            HybridCandidate(
                rank=1,
                score=0.01,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                text=chunk.text,
                fusion=FusionProvenance(rrf_score=0.01, dense_rank=1, dense_score=0.9),
            )
        ],
        dense_index_id="dense",
        lexical_index_id="lexical",
        fusion_config_hash="fusion",
        metadata={"corpus_id": "corpus", "chunk_set_id": "chunks"},
    )
    hybrid = Mock()
    hybrid.retrieve.return_value = fused

    def fail_scoring(**_):
        raise ValueError("fixture scorer failure")

    scorer._loaded = (Tokenizer(), fail_scoring)
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=scorer)

    with pytest.raises(HybridRerankRetrievalError, match="reranker scoring failed"):
        retriever.retrieve(query="query", check_ready=False)

    failed = next(
        record for record in caplog.records if record.event == "reranker_failed"
    )
    assert failed.error_type == "ValueError"
    assert failed.metrics["candidate_count"] == 1
    assert failed.metrics["scorer_latency_ms"] >= 0
    assert failed.metrics["retrieval_elapsed_ms"] >= failed.metrics["scorer_latency_ms"]
    assert failed.metrics["device"] == "cpu"
    assert failed.metrics["rss_scope"] == "process_lifetime_high_water"


def test_empty_candidate_pool_reports_retrieval_telemetry(scorer, caplog):
    caplog.set_level(logging.INFO)
    settings = load_settings(yaml_paths=[], environ={})
    fused = HybridRetrievalResult(
        query="query",
        top_k=30,
        candidates=[],
        dense_index_id="dense",
        lexical_index_id="lexical",
        fusion_config_hash="fusion",
        metadata={"corpus_id": "corpus", "chunk_set_id": "chunks"},
    )
    hybrid = Mock()
    hybrid.retrieve.return_value = fused
    retriever = HybridRerankRetriever(settings, hybrid=hybrid, reranker=scorer)

    result = retriever.retrieve(query="query", check_ready=False)

    execution = result.metadata["reranker_execution"]
    assert execution["scorer_invoked"] is False
    assert execution["input_candidate_count"] == 0
    event = next(
        record for record in caplog.records if record.event == "reranker_completed"
    )
    assert event.metrics["candidate_count"] == 0
    assert event.metrics["scorer_latency_ms"] == 0
    assert event.metrics["retrieval_latency_ms"] >= 0


@pytest.mark.parametrize("strategy", ["consecutive", "length_sorted_8"])
def test_shared_tokenizer_serializes_while_model_forward_can_overlap(scorer, strategy):
    first_tokenization = Barrier(2)
    forwards = Barrier(2)
    tokenizer_active = Lock()
    first_tokenization_seen = False

    class SharedTokenizer(Tokenizer):
        def __call__(self, **kwargs):
            nonlocal first_tokenization_seen
            assert scorer._tokenizer_lock.locked()
            assert tokenizer_active.acquire(blocking=False)
            try:
                if not first_tokenization_seen:
                    first_tokenization_seen = True
                    first_tokenization.wait(timeout=5)
                return super().__call__(**kwargs)
            finally:
                tokenizer_active.release()

    def model(input_ids, **_):
        forwards.wait(timeout=5)
        return SimpleNamespace(logits=input_ids[:, 3:4].float())

    scorer._loaded = (SharedTokenizer(), model)
    scorer.batching_strategy = strategy
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(scorer.score_pairs, [RerankerPair("a", "query", "0 17")])
        first_tokenization.wait(timeout=5)
        second = pool.submit(scorer.score_pairs, [RerankerPair("b", "query", "7 1")])
        assert first.result(timeout=10) == [10.0]
        assert second.result(timeout=10) == [17.0]
