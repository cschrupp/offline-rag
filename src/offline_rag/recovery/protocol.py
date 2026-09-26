"""Fail-closed validation and transition application for recovery-protocol-v1."""

from __future__ import annotations

from offline_rag.recovery.contracts import (
    MAX_ATTEMPT_NUMBER_V1,
    RECOVERY_ATTEMPT_ROLE_INITIAL,
    RECOVERY_ATTEMPT_ROLE_RECOVERY,
    RecoveryAttemptRecordV1,
    RecoveryErrorCodeV1,
    RecoveryErrorDetailsV1,
    RecoveryEventKindV1,
    RecoveryEventV1,
    RecoveryPhaseV1,
    RecoveryProtocolError,
    RecoveryStateV1,
    RecoverySufficiencyDecisionRefV1,
    RecoveryTerminalOutcomeV1,
)


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

    _validate_attempts(state)
    _validate_phase_consistency(state)


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


def _validate_phase_consistency(state: RecoveryStateV1) -> None:
    if state.phase == RecoveryPhaseV1.TERMINAL:
        if state.terminal_outcome is None:
            _fail(
                RecoveryErrorCodeV1.INVALID_STATE,
                "terminal phase requires terminal_outcome",
                field_name="terminal_outcome",
            )
        if (
            state.terminal_outcome
            == RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
            and state.failure_reason is None
        ):
            _fail(
                RecoveryErrorCodeV1.INVALID_STATE,
                "recovery failure terminal requires failure_reason",
                field_name="failure_reason",
            )
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
    if event.sufficiency is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "record_initial_sufficiency requires sufficiency",
            field_name="sufficiency",
        )
    if event.prepared_retrieval_query is not None or event.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "record_initial_sufficiency forbids prepared query / failure_reason",
        )

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
    if event.prepared_retrieval_query is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "prepare_recovery_query requires prepared_retrieval_query",
            field_name="prepared_retrieval_query",
        )
    if event.sufficiency is not None or event.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "prepare_recovery_query forbids sufficiency / failure_reason",
        )
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
    if event.sufficiency is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "record_recovery_sufficiency requires sufficiency",
            field_name="sufficiency",
        )
    if event.prepared_retrieval_query is not None or event.failure_reason is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "record_recovery_sufficiency forbids prepared query / failure_reason",
        )
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
    if event.failure_reason is None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "fail_recovery requires failure_reason",
            field_name="failure_reason",
        )
    if event.sufficiency is not None or event.prepared_retrieval_query is not None:
        _fail(
            RecoveryErrorCodeV1.INVALID_EVENT,
            "fail_recovery forbids sufficiency / prepared_retrieval_query",
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
    policy_contract: str,
    policy_version: str,
    sufficient: bool,
    triggered_gates: list[str],
    empty_context: bool,
    evidence_unit_count: int,
) -> RecoverySufficiencyDecisionRefV1:
    """Build a recovery sufficiency projection from scalar fields (tests/fixtures)."""
    return RecoverySufficiencyDecisionRefV1(
        policy_contract=policy_contract,
        policy_version=policy_version,
        sufficient=sufficient,
        triggered_gates=list(triggered_gates),
        empty_context=empty_context,
        evidence_unit_count=evidence_unit_count,
    )
