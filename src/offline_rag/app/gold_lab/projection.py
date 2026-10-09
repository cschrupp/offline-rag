"""Deterministic effective-state -> GoldAuthoringRun projection (16F-C)."""

from __future__ import annotations

from offline_rag.app.gold_lab.effective_state import EffectiveCampaignState
from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import absolute_relevance_task_id
from offline_rag.app.gold_lab.models import QuestionCheckDecision
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import (
    CategoryOverride,
    HumanJudgment,
    HumanReview,
    HumanReviewStatus,
    canonicalize_category,
    canonicalize_query,
    canonicalize_tags,
    tags_equal,
)


def project_authoring_run(state: EffectiveCampaignState) -> GoldAuthoringRun:
    """Pure deterministic scientific projection from baseline + effective state."""
    projected_cases: list[SilverCase] = []
    for case in state.baseline.cases:
        projected_cases.append(_project_case(state, case))
    try:
        run = state.baseline.model_copy(update={"cases": projected_cases})
        # Round-trip through existing validators / Slice-9 invariants.
        return GoldAuthoringRun.model_validate_json(run.model_dump_json())
    except Exception as exc:
        raise GoldLabError(
            "projection_invalid",
            f"projected GoldAuthoringRun failed validation: {exc}",
        ) from exc


def projection_text(run: GoldAuthoringRun) -> str:
    """Frozen 16F-C serialization: model_dump_json() + trailing newline."""
    return run.model_dump_json() + "\n"


def _project_case(state: EffectiveCampaignState, case: SilverCase) -> SilverCase:
    if not is_reviewable_case(case):
        # Preserve pristine baseline human state (None or empty PENDING).
        return case.model_copy(deep=True)

    qc = state.current_question_for_case(case.draft_case_id)
    if qc is None:
        review = HumanReview(
            status=HumanReviewStatus.PENDING,
            judgments=[],
            query_override=None,
            category_override=CategoryOverride(),
            tags_override=None,
            grade_basis_query=None,
        )
        return case.model_copy(update={"human_review": review}, deep=True)

    if qc.decision is QuestionCheckDecision.REJECT:
        review = HumanReview(
            status=HumanReviewStatus.REJECTED,
            judgments=[],
            query_override=None,
            category_override=CategoryOverride(),
            tags_override=None,
            grade_basis_query=None,
        )
        return case.model_copy(update={"human_review": review}, deep=True)

    # accept / edit
    assert qc.effective_query is not None
    assert qc.query_fingerprint is not None
    judgments = _current_judgments(
        state,
        case=case,
        query_fingerprint=qc.query_fingerprint,
    )
    grade_basis = qc.effective_query if judgments else None

    if qc.decision is QuestionCheckDecision.ACCEPT:
        review = HumanReview(
            status=_accept_status(case, judgments),
            judgments=judgments,
            query_override=None,
            category_override=CategoryOverride(),
            tags_override=None,
            grade_basis_query=grade_basis,
        )
        return case.model_copy(update={"human_review": review}, deep=True)

    # edit
    proposed_query = canonicalize_query(case.proposed_query)  # type: ignore[arg-type]
    proposed_category = canonicalize_category(case.proposed_category)
    proposed_tags = list(canonicalize_tags(case.proposed_tags))
    effective_tags = list(qc.effective_tags)

    query_override = (
        qc.effective_query if qc.effective_query != proposed_query else None
    )
    if qc.effective_category != proposed_category:
        category_override = CategoryOverride(
            is_overridden=True, value=qc.effective_category
        )
    else:
        category_override = CategoryOverride()
    tags_override = (
        effective_tags if not tags_equal(effective_tags, proposed_tags) else None
    )

    review = HumanReview(
        status=_edit_status(
            case,
            judgments=judgments,
            effective_query=qc.effective_query,
            effective_category=qc.effective_category,
            effective_tags=effective_tags,
        ),
        judgments=judgments,
        query_override=query_override,
        category_override=category_override,
        tags_override=tags_override,
        grade_basis_query=grade_basis,
    )
    return case.model_copy(update={"human_review": review}, deep=True)


def _current_judgments(
    state: EffectiveCampaignState,
    *,
    case: SilverCase,
    query_fingerprint: str,
) -> list[HumanJudgment]:
    judgments: list[HumanJudgment] = []
    for candidate in sorted(case.candidates, key=lambda item: item.chunk_id):
        task_id = absolute_relevance_task_id(
            campaign_id=state.campaign_id,
            case_id=case.draft_case_id,
            candidate_chunk_id=candidate.chunk_id,
        )
        current = state.absolute_by_basis.get((task_id, query_fingerprint))
        if current is None:
            continue
        judgments.append(
            HumanJudgment(
                chunk_id=candidate.chunk_id,
                relevance=current.relevance,  # type: ignore[arg-type]
            )
        )
    return judgments


def _accept_status(
    case: SilverCase, judgments: list[HumanJudgment]
) -> HumanReviewStatus:
    candidate_ids = {c.chunk_id for c in case.candidates}
    judged = {j.chunk_id for j in judgments}
    positives = sum(1 for j in judgments if j.relevance >= 1)
    if candidate_ids and judged == candidate_ids and positives >= 1:
        return HumanReviewStatus.ACCEPTED
    return HumanReviewStatus.PENDING


def _edit_status(
    case: SilverCase,
    *,
    judgments: list[HumanJudgment],
    effective_query: str,
    effective_category: str | None,
    effective_tags: list[str],
) -> HumanReviewStatus:
    candidate_ids = {c.chunk_id for c in case.candidates}
    judged = {j.chunk_id for j in judgments}
    positives = sum(1 for j in judgments if j.relevance >= 1)
    # Semantic change relative to proposal (mirrors proposal_content_changed).
    proposed_query = canonicalize_query(case.proposed_query)  # type: ignore[arg-type]
    changed = (
        effective_query != proposed_query
        or effective_category != canonicalize_category(case.proposed_category)
        or not tags_equal(effective_tags, case.proposed_tags)
    )
    if (
        candidate_ids
        and judged == candidate_ids
        and positives >= 1
        and changed
    ):
        return HumanReviewStatus.EDITED
    return HumanReviewStatus.PENDING
