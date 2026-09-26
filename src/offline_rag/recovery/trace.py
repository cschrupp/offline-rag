"""Typed 12B recovery runtime trace (separate from accepted 12A state schema)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from offline_rag.domain.types import NonNegativeInt
from offline_rag.recovery.contracts import (
    RecoveryFailureReasonV1,
    RecoveryStateV1,
    RecoverySufficiencyDecisionRefV1,
    RecoveryTerminalOutcomeV1,
)
from offline_rag.recovery.lineage import RecoveryLineageV1
from offline_rag.recovery.replay import build_recovery_state_hash
from offline_rag.recovery.rewrite_contracts import RecoveryRewriteProvenanceV1
from offline_rag.sufficiency.contracts import ExactNonBlankStr


class RecoveryRuntimeTraceV1(BaseModel):
    """Auditable recovery execution trace. No secrets."""

    model_config = ConfigDict(extra="forbid")

    schema_version: ExactNonBlankStr = "recovery-runtime-trace-v1"
    recovery_state_hash: ExactNonBlankStr
    original_query: ExactNonBlankStr
    active_retrieval_query: ExactNonBlankStr
    rewriter_contract: ExactNonBlankStr | None = None
    prompt_contract: ExactNonBlankStr | None = None
    response_contract: ExactNonBlankStr | None = None
    rewriter_config_hash: ExactNonBlankStr | None = None
    provider: ExactNonBlankStr | None = None
    normalized_endpoint: ExactNonBlankStr | None = None
    model: ExactNonBlankStr | None = None
    rewrite_call_count: NonNegativeInt = 0
    recovery_retrieval_attempt_count: NonNegativeInt = 0
    initial_sufficiency: RecoverySufficiencyDecisionRefV1 | None = None
    recovery_sufficiency: RecoverySufficiencyDecisionRefV1 | None = None
    initial_lineage: RecoveryLineageV1 | None = None
    recovery_lineage: RecoveryLineageV1 | None = None
    terminal_outcome: RecoveryTerminalOutcomeV1 | None = None
    failure_reason: RecoveryFailureReasonV1 | None = None
    rewrite_provenance: RecoveryRewriteProvenanceV1 | None = None

    def to_diagnostics_block(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        # Defense in depth: never emit secret-like keys.
        for key in list(payload):
            if "api_key" in key or "authorization" in key or "password" in key:
                del payload[key]
        return payload


def build_runtime_trace(
    *,
    state: RecoveryStateV1,
    rewrite_call_count: int,
    recovery_retrieval_attempt_count: int,
    initial_lineage: RecoveryLineageV1 | None = None,
    recovery_lineage: RecoveryLineageV1 | None = None,
    rewrite_provenance: RecoveryRewriteProvenanceV1 | None = None,
    recovery_sufficiency: RecoverySufficiencyDecisionRefV1 | None = None,
) -> RecoveryRuntimeTraceV1:
    initial_sufficiency = (
        state.attempts[0].sufficiency if state.attempts else state.current_sufficiency
    )
    return RecoveryRuntimeTraceV1(
        recovery_state_hash=build_recovery_state_hash(state),
        original_query=state.original_query,
        active_retrieval_query=state.active_retrieval_query,
        rewriter_contract=(
            None if rewrite_provenance is None else rewrite_provenance.adapter_contract
        ),
        prompt_contract=(
            None if rewrite_provenance is None else rewrite_provenance.prompt_contract
        ),
        response_contract=(
            None if rewrite_provenance is None else rewrite_provenance.output_contract
        ),
        rewriter_config_hash=(
            None
            if rewrite_provenance is None
            else rewrite_provenance.rewriter_config_hash
        ),
        provider=None if rewrite_provenance is None else rewrite_provenance.provider,
        normalized_endpoint=(
            None
            if rewrite_provenance is None
            else rewrite_provenance.normalized_endpoint
        ),
        model=None if rewrite_provenance is None else rewrite_provenance.model,
        rewrite_call_count=rewrite_call_count,
        recovery_retrieval_attempt_count=recovery_retrieval_attempt_count,
        initial_sufficiency=initial_sufficiency,
        recovery_sufficiency=recovery_sufficiency,
        initial_lineage=initial_lineage,
        recovery_lineage=recovery_lineage,
        terminal_outcome=state.terminal_outcome,
        failure_reason=state.failure_reason,
        rewrite_provenance=rewrite_provenance,
    )
