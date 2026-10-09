"""Question Check durable payload helpers (16F-B / Rework 1)."""

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

_ACCEPT_REJECT_KEYS = frozenset({"decision"})
_EDIT_KEYS = frozenset(
    {"decision", "effective_query", "effective_category", "effective_tags"}
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


def durable_question_check_payload(payload: QuestionCheckPayload) -> dict[str, Any]:
    """Exact durable JSON object for ledger storage / request fingerprinting."""
    if payload.decision is QuestionCheckDecision.EDIT:
        return {
            "decision": payload.decision.value,
            "effective_query": payload.effective_query,
            "effective_category": payload.effective_category,
            "effective_tags": list(payload.effective_tags or []),
        }
    return {"decision": payload.decision.value}


def canonicalize_question_check_payload(
    raw: dict[str, Any],
    *,
    case: SilverCase,
) -> QuestionCheckPayload:
    """COMMAND INPUT: canonicalize valid user intent into durable payload."""
    if not isinstance(raw, dict):
        raise GoldLabError(
            "question_check_payload_invalid",
            "Question Check payload must be an object",
        )
    try:
        provisional = QuestionCheckPayload.model_validate(raw)
    except Exception as exc:
        raise GoldLabError(
            "question_check_payload_invalid",
            f"invalid Question Check payload: {exc}",
        ) from exc

    if provisional.decision is QuestionCheckDecision.ACCEPT:
        # Reject caller-supplied null/extra edit keys even if model defaults None.
        if set(raw.keys()) != _ACCEPT_REJECT_KEYS:
            raise GoldLabError(
                "question_check_payload_invalid",
                "accept payload must be exactly {decision}",
            )
        return QuestionCheckPayload(decision=QuestionCheckDecision.ACCEPT)
    if provisional.decision is QuestionCheckDecision.REJECT:
        if set(raw.keys()) != _ACCEPT_REJECT_KEYS:
            raise GoldLabError(
                "question_check_payload_invalid",
                "reject payload must be exactly {decision}",
            )
        return QuestionCheckPayload(decision=QuestionCheckDecision.REJECT)

    if set(raw.keys()) != _EDIT_KEYS:
        raise GoldLabError(
            "question_check_payload_invalid",
            "edit payload must contain exactly decision/effective_query/"
            "effective_category/effective_tags",
        )
    try:
        effective_query = canonicalize_query(str(provisional.effective_query))
        effective_category = canonicalize_category(provisional.effective_category)
        effective_tags = sorted(canonicalize_tags(provisional.effective_tags))
    except (TypeError, ValueError) as exc:
        raise GoldLabError(
            "question_check_payload_invalid",
            f"invalid edit values: {exc}",
        ) from exc

    _assert_semantic_edit(
        case,
        effective_query=effective_query,
        effective_category=effective_category,
        effective_tags=effective_tags,
    )
    return QuestionCheckPayload(
        decision=QuestionCheckDecision.EDIT,
        effective_query=effective_query,
        effective_category=effective_category,
        effective_tags=effective_tags,
    )


def validate_durable_question_check_payload(
    raw: dict[str, Any],
    *,
    case: SilverCase,
) -> QuestionCheckPayload:
    """LEDGER REPLAY: persisted payload must already be exactly canonical."""
    if not isinstance(raw, dict):
        raise GoldLabError(
            "effective_state_qc_payload_invalid",
            "Question Check payload must be an object",
        )
    decision_raw = raw.get("decision")
    try:
        decision = QuestionCheckDecision(decision_raw)
    except Exception as exc:
        raise GoldLabError(
            "effective_state_qc_payload_invalid",
            f"invalid Question Check decision: {decision_raw!r}",
        ) from exc

    if decision is QuestionCheckDecision.ACCEPT:
        if set(raw.keys()) != _ACCEPT_REJECT_KEYS:
            raise GoldLabError(
                "effective_state_qc_payload_noncanonical",
                "accept durable payload must be exactly {decision}",
            )
        return QuestionCheckPayload(decision=QuestionCheckDecision.ACCEPT)

    if decision is QuestionCheckDecision.REJECT:
        if set(raw.keys()) != _ACCEPT_REJECT_KEYS:
            raise GoldLabError(
                "effective_state_qc_payload_noncanonical",
                "reject durable payload must be exactly {decision}",
            )
        return QuestionCheckPayload(decision=QuestionCheckDecision.REJECT)

    if set(raw.keys()) != _EDIT_KEYS:
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "edit durable payload must contain exactly four canonical keys",
        )
    effective_query = raw["effective_query"]
    effective_category = raw["effective_category"]
    effective_tags = raw["effective_tags"]
    if not isinstance(effective_query, str):
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "edit effective_query must be a string",
        )
    if effective_category is not None and not isinstance(effective_category, str):
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "edit effective_category must be string or null",
        )
    if not isinstance(effective_tags, list) or any(
        not isinstance(t, str) for t in effective_tags
    ):
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "edit effective_tags must be a list of strings",
        )

    try:
        canonical_query = canonicalize_query(effective_query)
        canonical_category = canonicalize_category(effective_category)
        canonical_tags = sorted(canonicalize_tags(effective_tags))
    except (TypeError, ValueError) as exc:
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            f"edit values are not canonical: {exc}",
        ) from exc

    if effective_query != canonical_query:
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "stored effective_query is not canonical",
        )
    if effective_category != canonical_category:
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "stored effective_category is not canonical",
        )
    if list(effective_tags) != canonical_tags:
        raise GoldLabError(
            "effective_state_qc_payload_noncanonical",
            "stored effective_tags are not the deterministic sorted canonical list",
        )

    _assert_semantic_edit(
        case,
        effective_query=canonical_query,
        effective_category=canonical_category,
        effective_tags=canonical_tags,
        reason="effective_state_qc_edit_not_semantic",
    )
    return QuestionCheckPayload(
        decision=QuestionCheckDecision.EDIT,
        effective_query=canonical_query,
        effective_category=canonical_category,
        effective_tags=canonical_tags,
    )


def _assert_semantic_edit(
    case: SilverCase,
    *,
    effective_query: str,
    effective_category: str | None,
    effective_tags: list[str],
    reason: str = "question_check_edit_not_semantic",
) -> None:
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
            reason,
            "edit must change query, category, or tag set",
        )


def question_check_query_fingerprint(
    payload: QuestionCheckPayload, case: SilverCase
) -> str | None:
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


def canonical_question_check_request_payload(
    payload: QuestionCheckPayload,
) -> dict[str, Any]:
    """Deterministic payload object for request fingerprinting."""
    return durable_question_check_payload(payload)
