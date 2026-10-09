"""Question Check durable payload helpers (16F-B)."""

from __future__ import annotations

from typing import Any

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import query_fingerprint
from offline_rag.app.gold_lab.models import QuestionCheckDecision, QuestionCheckPayload
from offline_rag.gold_authoring.models import SilverCase
from offline_rag.gold_authoring.review_models import (
    canonicalize_category,
    canonicalize_query,
    canonicalize_tags,
    tags_equal,
)


def proposal_effective_values(case: SilverCase) -> dict[str, Any]:
    query = (
        canonicalize_query(case.proposed_query)
        if case.proposed_query is not None
        else None
    )
    return {
        "effective_query": query,
        "effective_category": canonicalize_category(case.proposed_category),
        "effective_tags": sorted(canonicalize_tags(case.proposed_tags)),
    }


def canonicalize_question_check_payload(
    raw: dict[str, Any],
    *,
    case: SilverCase,
) -> QuestionCheckPayload:
    """Validate and canonicalize a Question Check decision for durable storage."""
    try:
        provisional = QuestionCheckPayload.model_validate(raw)
    except Exception as exc:
        raise GoldLabError(
            "question_check_payload_invalid",
            f"invalid Question Check payload: {exc}",
        ) from exc

    if provisional.decision is QuestionCheckDecision.ACCEPT:
        return QuestionCheckPayload(decision=QuestionCheckDecision.ACCEPT)
    if provisional.decision is QuestionCheckDecision.REJECT:
        return QuestionCheckPayload(decision=QuestionCheckDecision.REJECT)

    # edit
    try:
        effective_query = canonicalize_query(str(provisional.effective_query))
        effective_category = canonicalize_category(provisional.effective_category)
        effective_tags = sorted(canonicalize_tags(provisional.effective_tags))
    except (TypeError, ValueError) as exc:
        raise GoldLabError(
            "question_check_payload_invalid",
            f"invalid edit values: {exc}",
        ) from exc

    proposal = proposal_effective_values(case)
    if proposal["effective_query"] is None:
        raise GoldLabError(
            "question_check_case_not_reviewable",
            "edit requires a reviewable proposed query",
        )
    semantic_changed = (
        effective_query != proposal["effective_query"]
        or effective_category != proposal["effective_category"]
        or not tags_equal(effective_tags, proposal["effective_tags"])
    )
    if not semantic_changed:
        raise GoldLabError(
            "question_check_edit_not_semantic",
            "edit must change query, category, or tag set",
        )
    return QuestionCheckPayload(
        decision=QuestionCheckDecision.EDIT,
        effective_query=effective_query,
        effective_category=effective_category,
        effective_tags=effective_tags,
    )


def question_check_query_fingerprint(payload: QuestionCheckPayload, case: SilverCase) -> str | None:
    if payload.decision is QuestionCheckDecision.REJECT:
        return None
    if payload.decision is QuestionCheckDecision.ACCEPT:
        if case.proposed_query is None:
            raise GoldLabError(
                "question_check_case_not_reviewable",
                "accept requires proposed query",
            )
        return query_fingerprint(canonicalize_query(case.proposed_query))
    assert payload.effective_query is not None
    return query_fingerprint(payload.effective_query)


def canonical_question_check_request_payload(payload: QuestionCheckPayload) -> dict[str, Any]:
    """Deterministic payload object for request fingerprinting."""
    if payload.decision is QuestionCheckDecision.EDIT:
        return {
            "decision": payload.decision.value,
            "effective_query": payload.effective_query,
            "effective_category": payload.effective_category,
            "effective_tags": list(payload.effective_tags or []),
        }
    return {"decision": payload.decision.value}
