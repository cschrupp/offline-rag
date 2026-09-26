"""Unit tests for Slice 11B sufficiency measurement analysis."""

from __future__ import annotations

import json
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
    require_gold_manifest_lineage,
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

CORPUS_ID = "corpus_1"
CHUNK_SET_ID = "chunkset_1"


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
    corpus_id: str = CORPUS_ID,
    chunk_set_id: str = CHUNK_SET_ID,
) -> SufficiencyProvenanceV1:
    return SufficiencyProvenanceV1(
        case_id=case_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
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


def _loaded_gold(
    cases: list[GoldCase],
    *,
    chunk_set_id: str = CHUNK_SET_ID,
    corpus_id: str | None = CORPUS_ID,
) -> LoadedGoldDataset:
    dataset_id = compute_gold_dataset_id(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        corpus_name="ics_modules",
        cases=cases,
    )
    return LoadedGoldDataset(
        meta=GoldDatasetMeta(
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
            corpus_name="ics_modules",
            dataset_id=dataset_id,
        ),
        cases=tuple(sorted(cases, key=lambda c: c.id)),
        dataset_id=dataset_id,
        source_schema="offline-rag-gold-v1",
        compatibility_mode=None,
        path=Path("unused"),
    )


def _write_adjudication_map(
    path: Path,
    *,
    gold: LoadedGoldDataset,
    cohorts: dict[str, str],
) -> Path:
    payload = {
        "schema_version": "offline-rag-generation-cohort-map-v1",
        "gold_dataset_id": gold.dataset_id,
        "cases": [
            {"case_id": case_id, "label_cohort": cohorts[case_id]}
            for case_id in sorted(cohorts)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _persist_pair(
    tmp_path: Path,
    *,
    present_case: bool = True,
    score_a: float = 2.0,
    score_b: float = 0.5,
    docs_a: str = "doc_a",
    docs_b: str = "doc_b",
    case_a_cohort: str = "human_reviewed",
    case_b_cohort: str = "human_reviewed",
    chunk_set_id: str = CHUNK_SET_ID,
    corpus_id: str = CORPUS_ID,
) -> tuple[Path, LoadedGoldDataset, object, Path]:
    """Build A/B fixture: case_a present, case_b missing by default."""
    gold = _loaded_gold(
        [
            _gold_case("case_a", "query a", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
        ],
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
    )
    snap_a = build_sufficiency_snapshot(
        _provenance(
            case_id="case_a",
            query="query a",
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
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
            chunk_set_id=chunk_set_id,
            corpus_id=corpus_id,
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
    adj_path = _write_adjudication_map(
        tmp_path / "adjudication_cohort_map_v1.json",
        gold=gold,
        cohorts={"case_a": case_a_cohort, "case_b": case_b_cohort},
    )
    return tmp_path, gold, manifest, adj_path


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


def test_assign_cohort_fails_closed_without_gold_positives() -> None:
    with pytest.raises(Sufficiency11BError, match="no Gold positive"):
        assign_cohort(gold_positive_chunk_ids=set(), evidence_surface={"x"})


def test_matching_gold_manifest_lineage_succeeds(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    binding = require_gold_manifest_lineage(gold=gold, manifest=manifest)
    assert binding.gold_chunk_set_id == CHUNK_SET_ID
    assert binding.manifest_chunk_set_id == CHUNK_SET_ID
    assert binding.gold_corpus_id == CORPUS_ID
    labels, lineage, adjudication = join_authoritative_labels(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
    )
    assert lineage.gold_chunk_set_id == CHUNK_SET_ID
    assert adjudication.source_schema_version == (
        "offline-rag-generation-cohort-map-v1"
    )
    assert len(labels) == 2


def test_gold_chunk_set_mismatch_fails_closed(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    bad_gold = _loaded_gold(
        list(gold.cases),
        chunk_set_id="chunkset_OTHER",
        corpus_id=CORPUS_ID,
    )
    with pytest.raises(Sufficiency11BError, match="chunk_set_id mismatch"):
        join_authoritative_labels(
            manifest=manifest,
            gold=bad_gold,
            artifacts_root=artifacts_root,
            adjudication_map_path=adj_path,
        )


def test_gold_corpus_mismatch_fails_closed(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    bad_gold = _loaded_gold(
        list(gold.cases),
        chunk_set_id=CHUNK_SET_ID,
        corpus_id="corpus_OTHER",
    )
    with pytest.raises(Sufficiency11BError, match="corpus_id mismatch"):
        join_authoritative_labels(
            manifest=manifest,
            gold=bad_gold,
            artifacts_root=artifacts_root,
            adjudication_map_path=adj_path,
        )


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
    adj = _write_adjudication_map(
        tmp_path / "adj.json",
        gold=gold,
        cohorts={"case_a": "human_reviewed"},
    )
    assert incomplete.authoritative_for_11b is False
    with pytest.raises(Exception, match="not authoritative for 11B"):
        join_authoritative_labels(
            manifest=incomplete,
            gold=gold,
            artifacts_root=tmp_path,
            adjudication_map_path=adj,
        )


def test_exact_gold_snapshot_binding_and_cohorts(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    labels, _lineage, adjudication = join_authoritative_labels(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
    )
    assert [item.case_id for item in labels] == ["case_a", "case_b"]
    assert labels[0].threshold_cohort == "A"
    assert labels[1].threshold_cohort == "B"
    assert labels[0].adjudication_cohort == "human_reviewed"
    assert adjudication.human_reviewed_case_count == 2


def test_assistant_only_never_enters_threshold_counts(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(
        tmp_path,
        case_a_cohort="human_reviewed",
        case_b_cohort="assistant_only",
    )
    analysis = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert analysis.path_b_case_count == 2
    assert analysis.human_reviewed_case_count == 1
    assert analysis.assistant_only_case_count == 1
    assert analysis.assistant_only_case_ids == ["case_b"]
    assert analysis.population_a_count == 1
    assert analysis.population_b_count == 0
    assert analysis.population_a_case_ids == ["case_a"]
    assert analysis.population_b_case_ids == []

    by_id = {item.case_id: item for item in analysis.case_labels}
    assert by_id["case_b"].threshold_eligible is False
    assert by_id["case_b"].threshold_cohort is None
    assert by_id["case_b"].adjudication_cohort == "assistant_only"
    # Features still reported for assistant-only descriptively.
    assert by_id["case_b"].features.anchor_count == 2

    for item in analysis.threshold_evaluations:
        assert "case_b" not in item.gated_case_ids
        assert "case_b" not in item.gated_cohort_a_case_ids
        assert "case_b" not in item.gated_cohort_b_case_ids


def test_empty_b_marks_cohort_separation_not_assessable(tmp_path: Path) -> None:
    # Both human-reviewed and both present → A=2 B=0
    artifacts_root2 = tmp_path / "both_present"
    gold2 = _loaded_gold(
        [
            _gold_case("case_a", "query a", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
        ]
    )
    snaps = []
    for case_id, query, pos, score in (
        ("case_a", "query a", "pos_a", 2.0),
        ("case_b", "query b", "pos_b", 0.5),
    ):
        snap = build_sufficiency_snapshot(
            _provenance(
                case_id=case_id,
                query=query,
                anchors=[
                    _anchor(
                        chunk_id=pos,
                        rerank_rank=1,
                        reranker_score=score,
                        hybrid_rank=1,
                    ),
                    _anchor(
                        chunk_id=f"neg_{case_id}",
                        rerank_rank=2,
                        reranker_score=score - 0.1,
                        hybrid_rank=2,
                        dense_rank=None,
                        dense_score=None,
                        lexical_rank=2,
                        lexical_score=0.2,
                    ),
                ],
                units=[
                    _unit(
                        evidence_unit_id=f"ev_{case_id}",
                        document_id="doc",
                        section_path=["S"],
                        source_chunk_id=f"parent_{case_id}",
                        primary_anchor_chunk_id=pos,
                    )
                ],
            )
        )
        persist_sufficiency_snapshot(
            snap, path=default_snapshot_artifact_path(artifacts_root2, snap.suffctx_id)
        )
        snaps.append(snap)
    manifest2 = build_sufficiency_manifest(
        snapshots=snaps,
        failures=[],
        expected_case_ids=["case_a", "case_b"],
    )
    persist_sufficiency_manifest(
        manifest2,
        path=default_manifest_artifact_path(artifacts_root2, manifest2.suffctxrun_id),
    )
    adj2 = _write_adjudication_map(
        artifacts_root2 / "adj.json",
        gold=gold2,
        cohorts={"case_a": "human_reviewed", "case_b": "human_reviewed"},
    )
    analysis = build_11b_analysis(
        manifest=manifest2,
        gold=gold2,
        artifacts_root=artifacts_root2,
        adjudication_map_path=adj2,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert analysis.population_a_count == 2
    assert analysis.population_b_count == 0
    for dist in analysis.feature_distributions:
        assert dist.cohort_separation_assessable is False
    assert analysis.conclusion == "no_additional_gate_promoted"
    assert analysis.recommended_candidate_rule_ids == []
    score_dist = next(
        d for d in analysis.feature_distributions if d.feature == "top_reranker_score"
    )
    assert score_dist.varies_on_fixture is True


def test_threshold_enumeration_human_only_with_b_capture(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(
        tmp_path, score_a=2.0, score_b=0.5
    )
    analysis = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    rule = next(
        item
        for item in analysis.threshold_evaluations
        if item.rule_id.startswith("top_reranker_score<") and item.threshold == 2.0
    )
    assert rule.gated_case_ids == ["case_b"]
    assert rule.false_refusal_candidate_count == 0
    assert rule.retrieval_failure_proxy_capture_count == 1
    assert rule.eligible_for_recommendation is True
    assert analysis.conclusion == "candidate_gate_reported_for_review"


def test_query_mismatch_fails_closed(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    bad_gold = _loaded_gold(
        [
            _gold_case("case_a", "DIFFERENT", ["pos_a"]),
            _gold_case("case_b", "query b", ["pos_b"]),
        ]
    )
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
            manifest=manifest,
            gold=bad_gold,
            artifacts_root=artifacts_root,
            adjudication_map_path=adj_path,
        )


def test_snapshots_not_mutated(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    snap_id = manifest.attempt_groups[0].attempts[0].suffctx_id
    path = default_snapshot_artifact_path(artifacts_root, snap_id)
    before = path.read_text(encoding="utf-8")
    build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    after = path.read_text(encoding="utf-8")
    assert before == after


def test_no_retrieval_or_generation_calls(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    with patch(
        "offline_rag.context.assemble.HybridRerankContextAssembler",
        MagicMock(),
    ) as assembler_cls:
        build_11b_analysis(
            manifest=manifest,
            gold=gold,
            artifacts_root=artifacts_root,
            adjudication_map_path=adj_path,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assembler_cls.assert_not_called()


def test_analysis_rerun_identical_semantic_result(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path)
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    first = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
        created_at=stamp,
    )
    second = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
        adjudication_map_path=adj_path,
        created_at=datetime(2026, 2, 2, tzinfo=UTC),
    )
    assert analysis_semantic_payload(first) == analysis_semantic_payload(second)
    _j1, m1 = persist_11b_analysis(first, output_dir=tmp_path / "out1")
    _j2, m2 = persist_11b_analysis(second, output_dir=tmp_path / "out2")
    assert m1.read_text(encoding="utf-8") == m2.read_text(encoding="utf-8")


def test_run_11b_analysis_end_to_end_with_written_gold(tmp_path: Path) -> None:
    artifacts_root, gold, manifest, adj_path = _persist_pair(tmp_path / "arts")
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    meta = {
        "schema_version": "offline-rag-gold-v1",
        "chunk_set_id": CHUNK_SET_ID,
        "corpus_id": CORPUS_ID,
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
        adjudication_map_path=adj_path,
    )
    assert result.analysis.population_a_count == 1
    assert result.analysis.population_b_count == 1
    assert result.analysis.gold_dataset_id == gold.dataset_id
    assert result.analysis_json_path.is_file()
    assert result.analysis_md_path.is_file()
