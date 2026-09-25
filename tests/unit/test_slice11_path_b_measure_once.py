"""Unit tests for Slice 11 Path-B measure-once runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextError
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankCandidate,
    HybridRerankContextResult,
    HybridRerankProvenance,
)
from offline_rag.evaluation.sufficiency_path_b import (
    FrozenCaseBinding,
    PathBMeasureOnceError,
    run_path_b_measure_once,
)
from offline_rag.sufficiency import (
    SufficiencyArtifactError,
    SufficiencyErrorCodeV1,
    build_sufficiency_manifest,
    build_sufficiency_snapshot,
)
from offline_rag.sufficiency.contracts import (
    SufficiencyAnchorProvenance,
    SufficiencyAssemblyDiagnosticsV1,
    SufficiencyEvidenceUnitProvenance,
    SufficiencyProvenanceV1,
)


def _anchor_cand(
    *,
    chunk_id: str,
    rank: int,
    score: float,
    hybrid_rank: int,
    dense_rank: int | None = None,
    dense_score: float | None = None,
    lexical_rank: int | None = None,
    lexical_score: float | None = None,
) -> HybridRerankCandidate:
    return HybridRerankCandidate(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        document_id="doc_a",
        text=f"text {chunk_id}",
        section_path=["S"],
        token_count=2,
        hybrid_rerank=HybridRerankProvenance(
            reranker_score=score,
            hybrid_rank=hybrid_rank,
            rrf_score=0.1,
            dense_rank=dense_rank,
            dense_score=dense_score,
            lexical_rank=lexical_rank,
            lexical_score=lexical_score,
        ),
    )


def _context(
    *,
    query: str,
    corpus_id: str = "corpus_1",
    chunk_set_id: str = "chunkset_1",
    dense_index_id: str = "dense_1",
) -> HybridRerankContextResult:
    anchors = [
        _anchor_cand(
            chunk_id="chunk_a",
            rank=1,
            score=1.2,
            hybrid_rank=1,
            dense_rank=1,
            dense_score=0.9,
            lexical_rank=None,
            lexical_score=None,
        ),
        _anchor_cand(
            chunk_id="chunk_b",
            rank=2,
            score=0.4,
            hybrid_rank=2,
            dense_rank=None,
            dense_score=None,
            lexical_rank=1,
            lexical_score=0.5,
        ),
    ]
    units = [
        EvidenceUnit(
            evidence_unit_id="ev_1",
            source_chunk_id="chunk_src",
            kind="child",
            text="body must not enter snapshot semantics",
            token_count=4,
            primary_anchor_chunk_id="chunk_a",
            contributing_anchor_chunk_ids=["chunk_a"],
            document_id="doc_a",
            section_path=["A"],
        )
    ]
    return HybridRerankContextResult(
        query=query,
        evidence_units=units,
        assembled_text="assembled",
        context_token_count=12,
        max_context_tokens=100,
        context_config_hash="ctxcfg_1",
        anchors=anchors,
        dense_index_id=dense_index_id,
        lexical_index_id="lex_1",
        fusion_config_hash="fus_1",
        reranker_config_hash="rrk_1",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=2,
            anchors_processed=2,
            evidence_unit_count=1,
            context_token_count=12,
            stop_reason="completed",
            clipping_occurred=False,
            budget_exhausted=False,
            dedup_hits=0,
            containment_suppressions=0,
        ),
        metadata={"corpus_id": corpus_id, "chunk_set_id": chunk_set_id},
    )


def _bindings(n: int = 3) -> list[FrozenCaseBinding]:
    return [
        FrozenCaseBinding(case_id=f"case_{i}", original_query=f"query-{i}")
        for i in range(1, n + 1)
    ]


def test_one_assembler_call_per_case_and_authoritative(tmp_path: Path) -> None:
    bindings = _bindings(3)
    calls: list[str] = []

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        calls.append(query)
        return _context(query=query)

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
        population_source_dataset_id="gold_test",
    )
    assert calls == ["query-1", "query-2", "query-3"]
    assert assembler.assemble.call_count == 3
    assert result.report.successful_case_count == 3
    assert result.report.failed_case_count == 0
    assert result.report.authoritative_for_11b is True
    assert result.manifest.authoritative_for_11b is True
    assert set(result.report.case_to_suffctx_id) == {"case_1", "case_2", "case_3"}


def test_no_retry_after_failing_case(tmp_path: Path) -> None:
    bindings = _bindings(3)
    calls: list[str] = []

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        calls.append(query)
        if query == "query-2":
            raise HybridRerankContextError("boom")
        return _context(query=query)

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    assert calls == ["query-1", "query-2", "query-3"]
    assert assembler.assemble.call_count == 3
    assert result.report.successful_case_count == 2
    assert result.report.failed_case_count == 1
    assert result.report.authoritative_for_11b is False
    assert result.report.failure_case_ids == ["case_2"]


def test_exact_case_query_binding_enforced(tmp_path: Path) -> None:
    bindings = [
        FrozenCaseBinding(case_id="case_1", original_query="frozen"),
    ]

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        # Upstream returns a different query string — must fail the case.
        return _context(query="not-frozen")

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    assert result.report.successful_case_count == 0
    assert result.report.failed_case_count == 1
    assert result.report.authoritative_for_11b is False


def test_mixed_lineage_records_failure_and_continues(tmp_path: Path) -> None:
    bindings = _bindings(3)
    calls: list[str] = []

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        calls.append(query)
        if query == "query-2":
            return _context(query=query, corpus_id="corpus_B")
        return _context(query=query, corpus_id="corpus_A")

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    assert calls == ["query-1", "query-2", "query-3"]
    assert assembler.assemble.call_count == 3
    assert result.report.successful_case_count == 2
    assert result.report.failed_case_count == 1
    assert result.report.authoritative_for_11b is False
    assert result.report.failure_case_ids == ["case_2"]
    assert "case_2" not in result.report.case_to_suffctx_id
    assert "case_2" not in result.report.snapshot_paths
    assert result.failures[0].failure_stage == "validate_context"
    assert result.report.shared_lineage is not None
    assert result.report.shared_lineage["corpus_id"] == "corpus_A"


def test_missing_lineage_records_failure_and_continues(tmp_path: Path) -> None:
    bindings = _bindings(3)
    calls: list[str] = []

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        calls.append(query)
        if query == "query-1":
            # Assemble succeeds, but required lineage metadata is absent.
            result = _context(query=query, corpus_id="corpus_A")
            return result.model_copy(
                update={"metadata": {"chunk_set_id": "chunkset_1"}}
            )
        return _context(query=query, corpus_id="corpus_A")

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    assert calls == ["query-1", "query-2", "query-3"]
    assert assembler.assemble.call_count == 3
    assert result.report.successful_case_count == 2
    assert result.report.failed_case_count == 1
    assert result.report.authoritative_for_11b is False
    assert result.report.failure_case_ids == ["case_1"]
    assert result.failures[0].failure_stage == "validate_context"
    assert (
        result.failures[0].reason_code
        == SufficiencyErrorCodeV1.MISSING_REQUIRED_LINEAGE
    )
    assert result.report.shared_lineage is not None
    assert result.report.shared_lineage["corpus_id"] == "corpus_A"


def test_zero_success_without_lineage_fails_closed(tmp_path: Path) -> None:
    bindings = _bindings(2)

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        result = _context(query=query)
        return result.model_copy(update={"metadata": {}})

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    with pytest.raises(PathBMeasureOnceError, match="no trustworthy shared lineage"):
        run_path_b_measure_once(
            settings=AppSettings(),
            bindings=bindings,
            corpus_name="ics_modules",
            artifacts_root=tmp_path,
            assembler=assembler,
        )


def test_incomplete_coverage_is_non_authoritative(tmp_path: Path) -> None:
    bindings = _bindings(3)

    def _assemble(
        *, query: str, corpus_name: str = "default"
    ) -> HybridRerankContextResult:
        if query == "query-3":
            raise HybridRerankContextError("fail once")
        return _context(query=query)

    assembler = MagicMock()
    assembler.assemble.side_effect = _assemble
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    assert result.report.successful_case_count == 2
    assert result.report.failed_case_count == 1
    assert result.report.expected_case_count == 3
    assert result.report.authoritative_for_11b is False


def test_no_gold_truth_in_snapshot_semantic_payload(tmp_path: Path) -> None:
    bindings = [FrozenCaseBinding(case_id="case_1", original_query="q")]

    assembler = MagicMock()
    assembler.assemble.side_effect = lambda **kwargs: _context(query=kwargs["query"])
    assembler.close = MagicMock()

    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    snap = result.snapshots[0]
    dumped = snap.model_dump(mode="json")
    text = str(dumped)
    for forbidden in (
        "judgments",
        "relevant_chunk_ids",
        "gold_dataset_id",
        "positive_chunk",
        "grade",
        "label_cohort",
    ):
        assert forbidden not in text
    assert "body must not enter snapshot semantics" not in text
    assert "text" not in snap.provenance.final_evidence_units[0].model_dump()


def test_runner_does_not_invoke_generation_or_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gen = MagicMock(side_effect=AssertionError("generation must not run"))
    monkeypatch.setattr(
        "offline_rag.generation.orchestrate.GroundedAnswerOrchestrator.generate",
        gen,
        raising=False,
    )
    bindings = [FrozenCaseBinding(case_id="case_1", original_query="q")]
    assembler = MagicMock()
    assembler.assemble.side_effect = lambda **kwargs: _context(query=kwargs["query"])
    assembler.close = MagicMock()
    run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    gen.assert_not_called()


def test_successful_results_pass_snapshot_validation(tmp_path: Path) -> None:
    bindings = _bindings(2)
    assembler = MagicMock()
    assembler.assemble.side_effect = lambda **kwargs: _context(query=kwargs["query"])
    assembler.close = MagicMock()
    result = run_path_b_measure_once(
        settings=AppSettings(),
        bindings=bindings,
        corpus_name="ics_modules",
        artifacts_root=tmp_path,
        assembler=assembler,
    )
    for snap in result.snapshots:
        # Re-deriving identity via builder validates OD-11-14 / adapter contract.
        rebuilt = build_sufficiency_snapshot(
            snap.provenance, observation=snap.observation
        )
        assert rebuilt.suffctx_id == snap.suffctx_id


def test_build_manifest_rejects_mixed_lineage_from_hand_built_snapshots() -> None:
    def _prov(corpus_id: str, case_id: str) -> SufficiencyProvenanceV1:
        return SufficiencyProvenanceV1(
            case_id=case_id,
            corpus_id=corpus_id,
            chunk_set_id="chunkset_1",
            dense_index_id="dense_1",
            lexical_index_id="lex_1",
            fusion_config_hash="fus_1",
            reranker_config_hash="rrk_1",
            context_config_hash="ctx_1",
            original_query="q",
            active_retrieval_query="q",
            attempt_number=0,
            attempt_role="initial",
            anchors=[
                SufficiencyAnchorProvenance(
                    chunk_id="chunk_a",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                    rrf_score=0.1,
                )
            ],
            final_evidence_units=[
                SufficiencyEvidenceUnitProvenance(
                    evidence_unit_id="ev_1",
                    document_id="doc_a",
                    section_path=["A"],
                    source_chunk_id="chunk_src",
                    primary_anchor_chunk_id="chunk_a",
                )
            ],
            diagnostics=SufficiencyAssemblyDiagnosticsV1(
                evidence_unit_count=1,
                context_token_count=1,
                stop_reason="completed",
            ),
        )

    snap_a = build_sufficiency_snapshot(_prov("corpus_A", "case_1"))
    snap_b = build_sufficiency_snapshot(_prov("corpus_B", "case_2"))
    with pytest.raises(SufficiencyArtifactError, match="mixed shared lineage"):
        build_sufficiency_manifest(
            snapshots=[snap_a, snap_b],
            failures=[],
            expected_case_ids=["case_1", "case_2"],
        )
