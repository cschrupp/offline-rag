"""Slice 12A — project-owned recovery protocol contracts (no LangGraph/providers)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.context.contracts import (
    STOP_ANCHOR_WOULD_NOT_FIT,
    STOP_BUDGET_EXHAUSTED,
    STOP_CHILD_WOULD_NOT_FIT,
    STOP_COMPLETED,
    STOP_NO_ANCHORS,
    STOP_PARENT_CLIPPED_TO_BUDGET,
)
from offline_rag.recovery import (
    CONTEXT_STOP_REASONS_V1,
    RECOVERY_ATTEMPT_ROLE_INITIAL,
    RECOVERY_ATTEMPT_ROLE_RECOVERY,
    AssemblyStopReasonV1,
    RecoveryAttemptRecordV1,
    RecoveryDiagnosticsV1,
    RecoveryErrorCodeV1,
    RecoveryEventKindV1,
    RecoveryEventV1,
    RecoveryFailureReasonV1,
    RecoveryPhaseV1,
    RecoveryProtocolError,
    RecoveryStateV1,
    RecoverySufficiencyDecisionRefV1,
    RecoveryTerminalOutcomeV1,
    apply_recovery_event,
    build_initial_recovery_state,
    build_recovery_state_hash,
    recovery_semantic_equal,
    replay_recovery_events,
    sufficiency_ref_from_decision,
    validate_recovery_state,
)
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1, SUFFICIENCY_POLICY_V1

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sufficient(*, units: int = 1) -> RecoverySufficiencyDecisionRefV1:
    return sufficiency_ref_from_decision(sufficient=True, evidence_unit_count=units)


def _insufficient() -> RecoverySufficiencyDecisionRefV1:
    return sufficiency_ref_from_decision(sufficient=False)


def _diag(**kwargs) -> RecoveryDiagnosticsV1:
    return RecoveryDiagnosticsV1(
        evidence_unit_count=kwargs.get("evidence_unit_count", 0),
        stop_reason=kwargs.get("stop_reason", AssemblyStopReasonV1.NO_ANCHORS),
        **{
            key: value
            for key, value in kwargs.items()
            if key not in {"evidence_unit_count", "stop_reason"}
        },
    )


def _to_eligible(query: str = "q") -> RecoveryStateV1:
    return apply_recovery_event(
        build_initial_recovery_state(original_query=query),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )


def _to_pending(
    query: str = "q", *, prepared: str = "recovery query"
) -> RecoveryStateV1:
    return apply_recovery_event(
        _to_eligible(query),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query=prepared,
        ),
    )


def test_initial_state_construction() -> None:
    state = build_initial_recovery_state(
        original_query="what is max pressure?",
        case_id="case_1",
    )
    assert state.schema_version == "recovery-state-v1"
    assert state.protocol_contract == "recovery-protocol-v1"
    assert state.original_query == "what is max pressure?"
    assert state.active_retrieval_query == state.original_query
    assert state.current_attempt_number == 0
    assert state.current_attempt_role == RECOVERY_ATTEMPT_ROLE_INITIAL
    assert state.phase == RecoveryPhaseV1.AWAITING_INITIAL_SUFFICIENCY
    assert state.attempts == []
    assert state.terminal_outcome is None
    assert state.max_retries == 1


def test_initial_sufficient_terminal_path() -> None:
    terminal = apply_recovery_event(
        build_initial_recovery_state(original_query="q"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_sufficient(units=2),
            diagnostics=_diag(
                evidence_unit_count=2, stop_reason=AssemblyStopReasonV1.COMPLETED
            ),
        ),
    )
    assert terminal.phase == RecoveryPhaseV1.TERMINAL
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.INITIAL_EVIDENCE_SUFFICIENT
    )
    assert terminal.current_attempt_number == 0
    assert terminal.current_attempt_role == RECOVERY_ATTEMPT_ROLE_INITIAL
    assert terminal.active_retrieval_query == "q"
    assert len(terminal.attempts) == 1
    assert terminal.attempts[0].sufficiency.policy_version == "v1"


def test_initial_insufficient_recovery_eligible_path() -> None:
    eligible = _to_eligible()
    assert eligible.phase == RecoveryPhaseV1.RECOVERY_ELIGIBLE
    assert eligible.terminal_outcome is None
    assert eligible.attempts[0].sufficiency.sufficient is False
    assert eligible.attempts[0].attempt_role == RECOVERY_ATTEMPT_ROLE_INITIAL
    assert eligible.attempts[0].sufficiency.triggered_gates == [EMPTY_CONTEXT_GATE_V1]


def test_legal_recovery_attempt_representation() -> None:
    state = _to_pending("original", prepared="rewritten for recovery")
    assert state.phase == RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING
    assert state.current_attempt_number == 1
    assert state.current_attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY
    assert state.original_query == "original"
    assert state.active_retrieval_query == "rewritten for recovery"
    assert len(state.attempts) == 1


def test_recovered_sufficient_terminal() -> None:
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="recovery query",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(units=3),
            diagnostics=_diag(
                evidence_unit_count=3, stop_reason=AssemblyStopReasonV1.COMPLETED
            ),
        ),
    ]
    terminal = replay_recovery_events(
        build_initial_recovery_state(original_query="orig"), events
    )
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT
    )
    assert len(terminal.attempts) == 2
    assert terminal.attempts[1].attempt_number == 1
    assert terminal.attempts[1].attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY


def test_recovered_insufficient_terminal() -> None:
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="recovery query",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    ]
    terminal = replay_recovery_events(
        build_initial_recovery_state(original_query="orig"), events
    )
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
    )


def test_recovery_failure_terminal_before_prepare() -> None:
    terminal = apply_recovery_event(
        _to_eligible(),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.FAIL_RECOVERY,
            failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
        ),
    )
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
    )
    assert terminal.failure_reason == RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED
    assert terminal.current_attempt_number == 0
    assert terminal.active_retrieval_query == "q"


def test_recovery_failure_terminal_after_prepare() -> None:
    terminal = apply_recovery_event(
        _to_pending(prepared="prepared q"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.FAIL_RECOVERY,
            failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
        ),
    )
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
    )
    assert terminal.failure_reason == RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED
    assert terminal.current_attempt_number == 1
    assert terminal.active_retrieval_query == "prepared q"


def test_recovery_execution_failed_allows_noop_prepared_query() -> None:
    """Preparation is evidenced by the transition, not by query string change."""
    original = "same query"
    pending = _to_pending(original, prepared=original)
    assert pending.active_retrieval_query == original
    assert pending.current_attempt_number == 1
    assert pending.current_attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY

    terminal = apply_recovery_event(
        pending,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.FAIL_RECOVERY,
            failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
        ),
    )
    assert terminal.phase == RecoveryPhaseV1.TERMINAL
    assert (
        terminal.terminal_outcome
        == RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
    )
    assert terminal.failure_reason == RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED
    assert terminal.current_attempt_number == 1
    assert terminal.current_attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY
    assert terminal.active_retrieval_query == original
    assert terminal.original_query == original


def test_original_query_immutability() -> None:
    state = _to_pending("immutable", prepared="other")
    assert state.original_query == "immutable"
    mutated = state.model_copy(update={"original_query": "changed"})
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(mutated)
    assert exc.value.code in {
        RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION,
        RecoveryErrorCodeV1.ORIGINAL_QUERY_MUTATION,
    }


def test_attempt_0_and_attempt_1_role_semantics() -> None:
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="r1",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    ]
    terminal = replay_recovery_events(
        build_initial_recovery_state(original_query="o"), events
    )
    assert terminal.attempts[0].attempt_number == 0
    assert terminal.attempts[0].attempt_role == RECOVERY_ATTEMPT_ROLE_INITIAL
    assert terminal.attempts[0].active_retrieval_query == "o"
    assert terminal.attempts[1].attempt_number == 1
    assert terminal.attempts[1].attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY


def test_no_attempt_2() -> None:
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="r1",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    ]
    terminal = replay_recovery_events(
        build_initial_recovery_state(original_query="o"), events
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            terminal,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
                prepared_retrieval_query="r2",
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.TERMINAL_STATE_TRANSITION

    bad = terminal.model_copy(
        update={
            "attempts": [
                *terminal.attempts,
                RecoveryAttemptRecordV1(
                    attempt_number=2,
                    attempt_role=RECOVERY_ATTEMPT_ROLE_RECOVERY,
                    active_retrieval_query="r2",
                    sufficiency=_insufficient(),
                ),
            ],
            "phase": RecoveryPhaseV1.TERMINAL,
            "terminal_outcome": (
                RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
            ),
            "current_attempt_number": 2,
            "current_attempt_role": RECOVERY_ATTEMPT_ROLE_RECOVERY,
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc2:
        validate_recovery_state(bad)
    assert exc2.value.code == RecoveryErrorCodeV1.SECOND_RECOVERY_ATTEMPT


def test_contiguous_unique_attempts() -> None:
    gap = _to_eligible("o").model_copy(
        update={
            "attempts": [
                RecoveryAttemptRecordV1(
                    attempt_number=0,
                    attempt_role=RECOVERY_ATTEMPT_ROLE_INITIAL,
                    active_retrieval_query="o",
                    sufficiency=_insufficient(),
                ),
                RecoveryAttemptRecordV1(
                    attempt_number=2,
                    attempt_role=RECOVERY_ATTEMPT_ROLE_RECOVERY,
                    active_retrieval_query="x",
                    sufficiency=_insufficient(),
                ),
            ],
            "phase": RecoveryPhaseV1.TERMINAL,
            "terminal_outcome": (
                RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
            ),
            "current_attempt_number": 2,
            "current_attempt_role": RECOVERY_ATTEMPT_ROLE_RECOVERY,
            "current_sufficiency": _insufficient(),
            "active_retrieval_query": "x",
            "failure_reason": None,
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(gap)
    assert exc.value.code in {
        RecoveryErrorCodeV1.NON_CONTIGUOUS_ATTEMPTS,
        RecoveryErrorCodeV1.SECOND_RECOVERY_ATTEMPT,
    }


def test_no_recovery_after_terminal() -> None:
    terminal = apply_recovery_event(
        build_initial_recovery_state(original_query="q"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            terminal,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.FAIL_RECOVERY,
                failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.TERMINAL_STATE_TRANSITION


def test_recovery_cannot_begin_from_initially_sufficient_state() -> None:
    terminal = apply_recovery_event(
        build_initial_recovery_state(original_query="q"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            terminal,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
                prepared_retrieval_query="nope",
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.TERMINAL_STATE_TRANSITION


def test_deterministic_replay_identical_semantic_state() -> None:
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
            diagnostics=_diag(anchor_count=0),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="recovery q",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(units=1),
        ),
    ]
    initial_a = build_initial_recovery_state(original_query="same", case_id="c1")
    initial_b = build_initial_recovery_state(original_query="same", case_id="c1")
    left = replay_recovery_events(initial_a, events)
    right = replay_recovery_events(initial_b, events)
    assert recovery_semantic_equal(left, right)
    assert build_recovery_state_hash(left) == build_recovery_state_hash(right)
    assert build_recovery_state_hash(left).startswith("recov_")


def test_malformed_transition_sequence_fails_closed() -> None:
    initial = build_initial_recovery_state(original_query="q")
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            initial,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
                prepared_retrieval_query="too early",
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.INVALID_TRANSITION

    eligible = _to_eligible()
    with pytest.raises(RecoveryProtocolError) as exc2:
        apply_recovery_event(
            eligible,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
                sufficiency=_sufficient(),
            ),
        )
    assert exc2.value.code == RecoveryErrorCodeV1.INVALID_TRANSITION


def test_diagnostics_forbid_corpus_free_text() -> None:
    with pytest.raises(ValidationError):
        RecoveryDiagnosticsV1.model_validate(
            {"evidence_text": "chunk body from corpus"}
        )
    with pytest.raises(ValidationError):
        RecoveryStateV1.model_validate(
            {
                "original_query": "q",
                "active_retrieval_query": "q",
                "current_attempt_number": 0,
                "current_attempt_role": "initial",
                "phase": "awaiting_initial_sufficiency",
                "extra_evidence": "not allowed",
            }
        )


def test_active_query_mutation_outside_prepare_fails() -> None:
    mutated = _to_eligible("orig").model_copy(
        update={"active_retrieval_query": "sneaky"}
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(mutated)
    assert exc.value.code == RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION


def test_foreign_sufficiency_policy_contract_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            policy_contract="other-policy",  # type: ignore[arg-type]
            policy_version="v1",
            sufficient=True,
            triggered_gates=[],
            empty_context=False,
            evidence_unit_count=1,
        )


def test_wrong_policy_version_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            policy_contract=SUFFICIENCY_POLICY_V1,
            policy_version="1",  # type: ignore[arg-type]
            sufficient=True,
            triggered_gates=[],
            empty_context=False,
            evidence_unit_count=1,
        )


def test_sufficient_plus_empty_context_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            sufficient=True,
            triggered_gates=[],
            empty_context=True,
            evidence_unit_count=1,
        )


def test_insufficient_plus_nonzero_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            sufficient=False,
            triggered_gates=[EMPTY_CONTEXT_GATE_V1],
            empty_context=True,
            evidence_unit_count=2,
        )


def test_wrong_or_missing_triggered_gate_rejected() -> None:
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            sufficient=False,
            triggered_gates=[],
            empty_context=True,
            evidence_unit_count=0,
        )
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            sufficient=False,
            triggered_gates=["score_gate_v1"],
            empty_context=True,
            evidence_unit_count=0,
        )
    with pytest.raises(ValidationError):
        RecoverySufficiencyDecisionRefV1(
            sufficient=True,
            triggered_gates=[EMPTY_CONTEXT_GATE_V1],
            empty_context=False,
            evidence_unit_count=1,
        )


def test_success_terminal_carrying_failure_reason_rejected() -> None:
    terminal = apply_recovery_event(
        build_initial_recovery_state(original_query="q"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    )
    bad = terminal.model_copy(
        update={"failure_reason": RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED}
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(bad)
    assert exc.value.code == RecoveryErrorCodeV1.INCONSISTENT_TERMINAL


def test_initial_sufficient_terminal_with_insufficient_attempt_rejected() -> None:
    eligible = _to_eligible()
    bad = eligible.model_copy(
        update={
            "phase": RecoveryPhaseV1.TERMINAL,
            "terminal_outcome": RecoveryTerminalOutcomeV1.INITIAL_EVIDENCE_SUFFICIENT,
            "failure_reason": None,
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(bad)
    assert exc.value.code == RecoveryErrorCodeV1.INCONSISTENT_TERMINAL


def test_recovered_sufficient_terminal_with_insufficient_attempt1_rejected() -> None:
    terminal = apply_recovery_event(
        _to_pending(prepared="r1"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    bad = terminal.model_copy(
        update={
            "terminal_outcome": RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(bad)
    assert exc.value.code == RecoveryErrorCodeV1.INCONSISTENT_TERMINAL


def test_bounded_insufficient_terminal_with_sufficient_attempt1_rejected() -> None:
    terminal = apply_recovery_event(
        _to_pending(prepared="r1"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    )
    bad = terminal.model_copy(
        update={
            "terminal_outcome": (
                RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
            )
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(bad)
    assert exc.value.code == RecoveryErrorCodeV1.INCONSISTENT_TERMINAL


def test_current_attempt_metadata_inconsistent_with_terminal_rejected() -> None:
    terminal = apply_recovery_event(
        _to_pending(prepared="r1"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    )
    bad = terminal.model_copy(
        update={
            "current_attempt_number": 0,
            "current_attempt_role": RECOVERY_ATTEMPT_ROLE_INITIAL,
        }
    )
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(bad)
    assert exc.value.code == RecoveryErrorCodeV1.INCONSISTENT_TERMINAL


def test_all_authoritative_context_stop_reasons_accepted() -> None:
    expected = {
        STOP_COMPLETED,
        STOP_BUDGET_EXHAUSTED,
        STOP_CHILD_WOULD_NOT_FIT,
        STOP_PARENT_CLIPPED_TO_BUDGET,
        STOP_NO_ANCHORS,
        STOP_ANCHOR_WOULD_NOT_FIT,
    }
    assert CONTEXT_STOP_REASONS_V1 == expected
    assert {member.value for member in AssemblyStopReasonV1} == expected
    for reason in AssemblyStopReasonV1:
        diag = RecoveryDiagnosticsV1(stop_reason=reason)
        assert diag.stop_reason == reason
    with pytest.raises(ValidationError):
        RecoveryDiagnosticsV1.model_validate({"stop_reason": "empty_context"})


def test_irrelevant_event_diagnostics_rejected() -> None:
    eligible = _to_eligible()
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            eligible,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
                prepared_retrieval_query="r1",
                diagnostics=_diag(),
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.INVALID_EVENT

    with pytest.raises(RecoveryProtocolError) as exc2:
        apply_recovery_event(
            eligible,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.FAIL_RECOVERY,
                failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
                diagnostics=_diag(),
            ),
        )
    assert exc2.value.code == RecoveryErrorCodeV1.INVALID_EVENT


def test_protocol_violation_not_accepted_as_fail_recovery() -> None:
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            _to_eligible(),
            RecoveryEventV1(
                kind=RecoveryEventKindV1.FAIL_RECOVERY,
                failure_reason=RecoveryFailureReasonV1.PROTOCOL_VIOLATION,
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.INVALID_EVENT


def test_fail_recovery_reason_must_match_phase() -> None:
    with pytest.raises(RecoveryProtocolError) as exc:
        apply_recovery_event(
            _to_eligible(),
            RecoveryEventV1(
                kind=RecoveryEventKindV1.FAIL_RECOVERY,
                failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
            ),
        )
    assert exc.value.code == RecoveryErrorCodeV1.INVALID_EVENT

    with pytest.raises(RecoveryProtocolError) as exc2:
        apply_recovery_event(
            _to_pending(),
            RecoveryEventV1(
                kind=RecoveryEventKindV1.FAIL_RECOVERY,
                failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
            ),
        )
    assert exc2.value.code == RecoveryErrorCodeV1.INVALID_EVENT


def test_no_langgraph_retrieval_generation_rewriter_invocation() -> None:
    forbidden = (
        "langgraph",
        "langchain",
        "offline_rag.generation",
        "offline_rag.dense",
        "offline_rag.lexical",
        "offline_rag.hybrid",
        "offline_rag.rerank",
        "httpx",
        "ollama",
    )
    before = {name for name in sys.modules if any(f in name for f in forbidden)}
    events = [
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="hand-built recovery query",
        ),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
            sufficiency=_sufficient(),
        ),
    ]
    replay_recovery_events(build_initial_recovery_state(original_query="q"), events)
    after = {name for name in sys.modules if any(f in name for f in forbidden)}
    assert after == before

    recovery_src = REPO_ROOT / "src" / "offline_rag" / "recovery"
    import_patterns = (
        "import langgraph",
        "from langgraph",
        "import langchain",
        "from langchain",
    )
    for path in recovery_src.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for pattern in import_patterns:
            assert pattern not in text, f"{path.name} must not import {pattern}"

    mod = importlib.import_module("offline_rag.recovery")
    assert not hasattr(mod, "LangGraph")
    assert "rewriter" not in dir(mod)
    assert "retrieve" not in dir(mod)


def test_package_has_no_langgraph_dependency() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "langgraph" not in pyproject.lower()
    assert "langchain" not in pyproject.lower()
