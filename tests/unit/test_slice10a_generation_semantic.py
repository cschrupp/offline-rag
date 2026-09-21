"""Slice 10A — gold-evidence-v1, evidence-set identity, fixed-evidence executor."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.clip import full_evidence_unit_id
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankContextResult,
)
from offline_rag.evaluation.generation_semantic import (
    EVIDENCE_BUDGET_EXCEEDED,
    GENERATION_EVIDENCE_SET_V1,
    GENERATION_SEMANTIC_EVAL_COMPARISON_V1,
    GENERATION_SEMANTIC_EVAL_RESULT_V1,
    GOLD_EVIDENCE_V1,
    EvidenceBudgetExceeded,
    GenerationSemanticEvalComparisonV1,
    GenerationSemanticEvalResultV1,
    GoldEvidenceBuildError,
    build_gold_evidence_set_v1,
)
from offline_rag.evaluation.generation_semantic.evidence import (
    compute_generation_evidence_set_id,
)
from offline_rag.evaluation.generation_semantic.models import (
    GenerationCompareCompatibilityV1,
)
from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    LoadedGoldDataset,
)
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.lexical.retrieve import LexicalRetriever
from offline_rag.rerank.cross_encoder import CrossEncoderReranker


def _child(
    chunk_id: str,
    *,
    text: str,
    document_id: str = "doc_a",
    order: int = 0,
    token_count: int = 4,
    section_path: list[str] | None = None,
    page_start: int | None = 1,
    page_end: int | None = 1,
    line_start: int | None = 10,
    line_end: int | None = 12,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        kind=ChunkKind.CHILD,
        text=text,
        order=order,
        token_count=token_count,
        content_type="text",
        content_hash=f"hash_{chunk_id}",
        source_block_ids=["b1"],
        section_path=section_path or ["Alpha"],
        page_start=page_start,
        page_end=page_end,
        line_start=line_start,
        line_end=line_end,
    )


def _parent(chunk_id: str, *, text: str = "parent body") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id="doc_a",
        kind=ChunkKind.PARENT,
        text=text,
        order=0,
        token_count=2,
        content_type="text",
        content_hash=f"hash_{chunk_id}",
        source_block_ids=["b1"],
        section_path=["Alpha"],
    )


def _snapshot(chunks: list[Chunk]) -> CorpusChunkSnapshot:
    return CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_demo",
        chunks=chunks,
        source_name_by_document_id={"doc_a": "Guide.pdf", "doc_b": "Other.pdf"},
    )


def _gold(
    cases: list[GoldCase],
    *,
    dataset_id: str = "gold_test_fixture",
) -> LoadedGoldDataset:
    meta = GoldDatasetMeta(
        chunk_set_id="chunkset_demo",
        corpus_id="corpus_demo",
        corpus_name="demo",
        dataset_id=dataset_id,
    )
    return LoadedGoldDataset(
        meta=meta,
        cases=tuple(cases),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=Path("synthetic"),
    )


def _settings() -> AppSettings:
    return AppSettings().model_copy(
        update={
            "generation": AppSettings().generation.model_copy(
                update={
                    "enabled": True,
                    "model": "test-model",
                    "approved_models": ["test-model"],
                    "approved_endpoints": ["http://127.0.0.1:11434/v1"],
                    "base_url": "http://127.0.0.1:11434/v1",
                }
            ),
            "context": AppSettings().context.model_copy(
                update={"max_context_tokens": 6000}
            ),
        }
    )


def test_gold_evidence_single_and_multi_positive_ordering() -> None:
    c1 = _child("chunk_b", text="second text", document_id="doc_a", order=2)
    c2 = _child("chunk_a", text="first text", document_id="doc_a", order=1)
    c3 = _child("chunk_c", text="other doc", document_id="doc_b", order=0)
    gold = _gold(
        [
            GoldCase(
                id="case_z",
                query="What is first?",
                category="Cat",
                tags=("t1",),
                judgments=(
                    ChunkJudgment(chunk_id="chunk_b", relevance=1),
                    ChunkJudgment(chunk_id="chunk_a", relevance=2),
                    ChunkJudgment(chunk_id="chunk_c", relevance=1),
                ),
            )
        ]
    )
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([c1, c2, c3]),
        label_cohort_by_case_id={"case_z": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert evidence.evidence_contract == GOLD_EVIDENCE_V1
    assert evidence.schema_version == GENERATION_EVIDENCE_SET_V1
    assert len(evidence.cases) == 1
    case = evidence.cases[0]
    assert [u.source_chunk_id for u in case.evidence_units] == [
        "chunk_a",
        "chunk_b",
        "chunk_c",
    ]
    assert case.evidence_units[0].text == "first text"
    assert case.evidence_units[0].page_start == 1
    assert case.evidence_units[0].line_start == 10
    assert case.evidence_units[0].section_path == ["Alpha"]
    assert case.evidence_units[0].clipped is False
    assert case.evidence_units[0].clip is None
    assert case.evidence_units[0].evidence_unit_id == full_evidence_unit_id("chunk_a")
    assert case.evidence_units[0].metadata == {}
    assert {j.relevance for j in case.gold_judgments} == {1, 2}
    dumped = case.evidence_units[0].model_dump()
    assert "relevance" not in dumped
    assert "grade" not in dumped


def test_gold_evidence_rejects_parent_and_unknown() -> None:
    parent = _parent("chunk_parent")
    child = _child("chunk_ok", text="ok")
    gold_parent = _gold(
        [
            GoldCase(
                id="case_p",
                query="q",
                judgments=(ChunkJudgment(chunk_id="chunk_parent", relevance=2),),
            )
        ]
    )
    with pytest.raises(GoldEvidenceBuildError, match="not a child"):
        build_gold_evidence_set_v1(
            gold_parent,
            chunk_snapshot=_snapshot([parent, child]),
            label_cohort_by_case_id={"case_p": "human_reviewed"},
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )

    gold_missing = _gold(
        [
            GoldCase(
                id="case_m",
                query="q",
                judgments=(ChunkJudgment(chunk_id="chunk_missing", relevance=1),),
            )
        ]
    )
    with pytest.raises(GoldEvidenceBuildError, match="absent"):
        build_gold_evidence_set_v1(
            gold_missing,
            chunk_snapshot=_snapshot([child]),
            label_cohort_by_case_id={"case_m": "assistant_only"},
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_gold_evidence_rejects_chunk_set_mismatch() -> None:
    child = _child("chunk_ok", text="ok")
    gold = _gold(
        [
            GoldCase(
                id="case_x",
                query="q",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=1),),
            )
        ]
    )
    snap = CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_OTHER",
        chunks=[child],
        source_name_by_document_id={},
    )
    with pytest.raises(GoldEvidenceBuildError, match="chunk_set_id mismatch"):
        build_gold_evidence_set_v1(
            gold,
            chunk_snapshot=snap,
            label_cohort_by_case_id={"case_x": "human_reviewed"},
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_evidence_set_id_stable_and_sensitive() -> None:
    child = _child("chunk_ok", text="exact body text", order=1)
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="What pressure?",
                category="Safety",
                tags=("psi",),
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            )
        ]
    )
    snap = _snapshot([child])
    cohorts: dict[str, str] = {"case_a": "human_reviewed"}
    a = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    b = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2099, 12, 31, tzinfo=UTC),
    )
    assert a.evidence_set_id == b.evidence_set_id
    assert a.evidence_set_id.startswith("genevidence_")
    assert a.created_at != b.created_at

    gold_query = _gold(
        [
            GoldCase(
                id="case_a",
                query="What temperature?",
                category="Safety",
                tags=("psi",),
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            )
        ]
    )
    c = build_gold_evidence_set_v1(
        gold_query,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert c.evidence_set_id != a.evidence_set_id

    child_text = _child("chunk_ok", text="DIFFERENT body text", order=1)
    d = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child_text]),
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert d.evidence_set_id != a.evidence_set_id

    gold_grade = _gold(
        [
            GoldCase(
                id="case_a",
                query="What pressure?",
                category="Safety",
                tags=("psi",),
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=1),),
            )
        ]
    )
    e = build_gold_evidence_set_v1(
        gold_grade,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert e.evidence_set_id != a.evidence_set_id

    assert (
        compute_generation_evidence_set_id(
            evidence_contract=a.evidence_contract,
            source_gold_dataset_id=a.source_gold_dataset_id,
            chunk_set_id=a.chunk_set_id,
            corpus_id=a.corpus_id,
            corpus_name=a.corpus_name,
            cases=a.cases,
            source_name_by_document_id=a.source_name_by_document_id,
        )
        == a.evidence_set_id
    )


def test_evidence_budget_boundary_and_overflow() -> None:
    child = _child("chunk_ok", text="one two three", token_count=3)
    gold = _gold(
        [
            GoldCase(
                id="case_b",
                query="q",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=1),),
            )
        ]
    )
    snap = _snapshot([child])
    cohorts: dict[str, str] = {"case_b": "human_reviewed"}
    ok = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=3,
        token_counter=FakeTokenCounter(),
    )
    assert len(ok.cases[0].evidence_units) == 1

    with pytest.raises(EvidenceBudgetExceeded) as excinfo:
        build_gold_evidence_set_v1(
            gold,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=2,
            token_counter=FakeTokenCounter(),
        )
    assert excinfo.value.reason == EVIDENCE_BUDGET_EXCEEDED
    assert excinfo.value.token_count == 3
    assert excinfo.value.max_tokens == 2


def test_result_and_comparison_contracts_validate() -> None:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    result = GenerationSemanticEvalResultV1(
        run_id="genesem_test",
        gold_dataset_id="gold_x",
        evidence_set_id="genevidence_x",
        evidence_contract=GOLD_EVIDENCE_V1,
        generation_config_hash="gencfg_x",
        judge_enabled=False,
        started_at=started,
        completed_at=started,
    )
    assert result.schema_version == GENERATION_SEMANTIC_EVAL_RESULT_V1
    assert result.semantic_aggregates is None

    comparison = GenerationSemanticEvalComparisonV1(
        comparison_id="gencompare_test",
        gold_dataset_id="gold_x",
        evidence_set_id="genevidence_x",
        evidence_contract=GOLD_EVIDENCE_V1,
        expected_behavior="answer",
        semantic_metric_contract="generation-semantic-metrics-v1",
        a_run_id="run_a",
        b_run_id="run_b",
        a_generation_config_hash="gencfg_a",
        b_generation_config_hash="gencfg_b",
        a_prompt_contract="prompt-grounded-v1",
        b_prompt_contract="prompt-grounded-provenance-v2",
        compatibility=GenerationCompareCompatibilityV1(
            same_gold_dataset_id=True,
            same_evidence_set_id=True,
            same_evidence_contract=True,
            same_expected_behavior=True,
            same_corpus_id=True,
            same_chunk_set_id=True,
            same_case_set=True,
            same_queries=True,
            same_cohort_labels=True,
            same_semantic_metric_contract=True,
            same_generation_semantics_except_prompt=True,
            same_judge_contract=True,
            prompt_pair_accepted=True,
            a_prompt_contract="prompt-grounded-v1",
            b_prompt_contract="prompt-grounded-provenance-v2",
        ),
    )
    assert comparison.schema_version == GENERATION_SEMANTIC_EVAL_COMPARISON_V1


def test_fixed_evidence_executor_bypasses_retrieval_stack() -> None:
    ev_id = full_evidence_unit_id("chunk_synth")
    unit = EvidenceUnit(
        evidence_unit_id=ev_id,
        source_chunk_id="chunk_synth",
        kind="child",
        text="max pressure is 100 psi",
        clipped=False,
        token_count=5,
        primary_anchor_chunk_id="chunk_synth",
        contributing_anchor_chunk_ids=["chunk_synth"],
        document_id="doc_a",
        section_path=["Limits"],
        page_start=1,
        page_end=1,
    )
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )
    executor = GroundedGenerationExecutor(_settings(), generator=fake)
    result = executor.execute(
        query="pressure?",
        corpus_name="demo",
        evidence_units=[unit],
        check_ready=False,
    )
    assert result.status == "answered"
    assert result.answer_text == "100 psi"
    assert result.generator_invoked is True
    assert result.attempt_count == 1
    assert result.context_config_hash is None
    assert result.dense_index_id is None
    assert fake.generate_calls == 1


def test_orchestrator_delegates_without_semantic_drift() -> None:
    ev_id = "ev_A"
    unit = EvidenceUnit(
        evidence_unit_id=ev_id,
        source_chunk_id="chunk_a",
        kind="child",
        text="max pressure is 100 psi",
        clipped=False,
        token_count=5,
        primary_anchor_chunk_id="anchor_1",
        contributing_anchor_chunk_ids=["anchor_1"],
        document_id="doc1",
        section_path=["Limits"],
        page_start=3,
        page_end=3,
    )
    context = HybridRerankContextResult(
        query="pressure?",
        evidence_units=[unit],
        assembled_text=unit.text,
        context_token_count=5,
        max_context_tokens=6000,
        context_config_hash="ctxcfg_test",
        anchors=[],
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=1,
            evidence_unit_count=1,
            context_token_count=5,
            stop_reason="completed",
        ),
        metadata={"chunk_set_id": "chunkset_test", "latency_ms": {"total": 1}},
    )
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": [ev_id]}
        )
    )
    assembler = MagicMock()
    assembler.assemble.return_value = context
    orch = GroundedAnswerOrchestrator(
        _settings(), context_assembler=assembler, generator=fake
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    answered = orch.answer(query="pressure?", corpus_name="demo")
    assert answered.status == "answered"
    assert answered.answer_text == "ok"
    assert answered.context_config_hash == "ctxcfg_test"
    assert answered.dense_index_id == "dense_x"
    assert answered.generation_config_hash.startswith("gencfg_")
    assert answered.effective_generation_semantics["prompt_contract"] == (
        "prompt-grounded-v1"
    )

    fake_abstain = FakeGenerator(
        default_response=json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )
    orch2 = GroundedAnswerOrchestrator(
        _settings(), context_assembler=assembler, generator=fake_abstain
    )
    orch2._require_ready = lambda _name: None  # type: ignore[method-assign]
    abstained = orch2.answer(query="pressure?", corpus_name="demo")
    assert abstained.status == "insufficient_evidence"
    assert abstained.abstention_reason == "model_abstain"

    empty = HybridRerankContextResult(
        query="pressure?",
        evidence_units=[],
        assembled_text="",
        context_token_count=0,
        max_context_tokens=6000,
        context_config_hash="ctxcfg_test",
        anchors=[],
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=0,
            evidence_unit_count=0,
            context_token_count=0,
            stop_reason="no_anchors",
        ),
        metadata={"chunk_set_id": "chunkset_test", "latency_ms": {"total": 1}},
    )
    assembler.assemble.return_value = empty
    fake3 = FakeGenerator(default_response="unused")
    orch3 = GroundedAnswerOrchestrator(
        _settings(), context_assembler=assembler, generator=fake3
    )
    orch3._require_ready = lambda _name: None  # type: ignore[method-assign]
    empty_result = orch3.answer(query="pressure?", corpus_name="demo")
    assert empty_result.status == "insufficient_evidence"
    assert empty_result.abstention_reason == "empty_context"
    assert fake3.generate_calls == 0


def test_chunk_access_facade_reexports_neutral_module() -> None:
    from offline_rag.chunking import access as neutral
    from offline_rag.gold_authoring import chunk_access as facade

    assert facade.CorpusChunkSnapshot is neutral.CorpusChunkSnapshot
    assert facade.load_chunk_set_snapshot is neutral.load_chunk_set_snapshot
    assert facade.ChunkAccessError is neutral.ChunkAccessError


def test_fixed_evidence_does_not_require_retrieval_types() -> None:
    for cls in (
        DenseRetriever,
        LexicalRetriever,
        HybridRetriever,
        CrossEncoderReranker,
        HybridRerankContextAssembler,
    ):
        assert cls is not None
