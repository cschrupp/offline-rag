"""Deterministic OD-11-2 feature derivation and recomputation validation."""

from __future__ import annotations

import math
from typing import Any

from offline_rag.sufficiency.config_hash import authoritative_observation_config_hash
from offline_rag.sufficiency.contracts import (
    SUFFICIENCY_ATTEMPT_ROLE_INITIAL,
    SUFFICIENCY_ATTEMPT_ROLE_RECOVERY,
    SUFFICIENCY_OBSERVATION_V1,
    SufficiencyAnchorProvenance,
    SufficiencyDerivationError,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
    SufficiencyValidationError,
)


def _fail(
    code: SufficiencyErrorCodeV1,
    message: str,
    *,
    field_name: str | None = None,
    expected: str | float | bool | None = None,
    actual: str | float | bool | None = None,
    attempt_number: int | None = None,
) -> None:
    details = None
    if any(v is not None for v in (field_name, expected, actual, attempt_number)):
        details = SufficiencyErrorDetailsV1(
            field_name=field_name,
            expected=expected,
            actual=actual,
            attempt_number=attempt_number,
        )
    raise SufficiencyDerivationError(code, message, details=details)


def _require_finite(
    value: float,
    *,
    field_name: str,
    code: SufficiencyErrorCodeV1,
) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _fail(
            code,
            f"{field_name} must be a finite number",
            field_name=field_name,
            actual=str(type(value)),
        )
    number = float(value)
    if not math.isfinite(number):
        _fail(
            code,
            f"{field_name} must be finite",
            field_name=field_name,
            actual=str(number),
        )
    return number


def normalized_section_path(section_path: list[str] | None) -> list[str]:
    """Structural-only section-path normalization (OD-11-23)."""
    if section_path is None:
        return []
    if not isinstance(section_path, list):
        _fail(
            SufficiencyErrorCodeV1.INVALID_SECTION_PATH,
            "section_path must be a list of strings or null",
            field_name="section_path",
        )
    for segment in section_path:
        if not isinstance(segment, str):
            _fail(
                SufficiencyErrorCodeV1.INVALID_SECTION_PATH,
                "section_path segments must be strings",
                field_name="section_path",
            )
    return list(section_path)


def _validate_attempt_fields(provenance: SufficiencyProvenanceV1) -> None:
    role = provenance.attempt_role
    number = provenance.attempt_number
    if role == SUFFICIENCY_ATTEMPT_ROLE_INITIAL and number != 0:
        _fail(
            SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
            "attempt_role=initial requires attempt_number=0",
            field_name="attempt_number",
            expected=0,
            actual=number,
            attempt_number=number,
        )
    if role == SUFFICIENCY_ATTEMPT_ROLE_RECOVERY and number < 1:
        _fail(
            SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
            "attempt_role=recovery requires attempt_number>=1",
            field_name="attempt_number",
            expected=1,
            actual=number,
            attempt_number=number,
        )


def _validate_query_fields(provenance: SufficiencyProvenanceV1) -> None:
    # OD-11-10: Slice 11 / initial attempt requires exact query equality.
    if (
        provenance.attempt_role == SUFFICIENCY_ATTEMPT_ROLE_INITIAL
        or provenance.attempt_number == 0
    ) and provenance.active_retrieval_query != provenance.original_query:
        _fail(
            SufficiencyErrorCodeV1.INVALID_QUERY_FIELDS,
            "initial/attempt 0 requires active_retrieval_query == original_query",
            field_name="active_retrieval_query",
            expected=provenance.original_query,
            actual=provenance.active_retrieval_query,
            attempt_number=provenance.attempt_number,
        )


def _validate_lineage(provenance: SufficiencyProvenanceV1) -> None:
    required = {
        "case_id": provenance.case_id,
        "corpus_id": provenance.corpus_id,
        "chunk_set_id": provenance.chunk_set_id,
        "dense_index_id": provenance.dense_index_id,
        "lexical_index_id": provenance.lexical_index_id,
        "fusion_config_hash": provenance.fusion_config_hash,
        "reranker_config_hash": provenance.reranker_config_hash,
        "context_config_hash": provenance.context_config_hash,
        "original_query": provenance.original_query,
        "active_retrieval_query": provenance.active_retrieval_query,
    }
    for field_name, value in required.items():
        if not isinstance(value, str) or value.strip() == "":
            _fail(
                SufficiencyErrorCodeV1.MISSING_REQUIRED_LINEAGE,
                f"missing required lineage field: {field_name}",
                field_name=field_name,
            )


def _validate_branch_pair(
    *,
    rank: int | None,
    score: float | None,
    branch: str,
) -> None:
    rank_present = rank is not None
    score_present = score is not None
    if rank_present != score_present:
        _fail(
            SufficiencyErrorCodeV1.INVALID_BRANCH_RANK_SCORE_PAIR,
            f"{branch} rank/score nullability must be paired",
            field_name=f"{branch}_rank",
            expected="paired",
            actual="mixed",
        )
    if rank is not None and rank < 1:
        _fail(
            SufficiencyErrorCodeV1.INVALID_BRANCH_RANK,
            f"{branch}_rank must be a positive integer when present",
            field_name=f"{branch}_rank",
            actual=rank,
        )
    if score is not None:
        _require_finite(
            score,
            field_name=f"{branch}_score",
            code=SufficiencyErrorCodeV1.INVALID_BRANCH_SCORE,
        )


def _validate_anchors(anchors: list[SufficiencyAnchorProvenance]) -> None:
    seen_chunk_ids: set[str] = set()
    seen_hybrid_ranks: set[int] = set()
    seen_dense_ranks: set[int] = set()
    seen_lexical_ranks: set[int] = set()
    previous_score: float | None = None

    for index, anchor in enumerate(anchors):
        expected_rank = index + 1
        if anchor.rerank_rank != expected_rank:
            _fail(
                SufficiencyErrorCodeV1.INVALID_RERANK_RANK,
                "rerank_rank must equal list position (1-based)",
                field_name="rerank_rank",
                expected=expected_rank,
                actual=anchor.rerank_rank,
            )
        if anchor.chunk_id in seen_chunk_ids:
            _fail(
                SufficiencyErrorCodeV1.DUPLICATE_ANCHOR_CHUNK_ID,
                "duplicate chunk_id in reranked anchor list",
                field_name="chunk_id",
                actual=anchor.chunk_id,
            )
        seen_chunk_ids.add(anchor.chunk_id)

        if anchor.hybrid_rank < 1:
            _fail(
                SufficiencyErrorCodeV1.INVALID_HYBRID_RANK,
                "hybrid_rank must be a positive integer",
                field_name="hybrid_rank",
                actual=anchor.hybrid_rank,
            )
        if anchor.hybrid_rank in seen_hybrid_ranks:
            _fail(
                SufficiencyErrorCodeV1.INVALID_HYBRID_RANK,
                "duplicate hybrid_rank among stored anchors",
                field_name="hybrid_rank",
                actual=anchor.hybrid_rank,
            )
        seen_hybrid_ranks.add(anchor.hybrid_rank)
        _require_finite(
            anchor.rrf_score,
            field_name="rrf_score",
            code=SufficiencyErrorCodeV1.INVALID_RRF_SCORE,
        )

        score = _require_finite(
            anchor.reranker_score,
            field_name="reranker_score",
            code=SufficiencyErrorCodeV1.INVALID_RERANKER_SCORE,
        )
        # Upstream reranker contract sorts raw-logit DESC (OD-11 design closure).
        if previous_score is not None and score > previous_score:
            _fail(
                SufficiencyErrorCodeV1.INVALID_ANCHOR_ORDER,
                "reranker scores must be non-increasing with rerank order",
                field_name="reranker_score",
                expected=previous_score,
                actual=score,
            )
        previous_score = score

        _validate_branch_pair(
            rank=anchor.dense_rank,
            score=anchor.dense_score,
            branch="dense",
        )
        _validate_branch_pair(
            rank=anchor.lexical_rank,
            score=anchor.lexical_score,
            branch="lexical",
        )
        if anchor.dense_rank is not None:
            if anchor.dense_rank in seen_dense_ranks:
                _fail(
                    SufficiencyErrorCodeV1.INVALID_BRANCH_RANK,
                    "duplicate dense_rank among stored anchors",
                    field_name="dense_rank",
                    actual=anchor.dense_rank,
                )
            seen_dense_ranks.add(anchor.dense_rank)
        if anchor.lexical_rank is not None:
            if anchor.lexical_rank in seen_lexical_ranks:
                _fail(
                    SufficiencyErrorCodeV1.INVALID_BRANCH_RANK,
                    "duplicate lexical_rank among stored anchors",
                    field_name="lexical_rank",
                    actual=anchor.lexical_rank,
                )
            seen_lexical_ranks.add(anchor.lexical_rank)


def _validate_evidence_units(provenance: SufficiencyProvenanceV1) -> None:
    seen_ids: set[str] = set()
    for unit in provenance.final_evidence_units:
        if unit.document_id.strip() == "":
            _fail(
                SufficiencyErrorCodeV1.MISSING_DOCUMENT_ID,
                "final EvidenceUnit missing document_id",
                field_name="document_id",
            )
        if unit.evidence_unit_id in seen_ids:
            _fail(
                SufficiencyErrorCodeV1.DUPLICATE_EVIDENCE_UNIT_ID,
                "duplicate evidence_unit_id in final EvidenceUnit list",
                field_name="evidence_unit_id",
                actual=unit.evidence_unit_id,
            )
        seen_ids.add(unit.evidence_unit_id)
        normalized_section_path(unit.section_path)

    diagnostics = provenance.diagnostics
    expected_count = len(provenance.final_evidence_units)
    if diagnostics.evidence_unit_count != expected_count:
        _fail(
            SufficiencyErrorCodeV1.INVALID_DIAGNOSTICS,
            "diagnostics.evidence_unit_count must equal len(final_evidence_units)",
            field_name="evidence_unit_count",
            expected=expected_count,
            actual=diagnostics.evidence_unit_count,
        )


def _derive_features(
    provenance: SufficiencyProvenanceV1,
    *,
    observation_config_hash: str,
) -> SufficiencyObservationV1:
    anchors = provenance.anchors
    units = provenance.final_evidence_units
    anchor_count = len(anchors)
    empty_context = len(units) == 0

    if anchor_count == 0:
        top_score: float | None = None
        margin: float | None = None
        cross: bool | None = None
    else:
        top = anchors[0]
        top_score = float(top.reranker_score)
        cross = top.dense_rank is not None and top.lexical_rank is not None
        if anchor_count >= 2:
            margin = float(top.reranker_score) - float(anchors[1].reranker_score)
            if margin < 0:
                _fail(
                    SufficiencyErrorCodeV1.INVALID_ANCHOR_ORDER,
                    "top1_top2_margin must not be negative under ordered raw logits",
                    field_name="top1_top2_margin",
                    actual=margin,
                )
        else:
            margin = None

    document_ids = {unit.document_id for unit in units}
    section_ids = {
        (unit.document_id, tuple(normalized_section_path(unit.section_path)))
        for unit in units
    }

    return SufficiencyObservationV1(
        observation_contract=SUFFICIENCY_OBSERVATION_V1,
        observation_config_hash=observation_config_hash,
        empty_context=empty_context,
        top_reranker_score=top_score,
        top1_top2_margin=margin,
        top_anchor_cross_retriever_support=cross,
        anchor_count=anchor_count,
        distinct_document_count=len(document_ids),
        distinct_section_count=len(section_ids),
    )


def derive_sufficiency_observation(
    provenance: SufficiencyProvenanceV1,
    *,
    observation_config_hash: str | None = None,
) -> SufficiencyObservationV1:
    """Derive the seven OD-11-2 features from validated provenance."""
    if provenance.schema_version != "sufficiency-provenance-v1":
        _fail(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported provenance schema_version",
            field_name="schema_version",
            expected="sufficiency-provenance-v1",
            actual=provenance.schema_version,
        )

    expected_hash = authoritative_observation_config_hash()
    resolved_hash = observation_config_hash or expected_hash
    if resolved_hash != expected_hash:
        _fail(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONFIG,
            "unsupported observation_config_hash for this software",
            field_name="observation_config_hash",
            expected=expected_hash,
            actual=resolved_hash,
        )

    _validate_lineage(provenance)
    _validate_attempt_fields(provenance)
    _validate_query_fields(provenance)
    _validate_anchors(provenance.anchors)
    _validate_evidence_units(provenance)
    return _derive_features(provenance, observation_config_hash=resolved_hash)


def _observation_fields(observation: SufficiencyObservationV1) -> dict[str, Any]:
    return {
        "empty_context": observation.empty_context,
        "top_reranker_score": observation.top_reranker_score,
        "top1_top2_margin": observation.top1_top2_margin,
        "top_anchor_cross_retriever_support": (
            observation.top_anchor_cross_retriever_support
        ),
        "anchor_count": observation.anchor_count,
        "distinct_document_count": observation.distinct_document_count,
        "distinct_section_count": observation.distinct_section_count,
        "observation_contract": observation.observation_contract,
        "observation_config_hash": observation.observation_config_hash,
    }


def validate_observation_against_provenance(
    observation: SufficiencyObservationV1,
    provenance: SufficiencyProvenanceV1,
) -> None:
    """Recompute from provenance and require exact field match (OD-11-14)."""
    if observation.observation_contract != SUFFICIENCY_OBSERVATION_V1:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported observation_contract",
            details=SufficiencyErrorDetailsV1(
                field_name="observation_contract",
                expected=SUFFICIENCY_OBSERVATION_V1,
                actual=observation.observation_contract,
            ),
        )
    try:
        recomputed = derive_sufficiency_observation(
            provenance,
            observation_config_hash=observation.observation_config_hash,
        )
    except SufficiencyDerivationError as exc:
        raise SufficiencyValidationError(
            exc.code,
            exc.message,
            details=exc.details,
            cause=exc,
        ) from exc

    stored = _observation_fields(observation)
    fresh = _observation_fields(recomputed)
    for field_name, expected in fresh.items():
        actual = stored[field_name]
        if actual != expected:
            raise SufficiencyValidationError(
                SufficiencyErrorCodeV1.OBSERVATION_RECOMPUTE_MISMATCH,
                f"stored observation field mismatch: {field_name}",
                details=SufficiencyErrorDetailsV1(
                    field_name=field_name,
                    expected=(
                        expected
                        if isinstance(expected, (str, int, float, bool))
                        or expected is None
                        else str(expected)
                    ),
                    actual=(
                        actual
                        if isinstance(actual, (str, int, float, bool)) or actual is None
                        else str(actual)
                    ),
                ),
            )
