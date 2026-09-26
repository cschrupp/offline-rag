"""Unit tests for Slice 11B sufficiency measurement analysis."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from offline_rag.evaluation.gold import (
    ChunkJudgment,
    GoldCase,
    GoldDatasetMeta,
    LoadedGoldDataset,
    compute_gold_dataset_id,
)
from offline_rag.evaluation.sufficiency_11b import (
    Sufficiency11BError,
    analysis_semantic_payload,
    assign_cohort,
    build_11b_analysis,
    evidence_surface_chunk_ids,
    join_authoritative_labels,
    persist_11b_analysis,
    run_11b_analysis,
)
from offline_rag.sufficiency import (
    build_sufficiency_manifest,
    build_sufficiency_snapshot,
    default_manifest_artifact_path,
    default_snapshot_artifact_path,
    persist_sufficiency_manifest,
    persist_sufficiency_snapshot,
    require_authoritative_manifest,
)
from offline_rag.sufficiency.contracts import (
    SufficiencyAnchorProvenance,
    SufficiencyAssemblyDiagnosticsV1,
    SufficiencyEvidenceUnitProvenance,
    SufficiencyProvenanceV1,
)


def _anchor(
    *,
    chunk_id: str,
    rerank_rank: int,
    reranker_score: float,
    hybrid_rank: int,
    dense_rank: int | None = 1,
    dense_score: float | None = 0.9,
    lexical_rank: int | None = 1,
    lexical_score: float | None = 0.8,
) -> SufficiencyAnchorProvenance:
    return SufficiencyAnchorProvenance(
        chunk_id=chunk_id,
        rerank_rank=rerank_rank,
        reranker_score=reranker_score,
        hybrid_rank=hybrid_rank,
        rrf_score=0.1,
        dense_rank=dense_rank,
        dense_score=dense_score,
        lexical_rank=lexical_rank,
        lexical_score=lexical_score,
    )


def _unit(
    *,
    evidence_unit_id: str,
    document_id: str,
    section_path: list[str],
    source_chunk_id: str,
    primary_anchor_chunk_id: str,
) -> SufficiencyEvidenceUnitProvenance:
    return SufficiencyEvidenceUnitProvenance(
        evidence_unit_id=evidence_unit_id,
        document_id=document_id,
        section_path=section_path,
        source_chunk_id=source_chunk_id,
        primary_anchor_chunk_id=primary_anchor_chunk_id,
    )


def _provenance(
    *,
    case_id: str,
    query: str,
    anchors: list[SufficiencyAnchorProvenance],
    units: list[SufficiencyEvidenceUnitProvenance],
    corpus_id: str = "corpus_1",
) -> SufficiencyProvenanceV1:
    return SufficiencyProvenanceV1(
        case_id=case_id,
        corpus_id=corpus_id,
        chunk_set_id="chunkset_1",
        dense_index_id="dense_1",
        lexical_index_id="lexical_1",
        fusion_config_hash="fuscfg_1",
        reranker_config_hash="rrkcfg_1",
        context_config_hash="ctxcfg_1",
        original_query=query,
        active_retrieval_query=query,
        attempt_number=0,
        attempt_role="initial",
        anchors=anchors,
        final_evidence_units=units,
        diagnostics=SufficiencyAssemblyDiagnosticsV1(
            evidence_unit_count=len(units),
            context_token_count=10 if units else 0,
        ),
    )


def _gold_case(case_id: str, query: str, positive_ids: list[str]) -> GoldCase:
    return GoldCase(
        id=case_id,
        query=query,
        judgments=tuple(
            ChunkJudgment(chunk_id=cid, relevance=1) for cid in positive_ids
        ),
    )


def _loaded_gold(cases: list[GoldCase]) -> LoadedGoldDataset:
    dataset_id = compute_gold_dataset_id(
        chunk_set_id="chunkset_1",
        corpus_id="corpus_1",
        corpus_name="ics_modules",
        cases=cases,
    )
    return LoadedGoldDataset(
        meta=GoldDatasetMeta(
            chunk_set_id="chunkset_1",
            corpus_id="corpus_1",
            corpus_name="ics_modules",
            dataset_id=dataset_id,
        ),
        cases=tuple(sorted(cases, key=lambda c: c.id)),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=Path("unused"),
    )


def _persist_pair(
    tmp_path: Path,
    *,
    present_case: bool = True,
    score_a: float = 2.0,
    score_b: float = 0.5,
    docs_a: str = "doc_a",
    docs_b: str = "doc_b",
) -> tuple[Path, LoadedGoldDataset, object]:
    """Build A/B fixture: case_a present, case_b missing (unless toggled)."""
    gold = _loaded_gold(
        [
            _gold_case("case_a", "query a", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
        ]
    )
    snap_a = build_sufficiency_snapshot(
        _provenance(
            case_id="case_a",
            query="query a",
            anchors=[
                _anchor(
                    chunk_id="pos_a" if present_case else "other_a",
                    rerank_rank=1,
                    reranker_score=score_a,
                    hybrid_rank=1,
                ),
                _anchor(
                    chunk_id="neg_a",
                    rerank_rank=2,
                    reranker_score=score_a - 0.5,
                    hybrid_rank=2,
                    dense_rank=None,
                    dense_score=None,
                    lexical_rank=2,
                    lexical_score=0.4,
                ),
            ],
            units=[
                _unit(
                    evidence_unit_id="ev_a",
                    document_id=docs_a,
                    section_path=["S1"],
                    source_chunk_id="parent_a",
                    primary_anchor_chunk_id="pos_a" if present_case else "other_a",
                )
            ],
        )
    )
    snap_b = build_sufficiency_snapshot(
        _provenance(
            case_id="case_b",
            query="query b",
            anchors=[
                _anchor(
                    chunk_id="other_b",
                    rerank_rank=1,
                    reranker_score=score_b,
                    hybrid_rank=1,
                    dense_rank=None,
                    dense_score=None,
                    lexical_rank=1,
                    lexical_score=0.7,
                ),
                _anchor(
                    chunk_id="neg_b",
                    rerank_rank=2,
                    reranker_score=score_b - 0.1,
                    hybrid_rank=2,
                    dense_rank=2,
                    dense_score=0.3,
                    lexical_rank=None,
                    lexical_score=None,
                ),
            ],
            units=[
                _unit(
                    evidence_unit_id="ev_b",
                    document_id=docs_b,
                    section_path=["S2", "S2b"],
                    source_chunk_id="parent_b",
                    primary_anchor_chunk_id="other_b",
                )
            ],
        )
    )
    for snap in (snap_a, snap_b):
        persist_sufficiency_snapshot(
            snap, path=default_snapshot_artifact_path(tmp_path, snap.suffctx_id)
        )
    manifest = build_sufficiency_manifest(
        snapshots=[snap_a, snap_b],
        failures=[],
        expected_case_ids=["case_a", "case_b"],
        audit=None,
    )
    require_authoritative_manifest(manifest)
    persist_sufficiency_manifest(
        manifest,
        path=default_manifest_artifact_path(tmp_path, manifest.suffctxrun_id),
    )
    return tmp_path, gold, manifest


def test_presence_matching_uses_anchor_and_eu_chunk_ids() -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            case_id="c1",
            query="q",
            anchors=[
                _anchor(
                    chunk_id="anchor_only",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                )
            ],
            units=[
                _unit(
                    evidence_unit_id="ev",
                    document_id="d",
                    section_path=["S"],
                    source_chunk_id="source_chunk",
                    primary_anchor_chunk_id="primary_chunk",
                )
            ],
        )
    )
    surface = evidence_surface_chunk_ids(snap)
    assert surface == {"anchor_only", "source_chunk", "primary_chunk"}
    cohort, present = assign_cohort(
        gold_positive_chunk_ids={"primary_chunk", "missing"},
        evidence_surface=surface,
    )
    assert cohort == "A"
    assert present == {"primary_chunk"}
    cohort_b, present_b = assign_cohort(
        gold_positive_chunk_ids={"missing"},
        evidence_surface=surface,
    )
    assert cohort_b == "B"
    assert present_b == set()


def test_assign_cohort_fails_closed_without_gold_positives() -> None:
    with pytest.raises(Sufficiency11BError, match="no Gold positive"):
        assign_cohort(gold_positive_chunk_ids=set(), evidence_surface={"x"})


def test_authoritative_manifest_required(tmp_path: Path) -> None:
    gold = _loaded_gold([_gold_case("case_a", "query a", ["pos_a"])])
    snap = build_sufficiency_snapshot(
        _provenance(
            case_id="case_a",
            query="query a",
            anchors=[
                _anchor(
                    chunk_id="pos_a",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                )
            ],
            units=[
                _unit(
                    evidence_unit_id="ev",
                    document_id="d",
                    section_path=["S"],
                    source_chunk_id="pos_a",
                    primary_anchor_chunk_id="pos_a",
                )
            ],
        )
    )
    persist_sufficiency_snapshot(
        snap, path=default_snapshot_artifact_path(tmp_path, snap.suffctx_id)
    )
    incomplete = build_sufficiency_manifest(
        snapshots=[snap],
        failures=[],
        expected_case_ids=["case_a", "case_missing"],
    )
    assert incomplete.authoritative_for_11b is False
    with pytest.raises(Exception, match="not authoritative for 11B"):
        join_authoritative_labels(
            manifest=incomplete, gold=gold, artifacts_root=tmp_path
        )


def test_exact_gold_snapshot_binding_and_cohorts(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    labels = join_authoritative_labels(
        manifest=manifest, gold=gold, artifacts_root=artifacts_root
    )
    assert [item.case_id for item in labels] == ["case_a", "case_b"]
    assert labels[0].cohort == "A"
    assert labels[1].cohort == "B"
    assert labels[0].gold_dataset_id == gold.dataset_id
    assert "pos_a" in labels[0].present_positive_chunk_ids
    assert labels[1].present_positive_chunk_ids == []


def test_query_mismatch_fails_closed(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    bad_gold = _loaded_gold(
        [
            _gold_case("case_a", "DIFFERENT", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
        ]
    )
    # Force same dataset id surface for join path; mismatch is on query binding.
    bad_gold = LoadedGoldDataset(
        meta=gold.meta,
        cases=bad_gold.cases,
        dataset_id=gold.dataset_id,
        source_schema=gold.source_schema,
        compatibility_mode=None,
        path=gold.path,
    )
    with pytest.raises(Sufficiency11BError, match="case/query binding mismatch"):
        join_authoritative_labels(
            manifest=manifest, gold=bad_gold, artifacts_root=artifacts_root
        )


def test_case_coverage_mismatch_fails_closed(tmp_path: Path) -> None:
    artifacts_root, _gold, manifest = _persist_pair(tmp_path)
    extra = _loaded_gold(
        [
            _gold_case("case_a", "query a", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
            _gold_case("case_c", "query c", ["pos_c"]),
        ]
    )
    with pytest.raises(Sufficiency11BError, match="case coverage mismatch"):
        join_authoritative_labels(
            manifest=manifest, gold=extra, artifacts_root=artifacts_root
        )


def test_snapshots_not_mutated(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    snap_id = manifest.attempt_groups[0].attempts[0].suffctx_id
    path = default_snapshot_artifact_path(artifacts_root, snap_id)
    before = path.read_text(encoding="utf-8")
    build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_threshold_enumeration_and_affected_case_ids(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(
        tmp_path, score_a=2.0, score_b=0.5
    )
    analysis = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # Low-score gate: score < 1.0 should gate only case_b (Population B).
    rule = next(
        item
        for item in analysis.threshold_evaluations
        if item.rule_id.startswith("top_reranker_score<") and item.threshold == 2.0
    )
    # score_a=2.0, score_b=0.5 → top_reranker_score < 2.0 gates case_b only
    assert rule.gated_case_ids == ["case_b"]
    assert rule.false_refusal_candidate_count == 0
    assert rule.retrieval_failure_proxy_capture_count == 1
    assert rule.eligible_for_recommendation is True
    assert "top_reranker_score<2.0" in analysis.recommended_candidate_rule_ids
    assert analysis.conclusion == "candidate_gate_reported_for_review"


def test_constant_features_marked_non_discriminative(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    analysis = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    by_name = {item.feature: item for item in analysis.feature_distributions}
    assert by_name["empty_context"].non_discriminative is True
    assert by_name["anchor_count"].non_discriminative is True
    # Only observed boolean state is False → gates all cases; not eligible.
    empty_false = next(
        item
        for item in analysis.threshold_evaluations
        if item.rule_id == "empty_context==false"
    )
    assert empty_false.eligible_for_recommendation is False
    assert set(empty_false.gated_case_ids) == {"case_a", "case_b"}


def test_no_retrieval_or_generation_calls(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    with (
        patch(
            "offline_rag.context.assemble.HybridRerankContextAssembler",
            MagicMock(),
        ) as assembler_cls,
        patch(
            "offline_rag.evaluation.sufficiency_11b.load_gold_dataset",
            wraps=None,
        ),
    ):
        build_11b_analysis(
            manifest=manifest,
            gold=gold,
            artifacts_root=artifacts_root,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assembler_cls.assert_not_called()


def test_analysis_rerun_identical_semantic_result(tmp_path: Path) -> None:
    artifacts_root, gold, manifest = _persist_pair(tmp_path)
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    first = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        created_at=stamp,
    )
    second = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        created_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    assert analysis_semantic_payload(first) == analysis_semantic_payload(second)
    j1, m1 = persist_11b_analysis(first, output_dir=tmp_path / "out1")
    j2, m2 = persist_11b_analysis(second, output_dir=tmp_path / "out2")
    # Markdown includes created_at indirectly? No — render does not include created_at.
    assert m1.read_text(encoding="utf-8") == m2.read_text(encoding="utf-8")
    assert j1.is_file() and j2.is_file()


def test_run_11b_analysis_end_to_end_with_written_gold(tmp_path: Path) -> None:
    import json

    artifacts_root, gold, manifest = _persist_pair(tmp_path / "arts")
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    meta = {
        "schema_version": "offline-rag-gold-v1",
        "chunk_set_id": "chunkset_1",
        "corpus_id": "corpus_1",
        "corpus_name": "ics_modules",
        "dataset_id": gold.dataset_id,
    }
    (gold_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    lines = [
        json.dumps(
            {
                "id": case.id,
                "query": case.query,
                "judgments": [
                    {"chunk_id": j.chunk_id, "relevance": j.relevance}
                    for j in case.judgments
                ],
            },
            sort_keys=True,
        )
        for case in gold.cases
    ]
    (gold_dir / "cases.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = tmp_path / "11b_out"
    result = run_11b_analysis(
        manifest_path=default_manifest_artifact_path(
            artifacts_root, manifest.suffctxrun_id
        ),
        gold_dataset_path=gold_dir,
        artifacts_root=artifacts_root,
        output_dir=out,
    )
    assert result.analysis.population_a_count == 1
    assert result.analysis.population_b_count == 1
    assert result.analysis.gold_dataset_id == gold.dataset_id
    assert result.analysis_json_path.is_file()
    assert result.analysis_md_path.is_file()
