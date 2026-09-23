"""Unit tests for Slice 11A-1 sufficiency observation core."""

from __future__ import annotations

import copy

import pytest

from offline_rag.sufficiency import (
    SUFFICIENCY_OBSERVATION_V1,
    SufficiencyDerivationError,
    SufficiencyErrorCodeV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
    SufficiencyValidationError,
    build_observation_config_hash,
    build_suffctx_id,
    build_suffctxrun_id,
    derive_sufficiency_observation,
    validate_observation_against_provenance,
)
from offline_rag.sufficiency.config_hash import build_observation_derivation_config_v1
from offline_rag.sufficiency.contracts import (
    SufficiencyAnchorProvenance,
    SufficiencyAssemblyDiagnosticsV1,
    SufficiencyEvidenceUnitProvenance,
)
from offline_rag.sufficiency.ids import build_suffctx_semantic_payload


def _anchor(
    *,
    chunk_id: str,
    rerank_rank: int,
    reranker_score: float,
    hybrid_rank: int,
    rrf_score: float = 0.1,
    dense_rank: int | None = None,
    dense_score: float | None = None,
    lexical_rank: int | None = None,
    lexical_score: float | None = None,
) -> SufficiencyAnchorProvenance:
    return SufficiencyAnchorProvenance(
        chunk_id=chunk_id,
        rerank_rank=rerank_rank,
        reranker_score=reranker_score,
        hybrid_rank=hybrid_rank,
        rrf_score=rrf_score,
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
    source_chunk_id: str = "chunk_src",
    primary_anchor_chunk_id: str = "chunk_a",
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
    anchors: list[SufficiencyAnchorProvenance] | None = None,
    units: list[SufficiencyEvidenceUnitProvenance] | None = None,
    attempt_number: int = 0,
    attempt_role: str = "initial",
    original_query: str = "what is X?",
    active_retrieval_query: str | None = None,
    context_token_count: int = 0,
    stop_reason: str = "completed",
) -> SufficiencyProvenanceV1:
    final_units = list(units or [])
    return SufficiencyProvenanceV1(
        case_id="case_1",
        corpus_id="corpus_1",
        chunk_set_id="chunkset_1",
        dense_index_id="dense_1",
        lexical_index_id="lexical_1",
        fusion_config_hash="fuscfg_1",
        reranker_config_hash="rrkcfg_1",
        context_config_hash="ctxcfg_1",
        original_query=original_query,
        active_retrieval_query=(
            active_retrieval_query
            if active_retrieval_query is not None
            else original_query
        ),
        attempt_number=attempt_number,
        attempt_role=attempt_role,  # type: ignore[arg-type]
        anchors=list(anchors or []),
        final_evidence_units=final_units,
        diagnostics=SufficiencyAssemblyDiagnosticsV1(
            evidence_unit_count=len(final_units),
            context_token_count=context_token_count,
            stop_reason=stop_reason,
        ),
    )


def test_zero_evidence_units_empty_context_true() -> None:
    obs = derive_sufficiency_observation(_provenance(anchors=[], units=[]))
    assert obs.empty_context is True
    assert obs.anchor_count == 0
    assert obs.top_reranker_score is None
    assert obs.top1_top2_margin is None
    assert obs.top_anchor_cross_retriever_support is None
    assert obs.distinct_document_count == 0
    assert obs.distinct_section_count == 0


def test_anchors_present_but_zero_evidence_units() -> None:
    anchors = [
        _anchor(
            chunk_id="chunk_a",
            rerank_rank=1,
            reranker_score=1.5,
            hybrid_rank=1,
            dense_rank=1,
            dense_score=0.9,
            lexical_rank=2,
            lexical_score=4.0,
        )
    ]
    obs = derive_sufficiency_observation(_provenance(anchors=anchors, units=[]))
    assert obs.empty_context is True
    assert obs.anchor_count == 1
    assert obs.top_reranker_score == 1.5
    assert obs.top1_top2_margin is None
    assert obs.top_anchor_cross_retriever_support is True


def test_margin_nullability_for_0_1_2_plus_anchors() -> None:
    zero = derive_sufficiency_observation(_provenance())
    assert zero.top1_top2_margin is None

    one = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1", rerank_rank=1, reranker_score=-0.2, hybrid_rank=3
                )
            ]
        )
    )
    assert one.top_reranker_score == -0.2
    assert one.top1_top2_margin is None

    two = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1", rerank_rank=1, reranker_score=2.0, hybrid_rank=1
                ),
                _anchor(
                    chunk_id="c2", rerank_rank=2, reranker_score=1.0, hybrid_rank=2
                ),
            ]
        )
    )
    assert two.top1_top2_margin == 1.0


def test_tied_scores_produce_zero_margin() -> None:
    obs = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1", rerank_rank=1, reranker_score=0.5, hybrid_rank=1
                ),
                _anchor(
                    chunk_id="c2", rerank_rank=2, reranker_score=0.5, hybrid_rank=2
                ),
            ]
        )
    )
    assert obs.top1_top2_margin == 0.0


def test_cross_retriever_dense_only_lexical_only_both_neither() -> None:
    both = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                    dense_rank=1,
                    dense_score=0.8,
                    lexical_rank=1,
                    lexical_score=3.0,
                )
            ]
        )
    )
    assert both.top_anchor_cross_retriever_support is True

    dense_only = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                    dense_rank=1,
                    dense_score=0.8,
                )
            ]
        )
    )
    assert dense_only.top_anchor_cross_retriever_support is False

    lexical_only = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(
                    chunk_id="c1",
                    rerank_rank=1,
                    reranker_score=1.0,
                    hybrid_rank=1,
                    lexical_rank=1,
                    lexical_score=2.0,
                )
            ]
        )
    )
    assert lexical_only.top_anchor_cross_retriever_support is False

    neither = derive_sufficiency_observation(
        _provenance(
            anchors=[
                _anchor(chunk_id="c1", rerank_rank=1, reranker_score=1.0, hybrid_rank=1)
            ]
        )
    )
    assert neither.top_anchor_cross_retriever_support is False


def test_exact_document_identity_and_section_pairs() -> None:
    units = [
        _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["Intro"]),
        _unit(evidence_unit_id="ev_2", document_id="doc_b", section_path=["Intro"]),
        _unit(evidence_unit_id="ev_3", document_id="doc_a", section_path=["Intro"]),
    ]
    obs = derive_sufficiency_observation(_provenance(units=units))
    assert obs.empty_context is False
    assert obs.distinct_document_count == 2
    assert obs.distinct_section_count == 2


def test_structural_only_section_normalization() -> None:
    units = [
        _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["Intro"]),
        _unit(evidence_unit_id="ev_2", document_id="doc_a", section_path=[" intro "]),
        _unit(evidence_unit_id="ev_3", document_id="doc_a", section_path=[]),
        _unit(evidence_unit_id="ev_4", document_id="doc_a", section_path=[]),
    ]
    obs = derive_sufficiency_observation(_provenance(units=units))
    assert obs.distinct_section_count == 3


def test_multiple_units_sharing_chunk_count_literally() -> None:
    units = [
        _unit(
            evidence_unit_id="ev_1",
            document_id="doc_a",
            section_path=["A"],
            source_chunk_id="chunk_same",
            primary_anchor_chunk_id="chunk_same",
        ),
        _unit(
            evidence_unit_id="ev_2",
            document_id="doc_a",
            section_path=["A"],
            source_chunk_id="chunk_same",
            primary_anchor_chunk_id="chunk_same",
        ),
    ]
    obs = derive_sufficiency_observation(_provenance(units=units))
    assert obs.distinct_document_count == 1
    assert obs.distinct_section_count == 1
    assert len(units) == 2


def test_duplicate_anchor_chunk_id_fails() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1", rerank_rank=1, reranker_score=2.0, hybrid_rank=1
                    ),
                    _anchor(
                        chunk_id="c1", rerank_rank=2, reranker_score=1.0, hybrid_rank=2
                    ),
                ]
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.DUPLICATE_ANCHOR_CHUNK_ID


def test_duplicate_evidence_unit_id_fails() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                units=[
                    _unit(
                        evidence_unit_id="ev_1", document_id="doc_a", section_path=[]
                    ),
                    _unit(
                        evidence_unit_id="ev_1", document_id="doc_b", section_path=[]
                    ),
                ]
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.DUPLICATE_EVIDENCE_UNIT_ID


def test_invalid_rerank_rank_fails() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1", rerank_rank=2, reranker_score=1.0, hybrid_rank=1
                    )
                ]
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_RERANK_RANK


def test_unpaired_branch_rank_score_fails() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1",
                        rerank_rank=1,
                        reranker_score=1.0,
                        hybrid_rank=1,
                        dense_rank=1,
                        dense_score=None,
                    )
                ]
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_BRANCH_RANK_SCORE_PAIR


def test_increasing_scores_fail_closed() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1", rerank_rank=1, reranker_score=1.0, hybrid_rank=1
                    ),
                    _anchor(
                        chunk_id="c2", rerank_rank=2, reranker_score=2.0, hybrid_rank=2
                    ),
                ]
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_ANCHOR_ORDER


def test_invalid_attempt_fields_fail() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(attempt_number=1, attempt_role="initial")
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS


def test_recompute_validation_match_and_mismatch() -> None:
    provenance = _provenance(
        anchors=[
            _anchor(
                chunk_id="c1",
                rerank_rank=1,
                reranker_score=3.0,
                hybrid_rank=1,
                dense_rank=1,
                dense_score=0.7,
                lexical_rank=2,
                lexical_score=1.1,
            ),
            _anchor(chunk_id="c2", rerank_rank=2, reranker_score=1.0, hybrid_rank=4),
        ],
        units=[
            _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"]),
        ],
        context_token_count=12,
    )
    observation = derive_sufficiency_observation(provenance)
    validate_observation_against_provenance(observation, provenance)

    tampered = observation.model_copy(update={"distinct_document_count": 99})
    with pytest.raises(SufficiencyValidationError) as exc:
        validate_observation_against_provenance(tampered, provenance)
    assert exc.value.code == SufficiencyErrorCodeV1.OBSERVATION_RECOMPUTE_MISMATCH
    assert exc.value.details is not None
    assert exc.value.details.field_name == "distinct_document_count"


def test_observation_config_hash_stable_and_sensitive() -> None:
    left = build_observation_config_hash()
    right = build_observation_config_hash(build_observation_derivation_config_v1())
    assert left == right
    assert left.startswith("obsconfig_")

    altered = build_observation_derivation_config_v1()
    altered["features"] = dict(altered["features"])
    altered["features"]["empty_context"] = {
        **altered["features"]["empty_context"],
        "version": "empty-context-v2",
    }
    assert build_observation_config_hash(altered) != left


def test_suffctx_id_ignores_non_semantic_timing_and_tracks_semantic_change() -> None:
    provenance = _provenance(
        anchors=[
            _anchor(chunk_id="c1", rerank_rank=1, reranker_score=1.0, hybrid_rank=1)
        ],
        units=[
            _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"]),
        ],
    )
    observation = derive_sufficiency_observation(provenance)
    payload = build_suffctx_semantic_payload(provenance, observation)
    first = build_suffctx_id(payload)
    second = build_suffctx_id(copy.deepcopy(payload))
    assert first == second
    assert first.startswith("suffctx_")

    changed = copy.deepcopy(payload)
    changed["provenance"]["anchors"][0]["reranker_score"] = 9.0
    assert build_suffctx_id(changed) != first

    run_id = build_suffctxrun_id(
        {
            "contract": "offline-rag-sufficiency-eval-context-manifest-v1",
            "case_ids": ["case_1"],
            "suffctx_ids": [first],
        }
    )
    assert run_id.startswith("suffctxrun_")
    assert run_id != first


def test_observation_contract_constant() -> None:
    obs = derive_sufficiency_observation(_provenance())
    assert obs.observation_contract == SUFFICIENCY_OBSERVATION_V1
    assert isinstance(obs, SufficiencyObservationV1)


def test_evidence_order_is_identity_bearing_for_suffctx() -> None:
    units_a = [
        _unit(evidence_unit_id="ev_1", document_id="doc_a", section_path=["A"]),
        _unit(evidence_unit_id="ev_2", document_id="doc_b", section_path=["B"]),
    ]
    units_b = list(reversed(units_a))
    obs_a = derive_sufficiency_observation(_provenance(units=units_a))
    obs_b = derive_sufficiency_observation(_provenance(units=units_b))
    # Seven features may match after set-based diversity, but identity still differs.
    assert obs_a.distinct_document_count == obs_b.distinct_document_count
    id_a = build_suffctx_id(
        build_suffctx_semantic_payload(_provenance(units=units_a), obs_a)
    )
    id_b = build_suffctx_id(
        build_suffctx_semantic_payload(_provenance(units=units_b), obs_b)
    )
    assert id_a != id_b


def test_suffctx_ids_use_shared_canonical_config_hash() -> None:
    from offline_rag.core.ids import canonical_config_hash

    payload = {
        "contract": "sufficiency-eval-context-v1",
        "b": 2,
        "a": {"y": 1, "x": 0},
    }
    expected = canonical_config_hash(payload).replace("cfg_", "suffctx_", 1)
    assert build_suffctx_id(payload) == expected
    run_payload = {"cases": ["case_1"], "lineage": {"chunk_set_id": "cs_1"}}
    assert build_suffctxrun_id(run_payload) == canonical_config_hash(
        run_payload
    ).replace("cfg_", "suffctxrun_", 1)


def test_exact_identity_and_query_strings_are_preserved() -> None:
    query = "  keep leading and trailing spaces  "
    doc_id = " doc_exact "
    chunk_id = " chunk_exact "
    evidence_id = " ev_exact "
    provenance = _provenance(
        original_query=query,
        active_retrieval_query=query,
        anchors=[
            _anchor(
                chunk_id=chunk_id,
                rerank_rank=1,
                reranker_score=1.0,
                hybrid_rank=1,
            )
        ],
        units=[
            _unit(
                evidence_unit_id=evidence_id,
                document_id=doc_id,
                section_path=[" Intro "],
                source_chunk_id=chunk_id,
                primary_anchor_chunk_id=chunk_id,
            )
        ],
    )
    assert provenance.original_query == query
    assert provenance.active_retrieval_query == query
    assert provenance.anchors[0].chunk_id == chunk_id
    assert provenance.final_evidence_units[0].document_id == doc_id
    assert provenance.final_evidence_units[0].evidence_unit_id == evidence_id
    assert provenance.final_evidence_units[0].section_path == [" Intro "]
    obs = derive_sufficiency_observation(provenance)
    assert obs.distinct_document_count == 1


def test_initial_query_mismatch_fails_closed() -> None:
    with pytest.raises(SufficiencyDerivationError) as exc:
        derive_sufficiency_observation(
            _provenance(
                original_query="what is X?",
                active_retrieval_query="what is Y?",
                attempt_number=0,
                attempt_role="initial",
            )
        )
    assert exc.value.code == SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS


def test_returned_derivation_config_mutation_cannot_alter_authoritative_hash() -> None:
    from offline_rag.sufficiency.config_hash import (
        OBSERVATION_DERIVATION_CONFIG_V1,
        authoritative_observation_config_hash,
    )

    before = authoritative_observation_config_hash()
    returned = build_observation_derivation_config_v1()
    returned["features"]["empty_context"]["version"] = "mutated-v9"
    returned["canonicalization"]["anchor_order"] = "mutated"
    assert build_observation_config_hash() == before
    assert authoritative_observation_config_hash() == before
    # Public frozen view must reject nested mutation.
    with pytest.raises(TypeError):
        OBSERVATION_DERIVATION_CONFIG_V1["features"]["empty_context"]["version"] = "x"  # type: ignore[index]


def test_explicit_none_section_path_canonicalizes_to_empty_list() -> None:
    unit = SufficiencyEvidenceUnitProvenance(
        evidence_unit_id="ev_1",
        document_id="doc_a",
        section_path=None,  # type: ignore[arg-type]
        source_chunk_id="chunk_a",
        primary_anchor_chunk_id="chunk_a",
    )
    assert unit.section_path == []
    obs = derive_sufficiency_observation(_provenance(units=[unit]))
    assert obs.distinct_section_count == 1


def test_nonfinite_rrf_and_branch_scores_use_accurate_codes() -> None:
    with pytest.raises(SufficiencyDerivationError) as rrf_exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1",
                        rerank_rank=1,
                        reranker_score=1.0,
                        hybrid_rank=1,
                        rrf_score=float("nan"),
                    )
                ]
            )
        )
    assert rrf_exc.value.code == SufficiencyErrorCodeV1.INVALID_RRF_SCORE

    with pytest.raises(SufficiencyDerivationError) as branch_exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1",
                        rerank_rank=1,
                        reranker_score=1.0,
                        hybrid_rank=1,
                        dense_rank=1,
                        dense_score=float("inf"),
                    )
                ]
            )
        )
    assert branch_exc.value.code == SufficiencyErrorCodeV1.INVALID_BRANCH_SCORE

    with pytest.raises(SufficiencyDerivationError) as rerank_exc:
        derive_sufficiency_observation(
            _provenance(
                anchors=[
                    _anchor(
                        chunk_id="c1",
                        rerank_rank=1,
                        reranker_score=float("-inf"),
                        hybrid_rank=1,
                    )
                ]
            )
        )
    assert rerank_exc.value.code == SufficiencyErrorCodeV1.INVALID_RERANKER_SCORE


def test_reranked_anchor_order_is_identity_bearing_for_suffctx() -> None:
    anchors_a = [
        _anchor(chunk_id="c1", rerank_rank=1, reranker_score=2.0, hybrid_rank=1),
        _anchor(chunk_id="c2", rerank_rank=2, reranker_score=1.0, hybrid_rank=2),
    ]
    # Same scores/ranks positions but swapped chunk identities require rebuilding
    # ranks for the alternate ordered surface with equal scores (legal ties).
    anchors_b = [
        _anchor(chunk_id="c2", rerank_rank=1, reranker_score=2.0, hybrid_rank=2),
        _anchor(chunk_id="c1", rerank_rank=2, reranker_score=1.0, hybrid_rank=1),
    ]
    prov_a = _provenance(anchors=anchors_a)
    prov_b = _provenance(anchors=anchors_b)
    obs_a = derive_sufficiency_observation(prov_a)
    obs_b = derive_sufficiency_observation(prov_b)
    # Observations can match while ordered provenance differs.
    assert obs_a.top_reranker_score == obs_b.top_reranker_score
    id_a = build_suffctx_id(build_suffctx_semantic_payload(prov_a, obs_a))
    id_b = build_suffctx_id(build_suffctx_semantic_payload(prov_b, obs_b))
    assert id_a != id_b
