"""Slice 10D — human-grade0-hard-negative-v1 abstention fixture."""

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
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.documents import Chunk, ChunkKind
from offline_rag.evaluation.generation_semantic import (
    GENERATION_ABSTENTION_DETERMINISTIC_V1,
    GOLD_EVIDENCE_V1,
    HARD_NEGATIVE_N_V1,
    HARD_NEGATIVE_RETRIEVER_V1,
    HUMAN_GRADE0_HARD_NEGATIVE_V1,
    GenerationSemanticEvaluator,
    HardNegativeBuildError,
    build_gold_evidence_set_v1,
    build_human_grade0_hard_negative_set_v1,
    format_generation_semantic_result_human,
    run_generation_semantic_evaluation,
)
from offline_rag.evaluation.generation_semantic.judge_adapter import (
    FakeGenerationSemanticJudge,
)
from offline_rag.evaluation.generation_semantic.judge_protocol import (
    GenerationSemanticJudgeError,
)
from offline_rag.evaluation.generation_semantic.judge_readiness import (
    JudgePreflightKind,
)
from offline_rag.evaluation.generation_semantic.metrics import (
    build_abstention_aggregates,
    compute_case_deterministic_metrics,
)
from offline_rag.evaluation.generation_semantic.models import (
    GenerationSemanticEvalCaseResultV1,
)
from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    LoadedGoldDataset,
)
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.generation.fake import FakeGenerator
from offline_rag.gold_authoring.contracts import AUTHORING_ARTIFACT_CONTRACT
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase, SourceSeed
from offline_rag.gold_authoring.pooling_models import PoolCandidate, RetrievalHit
from offline_rag.gold_authoring.review_models import (
    CategoryOverride,
    HumanJudgment,
    HumanReview,
    HumanReviewStatus,
)
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


def _snapshot(chunks: list[Chunk]) -> CorpusChunkSnapshot:
    docs = sorted({c.document_id for c in chunks})
    return CorpusChunkSnapshot(
        corpus_name="demo",
        corpus_id="corpus_demo",
        chunk_set_id="chunkset_demo",
        chunks=chunks,
        source_name_by_document_id={doc_id: f"{doc_id}.pdf" for doc_id in docs},
    )


def _candidate(
    chunk_id: str,
    *,
    hybrid_rank: int | None = None,
    extra_hits: list[RetrievalHit] | None = None,
    document_id: str = "doc_a",
) -> PoolCandidate:
    hits: list[RetrievalHit] = list(extra_hits or [])
    if hybrid_rank is not None:
        hits.append(
            RetrievalHit(
                retriever=HARD_NEGATIVE_RETRIEVER_V1,
                chunk_id=chunk_id,
                rank=hybrid_rank,
                score=0.5,
            )
        )
    return PoolCandidate(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title="Guide",
        section_path=["Alpha"],
        retrieval_hits=hits,
    )


def _human_review(
    *,
    status: HumanReviewStatus,
    grades: dict[str, int],
    query: str,
    category: str | None = "ops",
    tags: list[str] | None = None,
) -> HumanReview:
    judgments = [
        HumanJudgment(chunk_id=cid, relevance=grade)  # type: ignore[arg-type]
        for cid, grade in sorted(grades.items())
    ]
    return HumanReview(
        status=status,
        judgments=judgments,
        query_override=None,
        category_override=CategoryOverride(is_overridden=False, value=None),
        tags_override=None,
        grade_basis_query=query,
    )


def _silver_case(
    draft_id: str,
    *,
    query: str,
    candidates: list[PoolCandidate],
    grades: dict[str, int],
    status: HumanReviewStatus = HumanReviewStatus.ACCEPTED,
    category: str | None = "ops",
    tags: list[str] | None = None,
) -> SilverCase:
    tag_list = tags if tags is not None else ["module-1"]
    return SilverCase(
        draft_case_id=draft_id,
        proposed_query=query,
        proposed_category=category,
        proposed_tags=tag_list,
        source_seed=SourceSeed(chunk_id=candidates[0].chunk_id),
        candidates=candidates,
        human_review=_human_review(
            status=status,
            grades=grades,
            query=query,
            category=category,
            tags=tag_list,
        ),
    )


def _authoring_run(
    cases: list[SilverCase],
    *,
    authoring_run_id: str = "authorrun_test10d",
    chunk_set_id: str = "chunkset_demo",
    corpus_id: str = "corpus_demo",
    corpus_name: str = "demo",
) -> GoldAuthoringRun:
    return GoldAuthoringRun(
        schema_version=AUTHORING_ARTIFACT_CONTRACT,
        authoring_run_id=authoring_run_id,
        authorcfg_id="authorcfg_testhash",
        network_policy="localhost_only",
        corpus_id=corpus_id,
        corpus_name=corpus_name,
        chunk_set_id=chunk_set_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        cases=cases,
    )


def _gold(
    cases: list[GoldCase],
    *,
    dataset_id: str = "gold_test_10d",
    authoring_run_id: str | None = "authorrun_test10d",
) -> LoadedGoldDataset:
    metadata: dict[str, object] = {}
    if authoring_run_id is not None:
        metadata["authoring_run_id"] = authoring_run_id
    meta = GoldDatasetMeta(
        chunk_set_id="chunkset_demo",
        corpus_id="corpus_demo",
        corpus_name="demo",
        dataset_id=dataset_id,
        metadata=metadata,
    )
    return LoadedGoldDataset(
        meta=meta,
        cases=tuple(cases),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=Path("/tmp/gold_test_10d"),
    )


def _standard_pool_ids() -> list[str]:
    # 1 positive + 6 grade-0 with hybrid ranks (enough for N=5)
    return ["pos_a", "neg_1", "neg_2", "neg_3", "neg_4", "neg_5", "neg_6"]


def _standard_fixture(
    *,
    include_assistant_only: bool = False,
    hybrid_ranks: dict[str, int] | None = None,
    extra_neg_without_hybrid: bool = False,
):
    """Build a coherent Gold + Silver + ChunkSet for one human-reviewed case."""
    query = "What is the trip pressure?"
    ranks = hybrid_ranks or {
        "neg_1": 3,
        "neg_2": 1,
        "neg_3": 2,
        "neg_4": 5,
        "neg_5": 4,
        "neg_6": 6,
    }
    candidates = [
        _candidate("pos_a", hybrid_rank=10),
        *[
            _candidate(cid, hybrid_rank=ranks[cid])
            for cid in ("neg_1", "neg_2", "neg_3", "neg_4", "neg_5", "neg_6")
        ],
    ]
    if extra_neg_without_hybrid:
        candidates.append(_candidate("neg_no_hybrid", hybrid_rank=None))

    grades = {
        "pos_a": 2,
        "neg_1": 0,
        "neg_2": 0,
        "neg_3": 0,
        "neg_4": 0,
        "neg_5": 0,
        "neg_6": 0,
    }
    if extra_neg_without_hybrid:
        grades["neg_no_hybrid"] = 0

    silver = _silver_case(
        "case_human",
        query=query,
        candidates=candidates,
        grades=grades,
    )
    gold_case = GoldCase(
        id="case_human",
        query=query,
        category="ops",
        tags=("module-1",),
        judgments=(ChunkJudgment(chunk_id="pos_a", relevance=2),),
    )

    chunks = [
        _child("pos_a", text="positive evidence body", order=0),
        _child("neg_1", text="neg one", document_id="doc_b", order=2),
        _child("neg_2", text="neg two", document_id="doc_a", order=5),
        _child("neg_3", text="neg three", document_id="doc_a", order=1),
        _child("neg_4", text="neg four", document_id="doc_b", order=1),
        _child("neg_5", text="neg five", document_id="doc_a", order=3),
        _child("neg_6", text="neg six", document_id="doc_c", order=0),
    ]
    if extra_neg_without_hybrid:
        chunks.append(_child("neg_no_hybrid", text="no hybrid", order=9))

    cases = [silver]
    gold_cases = [gold_case]
    cohorts: dict[str, str] = {"case_human": "human_reviewed"}

    if include_assistant_only:
        asst_cands = [
            _candidate("asst_pos", hybrid_rank=1),
            *[_candidate(f"asst_n{i}", hybrid_rank=i + 1) for i in range(1, 6)],
        ]
        asst_grades = {"asst_pos": 1, **{f"asst_n{i}": 0 for i in range(1, 6)}}
        asst_silver = _silver_case(
            "case_asst",
            query="Assistant only query?",
            candidates=asst_cands,
            grades=asst_grades,
        )
        # Populate human_review even for assistant_only to prove cohort gate.
        cases.append(asst_silver)
        gold_cases.append(
            GoldCase(
                id="case_asst",
                query="Assistant only query?",
                category="ops",
                tags=("module-1",),
                judgments=(ChunkJudgment(chunk_id="asst_pos", relevance=1),),
            )
        )
        cohorts["case_asst"] = "assistant_only"
        chunks.extend(
            [
                _child("asst_pos", text="asst positive", order=0),
                *[
                    _child(f"asst_n{i}", text=f"asst neg {i}", order=i)
                    for i in range(1, 6)
                ],
            ]
        )

    run = _authoring_run(cases)
    gold = _gold(gold_cases)
    snap = _snapshot(chunks)
    return gold, run, snap, cohorts


def _settings(tmp_path: Path) -> AppSettings:
    base = AppSettings()
    return base.model_copy(
        update={
            "paths": base.paths.model_copy(
                update={
                    "eval_results": tmp_path / "eval",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                }
            ),
            "context": base.context.model_copy(update={"max_context_tokens": 6000}),
            "evaluation": base.evaluation.model_copy(
                update={
                    "generation_semantic_judge": (
                        base.evaluation.generation_semantic_judge.model_copy(
                            update={
                                "enabled": True,
                                "provider": "openai_compatible",
                                "base_url": "http://127.0.0.1:9",
                                "model": "judge-model",
                                "api_key": "test-key",
                                "network_policy": "localhost_only",
                            }
                        )
                    )
                }
            ),
        }
    )


def _valid_judge_output(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "answer_correctness": "fully_correct",
        "faithfulness": "fully_supported",
        "completeness": "complete",
        "citation_coverage": "complete",
        "citation_usefulness": "all_useful",
        "unsupported_claims": [],
        "missing_key_points": [],
        "irrelevant_citation_ids": [],
        "rationale": "supported by evidence",
    }
    payload.update(overrides)
    return payload


def _ready_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    from offline_rag.evaluation.generation_semantic.judge_readiness import (
        JudgePreflightResult,
    )

    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.evaluate_judge_preflight",
        lambda _s: JudgePreflightResult(
            kind=JudgePreflightKind.READY,
            status="READY",
            reasons=(),
            details={},
        ),
    )
    monkeypatch.setattr(
        "offline_rag.evaluation.generation_semantic.runner.generation_provider_status",
        lambda _s: "READY",
    )


# ---------------------------------------------------------------------------
# Lineage / integrity
# ---------------------------------------------------------------------------


def test_valid_lineage_builds_hard_negative() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert evidence.evidence_contract == HUMAN_GRADE0_HARD_NEGATIVE_V1
    assert evidence.expected_behavior == "abstain"
    assert len(evidence.cases) == 1
    case = evidence.cases[0]
    assert case.expected_behavior == "abstain"
    assert case.hard_negative_selection is not None
    assert len(case.evidence_units) == HARD_NEGATIVE_N_V1
    assert len(case.hard_negative_selection.selected_candidates) == HARD_NEGATIVE_N_V1


def test_authoring_run_id_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    gold = _gold(list(gold.cases), authoring_run_id="authorrun_other")
    with pytest.raises(HardNegativeBuildError, match="authoring_run_id mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_chunk_set_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    bad_run = run.model_copy(update={"chunk_set_id": "chunkset_other"})
    with pytest.raises(HardNegativeBuildError, match="chunk_set_id mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_corpus_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    bad_run = run.model_copy(update={"corpus_id": "corpus_other"})
    with pytest.raises(HardNegativeBuildError, match="corpus_id mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_gold_case_absent_in_silver_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    empty_run = run.model_copy(update={"cases": []})
    with pytest.raises(HardNegativeBuildError, match="absent from authoring-run"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=empty_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_duplicate_silver_case_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    dup = list(run.cases) + list(run.cases)
    bad_run = run.model_copy(update={"cases": dup})
    with pytest.raises(HardNegativeBuildError, match="duplicate Silver case"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_effective_query_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    assert silver.human_review is not None
    bad_review = silver.human_review.model_copy(
        update={
            "query_override": "Different finalized query?",
            "grade_basis_query": "Different finalized query?",
            "status": HumanReviewStatus.EDITED,
        }
    )
    bad_silver = silver.model_copy(update={"human_review": bad_review})
    bad_run = run.model_copy(update={"cases": [bad_silver]})
    with pytest.raises(HardNegativeBuildError, match="effective_query mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_category_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    bad_silver = silver.model_copy(update={"proposed_category": "other-cat"})
    bad_run = run.model_copy(update={"cases": [bad_silver]})
    with pytest.raises(HardNegativeBuildError, match="category mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_tags_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    bad_silver = silver.model_copy(update={"proposed_tags": ["other-tag"]})
    bad_run = run.model_copy(update={"cases": [bad_silver]})
    with pytest.raises(HardNegativeBuildError, match="tags mismatch"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_pending_silver_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    assert silver.human_review is not None
    # Drop to incomplete pending by clearing review
    pending = silver.model_copy(update={"human_review": None})
    bad_run = run.model_copy(update={"cases": [pending]})
    with pytest.raises(HardNegativeBuildError, match="accepted/edited"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_incomplete_human_map_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    assert silver.human_review is not None
    # Remove one judgment -> incomplete (also breaks accepted invariant on model)
    # Construct via model_construct to bypass SilverCase status invariants.
    incomplete_review = HumanReview.model_construct(
        status=HumanReviewStatus.ACCEPTED,
        judgments=silver.human_review.judgments[:-1],
        query_override=None,
        category_override=CategoryOverride(is_overridden=False, value=None),
        tags_override=None,
        grade_basis_query=silver.human_review.grade_basis_query,
    )
    incomplete = SilverCase.model_construct(
        draft_case_id=silver.draft_case_id,
        proposed_query=silver.proposed_query,
        proposed_category=silver.proposed_category,
        proposed_tags=list(silver.proposed_tags),
        proposal_rationale=None,
        source_seed=silver.source_seed,
        candidates=list(silver.candidates),
        model_judgments=[],
        prelabel_provenance=None,
        prelabel_summary=None,
        human_review=incomplete_review,
    )
    bad_run = GoldAuthoringRun.model_construct(
        **{
            **run.model_dump(),
            "cases": [incomplete],
        }
    )
    with pytest.raises(HardNegativeBuildError, match="incomplete"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_positive_map_mismatch_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    # Change gold positive relevance without changing silver
    bad_gold_case = GoldCase(
        id="case_human",
        query=gold.cases[0].query,
        category="ops",
        tags=("module-1",),
        judgments=(ChunkJudgment(chunk_id="pos_a", relevance=1),),
    )
    bad_gold = _gold([bad_gold_case])
    with pytest.raises(HardNegativeBuildError, match="positive map"):
        build_human_grade0_hard_negative_set_v1(
            bad_gold,
            authoring_run=run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


# ---------------------------------------------------------------------------
# Cohort provenance
# ---------------------------------------------------------------------------


def test_human_reviewed_included_assistant_only_excluded() -> None:
    gold, run, snap, cohorts = _standard_fixture(include_assistant_only=True)
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert [c.case_id for c in evidence.cases] == ["case_human"]
    assert all(c.label_cohort == "human_reviewed" for c in evidence.cases)


def test_assistant_only_with_human_review_still_excluded() -> None:
    """Durable Silver human_review is not sufficient; cohort map is authority."""
    gold, run, snap, cohorts = _standard_fixture(include_assistant_only=True)
    assert run.cases[1].human_review is not None
    assert cohorts["case_asst"] == "assistant_only"
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert "case_asst" not in {c.case_id for c in evidence.cases}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def test_selection_rank_asc_then_chunk_id_and_top_five() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    selected = evidence.cases[0].hard_negative_selection
    assert selected is not None
    # ranks: neg_2=1, neg_3=2, neg_1=3, neg_5=4, neg_4=5  (neg_6=6 dropped)
    assert [c.chunk_id for c in selected.selected_candidates] == [
        "neg_2",
        "neg_3",
        "neg_1",
        "neg_5",
        "neg_4",
    ]
    assert [c.rank for c in selected.selected_candidates] == [1, 2, 3, 4, 5]
    assert selected.eligible_grade0_hard_candidate_count == 6


def test_grade1_2_never_selected() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    selected_ids = {
        c.chunk_id
        for c in evidence.cases[0].hard_negative_selection.selected_candidates  # type: ignore[union-attr]
    }
    assert "pos_a" not in selected_ids


def test_grade0_without_hybrid_excluded() -> None:
    gold, run, snap, cohorts = _standard_fixture(extra_neg_without_hybrid=True)
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    selected_ids = {
        c.chunk_id
        for c in evidence.cases[0].hard_negative_selection.selected_candidates  # type: ignore[union-attr]
    }
    assert "neg_no_hybrid" not in selected_ids


def test_duplicate_hybrid_hit_rejects() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    silver = run.cases[0]
    bad_cands = []
    for cand in silver.candidates:
        if cand.chunk_id == "neg_2":
            bad_cands.append(
                cand.model_copy(
                    update={
                        "retrieval_hits": list(cand.retrieval_hits)
                        + [
                            RetrievalHit(
                                retriever=HARD_NEGATIVE_RETRIEVER_V1,
                                chunk_id="neg_2",
                                rank=99,
                            )
                        ]
                    }
                )
            )
        else:
            bad_cands.append(cand)
    bad_silver = silver.model_copy(update={"candidates": bad_cands})
    bad_run = run.model_copy(update={"cases": [bad_silver]})
    with pytest.raises(HardNegativeBuildError, match="duplicate"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=bad_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


def test_fewer_than_five_eligible_fails() -> None:
    gold, run, snap, cohorts = _standard_fixture(
        hybrid_ranks={
            "neg_1": 1,
            "neg_2": 2,
            "neg_3": 3,
            "neg_4": None,  # type: ignore[dict-item]
            "neg_5": None,  # type: ignore[dict-item]
            "neg_6": None,  # type: ignore[dict-item]
        }
    )
    # Rebuild with only 3 hybrid grade-0
    silver = run.cases[0]
    candidates = [
        _candidate("pos_a", hybrid_rank=10),
        _candidate("neg_1", hybrid_rank=1),
        _candidate("neg_2", hybrid_rank=2),
        _candidate("neg_3", hybrid_rank=3),
        _candidate("neg_4", hybrid_rank=None),
        _candidate("neg_5", hybrid_rank=None),
        _candidate("neg_6", hybrid_rank=None),
    ]
    grades = {
        "pos_a": 2,
        "neg_1": 0,
        "neg_2": 0,
        "neg_3": 0,
        "neg_4": 0,
        "neg_5": 0,
        "neg_6": 0,
    }
    sparse = _silver_case(
        "case_human",
        query=silver.proposed_query or "",
        candidates=candidates,
        grades=grades,
    )
    sparse_run = run.model_copy(update={"cases": [sparse]})
    with pytest.raises(HardNegativeBuildError, match="fewer than 5"):
        build_human_grade0_hard_negative_set_v1(
            gold,
            authoring_run=sparse_run,
            chunk_snapshot=snap,
            label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
            max_evidence_tokens=6000,
            token_counter=FakeTokenCounter(),
        )


# ---------------------------------------------------------------------------
# Presentation order vs selection order
# ---------------------------------------------------------------------------


def test_presentation_order_differs_from_selection_rank_order() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    case = evidence.cases[0]
    selection_order = [
        c.chunk_id
        for c in case.hard_negative_selection.selected_candidates  # type: ignore[union-attr]
    ]
    presentation_order = [u.source_chunk_id for u in case.evidence_units]
    assert selection_order == ["neg_2", "neg_3", "neg_1", "neg_5", "neg_4"]
    # document_id ASC → order ASC → chunk_id ASC
    assert presentation_order == ["neg_3", "neg_5", "neg_2", "neg_4", "neg_1"]
    assert presentation_order != selection_order


def test_ranks_do_not_appear_in_generator_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    captured: list[str] = []

    def _capture(request):  # type: ignore[no-untyped-def]
        for msg in request.messages:
            captured.append(msg.content)
        return json.dumps({"abstain": True, "answer": None, "citation_ids": []})

    settings = _settings(Path("/tmp"))
    _ready_preflight(monkeypatch)
    fake_gen = FakeGenerator(response_fn=_capture)
    evaluator = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=fake_gen),
    )
    result = evaluator.evaluate(evidence, judge_requested=False)
    assert result.cases[0].status == "insufficient_evidence"
    prompt_blob = "\n".join(captured)
    assert "rank" not in prompt_blob.lower()
    assert "hybrid-rerank" not in prompt_blob
    assert "human_relevance" not in prompt_blob
    assert "grade 0" not in prompt_blob.lower()
    evaluator.close()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_genevidence_identity_stable_and_sensitive() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    a = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    b = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert a.evidence_set_id == b.evidence_set_id
    assert a.evidence_set_id.startswith("genevidence_")

    # selected candidate change via rank swap among eligible
    alt_ranks = {
        "neg_1": 1,
        "neg_2": 2,
        "neg_3": 3,
        "neg_4": 4,
        "neg_5": 5,
        "neg_6": 6,
    }
    gold2, run2, snap2, cohorts2 = _standard_fixture(hybrid_ranks=alt_ranks)
    c = build_human_grade0_hard_negative_set_v1(
        gold2,
        authoring_run=run2,
        chunk_snapshot=snap2,
        label_cohort_by_case_id=cohorts2,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert c.evidence_set_id != a.evidence_set_id

    # authoring_run_id change (without gold metadata conflict)
    gold_no_meta = _gold(list(gold.cases), authoring_run_id=None)
    run_alt = run.model_copy(update={"authoring_run_id": "authorrun_alt"})
    d = build_human_grade0_hard_negative_set_v1(
        gold_no_meta,
        authoring_run=run_alt,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    e = build_human_grade0_hard_negative_set_v1(
        gold_no_meta,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert d.evidence_set_id != e.evidence_set_id

    # source text change
    mutated = [
        chunk.model_copy(update={"text": "mutated " + chunk.text})
        if chunk.chunk_id == "neg_2"
        else chunk
        for chunk in snap.chunks
    ]
    snap_mut = _snapshot(mutated)
    f = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap_mut,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert f.evidence_set_id != a.evidence_set_id

    # source_name change
    snap_name = CorpusChunkSnapshot(
        corpus_name=snap.corpus_name,
        corpus_id=snap.corpus_id,
        chunk_set_id=snap.chunk_set_id,
        chunks=list(snap.chunks),
        source_name_by_document_id={
            **snap.source_name_by_document_id,
            "doc_a": "Renamed.pdf",
        },
    )
    g = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap_name,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert g.evidence_set_id != a.evidence_set_id


# ---------------------------------------------------------------------------
# Contamination / evidence invariants
# ---------------------------------------------------------------------------


def test_no_positive_leakage_and_exactly_five_grade0() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    case = evidence.cases[0]
    evidence_ids = {u.source_chunk_id for u in case.evidence_units}
    gold_ids = {j.chunk_id for j in case.gold_judgments}
    assert evidence_ids & gold_ids == set()
    assert len(case.evidence_units) == 5
    for unit in case.evidence_units:
        assert unit.metadata == {}
        assert "relevance" not in unit.model_dump()
        assert "rank" not in unit.model_dump()


# ---------------------------------------------------------------------------
# Abstention metrics
# ---------------------------------------------------------------------------


def test_abstention_aggregates_all_abstain() -> None:
    rows = [
        GenerationSemanticEvalCaseResultV1(
            case_id=f"c{i}",
            query="q",
            label_cohort="human_reviewed",
            status="insufficient_evidence",
            abstention_reason="model_abstain",
        )
        for i in range(3)
    ]
    agg = build_abstention_aggregates(rows)
    assert agg.metric_contract == GENERATION_ABSTENTION_DETERMINISTIC_V1
    assert agg.total_cases == 3
    assert agg.correct_abstention_rate == 1.0
    assert agg.false_answer_rate == 0.0
    assert agg.cohorts["assistant_only"].case_count == 0
    assert agg.cohorts["assistant_only"].correct_abstention_rate is None


def test_abstention_aggregates_mixed_denominators() -> None:
    rows = [
        GenerationSemanticEvalCaseResultV1(
            case_id="a",
            query="q",
            label_cohort="human_reviewed",
            status="insufficient_evidence",
            abstention_reason="model_abstain",
        ),
        GenerationSemanticEvalCaseResultV1(
            case_id="b",
            query="q",
            label_cohort="human_reviewed",
            status="insufficient_evidence",
            abstention_reason="model_abstain",
        ),
        GenerationSemanticEvalCaseResultV1(
            case_id="c",
            query="q",
            label_cohort="human_reviewed",
            status="answered",
        ),
        GenerationSemanticEvalCaseResultV1(
            case_id="d",
            query="q",
            label_cohort="human_reviewed",
            status="generation_failed",
        ),
        GenerationSemanticEvalCaseResultV1(
            case_id="e",
            query="q",
            label_cohort="human_reviewed",
            status="citation_invalid",
        ),
    ]
    agg = build_abstention_aggregates(rows)
    assert agg.total_cases == 5
    assert agg.correct_abstention_rate == pytest.approx(2 / 5)
    assert agg.false_answer_rate == pytest.approx(1 / 5)
    assert agg.generation_failed_rate == pytest.approx(1 / 5)
    assert agg.citation_invalid_rate == pytest.approx(1 / 5)
    assert agg.empty_context_rate == 0.0


def test_empty_context_not_correct_abstention() -> None:
    rows = [
        GenerationSemanticEvalCaseResultV1(
            case_id="a",
            query="q",
            label_cohort="human_reviewed",
            status="insufficient_evidence",
            abstention_reason="empty_context",
        )
    ]
    agg = build_abstention_aggregates(rows)
    assert agg.correct_abstention_rate == 0.0
    assert agg.empty_context_rate == 1.0
    assert agg.false_answer_rate == 0.0


def test_citation_invalid_not_false_answer() -> None:
    rows = [
        GenerationSemanticEvalCaseResultV1(
            case_id="a",
            query="q",
            label_cohort="human_reviewed",
            status="citation_invalid",
        )
    ]
    agg = build_abstention_aggregates(rows)
    assert agg.false_answer_rate == 0.0
    assert agg.citation_invalid_rate == 1.0


# ---------------------------------------------------------------------------
# Positive-mode regression
# ---------------------------------------------------------------------------


def test_positive_mode_unchanged_abstention_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child = _child("pos_a", text="The trip pressure is 100 psi.")
    gold = _gold(
        [
            GoldCase(
                id="case_human",
                query="What is the trip pressure?",
                category="ops",
                tags=("module-1",),
                judgments=(ChunkJudgment(chunk_id="pos_a", relevance=2),),
            )
        ],
        authoring_run_id=None,
    )
    snap = _snapshot([child])
    evidence = build_gold_evidence_set_v1(
        gold,
        chunk_snapshot=snap,
        label_cohort_by_case_id={"case_human": "human_reviewed"},
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert evidence.evidence_contract == GOLD_EVIDENCE_V1
    assert evidence.expected_behavior == "answer"
    assert evidence.cases[0].hard_negative_selection is None

    settings = _settings(tmp_path)
    _ready_preflight(monkeypatch)
    ev_id = evidence.cases[0].evidence_units[0].evidence_unit_id
    fake_gen = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": [ev_id]}
        )
    )
    evaluator = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=fake_gen),
    )
    result = evaluator.evaluate(evidence)
    assert result.expected_behavior == "answer"
    assert result.abstention_aggregates is None
    assert result.deterministic_aggregates.mean_gold_citation_recall.value == 1.0
    human = format_generation_semantic_result_human(result)
    assert "gold citation recall" in human
    assert "Abstention stress test" not in human
    evaluator.close()


def test_negative_mode_nulls_gold_citation_metrics() -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    from offline_rag.domain.generation import GroundedAnswerResult

    answered = GroundedAnswerResult(
        query="What is the trip pressure?",
        status="answered",
        answer_text="something",
        citations=[],
        generator_invoked=True,
        attempt_count=1,
        generation_config_hash="gencfg_x",
    )
    metrics = compute_case_deterministic_metrics(evidence.cases[0], answered)
    assert metrics.gold_citation_recall is None
    assert metrics.grade2_citation_hit is None


# ---------------------------------------------------------------------------
# Judge interaction
# ---------------------------------------------------------------------------


def test_judge_blind_and_does_not_rewrite_false_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    settings = _settings(tmp_path)
    _ready_preflight(monkeypatch)
    ev_id = evidence.cases[0].evidence_units[0].evidence_unit_id

    # abstain → not_applicable
    abstain_gen = FakeGenerator(
        default_response=json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )
    fake_judge = FakeGenerationSemanticJudge(output=_valid_judge_output())
    evaluator = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=abstain_gen),
        judge=fake_judge,
    )
    result = evaluator.evaluate(evidence, judge_requested=True)
    assert result.cases[0].status == "insufficient_evidence"
    assert result.cases[0].judge_result is not None
    assert result.cases[0].judge_result.judge_status == "not_applicable"
    assert result.abstention_aggregates is not None
    assert result.abstention_aggregates.correct_abstention_rate == 1.0
    assert fake_judge.judge_calls == 0
    evaluator.close()

    # answered + fully_supported → Layer-1 false answer unchanged
    answer_gen = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "made up", "citation_ids": [ev_id]}
        )
    )
    support_judge = FakeGenerationSemanticJudge(output=_valid_judge_output())
    evaluator2 = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=answer_gen),
        judge=support_judge,
    )
    result2 = evaluator2.evaluate(evidence, judge_requested=True)
    assert result2.cases[0].status == "answered"
    assert result2.cases[0].judge_result is not None
    assert result2.cases[0].judge_result.judge_status == "succeeded"
    assert result2.cases[0].judge_result.faithfulness == "fully_supported"
    assert result2.abstention_aggregates is not None
    assert result2.abstention_aggregates.false_answer_rate == 1.0
    assert support_judge.judge_calls == 1
    req = support_judge.last_request
    assert req is not None
    blob = json.dumps(
        {
            "query": req.query,
            "answer": req.answer_text,
            "citations": list(req.citation_ids),
        }
    )
    assert "grade 0" not in blob.lower()
    assert "negative" not in blob.lower()
    assert "abstention" not in blob.lower()
    assert "hybrid-rerank" not in blob
    assert "human_reviewed" not in blob
    evaluator2.close()

    # judge failure does not rewrite Layer-1
    fail_judge = FakeGenerationSemanticJudge(
        raise_on_judge=GenerationSemanticJudgeError(
            "bad", failure_reason="invalid_json"
        )
    )
    evaluator3 = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=answer_gen),
        judge=fail_judge,
    )
    result3 = evaluator3.evaluate(evidence, judge_requested=True)
    assert result3.cases[0].status == "answered"
    assert result3.abstention_aggregates is not None
    assert result3.abstention_aggregates.false_answer_rate == 1.0
    evaluator3.close()


# ---------------------------------------------------------------------------
# No retrieval
# ---------------------------------------------------------------------------


def test_hard_negative_build_does_not_instantiate_retrievers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for cls in (
        DenseRetriever,
        LexicalRetriever,
        HybridRetriever,
        CrossEncoderReranker,
        HybridRerankContextAssembler,
    ):
        monkeypatch.setattr(
            cls,
            "__init__",
            MagicMock(side_effect=AssertionError(f"{cls.__name__} must not be used")),
        )
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert evidence.evidence_contract == HUMAN_GRADE0_HARD_NEGATIVE_V1


def test_cli_authoring_run_required_and_gold_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gold, run, snap, _cohorts = _standard_fixture()
    settings = _settings(tmp_path)
    _ready_preflight(monkeypatch)

    # Persist authoring run + cohort map + gold-ish via direct API first
    run_path = tmp_path / "authoring.json"
    run_path.write_text(run.model_dump_json(), encoding="utf-8")

    with pytest.raises(Exception, match="authoring-run is required"):
        run_generation_semantic_evaluation(
            settings,
            dataset_path=tmp_path / "missing",
            cohort_map_path=tmp_path / "missing_map",
            evidence_mode="human-hard-negative",
            authoring_run_path=None,
            chunk_snapshot=snap,
        )

    # gold + authoring-run incompatible
    with pytest.raises(Exception, match="incompatible"):
        run_generation_semantic_evaluation(
            settings,
            dataset_path=tmp_path / "missing",
            cohort_map_path=tmp_path / "missing_map",
            evidence_mode="gold",
            authoring_run_path=run_path,
            chunk_snapshot=snap,
        )


def test_human_summary_negative_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gold, run, snap, cohorts = _standard_fixture()
    evidence = build_human_grade0_hard_negative_set_v1(
        gold,
        authoring_run=run,
        chunk_snapshot=snap,
        label_cohort_by_case_id=cohorts,  # type: ignore[arg-type]
        max_evidence_tokens=6000,
        token_counter=FakeTokenCounter(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    settings = _settings(tmp_path)
    _ready_preflight(monkeypatch)
    fake_gen = FakeGenerator(
        default_response=json.dumps(
            {"abstain": True, "answer": None, "citation_ids": []}
        )
    )
    evaluator = GenerationSemanticEvaluator(
        settings,
        executor=GroundedGenerationExecutor(settings, generator=fake_gen),
    )
    result = evaluator.evaluate(evidence)
    human = format_generation_semantic_result_human(result)
    assert "human-grade0-hard-negative-v1" in human
    assert "Expected behavior:" in human
    assert "abstain" in human
    assert "Abstention stress test" in human
    assert "correct abstention" in human
    assert "gold citation recall" not in human
    assert "grade-2 citation hit" not in human
    evaluator.close()
