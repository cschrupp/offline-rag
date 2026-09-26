"""Project-owned recovery protocol (Slice 12A/12B).

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
from offline_rag.recovery.coordinator import (
    RecoveryCoordinator,
    RecoveryCoordinatorResult,
    RecoveryRuntimeError,
)
from offline_rag.recovery.diagnostics_adapter import (
    adapt_context_to_recovery_diagnostics,
)
from offline_rag.recovery.fake import FakeRecoveryRewriter
from offline_rag.recovery.lineage import (
    RecoveryLineageV1,
    extract_recovery_lineage,
    lineage_stack_equal,
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
from offline_rag.recovery.rewrite_config_hash import (
    build_recovery_rewriter_config_hash,
    build_recovery_rewriter_semantic_payload,
)
from offline_rag.recovery.rewrite_contracts import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
    RECOVERY_REWRITER_ADAPTER_V1,
    RecoveryRewriteError,
    RecoveryRewriteInputV1,
    RecoveryRewriteOutputV1,
    RecoveryRewriteProvenanceV1,
)
from offline_rag.recovery.rewrite_provider import (
    OpenAICompatibleRecoveryRewriter,
    parse_recovery_rewrite_output,
)
from offline_rag.recovery.trace import RecoveryRuntimeTraceV1

__all__ = [
    "CONTEXT_STOP_REASONS_V1",
    "MAX_ATTEMPT_NUMBER_V1",
    "MAX_RECOVERY_RETRIES_V1",
    "RECOVERY_ATTEMPT_ROLE_INITIAL",
    "RECOVERY_ATTEMPT_ROLE_RECOVERY",
    "RECOVERY_POLICY_VERSION_V1",
    "RECOVERY_PROTOCOL_V1",
    "RECOVERY_REWRITER_ADAPTER_V1",
    "RECOVERY_REWRITE_OUTPUT_V1",
    "RECOVERY_REWRITE_PROMPT_V1",
    "RECOVERY_STATE_V1",
    "AssemblyStopReasonV1",
    "FakeRecoveryRewriter",
    "OpenAICompatibleRecoveryRewriter",
    "RecoveryAttemptRecordV1",
    "RecoveryCoordinator",
    "RecoveryCoordinatorResult",
    "RecoveryDiagnosticsV1",
    "RecoveryErrorCodeV1",
    "RecoveryErrorDetailsV1",
    "RecoveryEventKindV1",
    "RecoveryEventV1",
    "RecoveryFailureReasonV1",
    "RecoveryLineageV1",
    "RecoveryPhaseV1",
    "RecoveryProtocolError",
    "RecoveryRewriteError",
    "RecoveryRewriteInputV1",
    "RecoveryRewriteOutputV1",
    "RecoveryRewriteProvenanceV1",
    "RecoveryRuntimeError",
    "RecoveryRuntimeTraceV1",
    "RecoveryStateV1",
    "RecoverySufficiencyDecisionRefV1",
    "RecoveryTerminalOutcomeV1",
    "adapt_context_to_recovery_diagnostics",
    "apply_recovery_event",
    "build_initial_recovery_state",
    "build_recovery_rewriter_config_hash",
    "build_recovery_rewriter_semantic_payload",
    "build_recovery_semantic_payload",
    "build_recovery_state_hash",
    "extract_recovery_lineage",
    "lineage_stack_equal",
    "parse_recovery_rewrite_output",
    "recovery_semantic_equal",
    "replay_recovery_events",
    "sufficiency_ref_from_decision",
    "validate_recovery_state",
    "validate_sufficiency_ref",
]
