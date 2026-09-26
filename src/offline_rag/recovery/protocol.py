"""Fail-closed validation and transition application for recovery-protocol-v1."""

from __future__ import annotations

from offline_rag.recovery.contracts import (
    MAX_ATTEMPT_NUMBER_V1,
    RECOVERY_ATTEMPT_ROLE_INITIAL,
    RECOVERY_ATTEMPT_ROLE_RECOVERY,
    RECOVERY_POLICY_VERSION_V1,
    RecoveryAttemptRecordV1,
    RecoveryErrorCodeV1,
    RecoveryErrorDetailsV1,
    RecoveryEventKindV1,
    RecoveryEventV1,
    RecoveryFailureReasonV1,
    RecoveryPhaseV1,
    RecoveryProtocolError,
    RecoveryStateV1,
    RecoverySufficiencyDecisionRefV1,
    RecoveryTerminalOutcomeV1,
)
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1, SUFFICIENCY_POLICY_V1


def build_initial_recovery_state(
    *,
    original_query: str,
    case_id: str | None = None,
) -> RecoveryStateV1:
    """Construct pre-sufficiency attempt-0 state (active query == original)."""
    state = RecoveryStateV1(
        case_id=case_id,
        original_query=original_query,
        active_retrieval_query=original_query,
        current_attempt_number=0,
        current_attempt_role=RECOVERY_ATTEMPT_ROLE_INITIAL,
        phase=RecoveryPhaseV1.AWAITING_INITIAL_SUFFICIENCY,
        attempts=[],
        current_sufficiency=None,
        terminal_outcome=None,
        failure_reason=None,
    )
    validate_recovery_state(state)
    return state


def validate_recovery_state(state: RecoveryStateV1) -> None:
    """Fail closed on any invariant violation (no repair)."""
    if state.schema_version != "recovery-state-v1":
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "unsupported recovery schema_version",
            field_name="schema_version",
            actual=state.schema_version,
        )
    if state.protocol_contract != "recovery-protocol-v1":
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "unsupported recovery protocol_contract",
            field_name="protocol_contract",
            actual=state.protocol_contract,
        )
    if state.max_retries != 1:
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "max_retries must be 1 under the one-retry contract",
            field_name="max_retries",
            expected=1,
            actual=state.max_retries,
        )
    if state.current_attempt_number > MAX_ATTEMPT_NUMBER_V1:
        _fail(
            RecoveryErrorCodeV1.SECOND_RECOVERY_ATTEMPT,
            "attempt number exceeds one-retry contract",
            field_name="current_attempt_number",
            actual=state.current_attempt_number,
        )

    for attempt in state.attempts:
        validate_sufficiency_ref(attempt.sufficiency)
    if state.current_sufficiency is not None:
        validate_sufficiency_ref(state.current_sufficiency)

    _validate_attempts(state)
    _validate_phase_consistency(state)


def validate_sufficiency_ref(ref: RecoverySufficiencyDecisionRefV1) -> None:
    """Authoritative fail-closed check for sufficiency-v1 projections."""
    if ref.policy_contract != SUFFICIENCY_POLICY_V1:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "recovery sufficiency policy_contract must be sufficiency-v1",
            field_name="policy_contract",
            expected=SUFFICIENCY_POLICY_V1,
            actual=ref.policy_contract,
        )
    if ref.policy_version != RECOVERY_POLICY_VERSION_V1:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "recovery sufficiency policy_version must be v1",
            field_name="policy_version",
            expected=RECOVERY_POLICY_VERSION_V1,
            actual=ref.policy_version,
        )
    if ref.sufficient:
        if ref.empty_context:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
                "sufficient=true requires empty_context=false",
                field_name="empty_context",
                expected=False,
                actual=True,
            )
        if ref.evidence_unit_count <= 0:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
                "sufficient=true requires evidence_unit_count > 0",
                field_name="evidence_unit_count",
                actual=ref.evidence_unit_count,
            )
        if ref.triggered_gates:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
                "sufficient=true requires triggered_gates == []",
                field_name="triggered_gates",
            )
        return

    if not ref.empty_context:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "sufficient=false requires empty_context=true",
            field_name="empty_context",
            expected=True,
            actual=False,
        )
    if ref.evidence_unit_count != 0:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "sufficient=false requires evidence_unit_count == 0",
            field_name="evidence_unit_count",
            expected=0,
            actual=ref.evidence_unit_count,
        )
    if list(ref.triggered_gates) != [EMPTY_CONTEXT_GATE_V1]:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "sufficient=false requires triggered_gates == [empty_context_v1]",
            field_name="triggered_gates",
            expected=EMPTY_CONTEXT_GATE_V1,
        )


def _validate_attempts(state: RecoveryStateV1) -> None:
    seen: set[int] = set()
    for index, attempt in enumerate(state.attempts):
        if attempt.attempt_number in seen:
            _fail(
                RecoveryErrorCodeV1.DUPLICATE_ATTEMPT,
                f"duplicate attempt_number {attempt.attempt_number}",
                field_name="attempts.attempt_number",
                actual=attempt.attempt_number,
            )
        seen.add(attempt.attempt_number)
        if attempt.attempt_number != index:
            _fail(
                RecoveryErrorCodeV1.NON_CONTIGUOUS_ATTEMPTS,
                "attempt numbers must be contiguous from 0",
                field_name="attempts.attempt_number",
                expected=index,
                actual=attempt.attempt_number,
            )
        if attempt.attempt_number > MAX_ATTEMPT_NUMBER_V1:
            _fail(
                RecoveryErrorCodeV1.SECOND_RECOVERY_ATTEMPT,
                "attempt number exceeds one-retry contract",
                field_name="attempts.attempt_number",
                actual=attempt.attempt_number,
            )
        expected_role = (
            RECOVERY_ATTEMPT_ROLE_INITIAL
            if attempt.attempt_number == 0
            else RECOVERY_ATTEMPT_ROLE_RECOVERY
        )
        if attempt.attempt_role != expected_role:
            _fail(
                RecoveryErrorCodeV1.INVALID_ATTEMPT_ROLE,
                "attempt role does not match attempt number",
                field_name="attempts.attempt_role",
                expected=expected_role,
                actual=attempt.attempt_role,
            )
        if attempt.attempt_number == 0 and attempt.active_retrieval_query != (
            state.original_query
        ):
            _fail(
                RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION,
                "attempt 0 active_retrieval_query must equal original_query",
                field_name="attempts.active_retrieval_query",
            )

    if (
        state.attempts
        and state.current_sufficiency is not None
        and state.phase != RecoveryPhaseV1.AWAITING_INITIAL_SUFFICIENCY
    ):
        last = state.attempts[-1]
        if state.current_sufficiency.model_dump(
            mode="json"
        ) != last.sufficiency.model_dump(mode="json"):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
                "current_sufficiency must match latest attempt record",
                field_name="current_sufficiency",
            )


def _sufficiency_equal(
    left: RecoverySufficiencyDecisionRefV1 | None,
    right: RecoverySufficiencyDecisionRefV1 | None,
) -> bool:
    if left is None or right is None:
        return left is right
    return left.model_dump(mode="json") == right.model_dump(mode="json")


def _validate_phase_consistency(state: RecoveryStateV1) -> None:
    if state.phase == RecoveryPhaseV1.TERMINAL:
        _validate_terminal_state(state)
        return

    if state.terminal_outcome is not None or state.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "non-terminal phase must not carry terminal_outcome/failure_reason",
            field_name="phase",
            actual=state.phase.value,
        )

    if state.phase == RecoveryPhaseV1.AWAITING_INITIAL_SUFFICIENCY:
        if state.attempts:
            _fail(
                RecoveryErrorCodeV1.INVALID_STATE,
                "awaiting_initial_sufficiency must have empty attempts",
                field_name="attempts",
            )
        if state.active_retrieval_query != state.original_query:
            _fail(
                RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION,
                "active_retrieval_query must equal original_query before recovery",
                field_name="active_retrieval_query",
            )
        if state.current_attempt_number != 0 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_INITIAL
        ):
            _fail(
                RecoveryErrorCodeV1.INVALID_ATTEMPT_NUMBER,
                "awaiting initial sufficiency requires attempt 0/initial",
            )
        return

    if state.phase == RecoveryPhaseV1.RECOVERY_ELIGIBLE:
        if len(state.attempts) != 1 or state.attempts[0].sufficiency.sufficient:
            _fail(
                RecoveryErrorCodeV1.RECOVERY_WITHOUT_INITIAL_INSUFFICIENCY,
                "recovery_eligible requires exactly one insufficient initial attempt",
            )
        if state.active_retrieval_query != state.original_query:
            _fail(
                RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION,
                "active_retrieval_query may change only via prepare_recovery_query",
                field_name="active_retrieval_query",
            )
        if state.current_attempt_number != 0 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_INITIAL
        ):
            _fail(
                RecoveryErrorCodeV1.INVALID_ATTEMPT_NUMBER,
                "recovery_eligible requires attempt 0/initial until prepare",
            )
        return

    if state.phase == RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING:
        if len(state.attempts) != 1 or state.attempts[0].sufficiency.sufficient:
            _fail(
                RecoveryErrorCodeV1.RECOVERY_WITHOUT_INITIAL_INSUFFICIENCY,
                "recovery preparation requires insufficient initial attempt",
            )
        if state.current_attempt_number != 1 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_RECOVERY
        ):
            _fail(
                RecoveryErrorCodeV1.INVALID_ATTEMPT_NUMBER,
                "prepared recovery requires current attempt 1/recovery",
            )
        return

    _fail(
        RecoveryErrorCodeV1.INVALID_STATE,
        f"unsupported recovery phase: {state.phase}",
        field_name="phase",
        actual=state.phase.value,
    )


def _validate_terminal_state(state: RecoveryStateV1) -> None:
    if state.terminal_outcome is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "terminal phase requires terminal_outcome",
            field_name="terminal_outcome",
        )
    outcome = state.terminal_outcome

    if outcome == RecoveryTerminalOutcomeV1.INITIAL_EVIDENCE_SUFFICIENT:
        if state.failure_reason is not None:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient forbids failure_reason",
                field_name="failure_reason",
            )
        if len(state.attempts) != 1:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires exactly one attempt",
                field_name="attempts",
                expected=1,
                actual=len(state.attempts),
            )
        attempt0 = state.attempts[0]
        if (
            attempt0.attempt_number != 0
            or attempt0.attempt_role != RECOVERY_ATTEMPT_ROLE_INITIAL
        ):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires attempt 0/initial",
            )
        if not attempt0.sufficiency.sufficient:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires sufficient attempt 0",
                field_name="attempts[0].sufficiency.sufficient",
                expected=True,
                actual=False,
            )
        if state.current_attempt_number != 0 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_INITIAL
        ):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires current attempt 0/initial",
            )
        if state.active_retrieval_query != state.original_query:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires active query == original",
                field_name="active_retrieval_query",
            )
        if not _sufficiency_equal(state.current_sufficiency, attempt0.sufficiency):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "initial_evidence_sufficient requires current_sufficiency == attempt 0",
                field_name="current_sufficiency",
            )
        return

    if outcome == RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT:
        _validate_two_attempt_recovery_terminal(
            state,
            attempt1_must_be_sufficient=True,
            outcome_label="recovered_evidence_sufficient",
        )
        return

    if outcome == RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY:
        _validate_two_attempt_recovery_terminal(
            state,
            attempt1_must_be_sufficient=False,
            outcome_label="insufficient_after_bounded_recovery",
        )
        return

    if outcome == RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED:
        _validate_failure_terminal(state)
        return

    _fail(
        RecoveryErrorCodeV1.INVALID_STATE,
        f"unsupported terminal_outcome: {outcome}",
        field_name="terminal_outcome",
        actual=outcome.value,
    )


def _validate_two_attempt_recovery_terminal(
    state: RecoveryStateV1,
    *,
    attempt1_must_be_sufficient: bool,
    outcome_label: str,
) -> None:
    if state.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} forbids failure_reason",
            field_name="failure_reason",
        )
    if len(state.attempts) != 2:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires exactly two attempts",
            field_name="attempts",
            expected=2,
            actual=len(state.attempts),
        )
    attempt0, attempt1 = state.attempts
    if (
        attempt0.attempt_number != 0
        or attempt0.attempt_role != RECOVERY_ATTEMPT_ROLE_INITIAL
        or attempt0.sufficiency.sufficient
    ):
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires insufficient attempt 0/initial",
        )
    if (
        attempt1.attempt_number != 1
        or attempt1.attempt_role != RECOVERY_ATTEMPT_ROLE_RECOVERY
    ):
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires attempt 1/recovery",
        )
    if attempt1.sufficiency.sufficient != attempt1_must_be_sufficient:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires attempt 1 sufficient="
            f"{attempt1_must_be_sufficient}",
            field_name="attempts[1].sufficiency.sufficient",
            expected=attempt1_must_be_sufficient,
            actual=attempt1.sufficiency.sufficient,
        )
    if state.current_attempt_number != 1 or state.current_attempt_role != (
        RECOVERY_ATTEMPT_ROLE_RECOVERY
    ):
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires current attempt 1/recovery",
        )
    if state.active_retrieval_query != attempt1.active_retrieval_query:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires active query == attempt 1 query",
            field_name="active_retrieval_query",
        )
    if not _sufficiency_equal(state.current_sufficiency, attempt1.sufficiency):
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            f"{outcome_label} requires current_sufficiency == attempt 1",
            field_name="current_sufficiency",
        )


def _validate_failure_terminal(state: RecoveryStateV1) -> None:
    if state.failure_reason is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "recovery failure terminal requires failure_reason",
            field_name="failure_reason",
        )
    if state.failure_reason == RecoveryFailureReasonV1.PROTOCOL_VIOLATION:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            "protocol_violation is not a valid normal failure terminal reason",
            field_name="failure_reason",
        )
    if len(state.attempts) != 1 or state.attempts[0].sufficiency.sufficient:
        _fail(
            RecoveryErrorCodeV1.RECOVERY_WITHOUT_INITIAL_INSUFFICIENCY,
            "recovery failure terminal requires exactly one insufficient initial attempt",
        )
    if not _sufficiency_equal(state.current_sufficiency, state.attempts[0].sufficiency):
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
            "recovery failure terminal requires current_sufficiency == attempt 0",
            field_name="current_sufficiency",
        )

    if state.failure_reason == RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED:
        if state.current_attempt_number != 0 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_INITIAL
        ):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "rewrite_preparation_failed requires current attempt 0/initial",
            )
        if state.active_retrieval_query != state.original_query:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "rewrite_preparation_failed requires active query == original",
                field_name="active_retrieval_query",
            )
        return

    if state.failure_reason == RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED:
        if state.current_attempt_number != 1 or state.current_attempt_role != (
            RECOVERY_ATTEMPT_ROLE_RECOVERY
        ):
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "recovery_execution_failed requires current attempt 1/recovery",
            )
        if state.active_retrieval_query == state.original_query:
            _fail(
                RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
                "recovery_execution_failed requires prepared recovery active query",
                field_name="active_retrieval_query",
            )
        return

    _fail(
        RecoveryErrorCodeV1.INCONSISTENT_TERMINAL,
        f"unsupported failure_reason for recovery failure terminal: {state.failure_reason}",
        field_name="failure_reason",
        actual=state.failure_reason.value,
    )


def apply_recovery_event(
    state: RecoveryStateV1, event: RecoveryEventV1
) -> RecoveryStateV1:
    """Apply one deterministic event; fail closed on illegal transitions."""
    validate_recovery_state(state)
    if state.phase == RecoveryPhaseV1.TERMINAL:
        _fail(
            RecoveryErrorCodeV1.TERMINAL_STATE_TRANSITION,
            "cannot transition a terminal recovery state",
            field_name="phase",
        )

    if event.kind == RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY:
        return _apply_initial_sufficiency(state, event)
    if event.kind == RecoveryEventKindV1.PREPARE_RECOVERY_QUERY:
        return _apply_prepare_recovery_query(state, event)
    if event.kind == RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY:
        return _apply_recovery_sufficiency(state, event)
    if event.kind == RecoveryEventKindV1.FAIL_RECOVERY:
        return _apply_fail_recovery(state, event)
    _fail(
        RecoveryErrorCodeV1.INVALID_EVENT,
        f"unsupported recovery event kind: {event.kind}",
        field_name="kind",
        actual=str(event.kind),
    )


def _require_event_fields(
    event: RecoveryEventV1,
    *,
    require_sufficiency: bool,
    allow_diagnostics: bool,
    require_prepared_query: bool,
    require_failure_reason: bool,
) -> None:
    if require_sufficiency:
        if event.sufficiency is None:
            _fail(
                RecoveryErrorCodeV1.INVALID_EVENT,
                f"{event.kind.value} requires sufficiency",
                field_name="sufficiency",
            )
        validate_sufficiency_ref(event.sufficiency)
    elif event.sufficiency is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            f"{event.kind.value} forbids sufficiency",
            field_name="sufficiency",
        )

    if allow_diagnostics:
        pass
    elif event.diagnostics is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            f"{event.kind.value} forbids diagnostics",
            field_name="diagnostics",
        )

    if require_prepared_query:
        if event.prepared_retrieval_query is None:
            _fail(
                RecoveryErrorCodeV1.INVALID_EVENT,
                f"{event.kind.value} requires prepared_retrieval_query",
                field_name="prepared_retrieval_query",
            )
    elif event.prepared_retrieval_query is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            f"{event.kind.value} forbids prepared_retrieval_query",
            field_name="prepared_retrieval_query",
        )

    if require_failure_reason:
        if event.failure_reason is None:
            _fail(
                RecoveryErrorCodeV1.INVALID_EVENT,
                f"{event.kind.value} requires failure_reason",
                field_name="failure_reason",
            )
    elif event.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            f"{event.kind.value} forbids failure_reason",
            field_name="failure_reason",
        )


def _apply_initial_sufficiency(
    state: RecoveryStateV1, event: RecoveryEventV1
) -> RecoveryStateV1:
    if state.phase != RecoveryPhaseV1.AWAITING_INITIAL_SUFFICIENCY:
        _fail(
            RecoveryErrorCodeV1.INVALID_TRANSITION,
            "record_initial_sufficiency only valid from awaiting_initial_sufficiency",
            field_name="phase",
            actual=state.phase.value,
        )
    _require_event_fields(
        event,
        require_sufficiency=True,
        allow_diagnostics=True,
        require_prepared_query=False,
        require_failure_reason=False,
    )
    assert event.sufficiency is not None

    attempt = RecoveryAttemptRecordV1(
        attempt_number=0,
        attempt_role=RECOVERY_ATTEMPT_ROLE_INITIAL,
        active_retrieval_query=state.original_query,
        sufficiency=event.sufficiency,
        diagnostics=event.diagnostics,
    )
    if event.sufficiency.sufficient:
        next_state = state.model_copy(
            update={
                "attempts": [attempt],
                "current_sufficiency": event.sufficiency,
                "current_attempt_number": 0,
                "current_attempt_role": RECOVERY_ATTEMPT_ROLE_INITIAL,
                "active_retrieval_query": state.original_query,
                "phase": RecoveryPhaseV1.TERMINAL,
                "terminal_outcome": (
                    RecoveryTerminalOutcomeV1.INITIAL_EVIDENCE_SUFFICIENT
                ),
                "failure_reason": None,
            }
        )
    else:
        next_state = state.model_copy(
            update={
                "attempts": [attempt],
                "current_sufficiency": event.sufficiency,
                "current_attempt_number": 0,
                "current_attempt_role": RECOVERY_ATTEMPT_ROLE_INITIAL,
                "active_retrieval_query": state.original_query,
                "phase": RecoveryPhaseV1.RECOVERY_ELIGIBLE,
                "terminal_outcome": None,
                "failure_reason": None,
            }
        )
    validate_recovery_state(next_state)
    return next_state


def _apply_prepare_recovery_query(
    state: RecoveryStateV1, event: RecoveryEventV1
) -> RecoveryStateV1:
    if state.phase != RecoveryPhaseV1.RECOVERY_ELIGIBLE:
        _fail(
            RecoveryErrorCodeV1.INVALID_TRANSITION,
            "prepare_recovery_query only valid from recovery_eligible",
            field_name="phase",
            actual=state.phase.value,
        )
    _require_event_fields(
        event,
        require_sufficiency=False,
        allow_diagnostics=False,
        require_prepared_query=True,
        require_failure_reason=False,
    )
    assert event.prepared_retrieval_query is not None
    # 12A records a prepared query without invoking a rewriter/provider.
    next_state = state.model_copy(
        update={
            "active_retrieval_query": event.prepared_retrieval_query,
            "current_attempt_number": 1,
            "current_attempt_role": RECOVERY_ATTEMPT_ROLE_RECOVERY,
            "phase": RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING,
        }
    )
    validate_recovery_state(next_state)
    return next_state


def _apply_recovery_sufficiency(
    state: RecoveryStateV1, event: RecoveryEventV1
) -> RecoveryStateV1:
    if state.phase != RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING:
        _fail(
            RecoveryErrorCodeV1.INVALID_TRANSITION,
            "record_recovery_sufficiency only valid from recovery_attempt_pending",
            field_name="phase",
            actual=state.phase.value,
        )
    _require_event_fields(
        event,
        require_sufficiency=True,
        allow_diagnostics=True,
        require_prepared_query=False,
        require_failure_reason=False,
    )
    assert event.sufficiency is not None
    if len(state.attempts) != 1:
        _fail(
            RecoveryErrorCodeV1.INVALID_STATE,
            "recovery sufficiency requires exactly one prior attempt",
        )

    attempt = RecoveryAttemptRecordV1(
        attempt_number=1,
        attempt_role=RECOVERY_ATTEMPT_ROLE_RECOVERY,
        active_retrieval_query=state.active_retrieval_query,
        sufficiency=event.sufficiency,
        diagnostics=event.diagnostics,
    )
    if event.sufficiency.sufficient:
        outcome = RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT
    else:
        outcome = RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
    next_state = state.model_copy(
        update={
            "attempts": [*state.attempts, attempt],
            "current_sufficiency": event.sufficiency,
            "current_attempt_number": 1,
            "current_attempt_role": RECOVERY_ATTEMPT_ROLE_RECOVERY,
            "phase": RecoveryPhaseV1.TERMINAL,
            "terminal_outcome": outcome,
            "failure_reason": None,
        }
    )
    validate_recovery_state(next_state)
    return next_state


def _apply_fail_recovery(
    state: RecoveryStateV1, event: RecoveryEventV1
) -> RecoveryStateV1:
    if state.phase not in (
        RecoveryPhaseV1.RECOVERY_ELIGIBLE,
        RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING,
    ):
        _fail(
            RecoveryErrorCodeV1.INVALID_TRANSITION,
            "fail_recovery only valid after initial insufficiency",
            field_name="phase",
            actual=state.phase.value,
        )
    _require_event_fields(
        event,
        require_sufficiency=False,
        allow_diagnostics=False,
        require_prepared_query=False,
        require_failure_reason=True,
    )
    assert event.failure_reason is not None
    if event.failure_reason == RecoveryFailureReasonV1.PROTOCOL_VIOLATION:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "protocol_violation is not a valid FAIL_RECOVERY event reason",
            field_name="failure_reason",
        )
    if state.phase == RecoveryPhaseV1.RECOVERY_ELIGIBLE:
        if event.failure_reason != RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED:
            _fail(
                RecoveryErrorCodeV1.INVALID_EVENT,
                "fail_recovery from recovery_eligible requires rewrite_preparation_failed",
                field_name="failure_reason",
                expected=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED.value,
                actual=event.failure_reason.value,
            )
    elif event.failure_reason != RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "fail_recovery from recovery_attempt_pending requires recovery_execution_failed",
            field_name="failure_reason",
            expected=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED.value,
            actual=event.failure_reason.value,
        )

    next_state = state.model_copy(
        update={
            "phase": RecoveryPhaseV1.TERMINAL,
            "terminal_outcome": (
                RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
            ),
            "failure_reason": event.failure_reason,
        }
    )
    validate_recovery_state(next_state)
    return next_state


def _fail(
    code: RecoveryErrorCodeV1,
    message: str,
    *,
    field_name: str | None = None,
    expected: str | float | bool | None = None,
    actual: str | float | bool | None = None,
) -> None:
    raise RecoveryProtocolError(
        code,
        message,
        details=RecoveryErrorDetailsV1(
            field_name=field_name,
            expected=expected,
            actual=actual,
        ),
    )


def sufficiency_ref_from_decision(
    *,
    sufficient: bool,
    evidence_unit_count: int | None = None,
) -> RecoverySufficiencyDecisionRefV1:
    """Build a recovery sufficiency projection via the authoritative sufficiency-v1 path.

    Policy identity is frozen to sufficiency-v1 / v1. Derived empty_context /
    triggered_gates follow the accepted Slice-11 decision semantics.
    """
    if sufficient:
        units = 1 if evidence_unit_count is None else evidence_unit_count
        return RecoverySufficiencyDecisionRefV1(
            policy_contract=SUFFICIENCY_POLICY_V1,
            policy_version=RECOVERY_POLICY_VERSION_V1,
            sufficient=True,
            triggered_gates=[],
            empty_context=False,
            evidence_unit_count=units,
        )
    if evidence_unit_count is not None and evidence_unit_count != 0:
        _fail(
            RecoveryErrorCodeV1.INCONSISTENT_SUFFICIENCY,
            "insufficient recovery projection requires evidence_unit_count == 0",
            field_name="evidence_unit_count",
            expected=0,
            actual=evidence_unit_count,
        )
    return RecoverySufficiencyDecisionRefV1(
        policy_contract=SUFFICIENCY_POLICY_V1,
        policy_version=RECOVERY_POLICY_VERSION_V1,
        sufficient=False,
        triggered_gates=[EMPTY_CONTEXT_GATE_V1],
        empty_context=True,
        evidence_unit_count=0,
    )
