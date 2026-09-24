"""Unit tests for Slice 11A-3 context adapter + Path-A preflight."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.context.sufficiency_adapter import (
    SufficiencyAdapterError,
    adapt_hybrid_rerank_context_to_provenance,
)
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankCandidate,
    HybridRerankContextResult,
    HybridRerankProvenance,
)
from offline_rag.evaluation.result import (
    AggregateMetrics,
    CaseEvaluationResult,
    CaseMetrics,
    LatencySummary,
    MetricConfig,
    MetricValue,
    PopulationCounts,
    RetrievalEvaluationResultV1,
)
from offline_rag.evaluation.sufficiency_preflight import (
    PathACaseStatus,
    PathALineageConsistency,
    PathAMissingRequirement,
    PathAOverallResult,
    assess_hybrid_rerank_context_result_for_path_a,
    run_path_a_preflight,
)
from offline_rag.sufficiency import (
    SufficiencyErrorCodeV1,
    build_sufficiency_snapshot,
    derive_sufficiency_observation,
    validate_observation_against_provenance,
)


def _anchor(
    *,
    chunk_id: str,
    rank: int,
    score: float,
    hybrid_rank: int,
    rrf_score: float = 0.05,
    dense_rank: int | None = 1,
    dense_score: float | None = 0.9,
    lexical_rank: int | None = 2,
    lexical_score: float | None = 0.4,
    nested_score: float | None = None,
) -> HybridRerankCandidate:
    reranker_score = score if nested_score is None else nested_score
    return HybridRerankCandidate(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        document_id="doc_a",
        text=f"text for {chunk_id}",
        section_path=["S"],
        token_count=3,
        hybrid_rerank=HybridRerankProvenance(
            reranker_score=reranker_score,
            hybrid_rank=hybrid_rank,
            rrf_score=rrf_score,
            dense_rank=dense_rank,
            dense_score=dense_score,
            lexical_rank=lexical_rank,
            lexical_score=lexical_score,
        ),
    )


def _unit(
    *,
    evidence_unit_id: str,
    document_id: str,
    section_path: list[str],
    source_chunk_id: str,
    primary_anchor_chunk_id: str,
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=evidence_unit_id,
        source_chunk_id=source_chunk_id,
        kind="child",
        text="evidence body must not enter provenance",
        token_count=4,
        primary_anchor_chunk_id=primary_anchor_chunk_id,
        contributing_anchor_chunk_ids=[primary_anchor_chunk_id],
        document_id=document_id,
        section_path=section_path,
    )


def _context_result(
    *,
    query: str = "what is X?",
    anchors: list[HybridRerankCandidate] | None = None,
    units: list[EvidenceUnit] | None = None,
    metadata: dict | None = None,
    context_token_count: int | None = None,
    diagnostics_token_count: int | None = None,
    evidence_unit_count: int | None = None,
    actual_anchor_count: int | None = None,
    method: str = "hybrid-rerank-context",
) -> HybridRerankContextResult:
    final_anchors = (
        anchors
        if anchors is not None
        else [
            _anchor(chunk_id="chunk_a", rank=1, score=1.5, hybrid_rank=1),
            _anchor(
                chunk_id="chunk_b",
                rank=2,
                score=0.5,
                hybrid_rank=2,
                dense_rank=None,
                dense_score=None,
                lexical_rank=1,
                lexical_score=0.7,
            ),
        ]
    )
    final_units = (
        units
        if units is not None
        else [
            _unit(
                evidence_unit_id="ev_1",
                document_id="doc_a",
                section_path=["A", "B"],
                source_chunk_id="chunk_src",
                primary_anchor_chunk_id="chunk_a",
            )
        ]
    )
    token_count = 12 if context_token_count is None else context_token_count
    diag_tokens = (
        token_count if diagnostics_token_count is None else diagnostics_token_count
    )
    return HybridRerankContextResult(
        query=query,
        method=method,
        evidence_units=final_units,
        assembled_text="assembled",
        context_token_count=token_count,
        max_context_tokens=100,
        context_config_hash="ctxcfg_test",
        anchors=final_anchors,
        dense_index_id="dense_1",
        lexical_index_id="lex_1",
        fusion_config_hash="fus_1",
        reranker_config_hash="rrk_1",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=(
                len(final_anchors)
                if actual_anchor_count is None
                else actual_anchor_count
            ),
            anchors_processed=len(final_anchors),
            evidence_unit_count=(
                len(final_units) if evidence_unit_count is None else evidence_unit_count
            ),
            context_token_count=diag_tokens,
            budget_exhausted=False,
            stop_reason="completed",
            clipping_occurred=True,
            dedup_hits=2,
            containment_suppressions=1,
        ),
        metadata=metadata
        or {
            "corpus_id": "corpus_1",
            "chunk_set_id": "chunkset_1",
            "latency_ms": {"total": 99},
            "host": "ignored",
        },
    )


def _metric_zero() -> MetricValue:
    return MetricValue(value=0.0, applicable_count=0)


def _aggregates() -> AggregateMetrics:
    return AggregateMetrics(
        recall_at_1=_metric_zero(),
        recall_at_5=_metric_zero(),
        recall_at_10=_metric_zero(),
        precision_at_1=_metric_zero(),
        precision_at_5=_metric_zero(),
        precision_at_10=_metric_zero(),
        hit_rate_at_1=_metric_zero(),
        hit_rate_at_5=_metric_zero(),
        hit_rate_at_10=_metric_zero(),
        hit_rate_at_30=_metric_zero(),
        mrr=_metric_zero(),
        ndcg_at_1=_metric_zero(),
        ndcg_at_5=_metric_zero(),
        ndcg_at_10=_metric_zero(),
    )


def _retrieval_eval(
    *,
    run_id: str,
    cases: list[CaseEvaluationResult],
    lineage: dict[str, str],
) -> RetrievalEvaluationResultV1:
    now = datetime.now(tz=UTC)
    return RetrievalEvaluationResultV1(
        run_id=run_id,
        method="hybrid-rerank",
        gold_schema_version="offline-rag-gold-dataset-v1",
        gold_dataset_id="gold_test",
        gold_source_schema="offline-rag-gold-dataset-v1",
        chunk_set_id=lineage["chunk_set_id"],
        corpus_id=lineage["corpus_id"],
        semantic_provenance={
            "dense_index_id": lineage["dense_index_id"],
            "lexical_index_id": lineage["lexical_index_id"],
            "fusion_config_hash": lineage["fusion_config_hash"],
            "reranker_config_hash": lineage["reranker_config_hash"],
        },
        metric_config=MetricConfig(),
        population=PopulationCounts(
            total_cases=len(cases),
            executed_cases=len(cases),
            quality_eligible_cases=len(cases),
        ),
        aggregates=_aggregates(),
        latency=LatencySummary(),
        cases=cases,
        started_at=now,
        completed_at=now,
    )


def test_adapter_projects_exact_lineage_query_and_diagnostics() -> None:
    result = _context_result()
    provenance = adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert provenance.case_id == "case_1"
    assert provenance.corpus_id == "corpus_1"
    assert provenance.chunk_set_id == "chunkset_1"
    assert provenance.dense_index_id == "dense_1"
    assert provenance.lexical_index_id == "lex_1"
    assert provenance.fusion_config_hash == "fus_1"
    assert provenance.reranker_config_hash == "rrk_1"
    assert provenance.context_config_hash == "ctxcfg_test"
    assert provenance.original_query == "what is X?"
    assert provenance.active_retrieval_query == "what is X?"
    assert provenance.attempt_number == 0
    assert provenance.attempt_role == "initial"
    assert provenance.diagnostics.clipping_occurred is True
    assert provenance.diagnostics.dedup_hits == 2
    assert provenance.diagnostics.containment_suppressions == 1
    assert provenance.diagnostics.stop_reason == "completed"


def test_adapter_preserves_anchor_and_evidence_order_and_paired_branches() -> None:
    result = _context_result()
    provenance = adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert [a.chunk_id for a in provenance.anchors] == ["chunk_a", "chunk_b"]
    assert [a.rerank_rank for a in provenance.anchors] == [1, 2]
    assert provenance.anchors[0].reranker_score == 1.5
    assert provenance.anchors[0].hybrid_rank == 1
    assert provenance.anchors[0].rrf_score == 0.05
    assert provenance.anchors[0].dense_rank == 1
    assert provenance.anchors[0].dense_score == 0.9
    assert provenance.anchors[0].lexical_rank == 2
    assert provenance.anchors[0].lexical_score == 0.4
    assert provenance.anchors[1].dense_rank is None
    assert provenance.anchors[1].dense_score is None
    assert provenance.anchors[1].lexical_rank == 1
    unit = provenance.final_evidence_units[0]
    assert unit.evidence_unit_id == "ev_1"
    assert unit.document_id == "doc_a"
    assert unit.section_path == ["A", "B"]
    assert unit.source_chunk_id == "chunk_src"
    assert unit.primary_anchor_chunk_id == "chunk_a"
    assert "text" not in unit.model_dump()


def test_adapter_output_passes_derive_and_snapshot_validation() -> None:
    result = _context_result()
    provenance = adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    observation = derive_sufficiency_observation(provenance)
    validate_observation_against_provenance(observation, provenance)
    snapshot = build_sufficiency_snapshot(provenance, observation=observation)
    assert snapshot.suffctx_id.startswith("suffctx_")


def test_adapter_fails_closed_when_lineage_missing() -> None:
    result = _context_result(metadata={"chunk_set_id": "chunkset_1"})
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.details is not None
    assert exc.value.details.field_name == "corpus_id"


def test_adapter_fails_on_mismatched_candidate_score() -> None:
    result = _context_result(
        anchors=[
            _anchor(
                chunk_id="chunk_a",
                rank=1,
                score=1.5,
                hybrid_rank=1,
                nested_score=9.9,
            )
        ]
    )
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.code == SufficiencyErrorCodeV1.CONTRADICTORY_UPSTREAM_STATE
    assert exc.value.details is not None
    assert exc.value.details.field_name == "reranker_score"


def test_adapter_fails_on_mismatched_context_token_counts() -> None:
    result = _context_result(context_token_count=12, diagnostics_token_count=99)
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.code == SufficiencyErrorCodeV1.CONTRADICTORY_UPSTREAM_STATE
    assert exc.value.details is not None
    assert exc.value.details.field_name == "context_token_count"


def test_adapter_fails_on_mismatched_evidence_unit_count() -> None:
    result = _context_result(evidence_unit_count=99)
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.code == SufficiencyErrorCodeV1.CONTRADICTORY_UPSTREAM_STATE
    assert exc.value.details is not None
    assert exc.value.details.field_name == "evidence_unit_count"


def test_adapter_fails_on_mismatched_actual_anchor_count() -> None:
    result = _context_result(actual_anchor_count=99)
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.code == SufficiencyErrorCodeV1.CONTRADICTORY_UPSTREAM_STATE
    assert exc.value.details is not None
    assert exc.value.details.field_name == "actual_anchor_count"


def test_adapter_fails_on_wrong_source_method() -> None:
    result = _context_result(method="hybrid-rerank")
    with pytest.raises(SufficiencyAdapterError) as exc:
        adapt_hybrid_rerank_context_to_provenance(result, case_id="case_1")
    assert exc.value.code == SufficiencyErrorCodeV1.CONTRADICTORY_UPSTREAM_STATE
    assert exc.value.details is not None
    assert exc.value.details.field_name == "method"


def test_path_a_qualifies_complete_context_dump(tmp_path: Path) -> None:
    result = _context_result(query="frozen query")
    path = tmp_path / "ctx_case1.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_1": "frozen query"},
        artifact_paths=[path],
        context_result_case_id_by_path={str(path): "case_1"},
    )
    assert report.overall == PathAOverallResult.PATH_A_QUALIFIED
    assert report.case_assessments[0].status == PathACaseStatus.QUALIFIED
    assert report.lineage_consistency == PathALineageConsistency.CONSISTENT


def test_path_a_wrong_query_does_not_qualify(tmp_path: Path) -> None:
    result = _context_result(query="query belonging to case_19")
    path = tmp_path / "ctx.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_17": "query belonging to case_17"},
        artifact_paths=[path],
        context_result_case_id_by_path={str(path): "case_17"},
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    assert report.case_assessments[0].status == PathACaseStatus.NOT_QUALIFIED
    assert (
        PathAMissingRequirement.QUERY_CASE_BINDING
        in report.case_assessments[0].missing_or_ambiguous
    )


def test_path_a_swapped_queries_do_not_qualify(tmp_path: Path) -> None:
    a = _context_result(query="query-B")
    b = _context_result(query="query-A")
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(a.model_dump_json(), encoding="utf-8")
    path_b.write_text(b.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_A": "query-A", "case_B": "query-B"},
        artifact_paths=[path_a, path_b],
        context_result_case_id_by_path={
            str(path_a): "case_A",
            str(path_b): "case_B",
        },
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    by_id = {item.case_id: item for item in report.case_assessments}
    assert by_id["case_A"].status == PathACaseStatus.NOT_QUALIFIED
    assert by_id["case_B"].status == PathACaseStatus.NOT_QUALIFIED
    assert (
        PathAMissingRequirement.QUERY_CASE_BINDING
        in by_id["case_A"].missing_or_ambiguous
    )
    assert (
        PathAMissingRequirement.QUERY_CASE_BINDING
        in by_id["case_B"].missing_or_ambiguous
    )


def test_path_a_retrieval_eval_query_mismatch_reports_binding(
    tmp_path: Path,
) -> None:
    lineage = {
        "corpus_id": "corpus_1",
        "chunk_set_id": "chunkset_1",
        "dense_index_id": "dense_1",
        "lexical_index_id": "lex_1",
        "fusion_config_hash": "fus_1",
        "reranker_config_hash": "rrk_1",
    }
    bad = _retrieval_eval(
        run_id="eval_bad",
        cases=[
            CaseEvaluationResult(
                case_id="case_1",
                query="wrong historical query",
                quality_eligible=True,
                retrieved_chunk_ids=["chunk_a"],
                metrics=CaseMetrics(),
            )
        ],
        lineage=lineage,
    )
    path = tmp_path / "bad.json"
    path.write_text(bad.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_1": "frozen intended query"},
        artifact_paths=[path],
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    assert (
        PathAMissingRequirement.QUERY_CASE_BINDING
        in report.case_assessments[0].missing_or_ambiguous
    )


def test_path_a_one_incomplete_case_fails_whole_population(tmp_path: Path) -> None:
    good = _context_result(query="q1")
    good_path = tmp_path / "good.json"
    good_path.write_text(good.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_1": "q1", "case_2": "q2"},
        artifact_paths=[good_path],
        context_result_case_id_by_path={str(good_path): "case_1"},
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    by_id = {item.case_id: item for item in report.case_assessments}
    assert by_id["case_1"].status == PathACaseStatus.QUALIFIED
    assert by_id["case_2"].status == PathACaseStatus.NOT_QUALIFIED
    assert (
        PathAMissingRequirement.RERANKER_RAW_SCORES
        in by_id["case_2"].missing_or_ambiguous
    )


def test_path_a_historical_retrieval_eval_case_not_qualified(tmp_path: Path) -> None:
    lineage = {
        "corpus_id": "corpus_1",
        "chunk_set_id": "chunkset_1",
        "dense_index_id": "dense_1",
        "lexical_index_id": "lex_1",
        "fusion_config_hash": "fus_1",
        "reranker_config_hash": "rrk_1",
    }
    bad = _retrieval_eval(
        run_id="eval_bad",
        cases=[
            CaseEvaluationResult(
                case_id="case_1",
                query="q1",
                quality_eligible=True,
                retrieved_chunk_ids=["chunk_a"],
                metrics=CaseMetrics(),
            )
        ],
        lineage=lineage,
    )
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(bad.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_1": "q1"},
        artifact_paths=[bad_path],
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    missing = report.case_assessments[0].missing_or_ambiguous
    assert PathAMissingRequirement.RERANKER_RAW_SCORES in missing
    assert PathAMissingRequirement.EVIDENCE_UNIT_PROVENANCE in missing
    assert PathAMissingRequirement.SHARED_LINEAGE in missing


def test_path_a_mixed_lineage_fails(tmp_path: Path) -> None:
    a = _context_result(
        query="q1",
        metadata={"corpus_id": "corpus_1", "chunk_set_id": "chunkset_1"},
    )
    b = _context_result(
        query="q2",
        metadata={"corpus_id": "corpus_OTHER", "chunk_set_id": "chunkset_1"},
    )
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(a.model_dump_json(), encoding="utf-8")
    path_b.write_text(b.model_dump_json(), encoding="utf-8")
    report = run_path_a_preflight(
        intended_case_queries={"case_1": "q1", "case_2": "q2"},
        artifact_paths=[path_a, path_b],
        context_result_case_id_by_path={
            str(path_a): "case_1",
            str(path_b): "case_2",
        },
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    assert report.lineage_consistency == PathALineageConsistency.INCONSISTENT
    assert all(
        item.status == PathACaseStatus.NOT_QUALIFIED for item in report.case_assessments
    )


def test_path_a_preflight_performs_no_retrieval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assemble = MagicMock(side_effect=AssertionError("retrieval must not run"))
    monkeypatch.setattr(
        "offline_rag.context.assemble.HybridRerankContextAssembler.assemble",
        assemble,
    )
    result = _context_result(query="q1")
    path = tmp_path / "ctx.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    run_path_a_preflight(
        intended_case_queries={"case_1": "q1"},
        artifact_paths=[path],
        context_result_case_id_by_path={str(path): "case_1"},
    )
    assemble.assert_not_called()


def test_historical_hybrid_rerank_artifact_is_path_a_not_qualified() -> None:
    artifact = Path("eval/results/9h_p/F_hybrid_rerank_full22.json")
    if not artifact.exists():
        pytest.skip("historical 9H-P hybrid-rerank artifact not present")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    intended = {case["case_id"]: case["query"] for case in payload["cases"]}
    report = run_path_a_preflight(
        intended_case_queries=intended,
        artifact_paths=[artifact],
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    assert report.lineage_consistency in {
        PathALineageConsistency.INSUFFICIENT,
        PathALineageConsistency.INCONSISTENT,
    }
    assert (
        sum(1 for c in report.case_assessments if c.status == PathACaseStatus.QUALIFIED)
        == 0
    )
    sample = report.case_assessments[0]
    assert sample.status == PathACaseStatus.NOT_QUALIFIED
    for required in (
        PathAMissingRequirement.RERANKER_RAW_SCORES,
        PathAMissingRequirement.RERANK_RANKS_ORDER,
        PathAMissingRequirement.HYBRID_RANK_RRF_SCORE,
        PathAMissingRequirement.DENSE_BRANCH_RANK_SCORE,
        PathAMissingRequirement.LEXICAL_BRANCH_RANK_SCORE,
        PathAMissingRequirement.EVIDENCE_UNIT_PROVENANCE,
        PathAMissingRequirement.ASSEMBLY_DIAGNOSTICS,
    ):
        assert required in sample.missing_or_ambiguous


def test_path_a_historical_query_conflict_is_irreversible(tmp_path: Path) -> None:
    """A→B conflict must not be erased by a later qualified A sighting."""
    intended = {"case_1": "query-A"}
    path_a1 = tmp_path / "a1.json"
    path_b = tmp_path / "b.json"
    path_a2 = tmp_path / "a2.json"
    path_a1.write_text(
        _context_result(query="query-A").model_dump_json(), encoding="utf-8"
    )
    path_b.write_text(
        _context_result(query="query-B").model_dump_json(), encoding="utf-8"
    )
    path_a2.write_text(
        _context_result(query="query-A").model_dump_json(), encoding="utf-8"
    )
    report = run_path_a_preflight(
        intended_case_queries=intended,
        artifact_paths=[path_a1, path_b, path_a2],
        context_result_case_id_by_path={
            str(path_a1): "case_1",
            str(path_b): "case_1",
            str(path_a2): "case_1",
        },
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    case = report.case_assessments[0]
    assert case.status == PathACaseStatus.NOT_QUALIFIED
    assert PathAMissingRequirement.QUERY_CASE_BINDING in case.missing_or_ambiguous
    assert "conflicting historical query bindings for case" in case.notes


def test_path_a_historical_query_conflict_is_irreversible_reverse_order(
    tmp_path: Path,
) -> None:
    """B first, then qualified A twice: conflict must remain latched."""
    intended = {"case_1": "query-A"}
    path_b = tmp_path / "b.json"
    path_a1 = tmp_path / "a1.json"
    path_a2 = tmp_path / "a2.json"
    path_b.write_text(
        _context_result(query="query-B").model_dump_json(), encoding="utf-8"
    )
    path_a1.write_text(
        _context_result(query="query-A").model_dump_json(), encoding="utf-8"
    )
    path_a2.write_text(
        _context_result(query="query-A").model_dump_json(), encoding="utf-8"
    )
    report = run_path_a_preflight(
        intended_case_queries=intended,
        artifact_paths=[path_b, path_a1, path_a2],
        context_result_case_id_by_path={
            str(path_b): "case_1",
            str(path_a1): "case_1",
            str(path_a2): "case_1",
        },
    )
    assert report.overall == PathAOverallResult.PATH_A_NOT_QUALIFIED
    case = report.case_assessments[0]
    assert case.status == PathACaseStatus.NOT_QUALIFIED
    assert PathAMissingRequirement.QUERY_CASE_BINDING in case.missing_or_ambiguous
    assert "conflicting historical query bindings for case" in case.notes


def test_assess_complete_context_result_qualifies() -> None:
    assessment = assess_hybrid_rerank_context_result_for_path_a(
        _context_result(query="exact frozen"),
        case_id="case_1",
        intended_query="exact frozen",
    )
    assert assessment.status == PathACaseStatus.QUALIFIED
    assert assessment.missing_or_ambiguous == []


def test_assess_mismatched_query_does_not_qualify() -> None:
    assessment = assess_hybrid_rerank_context_result_for_path_a(
        _context_result(query="wrong"),
        case_id="case_1",
        intended_query="right",
    )
    assert assessment.status == PathACaseStatus.NOT_QUALIFIED
    assert PathAMissingRequirement.QUERY_CASE_BINDING in assessment.missing_or_ambiguous
