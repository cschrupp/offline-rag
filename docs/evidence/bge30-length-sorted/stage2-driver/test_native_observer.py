"""Deterministic tests for observer functions used by native Stage 2."""

import asyncio
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

import stage2_app_server as stage2

from offline_rag.api import workspaces as workspaces_api
from offline_rag.app.operations import OperationHandle, OperationRegistry
from offline_rag.app.runtime import ApplicationRuntime, ProcessResources
from offline_rag.app.traces import (
    ProductQueryTrace,
    ProductTraceExecutionSummary,
    ProductTraceIdentitySummary,
    ProductTraceRequestSummary,
)
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config import load_settings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.store import ChunkStructureStore
from offline_rag.domain.documents import Chunk
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    FusionProvenance,
    HybridCandidate,
    HybridRerankCandidate,
    HybridRerankContextResult,
    HybridRerankProvenance,
    HybridRetrievalResult,
)
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.protocol import ChatMessage, GeneratorRequest
from offline_rag.rerank import retrieve as rerank_retrieve
from offline_rag.rerank.cross_encoder import CrossEncoderReranker
from offline_rag.rerank.fake import FakeReranker
from offline_rag.rerank.protocol import RerankerPair
from offline_rag.rerank.retrieve import HybridRerankRetriever, _sort_scored


def _candidate(chunk_id, score):
    return HybridCandidate(
        rank=1,
        score=score,
        chunk_id=chunk_id,
        document_id="doc-1",
        text=f"safe fixture {chunk_id}",
        fusion=FusionProvenance(rrf_score=score, dense_rank=1, lexical_rank=1),
    )


def _context_result():
    anchor = HybridRerankCandidate(
        rank=1,
        score=0.9,
        chunk_id="chunk-1",
        document_id="doc-1",
        text="fixture context",
        hybrid_rerank=HybridRerankProvenance(
            reranker_score=0.9,
            hybrid_rank=1,
            rrf_score=0.8,
        ),
    )
    evidence = EvidenceUnit(
        evidence_unit_id="evidence-1",
        source_chunk_id="chunk-1",
        kind="child",
        text="fixture context",
        primary_anchor_chunk_id="chunk-1",
        contributing_anchor_chunk_ids=["chunk-1"],
        document_id="doc-1",
    )
    return HybridRerankContextResult(
        query="fixture question",
        evidence_units=[evidence],
        assembled_text="fixture context",
        context_token_count=3,
        max_context_tokens=64,
        context_config_hash="context-hash",
        anchors=[anchor],
        dense_index_id="dense-index",
        lexical_index_id="lexical-index",
        fusion_config_hash="fusion-hash",
        reranker_config_hash="reranker-hash",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=1,
            actual_anchor_count=1,
            anchors_processed=1,
            evidence_unit_count=1,
            context_token_count=3,
        ),
        metadata={
            "latency_ms": {
                "hybrid_rerank": 12,
                "context_expand": 3,
                "total": 15,
                "hybrid_rerank_breakdown": {
                    "hybrid": 8,
                    "pair_build": 1,
                    "rerank_infer": 5,
                    "sort": 1,
                    "total": 10,
                    "hybrid_breakdown": {
                        "dense": 2,
                        "lexical": 3,
                        "fusion": 1,
                        "total": 6,
                    },
                },
            },
            "reranker_execution": {"batching_strategy": "consecutive"},
        },
    )


def _trace():
    return ProductQueryTrace(
        trace_id="trace_0123456789abcdef0123456789abcdef",
        created_at=datetime.now(UTC),
        corpus="fixture-corpus",
        snapshot_id="fixture-snapshot",
        product_mode_id="grounded_v1",
        request=ProductTraceRequestSummary(
            question_sha256="question-hash",
            question_char_count=16,
        ),
        identity=ProductTraceIdentitySummary(
            corpus_id="corpus-id",
            chunk_set_id="chunk-set-id",
            dense_index_id="dense-id",
            lexical_index_id="lexical-id",
            fusion_config_hash="fusion-hash",
            reranker_config_hash="reranker-hash",
            context_config_hash="context-hash",
            generation_config_hash="generation-hash",
        ),
        status="answered",
        execution=ProductTraceExecutionSummary(
            citation_evidence_unit_ids=["evidence-1"],
            citation_document_ids=["doc-1"],
            citation_chunk_ids=["chunk-1"],
            citation_count=1,
            generator_invoked=True,
            attempt_count=1,
            context_latency_ms=15,
            generation_latency_ms=2,
            total_latency_ms=17,
        ),
    )


def _provider_fixture():
    path = (
        Path(__file__).resolve().parent.parent
        / "stage2-integration"
        / "provider_fixture.py"
    )
    spec = importlib.util.spec_from_file_location("stage2_test_provider_fixture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.respond


def test_native_observer_path_handles_canonical_rank_context_generation_and_citations(
    tmp_path, monkeypatch
):
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(stage2, "EVENTS", events_path)

    candidates = [_candidate("chunk-a", 0.1), _candidate("chunk-b", 0.9)]
    ordered = _sort_scored(candidates, [0.1, 0.9])
    assert [candidate.chunk_id for candidate, _score in ordered] == [
        "chunk-b",
        "chunk-a",
    ]
    stage2.observe_native_ranking(ordered, ordinal=1)

    context = _context_result()
    stage2.observe_native_context(context, ordinal=1)

    response = GeneratorRequest(
        messages=(
            ChatMessage(
                role="user",
                content="Answer with [EVIDENCE E1] only.",
            ),
        ),
        model="stage2-fixture",
        temperature=0,
        max_output_tokens=32,
    )
    generator = FakeGenerator(
        response_fn=lambda request: stage2.observe_fixture_generation(
            request, _provider_fixture()
        )
    )
    generated = generator.generate(response)
    assert json.loads(generated.content)["blocks"][0]["evidence_handles"] == ["E1"]
    stage2.observe_native_citations(
        SimpleNamespace(query_trace_id=_trace().trace_id), _trace(), ordinal=1
    )

    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert [row["event"] for row in rows] == [
        "native_ranked_candidates",
        "native_context",
        "synthetic_generator_invoked",
        "synthetic_generator_returned",
        "native_citations",
    ]
    assert rows[0]["ranked_candidate_order"] == [
        hashlib.sha256(b"chunk-b").hexdigest(),
        hashlib.sha256(b"chunk-a").hexdigest(),
    ]
    assert rows[1]["latency_ms"]["hybrid_rerank_breakdown"]["hybrid_breakdown"] == {
        "dense": 2,
        "lexical": 3,
        "fusion": 1,
        "total": 6,
    }
    assert rows[-1]["citation_chunk_count"] == 1
    assert rows[-1]["citation_evidence_unit_count"] == 1


def test_installed_native_observers_wrap_canonical_context_assembly(
    tmp_path, monkeypatch
):
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(stage2, "EVENTS", events_path)
    patch_points = (
        (OperationRegistry, "start_query_preflight"),
        (OperationRegistry, "promote_query_preflight"),
        (OperationRegistry, "claim_query_terminal"),
        (OperationRegistry, "release"),
        (OperationHandle, "signal_cancel"),
        (OperationHandle, "checkpoint"),
        (workspaces_api, "run_owned_worker"),
        (workspaces_api, "execute_prepared_conversation_turn"),
        (ApplicationRuntime, "wait_for_drain"),
        (ApplicationRuntime, "begin_drain"),
        (ProcessResources, "close"),
        (rerank_retrieve, "_sort_scored"),
        (HybridRerankContextAssembler, "assemble"),
    )
    for target, name in patch_points:
        monkeypatch.setattr(target, name, getattr(target, name))

    class FixtureApp:
        def add_middleware(self, *_args, **_kwargs):
            return None

        def post(self, *_args, **_kwargs):
            return lambda endpoint: endpoint

    settings = load_settings(overrides={"context": {"strategy": "child-only"}})
    fused = HybridRetrievalResult(
        query="fixture question",
        top_k=30,
        candidates=[_candidate("chunk-a", 0.1), _candidate("chunk-b", 0.2)],
        dense_index_id="dense-index",
        lexical_index_id="lexical-index",
        fusion_config_hash="fusion-hash",
        metadata={
            "corpus_id": "fixture-corpus",
            "chunk_set_id": "fixture-chunks",
            "latency_ms": {"dense": 2, "lexical": 3, "fusion": 1, "total": 6},
        },
    )

    class FixtureHybrid:
        def retrieve(self, **_kwargs):
            return fused

    children = {
        chunk_id: Chunk(
            chunk_id=chunk_id,
            document_id="doc-1",
            text=f"safe fixture {chunk_id}",
            order=index,
            token_count=3,
            content_hash=f"hash-{chunk_id}",
            source_block_ids=[f"block-{chunk_id}"],
        )
        for index, chunk_id in enumerate(("chunk-a", "chunk-b"))
    }
    store = ChunkStructureStore(
        children=children,
        parents={},
        chunk_set_id="fixture-chunks",
        corpus_id="fixture-corpus",
    )
    retriever = HybridRerankRetriever(
        settings,
        hybrid=FixtureHybrid(),
        reranker=FakeReranker(
            score_map={
                ("fixture question", "chunk-a"): 0.1,
                ("fixture question", "chunk-b"): 0.9,
            }
        ),
    )
    assembler = HybridRerankContextAssembler(
        settings,
        retriever=retriever,
        store=store,
        token_counter=FakeTokenCounter(),
    )
    assembler._require_ready = lambda _name: None
    runtime = SimpleNamespace(settings=settings, operations=SimpleNamespace())
    stage2.install_observers(
        FixtureApp(), runtime, {}, native_mode=True, strategy="consecutive"
    )
    token = stage2._ordinal.set(8)
    try:
        result = assembler.assemble(query="fixture question", check_ready=False)
    finally:
        stage2._ordinal.reset(token)

    assert [candidate.chunk_id for candidate in result.anchors] == [
        "chunk-b",
        "chunk-a",
    ]
    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert [row["event"] for row in rows] == [
        "native_ranked_candidates",
        "native_context",
    ]
    assert rows[0]["candidate_count"] == 2
    assert (
        rows[1]["context_sha256"]
        == hashlib.sha256(result.assembled_text.encode("utf-8")).hexdigest()
    )
    assert "latency_ms" in rows[1]


def test_worker_failure_diagnostics_capture_cause_frames_without_message_text():
    try:
        try:
            raise ValueError("private prompt text must not be recorded")
        except ValueError as cause:
            raise RuntimeError("outer failure") from cause
    except RuntimeError as error:
        diagnostics = stage2.exception_diagnostics(error)

    serialized = json.dumps(diagnostics)
    assert "RuntimeError" in serialized
    assert "ValueError" in serialized
    assert "private prompt text" not in serialized
    assert diagnostics["exception_chain"][1]["relation"] == "cause"


def test_native_scorer_observer_wraps_canonical_score_pairs_with_fixture_model(
    tmp_path, monkeypatch
):
    import torch

    events_path = tmp_path / "events.jsonl"
    monkeypatch.setattr(stage2, "EVENTS", events_path)

    class FixtureTokenizer:
        def encode(self, _text, *, add_special_tokens):
            assert add_special_tokens is False
            return [1]

        def num_special_tokens_to_add(self, *, pair):
            assert pair is True
            return 3

        def __call__(
            self,
            *,
            text,
            text_pair,
            truncation,
            max_length,
            padding,
            return_tensors,
            **kwargs,
        ):
            assert len(text) == len(text_pair)
            assert truncation == "only_second"
            assert max_length == 1024
            assert padding is True
            assert return_tensors == "pt"
            return {
                "input_ids": torch.ones((len(text), 4), dtype=torch.long),
                "attention_mask": torch.ones((len(text), 4), dtype=torch.long),
            }

    class FixtureModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(1.0))

        def forward(self, *, input_ids, attention_mask):
            logits = input_ids.sum(dim=1, keepdim=True).to(torch.float32) * self.weight
            return SimpleNamespace(logits=logits)

    model = FixtureModel().eval()
    tokenizer = FixtureTokenizer()
    scorer = CrossEncoderReranker.__new__(CrossEncoderReranker)
    scorer.batch_size = 1
    scorer.batching_strategy = "consecutive"
    scorer.max_length = 1024
    scorer.device = "cpu"
    scorer._tokenizer_lock = Lock()
    scorer._load = lambda: (tokenizer, model)

    original = CrossEncoderReranker.score_pairs
    previous_verified = stage2._native_model_verified
    stage2._native_model_verified = False
    try:
        stage2.install_native_scorer_observer({})
        pairs = [
            RerankerPair(
                chunk_id="chunk-a",
                query_text="query",
                passage_text="passage a",
            ),
            RerankerPair(
                chunk_id="chunk-b",
                query_text="query",
                passage_text="passage b",
            ),
        ]
        assert CrossEncoderReranker.score_pairs(scorer, pairs) == [4.0, 4.0]
    finally:
        CrossEncoderReranker.score_pairs = original
        stage2._native_model_verified = previous_verified

    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
    assert [row["event"] for row in rows] == [
        "scorer_entered",
        "forward_started",
        "forward_returned",
        "forward_started",
        "forward_returned",
        "native_scores",
        "scorer_returned",
    ]
    assert [row["shape"] for row in rows if row["event"] == "forward_started"] == [
        [1, 4],
        [1, 4],
    ]
    assert all(
        row["process_cpu_ms"] >= 0 for row in rows if row["event"] == "forward_returned"
    )


def test_native_http_observer_captures_sanitized_exception_chain(monkeypatch):
    events = []
    monkeypatch.setattr(
        stage2,
        "event",
        lambda kind, ordinal=None, **values: events.append(
            {"event": kind, "ordinal": ordinal, **values}
        ),
    )

    async def failing_app(_scope, _receive, _send):
        try:
            raise ValueError("untrusted response body")
        except ValueError as cause:
            raise RuntimeError("outer handler failure") from cause

    async def no_message():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def no_send(_message):
        return None

    try:
        asyncio.run(
            stage2.Stage2RequestObserver(failing_app)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/v1/workspaces/fixture/conversation/turn",
                    "headers": [(b"x-stage2-ordinal", b"7")],
                },
                no_message,
                no_send,
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("failing ASGI application did not propagate its error")

    assert len(events) == 2
    failure = events[-1]
    assert failure["event"] == "http_handler_raised"
    assert failure["ordinal"] == 7
    assert failure["exception"] == "RuntimeError"
    assert [item["exception_type"] for item in failure["exception_chain"]] == [
        "RuntimeError",
        "ValueError",
    ]
    serialized = json.dumps(failure)
    assert "untrusted response body" not in serialized
    assert "outer handler failure" not in serialized
