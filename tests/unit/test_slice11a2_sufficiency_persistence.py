"""Unit tests for Slice 11A-2 sufficiency snapshot/manifest persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from offline_rag.sufficiency import (
    SufficiencyArtifactError,
    SufficiencyDerivationError,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyPersistenceError,
    SufficiencyProvenanceV1,
    SufficiencySnapshotAuditV1,
    build_failure_record,
    build_sufficiency_manifest,
    build_sufficiency_snapshot,
    default_manifest_artifact_path,
    default_snapshot_artifact_path,
    derive_sufficiency_observation,
    load_sufficiency_manifest,
    load_sufficiency_snapshot,
    persist_sufficiency_manifest,
    persist_sufficiency_snapshot,
    require_authoritative_manifest,
    validate_observation_against_provenance,
)
from offline_rag.sufficiency.contracts import (
    SufficiencyAnchorProvenance,
    SufficiencyAssemblyDiagnosticsV1,
    SufficiencyEvidenceUnitProvenance,
)


def _anchor(
    *,
    chunk_id: str,
    rerank_rank: int,
    reranker_score: float,
    hybrid_rank: int,
) -> SufficiencyAnchorProvenance:
    return SufficiencyAnchorProvenance(
        chunk_id=chunk_id,
        rerank_rank=rerank_rank,
        reranker_score=reranker_score,
        hybrid_rank=hybrid_rank,
        rrf_score=0.1,
    )


def _unit(
    *,
    evidence_unit_id: str,
    document_id: str,
    section_path: list[str],
) -> SufficiencyEvidenceUnitProvenance:
    return SufficiencyEvidenceUnitProvenance(
        evidence_unit_id=evidence_unit_id,
        document_id=document_id,
        section_path=section_path,
        source_chunk_id="chunk_src",
        primary_anchor_chunk_id="chunk_a",
    )


def _provenance(
    *,
    case_id: str = "case_1",
    corpus_id: str = "corpus_1",
    chunk_set_id: str = "chunkset_1",
    units: list[SufficiencyEvidenceUnitProvenance] | None = None,
    anchors: list[SufficiencyAnchorProvenance] | None = None,
    original_query: str = "what is X?",
) -> SufficiencyProvenanceV1:
    final_units = list(units or [])
    return SufficiencyProvenanceV1(
        case_id=case_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id="dense_1",
        lexical_index_id="lexical_1",
        fusion_config_hash="fuscfg_1",
        reranker_config_hash="rrkcfg_1",
        context_config_hash="ctxcfg_1",
        original_query=original_query,
        active_retrieval_query=original_query,
        attempt_number=0,
        attempt_role="initial",
        anchors=list(
            anchors
            or [
                _anchor(
                    chunk_id="c1",
                    rerank_rank=1,
                    reranker_score=1.5,
                    hybrid_rank=1,
                )
            ]
        ),
        final_evidence_units=final_units,
        diagnostics=SufficiencyAssemblyDiagnosticsV1(
            evidence_unit_count=len(final_units),
            context_token_count=10 if final_units else 0,
        ),
    )


def test_snapshot_round_trip_and_recompute(tmp_path: Path) -> None:
    provenance = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])]
    )
    snapshot = build_sufficiency_snapshot(provenance)
    validate_observation_against_provenance(snapshot.observation, snapshot.provenance)

    path = default_snapshot_artifact_path(tmp_path, snapshot.suffctx_id)
    persist_sufficiency_snapshot(snapshot, path=path)
    loaded = load_sufficiency_snapshot(path)
    assert loaded.suffctx_id == snapshot.suffctx_id
    assert loaded.provenance == snapshot.provenance
    assert loaded.observation == snapshot.observation
    validate_observation_against_provenance(loaded.observation, loaded.provenance)


def test_snapshot_identity_deterministic_and_semantic_sensitive() -> None:
    provenance = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])]
    )
    first = build_sufficiency_snapshot(provenance)
    second = build_sufficiency_snapshot(provenance)
    assert first.suffctx_id == second.suffctx_id
    assert first.suffctx_id.startswith("suffctx_")

    changed = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_b", section_path=["A"])]
    )
    other = build_sufficiency_snapshot(changed)
    assert other.suffctx_id != first.suffctx_id


def test_audit_timing_does_not_change_snapshot_identity() -> None:
    provenance = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])]
    )
    left = build_sufficiency_snapshot(
        provenance,
        audit=SufficiencySnapshotAuditV1(
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
            latency_ms=12.5,
            source_path="/tmp/a",
            host="host-a",
        ),
    )
    right = build_sufficiency_snapshot(
        provenance,
        audit=SufficiencySnapshotAuditV1(
            created_at=datetime(2025, 6, 1, tzinfo=UTC),
            latency_ms=999.0,
            source_path="/tmp/b",
            host="host-b",
        ),
    )
    assert left.suffctx_id == right.suffctx_id


def test_manifest_identity_independent_of_timestamps() -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ]
        )
    )
    first = build_sufficiency_manifest(
        snapshots=[snap],
        failures=[],
        expected_case_ids=["case_1"],
    )
    second = build_sufficiency_manifest(
        snapshots=[snap],
        failures=[],
        expected_case_ids=["case_1"],
    )
    assert first.suffctxrun_id == second.suffctxrun_id
    assert first.suffctxrun_id.startswith("suffctxrun_")
    assert first.authoritative_for_11b is True


def test_manifest_attempt_group_ordering_by_case_id() -> None:
    snap_b = build_sufficiency_snapshot(
        _provenance(
            case_id="case_b",
            units=[
                _unit(evidence_unit_id="ev_b", document_id="doc_a", section_path=["A"])
            ],
        )
    )
    snap_a = build_sufficiency_snapshot(
        _provenance(
            case_id="case_a",
            units=[
                _unit(evidence_unit_id="ev_a", document_id="doc_a", section_path=["A"])
            ],
        )
    )
    manifest = build_sufficiency_manifest(
        snapshots=[snap_b, snap_a],
        failures=[],
        expected_case_ids=["case_b", "case_a"],
    )
    assert [group.case_id for group in manifest.attempt_groups] == ["case_a", "case_b"]


def test_slice11_rejects_recovery_attempt() -> None:
    provenance = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])]
    )
    recovery = provenance.model_copy(
        update={
            "attempt_number": 1,
            "attempt_role": "recovery",
            "active_retrieval_query": "rewritten?",
        }
    )
    snapshot = build_sufficiency_snapshot(recovery)
    with pytest.raises(SufficiencyArtifactError) as exc:
        build_sufficiency_manifest(
            snapshots=[snapshot],
            failures=[],
            expected_case_ids=["case_1"],
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS


def test_shared_lineage_mismatch_fails() -> None:
    snap_a = build_sufficiency_snapshot(
        _provenance(
            case_id="case_a",
            corpus_id="corpus_1",
            units=[
                _unit(evidence_unit_id="ev_a", document_id="doc_a", section_path=["A"])
            ],
        )
    )
    snap_b = build_sufficiency_snapshot(
        _provenance(
            case_id="case_b",
            corpus_id="corpus_OTHER",
            units=[
                _unit(evidence_unit_id="ev_b", document_id="doc_a", section_path=["A"])
            ],
        )
    )
    with pytest.raises(SufficiencyArtifactError) as exc:
        build_sufficiency_manifest(
            snapshots=[snap_a, snap_b],
            failures=[],
            expected_case_ids=["case_a", "case_b"],
        )
    assert "mixed shared lineage" in str(exc.value)


def test_duplicate_case_attempt_conflict_fails() -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ]
        )
    )
    with pytest.raises(SufficiencyArtifactError) as exc:
        build_sufficiency_manifest(
            snapshots=[snap, snap],
            failures=[],
            expected_case_ids=["case_1"],
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS


def test_snapshot_failure_produces_no_partial_artifact(tmp_path: Path) -> None:
    bad = _provenance(original_query="q1")
    bad = bad.model_copy(update={"active_retrieval_query": "q2"})
    path = tmp_path / "should_not_exist.json"
    with pytest.raises(SufficiencyDerivationError) as exc:
        build_sufficiency_snapshot(bad)
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS
    assert not path.exists()

    record = build_failure_record(
        case_id="case_1",
        failure_stage="derive",
        error=exc.value,
        original_query="q1",
    )
    assert record.reason_code == SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS
    assert record.details is not None


def test_manifest_failure_record_preserves_stable_code_and_details(
    tmp_path: Path,
) -> None:
    good = build_sufficiency_snapshot(
        _provenance(
            case_id="case_ok",
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ],
        )
    )
    failure = build_failure_record(
        case_id="case_bad",
        failure_stage="derive",
        error=SufficiencyDerivationError(
            SufficiencyErrorCodeV1.MISSING_DOCUMENT_ID,
            "missing document",
            details=SufficiencyErrorDetailsV1(field_name="document_id"),
        ),
        original_query="what failed?",
    )
    manifest = build_sufficiency_manifest(
        snapshots=[good],
        failures=[failure],
        expected_case_ids=["case_ok", "case_bad"],
    )
    assert manifest.authoritative_for_11b is False
    assert manifest.failed_case_count == 1
    assert (
        manifest.failures[0].reason_code == SufficiencyErrorCodeV1.MISSING_DOCUMENT_ID
    )
    assert manifest.failures[0].details is not None
    assert manifest.failures[0].details.field_name == "document_id"

    path = default_manifest_artifact_path(tmp_path, manifest.suffctxrun_id)
    persist_sufficiency_manifest(manifest, path=path)
    loaded = load_sufficiency_manifest(path)
    assert loaded.failures[0].reason_code == SufficiencyErrorCodeV1.MISSING_DOCUMENT_ID
    assert loaded.failures[0].details is not None
    assert loaded.failures[0].diagnostic == "missing document"


def test_incomplete_manifest_cannot_be_marked_authoritative() -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ]
        )
    )
    failure = build_failure_record(
        case_id="case_2",
        failure_stage="derive",
        error=SufficiencyDerivationError(
            SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS,
            "mismatch",
        ),
        original_query="q",
    )
    manifest = build_sufficiency_manifest(
        snapshots=[snap],
        failures=[failure],
        expected_case_ids=["case_1", "case_2"],
    )
    assert manifest.authoritative_for_11b is False
    with pytest.raises(SufficiencyArtifactError):
        require_authoritative_manifest(manifest)


def test_identical_persisted_write_is_idempotent(tmp_path: Path) -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ]
        )
    )
    path = default_snapshot_artifact_path(tmp_path, snap.suffctx_id)
    assert persist_sufficiency_snapshot(snap, path=path) == path
    again = snap.model_copy(
        update={"audit": SufficiencySnapshotAuditV1(latency_ms=1.0)}
    )
    assert persist_sufficiency_snapshot(again, path=path) == path

    manifest = build_sufficiency_manifest(
        snapshots=[snap],
        failures=[],
        expected_case_ids=["case_1"],
    )
    mpath = default_manifest_artifact_path(tmp_path, manifest.suffctxrun_id)
    assert persist_sufficiency_manifest(manifest, path=mpath) == mpath
    assert persist_sufficiency_manifest(manifest, path=mpath) == mpath


def test_conflicting_same_id_write_fails_closed(tmp_path: Path) -> None:
    snap = build_sufficiency_snapshot(
        _provenance(
            units=[
                _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])
            ]
        )
    )
    path = default_snapshot_artifact_path(tmp_path, snap.suffctx_id)
    persist_sufficiency_snapshot(snap, path=path)

    # Corrupt on-disk semantic contents while preserving the same suffctx_id.
    corrupted = snap.model_copy(
        update={
            "observation": snap.observation.model_copy(
                update={"distinct_document_count": 99}
            )
        }
    )
    path.write_text(corrupted.model_dump_json(), encoding="utf-8")

    with pytest.raises(SufficiencyPersistenceError, match="collision"):
        persist_sufficiency_snapshot(snap, path=path)


def test_derive_then_persist_pipeline(tmp_path: Path) -> None:
    provenance = _provenance(
        units=[_unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"])]
    )
    observation = derive_sufficiency_observation(provenance)
    snapshot = build_sufficiency_snapshot(provenance, observation=observation)
    path = tmp_path / f"{snapshot.suffctx_id}.json"
    persist_sufficiency_snapshot(snapshot, path=path)
    loaded = load_sufficiency_snapshot(path)
    validate_observation_against_provenance(loaded.observation, loaded.provenance)
