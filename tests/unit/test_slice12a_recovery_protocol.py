"""Slice 12A — project-owned recovery protocol contracts (no LangGraph/providers)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from offline_rag.recovery import (
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
    RecoveryTerminalOutcomeV1,
    apply_recovery_event,
    build_initial_recovery_state,
    build_recovery_state_hash,
    recovery_semantic_equal,
    replay_recovery_events,
    sufficiency_ref_from_decision,
    validate_recovery_state,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sufficient(*, empty: bool = False, units: int = 1):
    return sufficiency_ref_from_decision(
        policy_contract="sufficiency-v1",
        policy_version="1",
        sufficient=True,
        triggered_gates=[],
        empty_context=empty,
        evidence_unit_count=units,
    )


def _insufficient(*, gate: str = "empty_context_v1"):
    return sufficiency_ref_from_decision(
        policy_contract="sufficiency-v1",
        policy_version="1",
        sufficient=False,
        triggered_gates=[gate],
        empty_context=True,
        evidence_unit_count=0,
    )


def _diag(**kwargs) -> RecoveryDiagnosticsV1:
    return RecoveryDiagnosticsV1(
        evidence_unit_count=kwargs.get("evidence_unit_count", 0),
        stop_reason=kwargs.get("stop_reason", AssemblyStopReasonV1.EMPTY_CONTEXT),
        **{
            key: value
            for key, value in kwargs.items()
            if key not in {"evidence_unit_count", "stop_reason"}
        },
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
    initial = build_initial_recovery_state(original_query="q")
    terminal = apply_recovery_event(
        initial,
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


def test_initial_insufficient_recovery_eligible_path() -> None:
    initial = build_initial_recovery_state(original_query="q")
    eligible = apply_recovery_event(
        initial,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
            diagnostics=_diag(),
        ),
    )
    assert eligible.phase == RecoveryPhaseV1.RECOVERY_ELIGIBLE
    assert eligible.terminal_outcome is None
    assert eligible.attempts[0].sufficiency.sufficient is False
    assert eligible.attempts[0].attempt_role == RECOVERY_ATTEMPT_ROLE_INITIAL


def test_legal_recovery_attempt_representation() -> None:
    """12A may represent attempt 1 in fixtures without invoking a rewriter."""
    state = build_initial_recovery_state(original_query="original")
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="rewritten for recovery",
        ),
    )
    assert state.phase == RecoveryPhaseV1.RECOVERY_ATTEMPT_PENDING
    assert state.current_attempt_number == 1
    assert state.current_attempt_role == RECOVERY_ATTEMPT_ROLE_RECOVERY
    assert state.original_query == "original"
    assert state.active_retrieval_query == "rewritten for recovery"
    assert len(state.attempts) == 1  # attempt 1 not yet recorded until sufficiency


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


def test_recovery_failure_terminal() -> None:
    state = build_initial_recovery_state(original_query="q")
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    terminal = apply_recovery_event(
        state,
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


def test_original_query_immutability() -> None:
    state = build_initial_recovery_state(original_query="immutable")
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
            prepared_retrieval_query="other",
        ),
    )
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
    state = build_initial_recovery_state(original_query="o")
    state = apply_recovery_event(
        state,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    gap = state.model_copy(
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
                failure_reason=RecoveryFailureReasonV1.PROTOCOL_VIOLATION,
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

    eligible = apply_recovery_event(
        initial,
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
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
    eligible = apply_recovery_event(
        build_initial_recovery_state(original_query="orig"),
        RecoveryEventV1(
            kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
            sufficiency=_insufficient(),
        ),
    )
    mutated = eligible.model_copy(update={"active_retrieval_query": "sneaky"})
    with pytest.raises(RecoveryProtocolError) as exc:
        validate_recovery_state(mutated)
    assert exc.value.code == RecoveryErrorCodeV1.ACTIVE_QUERY_MUTATION


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

    # Package import surface must not pull graph/runtime orchestration.
    mod = importlib.import_module("offline_rag.recovery")
    assert not hasattr(mod, "LangGraph")
    assert "rewriter" not in dir(mod)
    assert "retrieve" not in dir(mod)


def test_package_has_no_langgraph_dependency() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "langgraph" not in pyproject.lower()
    assert "langchain" not in pyproject.lower()
