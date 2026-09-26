"""Deterministic recovery protocol replay (no providers / LangGraph)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from offline_rag.core.ids import canonical_config_hash
from offline_rag.recovery.contracts import RecoveryEventV1, RecoveryStateV1
from offline_rag.recovery.protocol import apply_recovery_event, validate_recovery_state


def build_recovery_semantic_payload(state: RecoveryStateV1) -> dict[str, Any]:
    """Allowlisted semantic surface for identity / replay equality."""
    return {
        "schema_version": state.schema_version,
        "protocol_contract": state.protocol_contract,
        "case_id": state.case_id,
        "original_query": state.original_query,
        "active_retrieval_query": state.active_retrieval_query,
        "current_attempt_number": state.current_attempt_number,
        "current_attempt_role": state.current_attempt_role,
        "max_retries": state.max_retries,
        "phase": state.phase.value,
        "attempts": [item.model_dump(mode="json") for item in state.attempts],
        "current_sufficiency": (
            None
            if state.current_sufficiency is None
            else state.current_sufficiency.model_dump(mode="json")
        ),
        "terminal_outcome": (
            None if state.terminal_outcome is None else state.terminal_outcome.value
        ),
        "failure_reason": (
            None if state.failure_reason is None else state.failure_reason.value
        ),
    }


def recovery_semantic_equal(left: RecoveryStateV1, right: RecoveryStateV1) -> bool:
    return build_recovery_semantic_payload(left) == build_recovery_semantic_payload(
        right
    )


def build_recovery_state_hash(state: RecoveryStateV1) -> str:
    """Content-addressed hash of the recovery semantic payload."""
    digest = canonical_config_hash(build_recovery_semantic_payload(state))
    return digest.replace("cfg_", "recov_", 1)


def replay_recovery_events(
    initial: RecoveryStateV1,
    events: Sequence[RecoveryEventV1],
) -> RecoveryStateV1:
    """Replay an ordered event sequence from a validated initial state.

    Does not call retrieval, generation, rewriter, LangGraph, or network I/O.
    """
    validate_recovery_state(initial)
    state = initial
    for event in events:
        state = apply_recovery_event(state, event)
    return state
