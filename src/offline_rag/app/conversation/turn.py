"""Conversation turn orchestration (A2-D05 / A2-D05b)."""

from __future__ import annotations

import hashlib
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
from offline_rag.app.snapshot import PRODUCT_MODE_GROUNDED_V1
from offline_rag.app.workspace.models import WorkspaceRevision, WorkspaceStatus
from offline_rag.app.workspace.store import WorkspaceStore

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
        }


def _commit_conversation_trace(
    store: ConversationTraceStore, record: ConversationTraceRecord
) -> None:
    try:
        store.commit(record)
    except AppError:
        raise AppError(ErrorCode.INTERNAL_ERROR)
    except Exception as exc:  # noqa: BLE001
        raise AppError(ErrorCode.INTERNAL_ERROR) from exc


def run_conversation_turn(
    runtime: ApplicationRuntime,
    *,
    workspace_id: str,
    question: str,
    prior_turns: object = None,
    source_ids: list[str] | None = None,
    control: OperationHandle | None = None,
) -> ConversationTurnResponse:
    """Execute one conversation turn under A2-D05 / A2-D05b admission order.

    Mutation after admission does **not** upgrade the bound snapshot and is not
    ``workspace_conflict`` — the turn continues on admitted scientific state.
    """
    # 1. Validate request (before resolver / admission).
    if control is not None:
        control.checkpoint("pre_validate")
    validated_prior: tuple[PriorTurn, ...] = validate_prior_turns(prior_turns)
    normalized_question = normalize_product_question(question)

    # 2. Require runtime ready.
    runtime.require_ready()

    # 3–4. Resolve + validate workspace.
    store = WorkspaceStore(runtime.settings)
    record = store.get(workspace_id)
    if record.status is not WorkspaceStatus.ACTIVE or record.current_snapshot_id is None:
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
    admitted_revision = record.revision
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

    if resolver.outcome == "clarification_required":
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
    )
    citations = _enrich_workspace_citations(
        outcome.citations,
        record=record,
        require_mapping=outcome.status == "answered",
        selected_source_ids=selected_logical,
    )

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
        question=normalized_question,
        retrieval_question=retrieval_question,
        context_used=resolver.context_used,
        answer=outcome.answer,
        answer_blocks=outcome.answer_blocks,
        citations=citations,
    )
