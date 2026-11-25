"""Conversation turn orchestration (A2-D05 / A2-D05b)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from offline_rag.app.conversation.prior_turns import PriorTurn, validate_prior_turns
from offline_rag.app.conversation.resolver import (
    RESOLVER_PROMPT_CONTRACT_ID,
    resolve_conversation_context,
)
from offline_rag.app.conversation.traces import (
    ConversationTraceRecord,
    ConversationTraceStore,
    allocate_conversation_trace_id,
)
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.operations import OperationHandle
from offline_rag.app.query import (
    _enrich_workspace_citations,
    _resolve_workspace_source_scope,
    normalize_product_question,
    run_bound_snapshot_query,
)
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.app.snapshot import PRODUCT_MODE_GROUNDED_V1, CorpusReadSnapshot
from offline_rag.app.traces import ProductTraceSourceScope
from offline_rag.app.workspace.models import (
    WorkspaceRecord,
    WorkspaceRevision,
    WorkspaceStatus,
)
from offline_rag.app.workspace.store import WorkspaceStore

logger = logging.getLogger(__name__)

ConversationSuccessStatus = Literal[
    "answered",
    "insufficient_evidence",
    "model_abstain",
    "clarification_required",
]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ConversationTurnResponse:
    workspace_id: str
    workspace_revision: WorkspaceRevision
    snapshot_id: str
    product_mode_id: str
    conversation_trace_id: str
    query_trace_id: str | None
    status: ConversationSuccessStatus
    abstention_reason: str | None
    question: str
    retrieval_question: str | None
    context_used: bool
    answer: str | None
    answer_blocks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    answer_origin: Literal["sources", "conversation"] = "sources"

    recovery_diagnostics: dict[str, int | bool] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_revision": self.workspace_revision,
            "snapshot_id": self.snapshot_id,
            "product_mode_id": self.product_mode_id,
            "conversation_trace_id": self.conversation_trace_id,
            "query_trace_id": self.query_trace_id,
            "status": self.status,
            "abstention_reason": self.abstention_reason,
            "question": self.question,
            "retrieval_question": self.retrieval_question,
            "context_used": self.context_used,
            "answer": self.answer,
            "answer_blocks": self.answer_blocks,
            "citations": self.citations,
            "answer_origin": self.answer_origin,
            **(
                {"recovery_diagnostics": self.recovery_diagnostics}
                if self.recovery_diagnostics is not None
                else {}
            ),
        }


def _commit_conversation_trace(
    store: ConversationTraceStore, record: ConversationTraceRecord
) -> None:
    try:
        store.commit(record)
    except AppError:
        logger.warning(
            "conversation trace persistence failed trace=%s",
            record.conversation_trace_id,
        )
        raise AppError(ErrorCode.INTERNAL_ERROR)
    except Exception as exc:
        logger.warning(
            "conversation trace persistence failed trace=%s",
            record.conversation_trace_id,
        )
        raise AppError(ErrorCode.INTERNAL_ERROR) from exc


@dataclass(frozen=True, slots=True)
class PreparedConversationTurn:
    question: str
    prior_turns: tuple[PriorTurn, ...]
    record: WorkspaceRecord
    snapshot: CorpusReadSnapshot
    source_scope: ProductTraceSourceScope
    selected_logical: frozenset[str]
    document_scope: frozenset[str]


def validate_conversation_request(
    question: str, prior_turns: object
) -> tuple[str, tuple[PriorTurn, ...]]:
    validated_prior = validate_prior_turns(prior_turns)
    return normalize_product_question(question), validated_prior


def prepare_conversation_turn(
    runtime: ApplicationRuntime,
    *,
    workspace_id: str,
    validated: tuple[str, tuple[PriorTurn, ...]],
    source_ids: list[str] | None,
    control: OperationHandle | None = None,
) -> PreparedConversationTurn:
    # 3–4. Resolve + validate workspace.
    store = WorkspaceStore(runtime.settings)
    record = store.get(workspace_id)
    if (
        record.status is not WorkspaceStatus.ACTIVE
        or record.current_snapshot_id is None
    ):
        raise AppError(
            ErrorCode.WORKSPACE_NOT_READY,
            details=SafeErrorDetails(
                workspace_id=workspace_id,
                reason="workspace_empty"
                if record.status is WorkspaceStatus.EMPTY
                else "workspace_no_current_publication",
            ),
        )

    # 5–6. Capture admitted revision + snapshot (immutable for this turn).
    admitted_snapshot_id = record.current_snapshot_id

    # 7–8. Resolve logical sources → document scope against admitted record.
    source_scope, selected_logical, document_scope = _resolve_workspace_source_scope(
        record, source_ids=source_ids
    )

    # 9. Bind immutable snapshot (scientific publication identity).
    if control is not None:
        control.checkpoint("pre_resolve")
    snapshot = runtime.publication.resolve_snapshot(
        record.backing_corpus_name, admitted_snapshot_id
    )

    return PreparedConversationTurn(
        *validated, record, snapshot, source_scope, selected_logical, document_scope
    )


def execute_prepared_conversation_turn(
    runtime: ApplicationRuntime,
    prepared: PreparedConversationTurn,
    *,
    control: OperationHandle | None = None,
    owned: bool = False,
) -> ConversationTurnResponse:
    normalized_question, validated_prior = prepared.question, prepared.prior_turns
    record, snapshot = prepared.record, prepared.snapshot
    workspace_id = record.workspace_id
    admitted_revision = record.revision
    admitted_snapshot_id = snapshot.snapshot_id
    source_scope = prepared.source_scope
    selected_logical = prepared.selected_logical
    document_scope = prepared.document_scope
    # 10. Allocate conversation orchestration trace (admission complete).
    conversation_trace_id = allocate_conversation_trace_id()
    created_at = datetime.now(tz=UTC)
    cstore = ConversationTraceStore(runtime.settings)

    # Intentionally do NOT re-read workspace for conflict after admission.
    # Concurrent mutation may change current revision/snapshot; this turn keeps
    # the admitted binding (A2-D05b Historical semantics).

    # 11. Resolver (after scientific state is bound).
    if control is not None:
        control.checkpoint("pre_resolver")
    resolver = resolve_conversation_context(
        runtime,
        prior_turns=validated_prior,
        current_question=normalized_question,
    )

    if control is not None:
        control.checkpoint("post_resolver")

    if resolver.outcome == "clarification_required":
        if owned and control is not None:
            runtime.operations.claim_query_terminal(control)
        _commit_conversation_trace(
            cstore,
            ConversationTraceRecord(
                conversation_trace_id=conversation_trace_id,
                created_at=created_at,
                workspace_id=workspace_id,
                workspace_revision=int(admitted_revision),
                snapshot_id=admitted_snapshot_id,
                product_mode_id=PRODUCT_MODE_GROUNDED_V1,
                source_scope=source_scope,
                question_sha256=_sha256(normalized_question),
                question_char_count=len(normalized_question),
                prior_turn_count=len(validated_prior),
                resolver_invoked=resolver.resolver_invoked,
                resolver_prompt_contract_id=RESOLVER_PROMPT_CONTRACT_ID,
                resolver_outcome="clarification_required",
                retrieval_question_sha256=None,
                retrieval_question_char_count=None,
                context_used=resolver.context_used,
                status="clarification_required",
                query_trace_id=None,
            ),
        )
        return ConversationTurnResponse(
            workspace_id=workspace_id,
            workspace_revision=admitted_revision,
            snapshot_id=admitted_snapshot_id,
            product_mode_id=PRODUCT_MODE_GROUNDED_V1,
            conversation_trace_id=conversation_trace_id,
            query_trace_id=None,
            status="clarification_required",
            abstention_reason="ambiguous_request",
            recovery_diagnostics={"source_count": len(source_scope.source_ids)},
            question=normalized_question,
            retrieval_question=None,
            context_used=resolver.context_used,
            answer=None,
            answer_blocks=[],
            citations=[],
        )

    assert resolver.retrieval_question is not None
    retrieval_question = resolver.retrieval_question
    answer_intent = normalized_question

    # 12. Shared grounded query core against admitted snapshot/scope.
    if control is not None:
        control.checkpoint("pre_grounded")
    outcome = run_bound_snapshot_query(
        runtime,
        snapshot=snapshot,
        retrieval_question=retrieval_question,
        answer_intent=answer_intent,
        control=control,
        document_ids=document_scope,
        source_scope=source_scope,
        claim_terminal=owned,
    )
    try:
        citations = _enrich_workspace_citations(
            outcome.citations,
            record=record,
            require_mapping=outcome.status == "answered",
            selected_source_ids=selected_logical,
        )
    except AppError:
        logger.warning(
            "conversation citation projection failed conversation_trace=%s query_trace=%s",
            conversation_trace_id,
            outcome.trace_id,
        )
        raise

    resolver_outcome_status = (
        "bypassed" if not resolver.resolver_invoked else "resolved"
    )
    _commit_conversation_trace(
        cstore,
        ConversationTraceRecord(
            conversation_trace_id=conversation_trace_id,
            created_at=created_at,
            workspace_id=workspace_id,
            workspace_revision=int(admitted_revision),
            snapshot_id=admitted_snapshot_id,
            product_mode_id=outcome.binding.product_mode_id,
            source_scope=source_scope,
            question_sha256=_sha256(normalized_question),
            question_char_count=len(normalized_question),
            prior_turn_count=len(validated_prior),
            resolver_invoked=resolver.resolver_invoked,
            resolver_prompt_contract_id=RESOLVER_PROMPT_CONTRACT_ID,
            resolver_outcome=resolver_outcome_status,
            retrieval_question_sha256=_sha256(retrieval_question),
            retrieval_question_char_count=len(retrieval_question),
            context_used=resolver.context_used,
            status=outcome.status,
            query_trace_id=outcome.trace_id,
        ),
    )

    return ConversationTurnResponse(
        workspace_id=workspace_id,
        workspace_revision=admitted_revision,
        snapshot_id=outcome.binding.snapshot_id,
        product_mode_id=outcome.binding.product_mode_id,
        conversation_trace_id=conversation_trace_id,
        query_trace_id=outcome.trace_id,
        status=outcome.status,
        abstention_reason=outcome.abstention_reason,
        recovery_diagnostics=(
            {
                **(outcome.recovery_diagnostics or {}),
                "source_count": len(source_scope.source_ids),
            }
            if outcome.status != "answered"
            else None
        ),
        question=normalized_question,
        retrieval_question=retrieval_question,
        context_used=resolver.context_used,
        answer=outcome.answer,
        answer_blocks=outcome.answer_blocks,
        citations=citations,
    )


def run_conversation_turn(
    runtime: ApplicationRuntime,
    *,
    workspace_id: str,
    question: str,
    prior_turns: object = None,
    source_ids: list[str] | None = None,
    control: OperationHandle | None = None,
) -> ConversationTurnResponse:
    """Execute a direct caller's turn using the same preparation and execution."""
    if control is not None:
        control.checkpoint("pre_validate")
    validated = validate_conversation_request(question, prior_turns)
    runtime.require_ready()
    prepared = prepare_conversation_turn(
        runtime,
        workspace_id=workspace_id,
        validated=validated,
        source_ids=source_ids,
        control=control,
    )
    return execute_prepared_conversation_turn(runtime, prepared, control=control)
