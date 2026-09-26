"""Project-owned recovery protocol contracts (Slice 12A).

Authoritative recovery semantics live here. LangGraph is not a dependency and
must not define recovery meaning (OD-12-3).
"""

from offline_rag.recovery.contracts import (
    CONTEXT_STOP_REASONS_V1,
    MAX_ATTEMPT_NUMBER_V1,
    MAX_RECOVERY_RETRIES_V1,
    RECOVERY_ATTEMPT_ROLE_INITIAL,
    RECOVERY_ATTEMPT_ROLE_RECOVERY,
    RECOVERY_POLICY_VERSION_V1,
    RECOVERY_PROTOCOL_V1,
    RECOVERY_STATE_V1,
    AssemblyStopReasonV1,
    RecoveryAttemptRecordV1,
    RecoveryDiagnosticsV1,
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
from offline_rag.recovery.protocol import (
    apply_recovery_event,
    build_initial_recovery_state,
    sufficiency_ref_from_decision,
    validate_recovery_state,
    validate_sufficiency_ref,
)
from offline_rag.recovery.replay import (
    build_recovery_semantic_payload,
    build_recovery_state_hash,
    recovery_semantic_equal,
    replay_recovery_events,
)

__all__ = [
    "CONTEXT_STOP_REASONS_V1",
    "MAX_ATTEMPT_NUMBER_V1",
    "MAX_RECOVERY_RETRIES_V1",
    "RECOVERY_ATTEMPT_ROLE_INITIAL",
    "RECOVERY_ATTEMPT_ROLE_RECOVERY",
    "RECOVERY_POLICY_VERSION_V1",
    "RECOVERY_PROTOCOL_V1",
    "RECOVERY_STATE_V1",
    "AssemblyStopReasonV1",
    "RecoveryAttemptRecordV1",
    "RecoveryDiagnosticsV1",
    "RecoveryErrorCodeV1",
    "RecoveryErrorDetailsV1",
    "RecoveryEventKindV1",
    "RecoveryEventV1",
    "RecoveryFailureReasonV1",
    "RecoveryPhaseV1",
    "RecoveryProtocolError",
    "RecoveryStateV1",
    "RecoverySufficiencyDecisionRefV1",
    "RecoveryTerminalOutcomeV1",
    "apply_recovery_event",
    "build_initial_recovery_state",
    "build_recovery_semantic_payload",
    "build_recovery_state_hash",
    "recovery_semantic_equal",
    "replay_recovery_events",
    "sufficiency_ref_from_decision",
    "validate_recovery_state",
    "validate_sufficiency_ref",
]
