"""Project-owned recovery coordinator (Slice 12B). Owns no generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.recovery.contracts import (
    RecoveryDiagnosticsV1,
    RecoveryEventKindV1,
    RecoveryEventV1,
    RecoveryFailureReasonV1,
    RecoveryPhaseV1,
    RecoveryStateV1,
    RecoveryTerminalOutcomeV1,
)
from offline_rag.recovery.diagnostics_adapter import (
    adapt_context_to_recovery_diagnostics,
)
from offline_rag.recovery.lineage import (
    RecoveryLineageV1,
    extract_recovery_lineage,
    lineage_stack_equal,
)
from offline_rag.recovery.protocol import (
    apply_recovery_event,
    build_initial_recovery_state,
    sufficiency_ref_from_decision,
)
from offline_rag.recovery.rewrite_contracts import (
    RecoveryRewriteError,
    RecoveryRewriteInputV1,
    RecoveryRewriteProvenanceV1,
    RecoveryRewriter,
)
from offline_rag.recovery.rewrite_provenance import (
    build_recovery_rewrite_attempt_provenance,
)
from offline_rag.recovery.rewrite_provider import OpenAICompatibleRecoveryRewriter
from offline_rag.recovery.trace import RecoveryRuntimeTraceV1, build_runtime_trace
from offline_rag.sufficiency.policy import (
    SufficiencyPolicyDecisionV1,
    evaluate_runtime_sufficiency,
)


class RecoveryRuntimeError(RuntimeError):
    """Auditable recovery operational failure (before generation)."""

    def __init__(
        self,
        message: str,
        *,
        state: RecoveryStateV1,
        trace: RecoveryRuntimeTraceV1,
        failure_reason: RecoveryFailureReasonV1,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.trace = trace
        self.failure_reason = failure_reason


@dataclass(frozen=True)
class RecoveryCoordinatorResult:
    """Outcome of maybe-running bounded recovery."""

    recovery_invoked: bool
    context: HybridRerankContextResult
    sufficiency: SufficiencyPolicyDecisionV1
    state: RecoveryStateV1 | None
    trace: RecoveryRuntimeTraceV1 | None
    rewrite_call_count: int
    recovery_retrieval_attempt_count: int


class RecoveryCoordinator:
    """Execute rewrite + one recovery retrieval against RecoveryProtocol."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        context_assembler: HybridRerankContextAssembler,
        rewriter: RecoveryRewriter | None = None,
    ) -> None:
        self.settings = settings
        self._assembler = context_assembler
        self._owned_rewriter = rewriter is None
        self._rewriter = rewriter

    def close(self) -> None:
        if self._owned_rewriter and self._rewriter is not None:
            close = getattr(self._rewriter, "close", None)
            if callable(close):
                close()

    def _get_rewriter(self) -> RecoveryRewriter:
        if self._rewriter is None:
            self._rewriter = OpenAICompatibleRecoveryRewriter(self.settings)
        return self._rewriter

    def _fail_preparation(
        self,
        state: RecoveryStateV1,
        message: str,
        *,
        initial_lineage: RecoveryLineageV1 | None,
        rewrite_provenance: RecoveryRewriteProvenanceV1 | None,
        rewrite_call_count: int,
        cause: BaseException | None = None,
    ) -> NoReturn:
        if state.phase != RecoveryPhaseV1.TERMINAL:
            state = apply_recovery_event(
                state,
                RecoveryEventV1(
                    kind=RecoveryEventKindV1.FAIL_RECOVERY,
                    failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
                ),
            )
        trace = build_runtime_trace(
            state=state,
            rewrite_call_count=rewrite_call_count,
            recovery_retrieval_attempt_count=0,
            initial_lineage=initial_lineage,
            rewrite_provenance=rewrite_provenance,
        )
        error = RecoveryRuntimeError(
            message,
            state=state,
            trace=trace,
            failure_reason=RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED,
        )
        if cause is not None:
            raise error from cause
        raise error

    def _fail_execution(
        self,
        state: RecoveryStateV1,
        message: str,
        *,
        initial_lineage: RecoveryLineageV1 | None,
        recovery_lineage: RecoveryLineageV1 | None,
        rewrite_provenance: RecoveryRewriteProvenanceV1 | None,
        cause: BaseException | None = None,
    ) -> NoReturn:
        if state.phase != RecoveryPhaseV1.TERMINAL:
            state = apply_recovery_event(
                state,
                RecoveryEventV1(
                    kind=RecoveryEventKindV1.FAIL_RECOVERY,
                    failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
                ),
            )
        trace = build_runtime_trace(
            state=state,
            rewrite_call_count=1,
            recovery_retrieval_attempt_count=1,
            initial_lineage=initial_lineage,
            recovery_lineage=recovery_lineage,
            rewrite_provenance=rewrite_provenance,
        )
        error = RecoveryRuntimeError(
            message,
            state=state,
            trace=trace,
            failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
        )
        if cause is not None:
            raise error from cause
        raise error

    def run(
        self,
        *,
        original_query: str,
        corpus_name: str,
        initial_context: HybridRerankContextResult,
        initial_sufficiency: SufficiencyPolicyDecisionV1,
    ) -> RecoveryCoordinatorResult:
        """Run recovery when enabled and initially insufficient.

        When recovery is disabled or initial evidence is sufficient, returns the
        initial context unchanged without rewriter / second assembly calls.
        """
        if initial_sufficiency.sufficient:
            return RecoveryCoordinatorResult(
                recovery_invoked=False,
                context=initial_context,
                sufficiency=initial_sufficiency,
                state=None,
                trace=None,
                rewrite_call_count=0,
                recovery_retrieval_attempt_count=0,
            )
        if not self.settings.retrieval_recovery.enabled:
            return RecoveryCoordinatorResult(
                recovery_invoked=False,
                context=initial_context,
                sufficiency=initial_sufficiency,
                state=None,
                trace=None,
                rewrite_call_count=0,
                recovery_retrieval_attempt_count=0,
            )
        if self.settings.retrieval_recovery.max_retries != 1:
            raise ValueError("retrieval_recovery.max_retries must be exactly 1")

        if initial_context.query != original_query:
            raise ValueError("initial context query must equal original_query")

        # Record attempt 0/initial insufficiency before any preparation work that
        # may fail, so every recovery-preparation failure is terminal/auditable.
        state = build_initial_recovery_state(original_query=original_query)
        sufficiency_ref = sufficiency_ref_from_decision(
            sufficient=False,
            evidence_unit_count=0,
        )
        diagnostics: RecoveryDiagnosticsV1 | None
        try:
            diagnostics = adapt_context_to_recovery_diagnostics(initial_context)
        except Exception as exc:  # noqa: BLE001 — fail closed into terminal prep error
            state = apply_recovery_event(
                state,
                RecoveryEventV1(
                    kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
                    sufficiency=sufficiency_ref,
                    diagnostics=None,
                ),
            )
            self._fail_preparation(
                state,
                f"recovery diagnostics adaptation failed: {exc}",
                initial_lineage=None,
                rewrite_provenance=None,
                rewrite_call_count=0,
                cause=exc,
            )

        state = apply_recovery_event(
            state,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.RECORD_INITIAL_SUFFICIENCY,
                sufficiency=sufficiency_ref,
                diagnostics=diagnostics,
            ),
        )

        initial_lineage: RecoveryLineageV1 | None = None
        try:
            initial_lineage = extract_recovery_lineage(initial_context)
        except ValueError as exc:
            self._fail_preparation(
                state,
                str(exc),
                initial_lineage=None,
                rewrite_provenance=None,
                rewrite_call_count=0,
                cause=exc,
            )

        rewrite_provenance: RecoveryRewriteProvenanceV1 | None = None
        try:
            rewrite_provenance = build_recovery_rewrite_attempt_provenance(
                self.settings, rewrite_call_count=1
            )
        except Exception as exc:  # noqa: BLE001 — fail closed into terminal prep error
            self._fail_preparation(
                state,
                f"recovery rewriter provenance build failed: {exc}",
                initial_lineage=initial_lineage,
                rewrite_provenance=None,
                rewrite_call_count=0,
                cause=exc,
            )

        rewrite_input = RecoveryRewriteInputV1(
            original_query=original_query,
            sufficiency=sufficiency_ref,
            diagnostics=diagnostics,
        )

        try:
            rewriter = self._get_rewriter()
        except RecoveryRewriteError as exc:
            provenance = exc.provenance or rewrite_provenance
            self._fail_preparation(
                state,
                str(exc),
                initial_lineage=initial_lineage,
                rewrite_provenance=provenance,
                rewrite_call_count=0,
                cause=exc,
            )
        except Exception as exc:  # noqa: BLE001 — constructor fail-closed
            self._fail_preparation(
                state,
                f"recovery rewriter construction failed: {exc}",
                initial_lineage=initial_lineage,
                rewrite_provenance=rewrite_provenance,
                rewrite_call_count=0,
                cause=exc,
            )

        try:
            rewrite_output, rewrite_provenance = rewriter.rewrite(rewrite_input)
        except RecoveryRewriteError as exc:
            provenance = exc.provenance or rewrite_provenance
            self._fail_preparation(
                state,
                str(exc),
                initial_lineage=initial_lineage,
                rewrite_provenance=provenance,
                rewrite_call_count=1,
                cause=exc,
            )
        except Exception as exc:  # noqa: BLE001 — provider surface fail-closed
            self._fail_preparation(
                state,
                f"recovery rewrite failed: {exc}",
                initial_lineage=initial_lineage,
                rewrite_provenance=rewrite_provenance,
                rewrite_call_count=1,
                cause=exc,
            )

        state = apply_recovery_event(
            state,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.PREPARE_RECOVERY_QUERY,
                prepared_retrieval_query=rewrite_output.rewritten_query,
            ),
        )

        try:
            recovered = self._assembler.assemble(
                query=state.active_retrieval_query,
                corpus_name=corpus_name,
            )
        except HybridRerankContextError as exc:
            self._fail_execution(
                state,
                str(exc),
                initial_lineage=initial_lineage,
                recovery_lineage=None,
                rewrite_provenance=rewrite_provenance,
                cause=exc,
            )
        except Exception as exc:  # noqa: BLE001 — assemble surface fail-closed
            self._fail_execution(
                state,
                f"recovery retrieval/context failed: {exc}",
                initial_lineage=initial_lineage,
                recovery_lineage=None,
                rewrite_provenance=rewrite_provenance,
                cause=exc,
            )

        if recovered.query != state.active_retrieval_query:
            self._fail_execution(
                state,
                "recovery context query must equal active_retrieval_query",
                initial_lineage=initial_lineage,
                recovery_lineage=None,
                rewrite_provenance=rewrite_provenance,
            )

        try:
            recovery_lineage = extract_recovery_lineage(recovered)
        except ValueError as exc:
            self._fail_execution(
                state,
                str(exc),
                initial_lineage=initial_lineage,
                recovery_lineage=None,
                rewrite_provenance=rewrite_provenance,
                cause=exc,
            )

        if not lineage_stack_equal(initial_lineage, recovery_lineage):
            self._fail_execution(
                state,
                "recovery attempt lineage differs from initial attempt",
                initial_lineage=initial_lineage,
                recovery_lineage=recovery_lineage,
                rewrite_provenance=rewrite_provenance,
            )

        recovery_decision = evaluate_runtime_sufficiency(
            self.settings, evidence_units=recovered.evidence_units
        )
        recovery_ref = sufficiency_ref_from_decision(
            sufficient=recovery_decision.sufficient,
            evidence_unit_count=recovery_decision.evidence_unit_count,
        )
        recovery_diag = adapt_context_to_recovery_diagnostics(recovered)
        state = apply_recovery_event(
            state,
            RecoveryEventV1(
                kind=RecoveryEventKindV1.RECORD_RECOVERY_SUFFICIENCY,
                sufficiency=recovery_ref,
                diagnostics=recovery_diag,
            ),
        )
        trace = build_runtime_trace(
            state=state,
            rewrite_call_count=1,
            recovery_retrieval_attempt_count=1,
            initial_lineage=initial_lineage,
            recovery_lineage=recovery_lineage,
            rewrite_provenance=rewrite_provenance,
            recovery_sufficiency=recovery_ref,
        )
        return RecoveryCoordinatorResult(
            recovery_invoked=True,
            context=recovered,
            sufficiency=recovery_decision,
            state=state,
            trace=trace,
            rewrite_call_count=1,
            recovery_retrieval_attempt_count=1,
        )


def assert_recovered_terminal(state: RecoveryStateV1 | None) -> None:
    if state is None:
        return
    if state.terminal_outcome not in {
        RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT,
        RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY,
    }:
        raise RecoveryRuntimeError(
            f"unexpected recovery terminal: {state.terminal_outcome}",
            state=state,
            trace=build_runtime_trace(
                state=state,
                rewrite_call_count=0,
                recovery_retrieval_attempt_count=0,
            ),
            failure_reason=RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED,
        )
