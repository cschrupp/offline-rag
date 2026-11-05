"""Conversation turn orchestration (A2-D05 / A2-D05b)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

from offline_rag.app.conversation.intent import (
    INTENT_ROUTER_CONTRACT_ID,
    ConversationRoute,
    route_conversation_intent,
)
from offline_rag.app.conversation.planner import (
    PLANNER_CONTRACT_ID,
    CurrentMessageTarget,
    PriorTurnTarget,
    TaskPlan,
    TaskPlanValidationError,
    build_planner_request,
    parse_and_validate_task_plan,
    transform_instruction,
)
from offline_rag.app.conversation.prior_turns import PriorTurn, validate_prior_turns
from offline_rag.app.conversation.resolver import (
    RESOLVER_PROMPT_CONTRACT_ID,
    ResolverResult,
    resolve_conversation_context,
)
from offline_rag.app.conversation.traces import (
    CONVERSATION_TRACE_SCHEMA_VERSION,
    PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION,
    ConversationTraceRecord,
    ConversationTraceStore,
    allocate_conversation_trace_id,
)
from offline_rag.app.conversation.transform import (
    TRANSFORM_PROMPT_CONTRACT_ID,
    transform_conversation_text,
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
    "transformed",
]
ConversationResponseKind = Literal[
    "grounded_answer", "conversation_transform", "clarification"
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
    response_kind: ConversationResponseKind
    transformation_source: (
        Literal["current_message", "prior_user_turn", "prior_assistant_turn"] | None
    )
    abstention_reason: str | None
    question: str
    retrieval_question: str | None
    context_used: bool
    answer: str | None
    answer_blocks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    guidance_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_revision": self.workspace_revision,
            "snapshot_id": self.snapshot_id,
            "product_mode_id": self.product_mode_id,
            "conversation_trace_id": self.conversation_trace_id,
            "query_trace_id": self.query_trace_id,
            "status": self.status,
            "response_kind": self.response_kind,
            "transformation_source": self.transformation_source,
            "abstention_reason": self.abstention_reason,
            "question": self.question,
            "retrieval_question": self.retrieval_question,
            "context_used": self.context_used,
            "answer": self.answer,
            "answer_blocks": self.answer_blocks,
            "citations": self.citations,
            "guidance_code": self.guidance_code,
        }


def _commit_conversation_trace(
    store: ConversationTraceStore, record: ConversationTraceRecord
) -> None:
    try:
        store.commit(record)
    except AppError:
        raise AppError(ErrorCode.INTERNAL_ERROR)
    except Exception as exc:
        raise AppError(ErrorCode.INTERNAL_ERROR) from exc


def _planner_failure_code(error: BaseException) -> str:
    provider_reason = getattr(error, "failure_reason", None)
    if provider_reason == "context_window_exceeded":
        return "planner_context_limit"
    if provider_reason == "timeout":
        return "planner_timeout"
    if provider_reason == "unavailable":
        return "planner_unavailable"
    if isinstance(error, AppError) and error.code == ErrorCode.GENERATION_UNAVAILABLE:
        return "planner_unavailable"
    if isinstance(error, AppError) and error.code == ErrorCode.GENERATION_TIMEOUT:
        return "planner_timeout"
    if isinstance(error, AppError) and error.code in {
        ErrorCode.REQUEST_CANCELLED,
        ErrorCode.REQUEST_TIMEOUT,
    }:
        return "planner_cancelled"
    return "planner_transport_error"


def _planner_public_error(error: BaseException) -> AppError:
    provider_reason = getattr(error, "failure_reason", None)
    if provider_reason == "timeout":
        return AppError(ErrorCode.GENERATION_TIMEOUT)
    if provider_reason in {"transport_error", "unavailable"}:
        return AppError(ErrorCode.GENERATION_UNAVAILABLE)
    if isinstance(error, AppError):
        return error
    return AppError(ErrorCode.GENERATION_FAILED)


def _write_planner_failure_trace(
    store: ConversationTraceStore,
    *,
    conversation_trace_id: str,
    created_at: datetime,
    workspace_id: str,
    workspace_revision: int,
    snapshot_id: str,
    source_scope: Any,
    question: str,
    prior_turns: tuple[PriorTurn, ...],
    call_count: int,
    duration_ms: int,
    input_char_count: int,
    reason_code: str,
) -> None:
    cancelled = reason_code == "planner_cancelled"
    _commit_conversation_trace(
        store,
        ConversationTraceRecord(
            schema_version=PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION,
            conversation_trace_id=conversation_trace_id,
            created_at=created_at,
            workspace_id=workspace_id,
            workspace_revision=workspace_revision,
            snapshot_id=snapshot_id,
            product_mode_id=PRODUCT_MODE_GROUNDED_V1,
            source_scope=source_scope,
            question_sha256=_sha256(question),
            question_char_count=len(question),
            prior_turn_count=len(prior_turns),
            resolver_invoked=False,
            resolver_prompt_contract_id=None,
            resolver_outcome="bypassed",
            context_used=False,
            status="cancelled" if cancelled else "failed",
            query_trace_id=None,
            intent_kind=None,
            intent_router_contract_id=PLANNER_CONTRACT_ID,
            router_mode="planner",
            planner_contract_id=PLANNER_CONTRACT_ID,
            planner_operation=None,
            planner_validation="cancelled" if cancelled else "unavailable",
            planner_reason_code=reason_code,
            planner_model_call_count=call_count,
            planner_duration_ms=duration_ms,
            planner_input_char_count=input_char_count,
            planner_output_char_count=0,
            referenced_context_turn_count=0,
            contextual_resolution_needed=bool(prior_turns),
        ),
    )


def _invalid_task_plan(*, input_char_count: int, output_char_count: int) -> TaskPlan:
    return TaskPlan(
        operation="clarify",
        transform_kind=None,
        target=None,
        retrieval_question=None,
        options=None,
        context_turn_ordinals=(),
        source_mentions=(),
        reason_code="planner_plan_invalid",
        planner_validation="rejected",
        input_char_count=input_char_count,
        output_char_count=output_char_count,
    )


def _resolve_planner_source_mentions(
    mentions: tuple[str, ...], *, record: Any, selected_source_ids: frozenset[str]
) -> bool:
    """Require each literal mention to identify one already-selected source."""
    active_sources = [source for source in record.sources if source.active]
    for mention in mentions:
        matches = [
            source
            for source in active_sources
            if source.display_name.casefold() == mention.casefold()
        ]
        if len(matches) != 1 or matches[0].source_id not in selected_source_ids:
            return False
    return True


def _planner_route(plan: TaskPlan) -> ConversationRoute:
    if plan.operation in {"clarify", "unsupported_operation"}:
        return ConversationRoute(
            kind="clarification_required",
            clarification_reason=plan.reason_code,
            guidance_code=plan.reason_code,
        )
    if plan.operation == "grounded_query":
        return ConversationRoute(kind="grounded_query")

    assert plan.transform_kind is not None
    assert plan.target is not None
    if isinstance(plan.target, CurrentMessageTarget):
        return ConversationRoute(
            kind="conversation_transform",
            operation=plan.transform_kind,
            source="current_message",
            source_role="user",
            target_text=plan.target.text,
            instruction=transform_instruction(plan),
        )
    assert isinstance(plan.target, PriorTurnTarget)
    return ConversationRoute(
        kind="conversation_transform",
        operation=plan.transform_kind,
        source=plan.target.kind,
        source_role="user" if plan.target.kind == "prior_user_turn" else "assistant",
        source_turn_ordinal=plan.target.ordinal,
        target_text=plan.target.text,
        instruction=transform_instruction(plan),
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

    # 11. Route only after request, workspace, scope, and snapshot are bound.
    router_mode = runtime.settings.conversation.router_mode
    planner: TaskPlan | None = None
    planner_duration_ms = 0
    planner_model_call_count = 0
    planner_input_char_count = len(normalized_question) + sum(
        len(turn.text) for turn in validated_prior
    )
    planner_guidance_code: str | None = None
    planner_resolver: ResolverResult | None = None

    if router_mode == "planner":
        resources = runtime.resources
        if (
            not runtime.settings.generation.enabled
            or resources is None
            or resources.generator_client is None
        ):
            error = AppError(ErrorCode.GENERATION_UNAVAILABLE)
            _write_planner_failure_trace(
                cstore,
                conversation_trace_id=conversation_trace_id,
                created_at=created_at,
                workspace_id=workspace_id,
                workspace_revision=int(admitted_revision),
                snapshot_id=admitted_snapshot_id,
                source_scope=source_scope,
                question=normalized_question,
                prior_turns=validated_prior,
                call_count=0,
                duration_ms=0,
                input_char_count=planner_input_char_count,
                reason_code="planner_unavailable",
            )
            raise error

        request = build_planner_request(
            question=normalized_question,
            prior_turns=validated_prior,
            scope_mode=source_scope.mode,
            selected_source_count=len(selected_logical),
            model=runtime.settings.generation.model,
            max_output_tokens=int(runtime.settings.generation.max_output_tokens),
        )
        planner_model_call_count = 1
        started = perf_counter()
        try:
            if control is not None:
                planner_model_call_count = 0
                control.checkpoint("pre_planner")
                planner_model_call_count = 1
            response = resources.generator_client.generate(request)
            planner_duration_ms = int((perf_counter() - started) * 1000)
            if control is not None:
                control.checkpoint("post_planner")
        except Exception as error:
            planner_duration_ms = int((perf_counter() - started) * 1000)
            failure_code = _planner_failure_code(error)
            _write_planner_failure_trace(
                cstore,
                conversation_trace_id=conversation_trace_id,
                created_at=created_at,
                workspace_id=workspace_id,
                workspace_revision=int(admitted_revision),
                snapshot_id=admitted_snapshot_id,
                source_scope=source_scope,
                question=normalized_question,
                prior_turns=validated_prior,
                call_count=planner_model_call_count,
                duration_ms=planner_duration_ms,
                input_char_count=planner_input_char_count,
                reason_code=failure_code,
            )
            raise _planner_public_error(error) from error

        try:
            planner = parse_and_validate_task_plan(
                response.content,
                question=normalized_question,
                prior_turns=validated_prior,
                max_output_tokens=request.max_output_tokens,
            )
        except TaskPlanValidationError:
            planner = _invalid_task_plan(
                input_char_count=planner_input_char_count,
                output_char_count=len(response.content)
                if isinstance(response.content, str)
                else 0,
            )

        if (
            planner.operation == "grounded_query"
            and not _resolve_planner_source_mentions(
                planner.source_mentions,
                record=record,
                selected_source_ids=selected_logical,
            )
        ):
            planner_guidance_code = "source_reference_unavailable"
            route = ConversationRoute(
                kind="clarification_required",
                clarification_reason="source_reference_unavailable",
                guidance_code=planner_guidance_code,
            )
        else:
            route = _planner_route(planner)
        if planner.operation == "grounded_query" and route.kind == "grounded_query":
            assert planner.retrieval_question is not None
            planner_resolver = ResolverResult(
                outcome="resolved",
                retrieval_question=planner.retrieval_question,
                context_used=planner.context_used,
                resolver_invoked=False,
            )
    else:
        # Preserve the reviewed BETA-CONV-01 path exactly in default mode.
        route = route_conversation_intent(normalized_question, validated_prior)

    planner_trace_fields: dict[str, Any] = {}
    if planner is not None:
        planner_trace_fields = {
            "router_mode": "planner",
            "planner_contract_id": PLANNER_CONTRACT_ID,
            "planner_operation": (
                planner.operation if planner.planner_validation == "valid" else None
            ),
            "planner_validation": planner.planner_validation,
            "planner_reason_code": planner_guidance_code or planner.reason_code,
            "planner_model_call_count": planner_model_call_count,
            "planner_duration_ms": planner_duration_ms,
            "planner_input_char_count": planner_input_char_count,
            "planner_output_char_count": planner.output_char_count,
            "referenced_context_turn_count": len(planner.context_turn_ordinals),
            "contextual_resolution_needed": bool(validated_prior),
        }

    trace_schema_version = (
        PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION
        if router_mode == "planner"
        else CONVERSATION_TRACE_SCHEMA_VERSION
    )
    intent_contract_id = (
        PLANNER_CONTRACT_ID if router_mode == "planner" else INTENT_ROUTER_CONTRACT_ID
    )

    if route.kind == "clarification_required":
        _commit_conversation_trace(
            cstore,
            ConversationTraceRecord(
                schema_version=trace_schema_version,
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
                resolver_invoked=False,
                resolver_prompt_contract_id=None,
                resolver_outcome="bypassed",
                retrieval_question_sha256=None,
                retrieval_question_char_count=None,
                context_used=planner.context_used if planner is not None else False,
                status="clarification_required",
                query_trace_id=None,
                intent_kind="clarification_required",
                intent_router_contract_id=intent_contract_id,
                **planner_trace_fields,
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
            response_kind="clarification",
            transformation_source=None,
            abstention_reason="ambiguous_request",
            question=normalized_question,
            retrieval_question=None,
            context_used=planner.context_used if planner is not None else False,
            answer=None,
            answer_blocks=[],
            citations=[],
            guidance_code=planner_guidance_code or route.guidance_code,
        )

    if route.kind == "conversation_transform":
        assert route.operation is not None
        assert route.source is not None
        assert route.instruction is not None
        assert route.target_text is not None
        if control is not None:
            control.checkpoint("pre_transform")
        transformed_text = transform_conversation_text(
            runtime,
            operation=route.operation,
            instruction=route.instruction,
            target_text=route.target_text,
        )
        _commit_conversation_trace(
            cstore,
            ConversationTraceRecord(
                schema_version=trace_schema_version,
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
                resolver_invoked=False,
                resolver_prompt_contract_id=None,
                resolver_outcome="bypassed",
                retrieval_question_sha256=None,
                retrieval_question_char_count=None,
                context_used=route.source != "current_message",
                status="transformed",
                query_trace_id=None,
                intent_kind="conversation_transform",
                intent_router_contract_id=intent_contract_id,
                transform_prompt_contract_id=TRANSFORM_PROMPT_CONTRACT_ID,
                transform_operation=route.operation,
                transform_source_kind=route.source,
                transform_source_role=route.source_role,
                transform_source_turn_ordinal=route.source_turn_ordinal,
                transform_target_sha256=_sha256(route.target_text),
                transform_target_char_count=len(route.target_text),
                transform_output_sha256=_sha256(transformed_text),
                transform_output_char_count=len(transformed_text),
                **planner_trace_fields,
            ),
        )
        return ConversationTurnResponse(
            workspace_id=workspace_id,
            workspace_revision=admitted_revision,
            snapshot_id=admitted_snapshot_id,
            product_mode_id=PRODUCT_MODE_GROUNDED_V1,
            conversation_trace_id=conversation_trace_id,
            query_trace_id=None,
            status="transformed",
            response_kind="conversation_transform",
            transformation_source=route.source,
            abstention_reason=None,
            question=normalized_question,
            retrieval_question=None,
            context_used=route.source != "current_message",
            answer=transformed_text,
            answer_blocks=[],
            citations=[],
        )

    # 12. Planner mode supplies the validated query directly; legacy mode keeps
    # the reviewed resolver and its existing first-turn bypass unchanged.
    if planner_resolver is not None:
        resolver = planner_resolver
    else:
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
                schema_version=trace_schema_version,
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
                resolver_prompt_contract_id=(
                    None if router_mode == "planner" else RESOLVER_PROMPT_CONTRACT_ID
                ),
                resolver_outcome="clarification_required",
                retrieval_question_sha256=None,
                retrieval_question_char_count=None,
                context_used=resolver.context_used,
                status="clarification_required",
                query_trace_id=None,
                intent_kind="grounded_query",
                intent_router_contract_id=intent_contract_id,
                **planner_trace_fields,
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
            response_kind="clarification",
            transformation_source=None,
            abstention_reason="ambiguous_request",
            question=normalized_question,
            retrieval_question=None,
            context_used=resolver.context_used,
            answer=None,
            answer_blocks=[],
            citations=[],
            guidance_code=planner_guidance_code or route.guidance_code,
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
            schema_version=trace_schema_version,
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
            resolver_prompt_contract_id=(
                RESOLVER_PROMPT_CONTRACT_ID if router_mode == "legacy" else None
            ),
            resolver_outcome=resolver_outcome_status,
            retrieval_question_sha256=_sha256(retrieval_question),
            retrieval_question_char_count=len(retrieval_question),
            context_used=resolver.context_used,
            status=outcome.status,
            query_trace_id=outcome.trace_id,
            intent_kind="grounded_query",
            intent_router_contract_id=intent_contract_id,
            **planner_trace_fields,
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
        response_kind="grounded_answer",
        transformation_source=None,
        abstention_reason=outcome.abstention_reason,
        question=normalized_question,
        retrieval_question=retrieval_question,
        context_used=resolver.context_used,
        answer=outcome.answer,
        answer_blocks=outcome.answer_blocks,
        citations=citations,
    )
