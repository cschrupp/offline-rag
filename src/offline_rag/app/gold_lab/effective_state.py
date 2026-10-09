"""Deterministic effective-state fold over baseline + append-only ledger (16F-B)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from offline_rag.app.gold_lab.errors import GoldLabError
from offline_rag.app.gold_lab.ids import (
    absolute_relevance_task_id,
    question_check_task_id,
)
from offline_rag.app.gold_lab.models import (
    AbsoluteRelevancePayload,
    GoldLedgerRecord,
    GoldLedgerRecordType,
    QuestionCheckDecision,
    QuestionCheckPayload,
)
from offline_rag.app.gold_lab.question_check import (
    canonicalize_question_check_payload,
    proposal_effective_values,
    question_check_query_fingerprint,
)
from offline_rag.app.gold_lab.reviewable import is_reviewable_case
from offline_rag.gold_authoring.models import GoldAuthoringRun, SilverCase


@dataclass(frozen=True)
class CurrentQuestionCheck:
    record: GoldLedgerRecord
    payload: QuestionCheckPayload
    decision: QuestionCheckDecision
    effective_query: str | None
    effective_category: str | None
    effective_tags: list[str]
    query_fingerprint: str | None


@dataclass(frozen=True)
class CurrentAbsoluteJudgment:
    record: GoldLedgerRecord
    relevance: int
    query_fingerprint: str


@dataclass
class EffectiveCampaignState:
    """Folded effective state for one campaign."""

    campaign_id: str
    baseline: GoldAuthoringRun
    records: list[GoldLedgerRecord]
    cases_by_id: dict[str, SilverCase] = field(default_factory=dict)
    question_by_task: dict[str, CurrentQuestionCheck] = field(default_factory=dict)
    # (task_id, query_fingerprint) -> current absolute judgment
    absolute_by_basis: dict[tuple[str, str], CurrentAbsoluteJudgment] = field(
        default_factory=dict
    )
    absolute_current_by_task: dict[str, CurrentAbsoluteJudgment] = field(
        default_factory=dict
    )
    judgment_index: dict[str, GoldLedgerRecord] = field(default_factory=dict)

    def current_question_for_case(self, case_id: str) -> CurrentQuestionCheck | None:
        task_id = question_check_task_id(
            campaign_id=self.campaign_id, case_id=case_id
        )
        return self.question_by_task.get(task_id)

    def question_active_accept_or_edit(self, case_id: str) -> CurrentQuestionCheck | None:
        current = self.current_question_for_case(case_id)
        if current is None:
            return None
        if current.decision is QuestionCheckDecision.REJECT:
            return None
        return current

    def current_absolute_for_task(
        self, task_id: str, *, query_fingerprint: str
    ) -> CurrentAbsoluteJudgment | None:
        return self.absolute_by_basis.get((task_id, query_fingerprint))


def fold_effective_state(
    *,
    campaign_id: str,
    baseline: GoldAuthoringRun,
    records: list[GoldLedgerRecord],
) -> EffectiveCampaignState:
    """Fold ledger in sequence order; fail closed on integrity violations."""
    state = EffectiveCampaignState(
        campaign_id=campaign_id,
        baseline=baseline,
        records=list(records),
        cases_by_id={case.draft_case_id: case for case in baseline.cases},
    )
    seen_judgment_ids: set[str] = set()
    # Per-task current QC judgment_id
    qc_current_id: dict[str, str] = {}
    # Per (task_id, query_fp) current absolute judgment_id
    abs_current_id: dict[tuple[str, str], str] = {}

    for record in records:
        if record.judgment_id in seen_judgment_ids:
            raise GoldLabError(
                "effective_state_duplicate_judgment_id",
                f"duplicate judgment_id: {record.judgment_id}",
            )
        seen_judgment_ids.add(record.judgment_id)
        state.judgment_index[record.judgment_id] = record

        if record.record_type is GoldLedgerRecordType.QUESTION_CHECK:
            _fold_question_check(
                state,
                record,
                qc_current_id=qc_current_id,
            )
        elif record.record_type is GoldLedgerRecordType.ABSOLUTE_RELEVANCE:
            _fold_absolute(
                state,
                record,
                qc_current_id=qc_current_id,
                abs_current_id=abs_current_id,
            )
        elif record.record_type is GoldLedgerRecordType.AUXILIARY_PREFERENCE:
            # Non-canonical; no effective-state chain.
            continue
        else:
            raise GoldLabError(
                "effective_state_unknown_record_type",
                f"unknown record_type: {record.record_type}",
            )

    _rebuild_absolute_current_by_task(state)
    return state


def _fold_question_check(
    state: EffectiveCampaignState,
    record: GoldLedgerRecord,
    *,
    qc_current_id: dict[str, str],
) -> None:
    case = state.cases_by_id.get(record.case_id)
    if case is None or not is_reviewable_case(case):
        raise GoldLabError(
            "effective_state_qc_non_reviewable",
            f"Question Check for non-reviewable case: {record.case_id}",
        )
    expected_task = question_check_task_id(
        campaign_id=state.campaign_id, case_id=record.case_id
    )
    if record.task_id != expected_task:
        raise GoldLabError(
            "effective_state_task_mismatch",
            "Question Check task_id mismatch",
        )

    try:
        raw_payload = QuestionCheckPayload.model_validate(record.payload)
    except Exception as exc:
        raise GoldLabError(
            "effective_state_qc_payload_invalid",
            f"invalid Question Check payload: {exc}",
        ) from exc

    if raw_payload.decision is QuestionCheckDecision.EDIT:
        payload = canonicalize_question_check_payload(
            record.payload, case=case
        )
    else:
        payload = raw_payload

    expected_fp = question_check_query_fingerprint(payload, case)
    if record.query_fingerprint != expected_fp:
        raise GoldLabError(
            "effective_state_qc_fingerprint_mismatch",
            "Question Check query_fingerprint disagrees with decision",
        )

    _validate_supersession(
        record,
        current_id=qc_current_id.get(record.task_id),
        known=state.judgment_index,
        expected_task_id=record.task_id,
        scope_label="question_check",
    )

    effective = _effective_values_from_qc(payload, case)
    current = CurrentQuestionCheck(
        record=record,
        payload=payload,
        decision=payload.decision,
        effective_query=effective["effective_query"],
        effective_category=effective["effective_category"],
        effective_tags=list(effective["effective_tags"]),
        query_fingerprint=expected_fp,
    )
    state.question_by_task[record.task_id] = current
    qc_current_id[record.task_id] = record.judgment_id


def _effective_values_from_qc(
    payload: QuestionCheckPayload, case: SilverCase
) -> dict[str, Any]:
    if payload.decision is QuestionCheckDecision.ACCEPT:
        return proposal_effective_values(case)
    if payload.decision is QuestionCheckDecision.EDIT:
        return {
            "effective_query": payload.effective_query,
            "effective_category": payload.effective_category,
            "effective_tags": list(payload.effective_tags or []),
        }
    return {
        "effective_query": None,
        "effective_category": None,
        "effective_tags": [],
    }


def _fold_absolute(
    state: EffectiveCampaignState,
    record: GoldLedgerRecord,
    *,
    qc_current_id: dict[str, str],
    abs_current_id: dict[tuple[str, str], str],
) -> None:
    case = state.cases_by_id.get(record.case_id)
    if case is None or not is_reviewable_case(case):
        raise GoldLabError(
            "effective_state_absolute_non_reviewable",
            f"absolute judgment for non-reviewable case: {record.case_id}",
        )
    if record.candidate_chunk_id is None:
        raise GoldLabError(
            "effective_state_absolute_missing_candidate",
            "absolute record missing candidate_chunk_id",
        )
    expected_task = absolute_relevance_task_id(
        campaign_id=state.campaign_id,
        case_id=record.case_id,
        candidate_chunk_id=record.candidate_chunk_id,
    )
    if record.task_id != expected_task:
        raise GoldLabError(
            "effective_state_task_mismatch",
            "absolute task_id mismatch",
        )
    if record.query_fingerprint is None:
        raise GoldLabError(
            "effective_state_absolute_null_fingerprint",
            "absolute record query_fingerprint must not be null",
        )

    try:
        payload = AbsoluteRelevancePayload.model_validate(record.payload)
    except Exception as exc:
        raise GoldLabError(
            "effective_state_absolute_payload_invalid",
            f"invalid absolute payload: {exc}",
        ) from exc

    # Event-time validity: QC must be accept/edit with matching fingerprint NOW
    # (at this ledger sequence — i.e. after prior folds in this walk).
    qc_task = question_check_task_id(
        campaign_id=state.campaign_id, case_id=record.case_id
    )
    qc_current = state.question_by_task.get(qc_task)
    if qc_current is None or qc_current.decision is QuestionCheckDecision.REJECT:
        raise GoldLabError(
            "effective_state_absolute_inactive_question",
            "absolute judgment committed while question task inactive",
        )
    if qc_current.query_fingerprint != record.query_fingerprint:
        raise GoldLabError(
            "effective_state_absolute_query_mismatch",
            "absolute query_fingerprint != then-current effective query",
        )

    basis = (record.task_id, record.query_fingerprint)
    _validate_supersession(
        record,
        current_id=abs_current_id.get(basis),
        known=state.judgment_index,
        expected_task_id=record.task_id,
        scope_label="absolute_relevance",
        expected_query_fingerprint=record.query_fingerprint,
    )

    judgment = CurrentAbsoluteJudgment(
        record=record,
        relevance=int(payload.relevance),
        query_fingerprint=record.query_fingerprint,
    )
    state.absolute_by_basis[basis] = judgment
    abs_current_id[basis] = record.judgment_id


def _validate_supersession(
    record: GoldLedgerRecord,
    *,
    current_id: str | None,
    known: dict[str, GoldLedgerRecord],
    expected_task_id: str,
    scope_label: str,
    expected_query_fingerprint: str | None = None,
) -> None:
    supersedes = record.supersedes_judgment_id
    if current_id is None:
        if supersedes is not None:
            raise GoldLabError(
                "effective_state_supersession_invalid",
                f"{scope_label}: first judgment must not supersede",
            )
        return
    if supersedes is None:
        raise GoldLabError(
            "effective_state_supersession_branch",
            f"{scope_label}: correction must supersede current judgment",
        )
    if supersedes not in known:
        raise GoldLabError(
            "effective_state_supersession_unknown",
            f"{scope_label}: unknown superseded judgment_id",
        )
    target = known[supersedes]
    if target.task_id != expected_task_id:
        raise GoldLabError(
            "effective_state_cross_task_supersession",
            f"{scope_label}: cross-task supersession",
        )
    if (
        expected_query_fingerprint is not None
        and target.record_type is GoldLedgerRecordType.ABSOLUTE_RELEVANCE
        and target.query_fingerprint != expected_query_fingerprint
    ):
        raise GoldLabError(
            "effective_state_cross_basis_supersession",
            f"{scope_label}: cross-query-basis supersession",
        )
    if supersedes != current_id:
        raise GoldLabError(
            "effective_state_supersession_non_current",
            f"{scope_label}: superseding non-current judgment",
        )


def _rebuild_absolute_current_by_task(state: EffectiveCampaignState) -> None:
    """Expose at most one current absolute per task under current QC query basis."""
    state.absolute_current_by_task.clear()
    for case in state.baseline.cases:
        if not is_reviewable_case(case):
            continue
        qc = state.current_question_for_case(case.draft_case_id)
        if qc is None or qc.decision is QuestionCheckDecision.REJECT:
            continue
        if qc.query_fingerprint is None:
            continue
        for candidate in case.candidates:
            task_id = absolute_relevance_task_id(
                campaign_id=state.campaign_id,
                case_id=case.draft_case_id,
                candidate_chunk_id=candidate.chunk_id,
            )
            current = state.absolute_by_basis.get((task_id, qc.query_fingerprint))
            if current is not None:
                state.absolute_current_by_task[task_id] = current
