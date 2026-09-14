"""Authoritative human-review domain mutations (Slice 9E)."""

from __future__ import annotations

from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase
from offline_rag.gold_authoring.review_models import (
    CategoryOverride,
    HumanJudgment,
    HumanReview,
    HumanReviewStatus,
    ReviewError,
    canonicalize_category,
    canonicalize_query,
    canonicalize_tags,
    tags_equal,
)


def _ensure_review(case: SilverCase) -> HumanReview:
    if case.human_review is None:
        return HumanReview()
    return case.human_review.model_copy(deep=True)


def _replace_case(run: GoldAuthoringRun, case: SilverCase) -> GoldAuthoringRun:
    cases = list(run.cases)
    for idx, existing in enumerate(cases):
        if existing.draft_case_id == case.draft_case_id:
            cases[idx] = case
            return run.model_copy(update={"cases": cases})
    raise ReviewError(
        f"unknown draft_case_id: {case.draft_case_id}",
        code="unknown_case",
    )


def get_case(run: GoldAuthoringRun, draft_case_id: str) -> SilverCase:
    for case in run.cases:
        if case.draft_case_id == draft_case_id:
            return case
    raise ReviewError(f"unknown draft_case_id: {draft_case_id}", code="unknown_case")


def set_human_grade(
    run: GoldAuthoringRun,
    *,
    draft_case_id: str,
    chunk_id: str,
    relevance: int,
) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if relevance not in (0, 1, 2) or type(relevance) is not int:
        raise ReviewError(
            "human relevance must be strict integer 0, 1, or 2",
            code="invalid_relevance",
        )
    candidate_ids = {c.chunk_id for c in case.candidates}
    chunk_id = chunk_id.strip()
    if chunk_id not in candidate_ids:
        raise ReviewError(
            f"chunk_id not in 9C candidate pool: {chunk_id}",
            code="unknown_candidate",
        )
    effective_query = case.effective_query()
    if effective_query is None:
        raise ReviewError(
            "cannot grade candidates without an effective query",
            code="missing_query",
        )

    review = _ensure_review(case)
    if review.status in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED):
        raise ReviewError(
            "reopen the case before changing grades",
            code="terminal_status",
        )
    if review.status == HumanReviewStatus.REJECTED:
        raise ReviewError(
            "reopen the case before changing grades",
            code="terminal_status",
        )

    if review.judgments and review.grade_basis_query != effective_query:
        raise ReviewError(
            "stale query-grade binding; clear via query edit or reopen path",
            code="stale_binding",
        )

    judgments = [j for j in review.judgments if j.chunk_id != chunk_id]
    judgments.append(HumanJudgment(chunk_id=chunk_id, relevance=relevance))  # type: ignore[arg-type]
    judgments.sort(key=lambda item: item.chunk_id)
    review.judgments = judgments
    review.grade_basis_query = effective_query
    review.status = HumanReviewStatus.PENDING
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def clear_human_grade(
    run: GoldAuthoringRun,
    *,
    draft_case_id: str,
    chunk_id: str,
) -> GoldAuthoringRun:
    """Remove one human judgment (returns candidate to unreviewed)."""
    case = get_case(run, draft_case_id)
    review = _ensure_review(case)
    if review.status != HumanReviewStatus.PENDING:
        raise ReviewError(
            "reopen the case before clearing grades",
            code="terminal_status",
        )
    chunk_id = chunk_id.strip()
    judgments = [j for j in review.judgments if j.chunk_id != chunk_id]
    if not judgments:
        review.judgments = []
        review.grade_basis_query = None
    else:
        review.judgments = sorted(judgments, key=lambda item: item.chunk_id)
    review.status = HumanReviewStatus.PENDING
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def set_reviewed_query(
    run: GoldAuthoringRun,
    *,
    draft_case_id: str,
    query: str,
) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if case.proposed_query is None:
        raise ReviewError(
            "case has no proposed_query to review against",
            code="missing_proposal",
        )
    new_query = canonicalize_query(query)
    proposed = canonicalize_query(case.proposed_query)
    current = case.effective_query()
    review = _ensure_review(case)

    if current == new_query:
        # No-op save: preserve grades/status.
        return run

    # Semantic query change: clear grades, demote terminal status.
    if new_query == proposed:
        review.query_override = None
    else:
        review.query_override = new_query
    review.judgments = []
    review.grade_basis_query = None
    review.status = HumanReviewStatus.PENDING
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def set_reviewed_category(
    run: GoldAuthoringRun,
    *,
    draft_case_id: str,
    category: str | None,
    clear: bool = False,
) -> GoldAuthoringRun:
    """Set category override. ``clear=True`` means explicit override to null."""
    case = get_case(run, draft_case_id)
    review = _ensure_review(case)
    proposed = canonicalize_category(case.proposed_category)

    if clear:
        override = CategoryOverride(is_overridden=True, value=None)
    else:
        value = canonicalize_category(category)
        if value == proposed:
            override = CategoryOverride(is_overridden=False, value=None)
        else:
            override = CategoryOverride(is_overridden=True, value=value)

    review.category_override = override
    review.status = _demote_if_classification_invalid(case, review)
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def set_reviewed_tags(
    run: GoldAuthoringRun,
    *,
    draft_case_id: str,
    tags: list[str] | None,
    clear_override: bool = False,
) -> GoldAuthoringRun:
    """
    Set tags override.

    ``clear_override=True`` removes the override (use proposed tags).
    ``tags=[]`` means human explicitly cleared all tags.
    ``tags=None`` with clear_override=False is invalid.
    """
    case = get_case(run, draft_case_id)
    review = _ensure_review(case)
    if clear_override:
        review.tags_override = None
    else:
        if tags is None:
            raise ReviewError(
                "tags must be a list (use clear_override to remove override)",
                code="invalid_tags",
            )
        normalized = list(canonicalize_tags(tags))
        if tags_equal(normalized, case.proposed_tags):
            review.tags_override = None
        else:
            review.tags_override = normalized

    review.status = _demote_if_classification_invalid(case, review)
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def _demote_if_classification_invalid(
    case: SilverCase,
    review: HumanReview,
) -> HumanReviewStatus:
    """Preserve pending/rejected; demote accepted/edited when classification drifts."""
    if review.status not in (HumanReviewStatus.ACCEPTED, HumanReviewStatus.EDITED):
        return review.status
    probe = case.model_copy(update={"human_review": review})
    changed = probe.proposal_content_changed()
    if review.status == HumanReviewStatus.ACCEPTED and changed:
        return HumanReviewStatus.PENDING
    if review.status == HumanReviewStatus.EDITED and not changed:
        return HumanReviewStatus.PENDING
    return review.status


def accept_case(run: GoldAuthoringRun, *, draft_case_id: str) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if case.human_status != HumanReviewStatus.PENDING:
        raise ReviewError(
            "only pending cases may be accepted",
            code="invalid_transition",
        )
    if not case.quality_eligible_for_gold():
        raise ReviewError(
            "accept requires complete human map and at least one positive grade",
            code="review_incomplete",
        )
    if case.proposal_content_changed():
        raise ReviewError(
            "proposal metadata changed; use approve-edited instead",
            code="wrong_status",
        )
    review = _ensure_review(case)
    if review.grade_basis_query != case.effective_query():
        raise ReviewError("stale query-grade binding", code="stale_binding")
    review.status = HumanReviewStatus.ACCEPTED
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def approve_edited_case(
    run: GoldAuthoringRun, *, draft_case_id: str
) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if case.human_status != HumanReviewStatus.PENDING:
        raise ReviewError(
            "only pending cases may be approved as edited",
            code="invalid_transition",
        )
    if not case.quality_eligible_for_gold():
        raise ReviewError(
            "approve-edited requires complete human map and at least one positive",
            code="review_incomplete",
        )
    if not case.proposal_content_changed():
        raise ReviewError(
            "no proposal metadata change; use accept instead",
            code="wrong_status",
        )
    review = _ensure_review(case)
    if review.grade_basis_query != case.effective_query():
        raise ReviewError("stale query-grade binding", code="stale_binding")
    review.status = HumanReviewStatus.EDITED
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def reject_case(run: GoldAuthoringRun, *, draft_case_id: str) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if case.human_status != HumanReviewStatus.PENDING:
        raise ReviewError(
            "only pending cases may be rejected",
            code="invalid_transition",
        )
    review = _ensure_review(case)
    review.status = HumanReviewStatus.REJECTED
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)


def reopen_case(run: GoldAuthoringRun, *, draft_case_id: str) -> GoldAuthoringRun:
    case = get_case(run, draft_case_id)
    if case.human_status == HumanReviewStatus.PENDING:
        raise ReviewError(
            "case is already pending",
            code="invalid_transition",
        )
    review = _ensure_review(case)
    review.status = HumanReviewStatus.PENDING
    updated = case.model_copy(update={"human_review": review})
    return _replace_case(run, updated)
