"""Slice 10B — deterministic generation/citation eval, readiness, persistence, CLI."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.chunking.access import CorpusChunkSnapshot
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.cli import build_parser, main
from offline_rag.config.models import AppSettings, GenerationPromptSettings
from offline_rag.context.clip import full_evidence_unit_id
from offline_rag.core.ids import (
    PROMPT_GROUNDED_PROVENANCE_V2,
    gold_dataset_id_from_payload,
)
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.evaluation.generation_semantic import (
    GENERATION_COHORT_MAP_V1,
    GENERATION_SEMANTIC_DETERMINISTIC_V1,
    CohortMapError,
    GenerationSemanticEvaluationError,
    GenerationSemanticEvaluator,
    build_gold_evidence_set_v1,
    load_cohort_map,
    run_generation_semantic_evaluation,
    validate_cohort_map_for_gold,
)
from offline_rag.evaluation.generation_semantic.metrics import (
    build_deterministic_aggregates,
    build_population,
    compute_case_deterministic_metrics,
)
from offline_rag.evaluation.generation_semantic.models import (
    GenerationCohortMapCaseV1,
    GenerationCohortMapV1,
    GenerationEvidenceCaseV1,
    GenerationSemanticEvalCaseResultV1,
    GoldEvidenceJudgmentV1,
)
from offline_rag.evaluation.generation_semantic.persistence import (
    GenerationSemanticPersistenceError,
    persist_evidence_set,
)
from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    LoadedGoldDataset,
    gold_semantic_payload,
)
from offline_rag.generation.config_hash import build_generation_semantic_payload
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.status import (
    generation_provider_status,
    generation_status_for_corpus,
)


def _child(
    chunk_id: str,
    *,
    text: str,
    document_id: str = "doc_a",
    order: int = 0,
    token_count: int = 4,
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
        section_path=["Alpha"],
        page_start=1,
        page_end=1,
        line_start=10,
        line_end=12,
    )


def _snapshot(
    chunks: list[Chunk],
    *,
    sources: dict[str, str] | None = None,
) -> CorpusChunkSnapshot:
    return CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_demo",
        chunks=chunks,
        source_name_by_document_id=sources
        or {"doc_a": "Guide.pdf", "doc_b": "Other.pdf"},
    )


def _gold(
    cases: list[GoldCase],
    *,
    dataset_id: str = "gold_test_10b",
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


def _settings(*, prompt_contract: str | None = None) -> AppSettings:
    base = AppSettings()
    gen_update: dict[str, object] = {
        "enabled": True,
        "model": "test-model",
        "approved_models": ["test-model"],
        "approved_endpoints": ["http://127.0.0.1:11434/v1"],
        "base_url": "http://127.0.0.1:11434/v1",
    }
    if prompt_contract == PROMPT_GROUNDED_PROVENANCE_V2:
        gen_update["prompt"] = GenerationPromptSettings(
            strategy="grounded_provenance",
            contract_version=PROMPT_GROUNDED_PROVENANCE_V2,
        )
    elif prompt_contract is not None:
        gen_update["prompt"] = GenerationPromptSettings(
            strategy="grounded",
            contract_version=prompt_contract,
        )
    return base.model_copy(
        update={
            "generation": base.generation.model_copy(update=gen_update),
            "context": base.context.model_copy(update={"max_context_tokens": 6000}),
        }
    )


def _unit(
    chunk_id: str,
    text: str,
    *,
    document_id: str = "doc_a",
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=full_evidence_unit_id(chunk_id),
        source_chunk_id=chunk_id,
        kind="child",
        text=text,
        clipped=False,
        token_count=len(text.split()),
        primary_anchor_chunk_id=chunk_id,
        contributing_anchor_chunk_ids=[chunk_id],
        document_id=document_id,
        section_path=["Alpha"],
        page_start=1,
        page_end=1,
    )


def _citation(chunk_id: str, *, document_id: str = "doc_a") -> ResolvedCitation:
    return ResolvedCitation(
        evidence_unit_id=full_evidence_unit_id(chunk_id),
        source_chunk_id=chunk_id,
        document_id=document_id,
        kind="child",
        clipped=False,
        primary_anchor_chunk_id=chunk_id,
        section_path=["Alpha"],
    )


def _case_result(
    *,
    case_id: str,
    status: str,
    label_cohort: str = "human_reviewed",
    abstention_reason: str | None = None,
    gold_judgments: list[GoldEvidenceJudgmentV1] | None = None,
    citations: list[ResolvedCitation] | None = None,
    cited_evidence_count: int | None = None,
) -> tuple[GenerationEvidenceCaseV1, GenerationSemanticEvalCaseResultV1]:
    judgments = gold_judgments or [
        GoldEvidenceJudgmentV1(chunk_id="chunk_a", relevance=2)
    ]
    evidence_case = GenerationEvidenceCaseV1(
        case_id=case_id,
        query=f"query-{case_id}",
        label_cohort=label_cohort,  # type: ignore[arg-type]
        evidence_units=[_unit(j.chunk_id, "text") for j in judgments],
        gold_judgments=judgments,
    )
    resolved = citations or []
    ga = GroundedAnswerResult(
        method="query",
        query=evidence_case.query,
        status=status,  # type: ignore[arg-type]
        answer_text="ans" if status == "answered" else None,
        citations=resolved,
        abstention_reason=abstention_reason,  # type: ignore[arg-type]
        generation_config_hash="gencfg_x",
        effective_generation_semantics={},
        generator_invoked=True,
        attempt_count=1,
    )
    metrics = compute_case_deterministic_metrics(evidence_case, ga)
    if cited_evidence_count is not None:
        metrics = metrics.model_copy(
            update={"cited_evidence_count": cited_evidence_count}
        )
    row = GenerationSemanticEvalCaseResultV1(
        case_id=case_id,
        query=evidence_case.query,
        label_cohort=label_cohort,  # type: ignore[arg-type]
        status=status,
        abstention_reason=abstention_reason,
        deterministic_metrics=metrics,
        latency_ms=10,
        generation_latency_ms=5,
    )
    return evidence_case, row


# ---------------------------------------------------------------------------
# Frozen provenance
# ---------------------------------------------------------------------------


def test_frozen_source_map_persisted_and_in_identity() -> None:
    child = _child("chunk_ok", text="pressure is 100 psi", order=1)
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="What pressure?",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            )
        ]
    )
    snap = _snapshot([child], sources={"doc_a": "Guide.pdf"})
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert evidence.source_name_by_document_id == {"doc_a": "Guide.pdf"}

    same = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    assert same.evidence_set_id == evidence.evidence_set_id

    renamed = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child], sources={"doc_a": "Guide-RENAMED.pdf"}),
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert renamed.evidence_set_id != evidence.evidence_set_id
    assert renamed.source_name_by_document_id == {"doc_a": "Guide-RENAMED.pdf"}


def test_provenance_v2_uses_frozen_map_not_current_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(prompt_contract=PROMPT_GROUNDED_PROVENANCE_V2)
    unit = _unit("chunk_ok", "pressure is 100 psi", document_id="doc_a")
    ev_id = unit.evidence_unit_id
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )
    executor = GroundedGenerationExecutor(settings, generator=fake)

    def _boom(_self: object, _corpus_name: str) -> dict[str, str]:
        raise AssertionError("should not load current corpus metadata")

    monkeypatch.setattr(
        GroundedGenerationExecutor,
        "_load_source_name_by_document_id",
        _boom,
    )
    result = executor.execute(
        query="pressure?",
        corpus_name="demo",
        evidence_units=[unit],
        check_ready=False,
        source_name_by_document_id={"doc_a": "FrozenGuide.pdf"},
    )
    assert result.status == "answered"
    assert fake.generate_calls == 1
    # Capture last request content via response_fn style — FakeGenerator stores calls only.
    # Re-run with response_fn to inspect prompt title.
    seen: list[str] = []

    def _capture(request):  # type: ignore[no-untyped-def]
        seen.append(request.messages[1].content)
        return json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )

    fake2 = FakeGenerator(response_fn=_capture)
    executor2 = GroundedGenerationExecutor(settings, generator=fake2)
    monkeypatch.setattr(
        GroundedGenerationExecutor,
        "_load_source_name_by_document_id",
        _boom,
    )
    executor2.execute(
        query="pressure?",
        corpus_name="demo",
        evidence_units=[unit],
        check_ready=False,
        source_name_by_document_id={"doc_a": "FrozenGuide.pdf"},
    )
    assert "FrozenGuide" in seen[0]


def test_slice8_executor_without_map_uses_current_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(prompt_contract=PROMPT_GROUNDED_PROVENANCE_V2)
    unit = _unit("chunk_ok", "pressure is 100 psi", document_id="doc_a")
    ev_id = unit.evidence_unit_id
    seen: list[str] = []

    def _capture(request):  # type: ignore[no-untyped-def]
        seen.append(request.messages[1].content)
        return json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )

    fake = FakeGenerator(response_fn=_capture)
    executor = GroundedGenerationExecutor(settings, generator=fake)
    monkeypatch.setattr(
        GroundedGenerationExecutor,
        "_load_source_name_by_document_id",
        lambda _self, _name: {"doc_a": "CurrentCorpus.pdf"},
    )
    result = executor.execute(
        query="pressure?",
        corpus_name="demo",
        evidence_units=[unit],
        check_ready=False,
    )
    assert result.status == "answered"
    assert "CurrentCorpus" in seen[0]


# ---------------------------------------------------------------------------
# Provider readiness
# ---------------------------------------------------------------------------


def test_provider_ready_while_context_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()

    class _ProbeOk:
        def probe(self):  # type: ignore[no-untyped-def]
            from offline_rag.generation.protocol import GeneratorProbeResult

            return GeneratorProbeResult(
                ok=True, reason="ok", available_models=("test-model",)
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "offline_rag.generation.status.OpenAICompatibleGenerator",
        lambda _settings: _ProbeOk(),
    )
    monkeypatch.setattr(
        "offline_rag.generation.status.context_status_for_corpus",
        lambda _s, _n: "NOT_READY",
    )
    assert generation_provider_status(settings) == "READY"
    assert generation_status_for_corpus(settings, "demo") == "NOT_READY"

    child = _child("chunk_ok", text="pressure is 100 psi", order=1)
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="pressure?",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            )
        ]
    )
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child]),
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
    )
    ev_id = evidence.cases[0].evidence_units[0].evidence_unit_id
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )
    evaluator = GenerationSemanticEvaluator(
        settings, executor=GroundedGenerationExecutor(settings, generator=fake)
    )
    result = evaluator.evaluate(evidence, corpus_name="demo")
    assert result.population.answered == 1
    assert result.semantic_aggregates is None
    evaluator.close()


# ---------------------------------------------------------------------------
# Per-case metrics
# ---------------------------------------------------------------------------


def test_case_metrics_answered_recall_and_grade2() -> None:
    judgments = [
        GoldEvidenceJudgmentV1(chunk_id="chunk_a", relevance=2),
        GoldEvidenceJudgmentV1(chunk_id="chunk_b", relevance=1),
    ]
    case = GenerationEvidenceCaseV1(
        case_id="c1",
        query="q",
        label_cohort="human_reviewed",
        evidence_units=[_unit("chunk_a", "a"), _unit("chunk_b", "b")],
        gold_judgments=judgments,
    )
    citations = [_citation("chunk_a")]
    answered = GroundedAnswerResult(
        method="query",
        query="q",
        status="answered",
        answer_text="a",
        citations=citations,
        generation_config_hash="gencfg_x",
        effective_generation_semantics={},
        generator_invoked=True,
        attempt_count=1,
    )
    m = compute_case_deterministic_metrics(case, answered)
    assert m.gold_citation_recall == 0.5
    assert m.grade2_citation_hit is True
    assert m.cited_gold_chunk_ids == ["chunk_a"]

    both = [_citation("chunk_a"), _citation("chunk_b")]
    answered_both = answered.model_copy(update={"citations": both})
    m2 = compute_case_deterministic_metrics(case, answered_both)
    assert m2.gold_citation_recall == 1.0

    only_b = [_citation("chunk_b")]
    answered_b = answered.model_copy(update={"citations": only_b})
    m3 = compute_case_deterministic_metrics(case, answered_b)
    assert m3.gold_citation_recall == 0.5
    assert m3.grade2_citation_hit is False

    grade1_only = GenerationEvidenceCaseV1(
        case_id="c2",
        query="q",
        label_cohort="assistant_only",
        evidence_units=[_unit("chunk_b", "b")],
        gold_judgments=[GoldEvidenceJudgmentV1(chunk_id="chunk_b", relevance=1)],
    )
    m4 = compute_case_deterministic_metrics(grade1_only, answered_b)
    assert m4.grade2_citation_hit is None
    assert m4.gold_citation_recall == 1.0

    abstain = GroundedAnswerResult(
        method="query",
        query="q",
        status="insufficient_evidence",
        abstention_reason="model_abstain",
        citations=[],
        generation_config_hash="gencfg_x",
        effective_generation_semantics={},
        generator_invoked=True,
        attempt_count=1,
    )
    m5 = compute_case_deterministic_metrics(case, abstain)
    assert m5.gold_citation_recall is None
    assert m5.grade2_citation_hit is None


def test_case_metrics_failure_modes_null_recall() -> None:
    case = GenerationEvidenceCaseV1(
        case_id="c1",
        query="q",
        label_cohort="human_reviewed",
        evidence_units=[_unit("chunk_a", "a")],
        gold_judgments=[GoldEvidenceJudgmentV1(chunk_id="chunk_a", relevance=2)],
    )
    for status in ("generation_failed", "citation_invalid"):
        result = GroundedAnswerResult(
            method="query",
            query="q",
            status=status,  # type: ignore[arg-type]
            generation_failure_reason=(
                "transport_error" if status == "generation_failed" else None
            ),
            citations=[],
            generation_config_hash="gencfg_x",
            effective_generation_semantics={},
            generator_invoked=True,
            attempt_count=1,
        )
        metrics = compute_case_deterministic_metrics(case, result)
        assert metrics.gold_citation_recall is None
        assert metrics.grade2_citation_hit is None


# ---------------------------------------------------------------------------
# Aggregates + cohorts
# ---------------------------------------------------------------------------


def test_aggregates_and_cohorts() -> None:
    rows: list[GenerationSemanticEvalCaseResultV1] = []
    # answered human
    _, r1 = _case_result(
        case_id="h1",
        status="answered",
        label_cohort="human_reviewed",
        citations=[_citation("chunk_a")],
    )
    rows.append(r1)
    # false abstain human
    _, r2 = _case_result(
        case_id="h2",
        status="insufficient_evidence",
        label_cohort="human_reviewed",
        abstention_reason="model_abstain",
    )
    rows.append(r2)
    # generation failed assistant
    _, r3 = _case_result(
        case_id="a1",
        status="generation_failed",
        label_cohort="assistant_only",
    )
    rows.append(r3)
    # citation invalid assistant
    _, r4 = _case_result(
        case_id="a2",
        status="citation_invalid",
        label_cohort="assistant_only",
    )
    rows.append(r4)

    pop = build_population(rows)
    assert pop.total_cases == 4
    assert pop.answered == 1
    assert pop.model_abstain == 1
    assert pop.generation_failed == 1
    assert pop.citation_invalid == 1
    assert pop.human_reviewed_cases == 2
    assert pop.assistant_only_cases == 2

    agg = build_deterministic_aggregates(rows)
    assert agg.metric_contract == GENERATION_SEMANTIC_DETERMINISTIC_V1
    assert agg.answer_rate == 0.25
    assert agg.false_abstention_rate == 0.25
    assert agg.generation_failed_rate == 0.25
    assert agg.citation_invalid_rate == 0.25
    assert agg.mean_gold_citation_recall.applicable_count == 1
    assert agg.mean_gold_citation_recall.value == 1.0
    assert agg.grade2_citation_hit_rate.applicable_count == 1
    assert agg.grade2_citation_hit_rate.value == 1.0
    assert agg.cohorts["full"].case_count == 4
    assert agg.cohorts["human_reviewed"].case_count == 2
    assert agg.cohorts["assistant_only"].case_count == 2
    assert agg.cohorts["human_reviewed"].answer_rate == 0.5
    assert agg.cohorts["assistant_only"].answer_rate == 0.0


def test_empty_cohort_rates_null() -> None:
    _, only_human = _case_result(case_id="h1", status="answered")
    agg = build_deterministic_aggregates([only_human])
    empty = agg.cohorts["assistant_only"]
    assert empty.case_count == 0
    assert empty.answer_rate is None
    assert empty.false_abstention_rate is None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_evidence_persistence_reuse_and_conflict(tmp_path: Path) -> None:
    child = _child("chunk_ok", text="pressure is 100 psi", order=1)
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="What pressure?",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            )
        ]
    )
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child]),
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    path = tmp_path / "evidence" / f"{evidence.evidence_set_id}.json"
    assert persist_evidence_set(evidence, path=path) == path
    assert path.exists()
    # identical rebuild → reuse
    again = evidence.model_copy(update={"created_at": datetime(2099, 1, 1, tzinfo=UTC)})
    assert persist_evidence_set(again, path=path) == path

    # Same ID on disk with divergent semantic contents → hard fail
    divergent = evidence.model_copy(
        update={
            "cases": [evidence.cases[0].model_copy(update={"query": "DIFFERENT QUERY"})]
        }
    )
    path.write_text(divergent.model_dump_json(), encoding="utf-8")
    with pytest.raises(GenerationSemanticPersistenceError, match="collision"):
        persist_evidence_set(evidence, path=path)


def test_result_persistence_records_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={"eval_results": tmp_path / "eval_results"}
            )
        }
    )
    child = _child("chunk_ok", text="pressure is 100 psi", order=1)
    snap = _snapshot([child])
    payload_cases = [
        GoldCase(
            id="case_a",
            query="pressure?",
            judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
        )
    ]
    dataset_id = gold_dataset_id_from_payload(
        gold_semantic_payload(
            chunk_set_id="chunkset_demo",
            corpus_id="corpus_demo",
            corpus_name="demo",
            cases=payload_cases,
        )
    )
    ds = tmp_path / "gold"
    ds.mkdir()
    (ds / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": "offline-rag-gold-v1",
                "chunk_set_id": "chunkset_demo",
                "corpus_id": "corpus_demo",
                "corpus_name": "demo",
                "dataset_id": dataset_id,
            }
        ),
        encoding="utf-8",
    )
    (ds / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "case_a",
                "query": "pressure?",
                "judgments": [{"chunk_id": "chunk_ok", "relevance": 2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cohort_path = tmp_path / "cohort.json"
    cohort_path.write_text(
        GenerationCohortMapV1(
            schema_version=GENERATION_COHORT_MAP_V1,
            gold_dataset_id=dataset_id,
            cases=[
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="human_reviewed"
                )
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )
    gold_loaded = LoadedGoldDataset(
        meta=GoldDatasetMeta(
            chunk_set_id="chunkset_demo",
            corpus_id="corpus_demo",
            corpus_name="demo",
            dataset_id=dataset_id,
        ),
        cases=tuple(payload_cases),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=ds,
    )
    evidence = build_gold_evidence_set_v1(
        gold_loaded,
        chunk_snapshot=snap,
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
    )
    ev_id = evidence.cases[0].evidence_units[0].evidence_unit_id
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "READY",
    )
    result = run_generation_semantic_evaluation(
        settings,
        dataset_path=ds,
        cohort_map_path=cohort_path,
        corpus_name="demo",
        executor=GroundedGenerationExecutor(settings, generator=fake),
        chunk_snapshot=snap,
        token_counter=FakeTokenCounter(),
    )
    assert result.metadata["evidence_path"]
    assert result.metadata["result_path"]
    assert Path(result.metadata["evidence_path"]).exists()
    assert Path(result.metadata["result_path"]).exists()
    assert result.semantic_aggregates is None
    assert result.judge_enabled is False
    loaded = json.loads(
        Path(result.metadata["result_path"]).read_text(encoding="utf-8")
    )
    assert loaded["run_id"] == result.run_id
    assert "provider" in result.generation_semantic_provenance
    assert (
        build_generation_semantic_payload(settings)["model"]
        == (result.generation_semantic_provenance["model"])
    )


# ---------------------------------------------------------------------------
# Cohort map
# ---------------------------------------------------------------------------


def test_cohort_map_validation(tmp_path: Path) -> None:
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="q1",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
            ),
            GoldCase(
                id="case_b",
                query="q2",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=1),),
            ),
        ]
    )
    valid = GenerationCohortMapV1(
        schema_version=GENERATION_COHORT_MAP_V1,
        gold_dataset_id=gold.dataset_id,
        cases=[
            GenerationCohortMapCaseV1(case_id="case_a", label_cohort="human_reviewed"),
            GenerationCohortMapCaseV1(case_id="case_b", label_cohort="assistant_only"),
        ],
    )
    path = tmp_path / "map.json"
    path.write_text(valid.model_dump_json(), encoding="utf-8")
    loaded = load_cohort_map(path)
    mapping = validate_cohort_map_for_gold(loaded, gold)
    assert mapping == {"case_a": "human_reviewed", "case_b": "assistant_only"}

    missing = valid.model_copy(update={"cases": valid.cases[:1]})
    with pytest.raises(CohortMapError, match="missing"):
        validate_cohort_map_for_gold(missing, gold)

    unknown = valid.model_copy(
        update={
            "cases": list(valid.cases)
            + [
                GenerationCohortMapCaseV1(
                    case_id="case_z", label_cohort="human_reviewed"
                )
            ]
        }
    )
    with pytest.raises(CohortMapError, match="unknown"):
        validate_cohort_map_for_gold(unknown, gold)

    dup = valid.model_copy(
        update={
            "cases": [
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="human_reviewed"
                ),
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="assistant_only"
                ),
            ]
        }
    )
    with pytest.raises(CohortMapError, match="duplicate"):
        validate_cohort_map_for_gold(dup, gold)

    wrong_id = valid.model_copy(update={"gold_dataset_id": "gold_other"})
    with pytest.raises(CohortMapError, match="gold_dataset_id"):
        validate_cohort_map_for_gold(wrong_id, gold)


# ---------------------------------------------------------------------------
# Evaluator outcome modes via FakeGenerator
# ---------------------------------------------------------------------------


def test_evaluator_outcome_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "READY",
    )
    child_a = _child("chunk_a", text="A text", order=1)
    child_b = _child("chunk_b", text="B text", order=2)
    gold = _gold(
        [
            GoldCase(
                id="ans1",
                query="one cite",
                judgments=(ChunkJudgment(chunk_id="chunk_a", relevance=2),),
            ),
            GoldCase(
                id="ans2",
                query="two cite",
                judgments=(
                    ChunkJudgment(chunk_id="chunk_a", relevance=2),
                    ChunkJudgment(chunk_id="chunk_b", relevance=1),
                ),
            ),
            GoldCase(
                id="abs1",
                query="abstain",
                judgments=(ChunkJudgment(chunk_id="chunk_a", relevance=2),),
            ),
            GoldCase(
                id="fail1",
                query="fail",
                judgments=(ChunkJudgment(chunk_id="chunk_a", relevance=2),),
            ),
            GoldCase(
                id="badcite",
                query="badcite",
                judgments=(ChunkJudgment(chunk_id="chunk_a", relevance=2),),
            ),
        ]
    )
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child_a, child_b]),
        label_cohort_by_case_id={
            "ans1": "human_reviewed",
            "ans2": "human_reviewed",
            "abs1": "assistant_only",
            "fail1": "assistant_only",
            "badcite": "assistant_only",
        },
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
    )
    by_case = {c.case_id: c for c in evidence.cases}
    ev_a = by_case["ans1"].evidence_units[0].evidence_unit_id
    ev_b = by_case["ans2"].evidence_units[1].evidence_unit_id

    def _response_fn(request):  # type: ignore[no-untyped-def]
        user = request.messages[1].content
        query = user.split("QUERY:\n", 1)[1].split("\n\n", 1)[0]
        if query == "one cite":
            return json.dumps({"abstain": False, "answer": "A", "citation_ids": [ev_a]})
        if query == "two cite":
            return json.dumps(
                {
                    "abstain": False,
                    "answer": "A and B",
                    "citation_ids": [ev_a, ev_b],
                }
            )
        if query == "abstain":
            return json.dumps({"abstain": True, "answer": None, "citation_ids": []})
        if query == "fail":
            return "not-json"
        if query == "badcite":
            return json.dumps(
                {"abstain": False, "answer": "x", "citation_ids": ["ev_missing"]}
            )
        raise AssertionError(query)

    fake = FakeGenerator(response_fn=_response_fn)
    evaluator = GenerationSemanticEvaluator(
        settings, executor=GroundedGenerationExecutor(settings, generator=fake)
    )
    result = evaluator.evaluate(evidence)
    by_id = {c.case_id: c for c in result.cases}
    assert by_id["ans1"].status == "answered"
    assert by_id["ans1"].deterministic_metrics.gold_citation_recall == 1.0
    assert by_id["ans2"].deterministic_metrics.gold_citation_recall == 1.0
    assert by_id["abs1"].status == "insufficient_evidence"
    assert by_id["abs1"].abstention_reason == "model_abstain"
    assert by_id["abs1"].deterministic_metrics.gold_citation_recall is None
    assert by_id["fail1"].status == "generation_failed"
    assert by_id["badcite"].status == "citation_invalid"
    assert result.population.answered == 2
    assert result.population.model_abstain == 1
    assert result.population.generation_failed == 1
    assert result.population.citation_invalid == 1
    evaluator.close()


def test_provider_not_ready_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings()
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "NOT_READY",
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.describe_generation_provider_status",
        lambda _s: {"status": "NOT_READY", "reasons": ["probe failed"]},
    )
    child = _child("chunk_ok", text="x", order=1)
    gold = _gold(
        [
            GoldCase(
                id="case_a",
                query="q",
                judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=1),),
            )
        ]
    )
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=_snapshot([child]),
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
    )
    evaluator = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(
            settings, generator=FakeGenerator(default_response="{}")
        ),
    )
    with pytest.raises(GenerationSemanticEvaluationError, match="unavailable"):
        evaluator.evaluate(evidence)
    evaluator.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_eval_generation_parser_surface() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "eval",
            "generation",
            "--dataset",
            "ds",
            "--cohort-map",
            "map.json",
            "--corpus",
            "demo",
            "--json",
        ]
    )
    assert args.func.__name__ == "cmd_eval_generation"
    assert args.evidence_mode == "gold"


def test_cli_eval_generation_success_and_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={"eval_results": tmp_path / "eval_results"}
            )
        }
    )
    cases = [
        GoldCase(
            id="case_a",
            query="pressure?",
            judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
        )
    ]
    dataset_id = gold_dataset_id_from_payload(
        gold_semantic_payload(
            chunk_set_id="chunkset_demo",
            corpus_id="corpus_demo",
            corpus_name="demo",
            cases=cases,
        )
    )
    ds = tmp_path / "gold"
    ds.mkdir()
    (ds / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": "offline-rag-gold-v1",
                "chunk_set_id": "chunkset_demo",
                "corpus_id": "corpus_demo",
                "corpus_name": "demo",
                "dataset_id": dataset_id,
            }
        ),
        encoding="utf-8",
    )
    (ds / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "case_a",
                "query": "pressure?",
                "judgments": [{"chunk_id": "chunk_ok", "relevance": 2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cohort = tmp_path / "cohort.json"
    cohort.write_text(
        GenerationCohortMapV1(
            schema_version=GENERATION_COHORT_MAP_V1,
            gold_dataset_id=dataset_id,
            cases=[
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="human_reviewed"
                )
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )
    child = _child("chunk_ok", text="pressure is 100 psi", order=1)
    snap = _snapshot([child])
    gold_loaded = LoadedGoldDataset(
        meta=GoldDatasetMeta(
            chunk_set_id="chunkset_demo",
            corpus_id="corpus_demo",
            corpus_name="demo",
            dataset_id=dataset_id,
        ),
        cases=tuple(cases),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=ds,
    )
    evidence = build_gold_evidence_set_v1(
        gold_loaded,
        chunk_snapshot=snap,
        label_cohort_by_case_id={"case_a": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
    )
    ev_id = evidence.cases[0].evidence_units[0].evidence_unit_id
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )

    monkeypatch.setattr(
        "offline_rag.cli._load_settings",
        lambda _args: settings,
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "READY",
    )

    def _run(settings_arg: AppSettings, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["executor"] = GroundedGenerationExecutor(settings_arg, generator=fake)
        kwargs["chunk_snapshot"] = snap
        kwargs["token_counter"] = FakeTokenCounter()
        return run_generation_semantic_evaluation(settings_arg, **kwargs)

    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.run_generation_semantic_evaluation",
        _run,
    )

    code = main(
        [
            "eval",
            "generation",
            "--dataset",
            str(ds),
            "--cohort-map",
            str(cohort),
            "--corpus",
            "demo",
            "--json",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["schema_version"] == "offline-rag-generation-semantic-eval-result-v1"
    assert payload["population"]["answered"] == 1
    assert payload["semantic_aggregates"] is None

    code2 = main(
        [
            "eval",
            "generation",
            "--dataset",
            str(ds),
            "--cohort-map",
            str(cohort),
            "--corpus",
            "demo",
        ]
    )
    assert code2 == 0
    human = capsys.readouterr().out
    assert "Generation semantic evaluation completed" in human
    assert "gold citation recall" in human


def test_cli_invalid_cohort_and_missing_chunkset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "eval_results": tmp_path / "eval_results",
                    "chunk_manifests": tmp_path / "chunk_manifests",
                    "manifests": tmp_path / "manifests",
                    "corpora": tmp_path / "corpora",
                }
            )
        }
    )
    cases = [
        GoldCase(
            id="case_a",
            query="pressure?",
            judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
        )
    ]
    dataset_id = gold_dataset_id_from_payload(
        gold_semantic_payload(
            chunk_set_id="chunkset_missing",
            corpus_id="corpus_demo",
            corpus_name="demo",
            cases=cases,
        )
    )
    ds = tmp_path / "gold"
    ds.mkdir()
    (ds / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": "offline-rag-gold-v1",
                "chunk_set_id": "chunkset_missing",
                "corpus_id": "corpus_demo",
                "corpus_name": "demo",
                "dataset_id": dataset_id,
            }
        ),
        encoding="utf-8",
    )
    (ds / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "case_a",
                "query": "pressure?",
                "judgments": [{"chunk_id": "chunk_ok", "relevance": 2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    bad_cohort = tmp_path / "bad_cohort.json"
    bad_cohort.write_text(
        GenerationCohortMapV1(
            schema_version=GENERATION_COHORT_MAP_V1,
            gold_dataset_id=dataset_id,
            cases=[],  # missing case
        ).model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr("offline_rag.cli._load_settings", lambda _args: settings)
    assert (
        main(
            [
                "eval",
                "generation",
                "--dataset",
                str(ds),
                "--cohort-map",
                str(bad_cohort),
                "--corpus",
                "demo",
            ]
        )
        == 1
    )

    good_cohort = tmp_path / "good_cohort.json"
    good_cohort.write_text(
        GenerationCohortMapV1(
            schema_version=GENERATION_COHORT_MAP_V1,
            gold_dataset_id=dataset_id,
            cases=[
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="human_reviewed"
                )
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "eval",
                "generation",
                "--dataset",
                str(ds),
                "--cohort-map",
                str(good_cohort),
                "--corpus",
                "demo",
            ]
        )
        == 1
    )


def test_cli_provider_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings()
    settings = settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={"eval_results": tmp_path / "eval_results"}
            )
        }
    )
    cases = [
        GoldCase(
            id="case_a",
            query="pressure?",
            judgments=(ChunkJudgment(chunk_id="chunk_ok", relevance=2),),
        )
    ]
    dataset_id = gold_dataset_id_from_payload(
        gold_semantic_payload(
            chunk_set_id="chunkset_demo",
            corpus_id="corpus_demo",
            corpus_name="demo",
            cases=cases,
        )
    )
    ds = tmp_path / "gold"
    ds.mkdir()
    (ds / "meta.json").write_text(
        json.dumps(
            {
                "schema_version": "offline-rag-gold-v1",
                "chunk_set_id": "chunkset_demo",
                "corpus_id": "corpus_demo",
                "corpus_name": "demo",
                "dataset_id": dataset_id,
            }
        ),
        encoding="utf-8",
    )
    (ds / "cases.jsonl").write_text(
        json.dumps(
            {
                "id": "case_a",
                "query": "pressure?",
                "judgments": [{"chunk_id": "chunk_ok", "relevance": 2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    cohort = tmp_path / "cohort.json"
    cohort.write_text(
        GenerationCohortMapV1(
            schema_version=GENERATION_COHORT_MAP_V1,
            gold_dataset_id=dataset_id,
            cases=[
                GenerationCohortMapCaseV1(
                    case_id="case_a", label_cohort="human_reviewed"
                )
            ],
        ).model_dump_json(),
        encoding="utf-8",
    )
    snap = _snapshot([_child("chunk_ok", text="x", order=1)])
    monkeypatch.setattr("offline_rag.cli._load_settings", lambda _args: settings)
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "NOT_READY",
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.describe_generation_provider_status",
        lambda _s: {"status": "NOT_READY", "reasons": ["not ready"]},
    )

    def _run(settings_arg: AppSettings, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["chunk_snapshot"] = snap
        kwargs["token_counter"] = FakeTokenCounter()
        kwargs["executor"] = GroundedGenerationExecutor(
            settings_arg, generator=FakeGenerator(default_response="{}")
        )
        return run_generation_semantic_evaluation(settings_arg, **kwargs)

    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.run_generation_semantic_evaluation",
        _run,
    )
    assert (
        main(
            [
                "eval",
                "generation",
                "--dataset",
                str(ds),
                "--cohort-map",
                str(cohort),
                "--corpus",
                "demo",
            ]
        )
        == 1
    )


def test_cli_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from offline_rag.config import ConfigError

    def _boom(_args):  # type: ignore[no-untyped-def]
        raise ConfigError("bad config")

    monkeypatch.setattr("offline_rag.cli._load_settings", _boom)
    assert (
        main(
            [
                "eval",
                "generation",
                "--dataset",
                "ds",
                "--cohort-map",
                "map.json",
            ]
        )
        == 1
    )
