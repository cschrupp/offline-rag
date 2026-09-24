"""OD-11-5 Path-A historical artifact preflight (read-only, no retrieval)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.evaluation.result import (
    CaseEvaluationResult,
    RetrievalEvaluationResultV1,
)
from offline_rag.sufficiency.contracts import ExactNonBlankStr


class PathAMissingRequirement(str, Enum):
    """Explicit missing/ambiguous requirement classes for Path-A reports."""

    RERANKER_RAW_SCORES = "reranker_raw_scores"
    RERANK_RANKS_ORDER = "rerank_ranks_order"
    HYBRID_RANK_RRF_SCORE = "hybrid_rank_rrf_score"
    DENSE_BRANCH_RANK_SCORE = "dense_branch_rank_score"
    LEXICAL_BRANCH_RANK_SCORE = "lexical_branch_rank_score"
    EVIDENCE_UNIT_PROVENANCE = "evidence_unit_identity_order_document_section"
    ASSEMBLY_DIAGNOSTICS = "deterministic_assembly_diagnostics"
    SHARED_LINEAGE = "full_shared_lineage"
    QUERY_CASE_BINDING = "exact_query_case_binding"


class PathACaseStatus(str, Enum):
    QUALIFIED = "qualified"
    NOT_QUALIFIED = "not_qualified"


class PathAOverallResult(str, Enum):
    PATH_A_QUALIFIED = "PATH_A_QUALIFIED"
    PATH_A_NOT_QUALIFIED = "PATH_A_NOT_QUALIFIED"


class PathALineageConsistency(str, Enum):
    CONSISTENT = "consistent"
    INCONSISTENT = "inconsistent"
    INSUFFICIENT = "insufficient"


class PathASharedLineageView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str | None = None
    chunk_set_id: str | None = None
    dense_index_id: str | None = None
    lexical_index_id: str | None = None
    fusion_config_hash: str | None = None
    reranker_config_hash: str | None = None
    context_config_hash: str | None = None


class PathACaseAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: ExactNonBlankStr
    status: PathACaseStatus
    query: str | None = None
    missing_or_ambiguous: list[PathAMissingRequirement] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_artifact_id: str | None = None


class PathAInspectedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: ExactNonBlankStr
    artifact_kind: ExactNonBlankStr
    run_id: str | None = None
    method: str | None = None
    gold_dataset_id: str | None = None
    lineage: PathASharedLineageView = Field(default_factory=PathASharedLineageView)
    case_ids_present: list[str] = Field(default_factory=list)


class PathAPreflightReport(BaseModel):
    """Deterministic Path-A qualification report (OD-11-5)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-path-a-preflight-v1"] = (
        "sufficiency-path-a-preflight-v1"
    )
    intended_case_ids: list[ExactNonBlankStr]
    intended_case_queries: dict[str, str]
    inspected_artifacts: list[PathAInspectedArtifact] = Field(default_factory=list)
    case_assessments: list[PathACaseAssessment] = Field(default_factory=list)
    lineage_consistency: PathALineageConsistency
    overall: PathAOverallResult
    notes: list[str] = Field(default_factory=list)


def _blank(value: Any) -> bool:
    return not isinstance(value, str) or value == "" or value.strip() == ""


def _normalize_intended_case_queries(
    intended_case_queries: Mapping[str, str],
) -> dict[str, str]:
    if not intended_case_queries:
        raise ValueError("intended_case_queries must be non-empty")
    ordered: dict[str, str] = {}
    for case_id, query in intended_case_queries.items():
        if _blank(case_id):
            raise ValueError("intended case_id must be a nonblank string")
        if case_id in ordered:
            raise ValueError(f"duplicate intended case_id: {case_id}")
        if not isinstance(query, str) or query == "":
            # Exact binding: blank/non-string queries are invalid; do not strip.
            raise ValueError(
                f"intended original_query for case_id={case_id!r} must be a "
                "non-empty string (no trimming/normalization)"
            )
        if query.strip() == "":
            raise ValueError(
                f"intended original_query for case_id={case_id!r} is whitespace-only"
            )
        ordered[case_id] = query
    return ordered


def _lineage_tuple(view: PathASharedLineageView) -> tuple[str | None, ...]:
    return (
        view.corpus_id,
        view.chunk_set_id,
        view.dense_index_id,
        view.lexical_index_id,
        view.fusion_config_hash,
        view.reranker_config_hash,
        view.context_config_hash,
    )


def _lineage_complete(view: PathASharedLineageView) -> bool:
    return all(not _blank(item) for item in _lineage_tuple(view))


def _merge_lineage_views(
    views: list[PathASharedLineageView],
) -> tuple[PathALineageConsistency, PathASharedLineageView | None]:
    if not views:
        return PathALineageConsistency.INSUFFICIENT, None
    if any(not _lineage_complete(view) for view in views):
        complete = [view for view in views if _lineage_complete(view)]
        if not complete:
            return PathALineageConsistency.INSUFFICIENT, views[0]
        base = _lineage_tuple(complete[0])
        for view in views:
            if _lineage_complete(view) and _lineage_tuple(view) != base:
                return PathALineageConsistency.INCONSISTENT, complete[0]
            if not _lineage_complete(view):
                return PathALineageConsistency.INCONSISTENT, complete[0]
        return PathALineageConsistency.CONSISTENT, complete[0]

    base = _lineage_tuple(views[0])
    for view in views[1:]:
        if _lineage_tuple(view) != base:
            return PathALineageConsistency.INCONSISTENT, views[0]
    return PathALineageConsistency.CONSISTENT, views[0]


def _lineage_from_retrieval_eval(
    report: RetrievalEvaluationResultV1,
) -> PathASharedLineageView:
    prov = dict(report.semantic_provenance or {})
    return PathASharedLineageView(
        corpus_id=report.corpus_id,
        chunk_set_id=report.chunk_set_id,
        dense_index_id=(
            None
            if _blank(prov.get("dense_index_id"))
            else str(prov.get("dense_index_id"))
        ),
        lexical_index_id=(
            None
            if _blank(prov.get("lexical_index_id"))
            else str(prov.get("lexical_index_id"))
        ),
        fusion_config_hash=(
            None
            if _blank(prov.get("fusion_config_hash"))
            else str(prov.get("fusion_config_hash"))
        ),
        reranker_config_hash=(
            None
            if _blank(prov.get("reranker_config_hash"))
            else str(prov.get("reranker_config_hash"))
        ),
        context_config_hash=(
            None
            if _blank(prov.get("context_config_hash"))
            else str(prov.get("context_config_hash"))
        ),
    )


def _dedupe_missing(
    missing: list[PathAMissingRequirement],
) -> list[PathAMissingRequirement]:
    seen: set[PathAMissingRequirement] = set()
    ordered: list[PathAMissingRequirement] = []
    for item in missing:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _binding_matches(*, historical_query: str | None, intended_query: str) -> bool:
    """Exact string equality; no trim/normalize/fuzzy compare."""
    return isinstance(historical_query, str) and historical_query == intended_query


def _missing_for_retrieval_eval_case(
    case: CaseEvaluationResult,
    *,
    lineage: PathASharedLineageView,
    intended_query: str | None,
) -> list[PathAMissingRequirement]:
    """Classify gaps for common retrieval-eval envelopes (no full context dump)."""
    missing: list[PathAMissingRequirement] = []
    if (
        _blank(case.case_id)
        or _blank(case.query)
        or intended_query is None
        or not _binding_matches(
            historical_query=case.query, intended_query=intended_query
        )
    ):
        missing.append(PathAMissingRequirement.QUERY_CASE_BINDING)

    if not _lineage_complete(lineage):
        missing.append(PathAMissingRequirement.SHARED_LINEAGE)

    missing.extend(
        [
            PathAMissingRequirement.RERANKER_RAW_SCORES,
            PathAMissingRequirement.RERANK_RANKS_ORDER,
            PathAMissingRequirement.HYBRID_RANK_RRF_SCORE,
            PathAMissingRequirement.DENSE_BRANCH_RANK_SCORE,
            PathAMissingRequirement.LEXICAL_BRANCH_RANK_SCORE,
            PathAMissingRequirement.EVIDENCE_UNIT_PROVENANCE,
            PathAMissingRequirement.ASSEMBLY_DIAGNOSTICS,
        ]
    )
    return _dedupe_missing(missing)


def assess_hybrid_rerank_context_result_for_path_a(
    result: HybridRerankContextResult,
    *,
    case_id: str,
    intended_query: str,
) -> PathACaseAssessment:
    """Assess whether a full context result can reconstruct SufficiencyProvenanceV1."""
    from offline_rag.context.sufficiency_adapter import (
        adapt_hybrid_rerank_context_to_provenance,
    )
    from offline_rag.sufficiency import (
        build_sufficiency_snapshot,
        derive_sufficiency_observation,
    )

    notes: list[str] = []
    missing: list[PathAMissingRequirement] = []
    if _blank(case_id) or _blank(result.query):
        missing.append(PathAMissingRequirement.QUERY_CASE_BINDING)
    elif not _binding_matches(
        historical_query=result.query, intended_query=intended_query
    ):
        missing.append(PathAMissingRequirement.QUERY_CASE_BINDING)
        notes.append(
            "historical query does not exactly equal frozen intended original_query"
        )

    metadata = dict(result.metadata or {})
    lineage = PathASharedLineageView(
        corpus_id=None
        if _blank(metadata.get("corpus_id"))
        else str(metadata["corpus_id"]),
        chunk_set_id=(
            None
            if _blank(metadata.get("chunk_set_id"))
            else str(metadata["chunk_set_id"])
        ),
        dense_index_id=(
            None if _blank(result.dense_index_id) else result.dense_index_id
        ),
        lexical_index_id=(
            None if _blank(result.lexical_index_id) else result.lexical_index_id
        ),
        fusion_config_hash=(
            None if _blank(result.fusion_config_hash) else result.fusion_config_hash
        ),
        reranker_config_hash=(
            None if _blank(result.reranker_config_hash) else result.reranker_config_hash
        ),
        context_config_hash=(
            None if _blank(result.context_config_hash) else result.context_config_hash
        ),
    )
    if not _lineage_complete(lineage):
        missing.append(PathAMissingRequirement.SHARED_LINEAGE)

    if not result.anchors:
        notes.append("anchors list is empty (empty_context-capable)")
    else:
        for anchor in result.anchors:
            prov = anchor.hybrid_rerank
            if prov.reranker_score is None:
                missing.append(PathAMissingRequirement.RERANKER_RAW_SCORES)
            if anchor.rank is None:
                missing.append(PathAMissingRequirement.RERANK_RANKS_ORDER)
            if prov.hybrid_rank is None or prov.rrf_score is None:
                missing.append(PathAMissingRequirement.HYBRID_RANK_RRF_SCORE)
            dense_pair_ok = (prov.dense_rank is None) == (prov.dense_score is None)
            lexical_pair_ok = (prov.lexical_rank is None) == (
                prov.lexical_score is None
            )
            if not dense_pair_ok:
                missing.append(PathAMissingRequirement.DENSE_BRANCH_RANK_SCORE)
            if not lexical_pair_ok:
                missing.append(PathAMissingRequirement.LEXICAL_BRANCH_RANK_SCORE)

    for unit in result.evidence_units:
        if (
            _blank(unit.evidence_unit_id)
            or _blank(unit.document_id)
            or _blank(unit.source_chunk_id)
            or _blank(unit.primary_anchor_chunk_id)
        ):
            missing.append(PathAMissingRequirement.EVIDENCE_UNIT_PROVENANCE)
            break

    diag = result.diagnostics
    if (
        diag is None
        or _blank(diag.stop_reason)
        or diag.evidence_unit_count is None
        or diag.context_token_count is None
    ):
        missing.append(PathAMissingRequirement.ASSEMBLY_DIAGNOSTICS)

    ordered_missing = _dedupe_missing(missing)
    if ordered_missing:
        return PathACaseAssessment(
            case_id=case_id if not _blank(case_id) else "unknown",
            status=PathACaseStatus.NOT_QUALIFIED,
            query=None if _blank(result.query) else result.query,
            missing_or_ambiguous=ordered_missing,
            notes=notes,
        )

    try:
        provenance = adapt_hybrid_rerank_context_to_provenance(result, case_id=case_id)
        observation = derive_sufficiency_observation(provenance)
        build_sufficiency_snapshot(provenance, observation=observation)
    except Exception as exc:  # noqa: BLE001 - fail closed on any projection/derive error
        notes.append(f"adapter/derive validation failed: {exc}")
        return PathACaseAssessment(
            case_id=case_id,
            status=PathACaseStatus.NOT_QUALIFIED,
            query=result.query,
            missing_or_ambiguous=[PathAMissingRequirement.SHARED_LINEAGE],
            notes=notes,
        )

    return PathACaseAssessment(
        case_id=case_id,
        status=PathACaseStatus.QUALIFIED,
        query=result.query,
        missing_or_ambiguous=[],
        notes=notes,
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"artifact root must be a JSON object: {path}")
    return payload


def _inspect_retrieval_eval(
    path: Path,
    payload: dict[str, Any],
    *,
    intended_case_queries: Mapping[str, str],
) -> tuple[PathAInspectedArtifact, list[PathACaseAssessment], PathASharedLineageView]:
    report = RetrievalEvaluationResultV1.model_validate(payload)
    lineage = _lineage_from_retrieval_eval(report)
    inspected = PathAInspectedArtifact(
        path=str(path),
        artifact_kind="offline-rag-retrieval-eval-result-v1",
        run_id=report.run_id,
        method=report.method,
        gold_dataset_id=report.gold_dataset_id,
        lineage=lineage,
        case_ids_present=[case.case_id for case in report.cases],
    )
    assessments: list[PathACaseAssessment] = []
    for case in report.cases:
        intended_query = intended_case_queries.get(case.case_id)
        assessments.append(
            PathACaseAssessment(
                case_id=case.case_id,
                status=PathACaseStatus.NOT_QUALIFIED,
                query=case.query,
                missing_or_ambiguous=_missing_for_retrieval_eval_case(
                    case,
                    lineage=lineage,
                    intended_query=intended_query,
                ),
                notes=[
                    (
                        "historical retrieval-eval envelope lacks full "
                        "sufficiency provenance"
                    )
                ],
                source_artifact_id=report.run_id,
            )
        )
    return inspected, assessments, lineage


def _inspect_context_result_dump(
    path: Path,
    payload: dict[str, Any],
    *,
    case_id: str | None,
    intended_case_queries: Mapping[str, str],
) -> tuple[PathAInspectedArtifact, list[PathACaseAssessment], PathASharedLineageView]:
    result = HybridRerankContextResult.model_validate(payload)
    metadata = dict(result.metadata or {})
    resolved_case = case_id or (
        None if _blank(metadata.get("case_id")) else str(metadata["case_id"])
    )
    lineage = PathASharedLineageView(
        corpus_id=None
        if _blank(metadata.get("corpus_id"))
        else str(metadata["corpus_id"]),
        chunk_set_id=(
            None
            if _blank(metadata.get("chunk_set_id"))
            else str(metadata["chunk_set_id"])
        ),
        dense_index_id=(
            None if _blank(result.dense_index_id) else result.dense_index_id
        ),
        lexical_index_id=(
            None if _blank(result.lexical_index_id) else result.lexical_index_id
        ),
        fusion_config_hash=(
            None if _blank(result.fusion_config_hash) else result.fusion_config_hash
        ),
        reranker_config_hash=(
            None if _blank(result.reranker_config_hash) else result.reranker_config_hash
        ),
        context_config_hash=(
            None if _blank(result.context_config_hash) else result.context_config_hash
        ),
    )
    inspected = PathAInspectedArtifact(
        path=str(path),
        artifact_kind="hybrid-rerank-context-result",
        run_id=None if _blank(metadata.get("run_id")) else str(metadata["run_id"]),
        method=result.method,
        gold_dataset_id=(
            None
            if _blank(metadata.get("gold_dataset_id"))
            else str(metadata["gold_dataset_id"])
        ),
        lineage=lineage,
        case_ids_present=[] if resolved_case is None else [resolved_case],
    )
    if resolved_case is None:
        assessment = PathACaseAssessment(
            case_id="unknown",
            status=PathACaseStatus.NOT_QUALIFIED,
            query=result.query,
            missing_or_ambiguous=[PathAMissingRequirement.QUERY_CASE_BINDING],
            notes=["context result dump missing case_id binding"],
            source_artifact_id=str(path),
        )
    elif resolved_case not in intended_case_queries:
        assessment = PathACaseAssessment(
            case_id=resolved_case,
            status=PathACaseStatus.NOT_QUALIFIED,
            query=result.query,
            missing_or_ambiguous=[PathAMissingRequirement.QUERY_CASE_BINDING],
            notes=["case_id is outside the intended frozen population"],
            source_artifact_id=str(path),
        )
    else:
        assessment = assess_hybrid_rerank_context_result_for_path_a(
            result,
            case_id=resolved_case,
            intended_query=intended_case_queries[resolved_case],
        )
        assessment = assessment.model_copy(update={"source_artifact_id": str(path)})
    return inspected, [assessment], lineage


_HISTORICAL_QUERY_CONFLICT_NOTE = "conflicting historical query bindings for case"


def _has_historical_query_conflict(assessment: PathACaseAssessment) -> bool:
    return _HISTORICAL_QUERY_CONFLICT_NOTE in assessment.notes


def _merge_case_assessment(
    prior: PathACaseAssessment,
    incoming: PathACaseAssessment,
) -> PathACaseAssessment:
    """Merge historical sightings; conflicting query bindings fail closed.

    Once conflicting historical query bindings are observed for a case, that
    conflict is irreversible for the remainder of the preflight run. A later
    qualified sighting must not clear ``QUERY_CASE_BINDING``.
    """
    queries_conflict = (
        prior.query is not None
        and incoming.query is not None
        and prior.query != incoming.query
    )
    conflict_latched = (
        _has_historical_query_conflict(prior)
        or _has_historical_query_conflict(incoming)
        or queries_conflict
    )
    if conflict_latched:
        missing = list(prior.missing_or_ambiguous)
        for item in incoming.missing_or_ambiguous:
            if item not in missing:
                missing.append(item)
        if PathAMissingRequirement.QUERY_CASE_BINDING not in missing:
            missing.insert(0, PathAMissingRequirement.QUERY_CASE_BINDING)
        return prior.model_copy(
            update={
                "status": PathACaseStatus.NOT_QUALIFIED,
                "missing_or_ambiguous": missing,
                "notes": list(
                    dict.fromkeys(
                        [
                            *prior.notes,
                            *incoming.notes,
                            _HISTORICAL_QUERY_CONFLICT_NOTE,
                        ]
                    )
                ),
                # Keep first observed query; conflict latch is in notes/missing.
                "query": prior.query if prior.query is not None else incoming.query,
            }
        )

    if incoming.status == PathACaseStatus.QUALIFIED:
        return incoming
    if prior.status == PathACaseStatus.QUALIFIED:
        return prior

    merged_missing = list(prior.missing_or_ambiguous)
    for item in incoming.missing_or_ambiguous:
        if item not in merged_missing:
            merged_missing.append(item)
    return prior.model_copy(
        update={
            "missing_or_ambiguous": merged_missing,
            "notes": list(dict.fromkeys([*prior.notes, *incoming.notes])),
            "query": prior.query if prior.query is not None else incoming.query,
        }
    )


def run_path_a_preflight(
    *,
    intended_case_queries: Mapping[str, str],
    artifact_paths: list[Path],
    context_result_case_id_by_path: dict[str, str] | None = None,
) -> PathAPreflightReport:
    """Read-only Path-A qualification over immutable historical artifacts.

    ``intended_case_queries`` is the frozen ``case_id -> original_query`` mapping.
    Path A succeeds only when every intended binding matches exactly and each case
    is reconstructible from one coherent historical lineage. Never invokes
    retrieval or synthesizes missing ranks/scores.
    """
    frozen = _normalize_intended_case_queries(intended_case_queries)
    ordered_intended = list(frozen.keys())
    if not artifact_paths:
        raise ValueError("artifact_paths must be non-empty")

    case_id_by_path = dict(context_result_case_id_by_path or {})
    inspected: list[PathAInspectedArtifact] = []
    assessments_by_case: dict[str, PathACaseAssessment] = {}
    lineage_views: list[PathASharedLineageView] = []
    notes: list[str] = [
        "preflight is read-only; no retrieval or live index access is performed",
        "no partial historical/live mixing is authorized",
        "case/query binding uses exact string equality against intended_case_queries",
    ]

    for path in artifact_paths:
        payload = _load_json(path)
        schema = str(payload.get("schema_version") or "")
        method = payload.get("method")
        try:
            if schema.startswith("offline-rag-retrieval-eval-result"):
                art, case_assessments, lineage = _inspect_retrieval_eval(
                    path,
                    payload,
                    intended_case_queries=frozen,
                )
            elif method == "hybrid-rerank-context" or (
                "evidence_units" in payload and "anchors" in payload
            ):
                art, case_assessments, lineage = _inspect_context_result_dump(
                    path,
                    payload,
                    case_id=case_id_by_path.get(str(path)),
                    intended_case_queries=frozen,
                )
            else:
                lineage = PathASharedLineageView()
                art = PathAInspectedArtifact(
                    path=str(path),
                    artifact_kind="unsupported-historical-artifact",
                    run_id=None,
                    method=None if method is None else str(method),
                    gold_dataset_id=None,
                    lineage=lineage,
                    case_ids_present=[],
                )
                case_assessments = []
                notes.append(
                    f"unsupported artifact schema at {path}; cannot qualify Path A"
                )
        except (ValidationError, ValueError, TypeError) as exc:
            lineage = PathASharedLineageView()
            art = PathAInspectedArtifact(
                path=str(path),
                artifact_kind="unparseable-historical-artifact",
                lineage=lineage,
            )
            case_assessments = []
            notes.append(f"failed to parse artifact {path}: {exc}")

        inspected.append(art)
        lineage_views.append(lineage)
        for assessment in case_assessments:
            # Historical cases outside the intended population are ignored for
            # coverage, but still inspected for lineage consistency above.
            if assessment.case_id not in frozen:
                continue
            prior = assessments_by_case.get(assessment.case_id)
            if prior is None:
                assessments_by_case[assessment.case_id] = assessment
            else:
                assessments_by_case[assessment.case_id] = _merge_case_assessment(
                    prior, assessment
                )

    lineage_consistency, _ = _merge_lineage_views(lineage_views)

    final_assessments: list[PathACaseAssessment] = []
    for case_id in ordered_intended:
        intended_query = frozen[case_id]
        found = assessments_by_case.get(case_id)
        if found is None:
            final_assessments.append(
                PathACaseAssessment(
                    case_id=case_id,
                    status=PathACaseStatus.NOT_QUALIFIED,
                    missing_or_ambiguous=[
                        PathAMissingRequirement.QUERY_CASE_BINDING,
                        PathAMissingRequirement.SHARED_LINEAGE,
                        PathAMissingRequirement.RERANKER_RAW_SCORES,
                        PathAMissingRequirement.RERANK_RANKS_ORDER,
                        PathAMissingRequirement.HYBRID_RANK_RRF_SCORE,
                        PathAMissingRequirement.DENSE_BRANCH_RANK_SCORE,
                        PathAMissingRequirement.LEXICAL_BRANCH_RANK_SCORE,
                        PathAMissingRequirement.EVIDENCE_UNIT_PROVENANCE,
                        PathAMissingRequirement.ASSEMBLY_DIAGNOSTICS,
                    ],
                    notes=["case absent from inspected historical artifacts"],
                )
            )
            continue

        missing = list(found.missing_or_ambiguous)
        notes_out = list(found.notes)
        if not _binding_matches(
            historical_query=found.query, intended_query=intended_query
        ):
            if PathAMissingRequirement.QUERY_CASE_BINDING not in missing:
                missing.insert(0, PathAMissingRequirement.QUERY_CASE_BINDING)
            notes_out.append(
                "historical query does not exactly equal frozen intended original_query"
            )

        if lineage_consistency != PathALineageConsistency.CONSISTENT:
            if PathAMissingRequirement.SHARED_LINEAGE not in missing:
                missing.insert(0, PathAMissingRequirement.SHARED_LINEAGE)
            notes_out.append(f"lineage_consistency={lineage_consistency.value}")

        status = (
            PathACaseStatus.QUALIFIED
            if (
                found.status == PathACaseStatus.QUALIFIED
                and not missing
                and lineage_consistency == PathALineageConsistency.CONSISTENT
            )
            else PathACaseStatus.NOT_QUALIFIED
        )
        final_assessments.append(
            found.model_copy(
                update={
                    "status": status,
                    "missing_or_ambiguous": _dedupe_missing(missing),
                    "notes": list(dict.fromkeys(notes_out)),
                }
            )
        )

    all_qualified = bool(final_assessments) and all(
        item.status == PathACaseStatus.QUALIFIED for item in final_assessments
    )
    overall = (
        PathAOverallResult.PATH_A_QUALIFIED
        if (all_qualified and lineage_consistency == PathALineageConsistency.CONSISTENT)
        else PathAOverallResult.PATH_A_NOT_QUALIFIED
    )
    if overall == PathAOverallResult.PATH_A_NOT_QUALIFIED:
        notes.append(
            "PATH_A_NOT_QUALIFIED: authorize one dedicated Path-B measure-once "
            "snapshot for the entire intended population"
        )

    return PathAPreflightReport(
        intended_case_ids=ordered_intended,
        intended_case_queries=dict(frozen),
        inspected_artifacts=inspected,
        case_assessments=final_assessments,
        lineage_consistency=lineage_consistency,
        overall=overall,
        notes=notes,
    )
