"""Transient review view-model builders (Slice 9E). No durable body duplication."""

from __future__ import annotations

from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.core.document_metadata import render_section_path_v1
from offline_rag.gold_authoring.chunk_access import (
    ChunkAccessError,
    resolve_seed_text_from_chunk_set,
)
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import HumanReviewStatus, ReviewError


def _model_judgments_by_chunk(case: SilverCase) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for judgment in case.model_judgments:
        slot = out.setdefault(
            judgment.chunk_id,
            {"pass_1": None, "pass_2": None},
        )
        slot[judgment.pass_id] = {
            "grade": judgment.grade,
            "rationale": judgment.rationale,
        }
    return out


def _agreement_by_chunk(case: SilverCase) -> dict[str, dict[str, Any]]:
    if case.prelabel_summary is None:
        return {}
    return {
        item.chunk_id: {
            "agreement": item.agreement.value
            if hasattr(item.agreement, "value")
            else str(item.agreement),
            "disagreement_severity": item.disagreement_severity.value
            if hasattr(item.disagreement_severity, "value")
            else str(item.disagreement_severity),
        }
        for item in case.prelabel_summary.candidate_summaries
    }


def build_case_list_payload(run: GoldAuthoringRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ordinal, case in enumerate(run.cases, start=1):
        judged = len(case.human_judgment_map())
        priority = None
        if case.prelabel_summary is not None:
            priority = case.prelabel_summary.review_priority.value
        rows.append(
            {
                "ordinal": ordinal,
                "draft_case_id": case.draft_case_id,
                "effective_query": case.effective_query(),
                "proposed_query": case.proposed_query,
                "status": case.human_status.value,
                "review_priority": priority,
                "judged_count": judged,
                "candidate_count": len(case.candidates),
                "query_edited": (
                    case.effective_query() != case.proposed_query
                    if case.proposed_query is not None
                    else False
                ),
            }
        )
    return rows


def build_case_detail_payload(
    settings: AppSettings,
    run: GoldAuthoringRun,
    case: SilverCase,
) -> dict[str, Any]:
    if not run.chunk_set_id:
        raise ReviewError(
            "historical evidence unavailable: run.chunk_set_id is required",
            code="evidence_unavailable",
        )

    model_by_chunk = _model_judgments_by_chunk(case)
    agreement_by_chunk = _agreement_by_chunk(case)
    human_map = case.human_judgment_map()
    seed_id = case.source_seed.chunk_id if case.source_seed is not None else None
    effective_query = case.effective_query()
    proposed_query = case.proposed_query
    query_edited = (
        effective_query != proposed_query if proposed_query is not None else False
    )

    priority = None
    priority_reasons: list[str] = []
    if case.prelabel_summary is not None:
        summary = case.prelabel_summary
        priority = summary.review_priority.value
        if summary.case_has_polar_disagreement:
            priority_reasons.append("polar disagreement")
        elif summary.case_has_disagreement:
            priority_reasons.append("some disagreement")
        if summary.case_has_source_seed_zero:
            priority_reasons.append("source seed graded 0 by model")
        if summary.case_has_competing_grade_2:
            priority_reasons.append("multiple grade-2 candidates")
        if summary.case_has_no_positive_prelabel:
            priority_reasons.append("no positive model prelabel")

    candidates: list[dict[str, Any]] = []
    for ordinal, candidate in enumerate(case.candidates, start=1):
        # Fail closed: never present placeholder text as gradable evidence.
        try:
            text = resolve_seed_text_from_chunk_set(
                settings,
                chunk_set_id=run.chunk_set_id,
                chunk_id=candidate.chunk_id,
            )
        except ChunkAccessError as exc:
            raise ReviewError(
                f"historical evidence unavailable for "
                f"chunk_set_id={run.chunk_set_id} chunk_id={candidate.chunk_id}: {exc}",
                code="evidence_unavailable",
            ) from exc

        section = render_section_path_v1(candidate.section_path) or ""
        human_grade = human_map.get(candidate.chunk_id)
        retrieval = [
            {
                "retriever": hit.retriever,
                "rank": hit.rank,
                "score": hit.score,
            }
            for hit in candidate.retrieval_hits
        ]
        candidates.append(
            {
                "ordinal": ordinal,
                "chunk_id": candidate.chunk_id,
                "document_title": candidate.document_title or "",
                "section_path": list(candidate.section_path),
                "section": section,
                "text": text,
                "is_source_seed": candidate.chunk_id == seed_id,
                "human_relevance": human_grade,
                "model": model_by_chunk.get(
                    candidate.chunk_id, {"pass_1": None, "pass_2": None}
                ),
                "agreement": agreement_by_chunk.get(candidate.chunk_id),
                "retrieval_provenance": retrieval,
            }
        )

    return {
        "authoring_run_id": run.authoring_run_id,
        "chunk_set_id": run.chunk_set_id,
        "draft_case_id": case.draft_case_id,
        "status": case.human_status.value,
        "proposed_query": proposed_query,
        "effective_query": effective_query,
        "proposed_category": case.proposed_category,
        "effective_category": case.effective_category(),
        "proposed_tags": list(case.proposed_tags),
        "effective_tags": list(case.effective_tags()),
        "query_edited": query_edited,
        "model_prelabels_for_proposed_query": query_edited,
        "judged_count": len(human_map),
        "candidate_count": len(case.candidates),
        "human_positive_count": case.human_positive_count(),
        "review_complete": case.review_complete(),
        "review_priority": priority,
        "review_priority_reasons": priority_reasons,
        "candidates": candidates,
        "can_accept": (
            case.human_status == HumanReviewStatus.PENDING
            and case.quality_eligible_for_gold()
            and not case.proposal_content_changed()
        ),
        "can_approve_edited": (
            case.human_status == HumanReviewStatus.PENDING
            and case.quality_eligible_for_gold()
            and case.proposal_content_changed()
        ),
        "can_reject": case.human_status == HumanReviewStatus.PENDING,
        "can_reopen": case.human_status != HumanReviewStatus.PENDING,
    }
