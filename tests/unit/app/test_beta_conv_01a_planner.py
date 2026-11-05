"""BETA-CONV-01A task-plan validation and opt-in orchestration tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from offline_rag.app.conversation import turn as conversation_turn
from offline_rag.app.conversation.planner import (
    PLANNER_CONTRACT_ID,
    TaskPlanValidationError,
    build_planner_request,
    parse_and_validate_task_plan,
)
from offline_rag.app.conversation.traces import (
    CONVERSATION_TRACE_SCHEMA_VERSION,
    PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION,
    ConversationTraceRecord,
    ConversationTraceStore,
)
from offline_rag.app.conversation.turn import _resolve_planner_source_mentions
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.traces import ProductTraceSourceScope
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.config import load_settings
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    OpenAICompatibleGeneratorError,
)


def _wire_plan(**updates: Any) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema_version": PLANNER_CONTRACT_ID,
        "operation": "grounded_query",
        "transform_kind": None,
        "target": None,
        "retrieval_question": "What does the report say?",
        "options": None,
        "context_turn_ordinals": [],
        "source_mentions": [],
        "reason_code": None,
    }
    plan.update(updates)
    return plan


def _parse(plan: dict[str, Any], *, question: str = "What does the report say?"):
    return parse_and_validate_task_plan(
        json.dumps(plan),
        question=question,
        prior_turns=(),
        max_output_tokens=512,
    )


def test_planner_accepts_exact_grounded_plan_and_builds_bounded_request() -> None:
    plan = _parse(_wire_plan())
    request = build_planner_request(
        question="What does the report say?",
        prior_turns=(),
        scope_mode="all_active",
        selected_source_count=2,
        model="local-model",
        max_output_tokens=1200,
    )

    assert plan.operation == "grounded_query"
    assert plan.retrieval_question == "What does the report say?"
    assert plan.context_used is False
    assert request.max_output_tokens == 512
    assert request.temperature == 0.0
    assert request.metadata["prompt_contract"] == PLANNER_CONTRACT_ID
    assert request.response_format is not None
    assert request.response_format["json_schema"]["strict"] is True
    assert "current_question" in request.messages[1].content


def test_approved_local_adapter_receives_strict_structured_planner_request() -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_LLM_MODEL": "approved-local-model",
            "OFFLINE_RAG_APPROVED_LLM_MODELS": "approved-local-model",
            "OFFLINE_RAG_APPROVED_LLM_ENDPOINTS": "http://127.0.0.1:11434/v1",
        },
    )
    response_payload = {"choices": [{"message": {"content": json.dumps(_wire_plan())}}]}
    client = MagicMock(spec=httpx.Client)
    client.post.return_value.status_code = 200
    client.post.return_value.json.return_value = response_payload
    adapter = OpenAICompatibleGenerator(settings, client=client)
    request = build_planner_request(
        question="What does the report say?",
        prior_turns=(),
        scope_mode="all_active",
        selected_source_count=1,
        model="approved-local-model",
        max_output_tokens=512,
    )

    result = adapter.generate(request)

    assert result.content == json.dumps(_wire_plan())
    body = client.post.call_args.kwargs["json"]
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 512


def test_planner_resolves_current_message_codepoint_span() -> None:
    question = "Summarize: 🌋 Café is online."
    selected = "Café is online."
    start = question.index(selected)
    plan = _parse(
        _wire_plan(
            operation="transform_text",
            transform_kind="summarize",
            target={
                "kind": "current_message_span",
                "start": start,
                "end": start + len(selected),
            },
            retrieval_question=None,
            options={
                "bullet_count": 3,
                "audience": None,
                "target_language": None,
            },
        ),
        question=question,
    )

    assert plan.target is not None
    assert plan.target.text == selected
    assert plan.context_used is False


def test_planner_resolves_exact_prior_turn_role_and_context_reference() -> None:
    from offline_rag.app.conversation.prior_turns import PriorTurn

    turns = (
        PriorTurn(role="user", text="What happened?"),
        PriorTurn(role="assistant", text="The pump stopped."),
    )
    plan = parse_and_validate_task_plan(
        json.dumps(
            _wire_plan(
                operation="transform_text",
                transform_kind="rewrite",
                target={"kind": "prior_assistant_turn", "ordinal": 2},
                retrieval_question=None,
                options={
                    "bullet_count": None,
                    "audience": "field operators",
                    "target_language": None,
                },
                context_turn_ordinals=[2],
            )
        ),
        question="Rewrite your previous answer.",
        prior_turns=turns,
        max_output_tokens=512,
    )

    assert plan.target is not None
    assert plan.target.text == "The pump stopped."
    assert plan.context_used is True


def test_planner_accepts_unicode_language_labels_but_not_digits() -> None:
    translated = _wire_plan(
        operation="transform_text",
        transform_kind="translate",
        target={"kind": "current_message_span", "start": 0, "end": 12},
        retrieval_question=None,
        options={"bullet_count": None, "audience": None, "target_language": "Español"},
    )
    plan = _parse(translated, question="Translate me")
    assert plan.options is not None
    assert plan.options.target_language == "Español"

    translated["options"]["target_language"] = "Spanish 2"
    with pytest.raises(TaskPlanValidationError, match="language_invalid"):
        _parse(translated, question="Translate me")


@pytest.mark.parametrize(
    "content",
    [
        '{"schema_version":"x","schema_version":"y"}',
        json.dumps(_wire_plan(extra="not allowed")),
        json.dumps(_wire_plan(context_turn_ordinals=[True])),
        json.dumps(
            _wire_plan(source_mentions=[{"kind": "span", "start": 0, "end": 3}])
        ),
        json.dumps(_wire_plan(operation=[])),
        json.dumps(
            _wire_plan(
                operation="clarify",
                retrieval_question=None,
                reason_code=[],
            )
        ),
        json.dumps(
            _wire_plan(
                operation="transform_text",
                transform_kind="summarize",
                target={"kind": [], "ordinal": 1},
                retrieval_question=None,
                options={
                    "bullet_count": None,
                    "audience": None,
                    "target_language": None,
                },
                context_turn_ordinals=[1],
            )
        ),
        '{"schema_version":NaN}',
    ],
)
def test_planner_rejects_malformed_or_non_strict_wire_content(content: str) -> None:
    with pytest.raises(TaskPlanValidationError):
        parse_and_validate_task_plan(
            content,
            question="What does the report say?",
            prior_turns=(),
            max_output_tokens=512,
        )


def test_planner_rejects_wrong_prior_role_and_out_of_bounds_span() -> None:
    from offline_rag.app.conversation.prior_turns import PriorTurn

    turns = (PriorTurn(role="user", text="Original question."),)
    wrong_role = _wire_plan(
        operation="transform_text",
        transform_kind="summarize",
        target={"kind": "prior_assistant_turn", "ordinal": 1},
        retrieval_question=None,
        options={"bullet_count": None, "audience": None, "target_language": None},
        context_turn_ordinals=[1],
    )
    with pytest.raises(TaskPlanValidationError, match="target_role_invalid"):
        parse_and_validate_task_plan(
            json.dumps(wrong_role),
            question="Summarize my previous question.",
            prior_turns=turns,
            max_output_tokens=512,
        )

    out_of_bounds = _wire_plan(
        operation="transform_text",
        transform_kind="summarize",
        target={"kind": "current_message_span", "start": 0, "end": 999},
        retrieval_question=None,
        options={"bullet_count": None, "audience": None, "target_language": None},
    )
    with pytest.raises(TaskPlanValidationError, match="span_offset_invalid"):
        _parse(out_of_bounds)


@pytest.mark.parametrize(
    ("transform_kind", "options"),
    [
        (
            "summarize",
            {"bullet_count": 13, "audience": None, "target_language": None},
        ),
        (
            "rewrite",
            {"bullet_count": None, "audience": "operators2", "target_language": None},
        ),
        (
            "translate",
            {"bullet_count": None, "audience": None, "target_language": None},
        ),
    ],
)
def test_planner_rejects_unsupported_or_incompatible_transform_options(
    transform_kind: str, options: dict[str, Any]
) -> None:
    with pytest.raises(TaskPlanValidationError):
        _parse(
            _wire_plan(
                operation="transform_text",
                transform_kind=transform_kind,
                target={"kind": "current_message_span", "start": 0, "end": 5},
                retrieval_question=None,
                options=options,
            ),
            question="Edit me",
        )


def test_source_mentions_must_match_unique_already_selected_sources() -> None:
    report = SimpleNamespace(
        display_name="Maintenance Manual.pdf",
        source_id="src_selected",
        active=True,
    )
    inactive = SimpleNamespace(
        display_name="Old Manual.pdf",
        source_id="src_inactive",
        active=False,
    )
    record = SimpleNamespace(sources=[report, inactive])

    assert _resolve_planner_source_mentions(
        ("maintenance manual.pdf",),
        record=record,
        selected_source_ids=frozenset({"src_selected"}),
    )
    assert not _resolve_planner_source_mentions(
        ("Maintenance Manual.pdf",),
        record=record,
        selected_source_ids=frozenset(),
    )
    assert not _resolve_planner_source_mentions(
        ("Old Manual.pdf",),
        record=record,
        selected_source_ids=frozenset({"src_selected"}),
    )


def _planner_runtime(tmp_path: Path, plan_response: str):
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_CONVERSATION_ROUTER_MODE": "planner",
        },
    )
    generator = FakeGenerator(default_response=plan_response)
    workspace = SimpleNamespace(
        status=WorkspaceStatus.ACTIVE,
        revision=4,
        current_snapshot_id="snap_frozen",
        backing_corpus_name="workspace_test",
        sources=[],
    )
    runtime = SimpleNamespace(
        settings=settings,
        resources=SimpleNamespace(generator_client=generator),
        publication=SimpleNamespace(resolve_snapshot=lambda *_args: object()),
        require_ready=lambda: None,
    )
    source_scope = ProductTraceSourceScope(
        workspace_id="ws_test",
        workspace_revision=4,
        mode="all_active",
        source_ids=[],
        document_ids=[],
    )
    return runtime, generator, workspace, source_scope


def _admit_planner_runtime(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Any,
    source_scope: ProductTraceSourceScope,
) -> None:
    monkeypatch.setattr(
        conversation_turn.WorkspaceStore,
        "get",
        lambda _self, _workspace_id: workspace,
    )
    monkeypatch.setattr(
        conversation_turn,
        "_resolve_workspace_source_scope",
        lambda *_args, **_kwargs: (source_scope, [], []),
    )


def test_planner_grounded_operation_uses_bound_query_without_old_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = json.dumps(_wire_plan(retrieval_question="pump maintenance interval"))
    runtime, generator, workspace, scope = _planner_runtime(tmp_path, response)
    _admit_planner_runtime(monkeypatch, workspace, scope)
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("planner invoked the old resolver"),
    )
    observed: dict[str, Any] = {}

    def query(_runtime: Any, **kwargs: Any):
        observed.update(kwargs)
        return SimpleNamespace(
            status="answered",
            citations=[],
            binding=SimpleNamespace(
                product_mode_id="grounded-v1", snapshot_id="snap_frozen"
            ),
            answer_blocks=[{"text": "Answer", "citation_refs": []}],
            trace_id="trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            abstention_reason=None,
            answer="Answer",
        )

    monkeypatch.setattr(conversation_turn, "run_bound_snapshot_query", query)
    monkeypatch.setattr(
        conversation_turn,
        "_enrich_workspace_citations",
        lambda citations, **_kwargs: citations,
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime, workspace_id="ws_test", question="PRIVATE user question"
    )

    assert generator.generate_calls == 1
    assert observed["retrieval_question"] == "pump maintenance interval"
    assert observed["answer_intent"] == "PRIVATE user question"
    trace = ConversationTraceStore(runtime.settings).get(outcome.conversation_trace_id)
    assert trace is not None
    assert trace.schema_version == PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION
    assert trace.planner_operation == "grounded_query"
    assert trace.planner_model_call_count == 1
    assert "PRIVATE user question" not in trace.model_dump_json()


def test_planner_transform_uses_sealed_transform_executor_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    question = "Summarize this: The valve is closed."
    target = "The valve is closed."
    start = question.index(target)
    plan = _wire_plan(
        operation="transform_text",
        transform_kind="summarize",
        target={
            "kind": "current_message_span",
            "start": start,
            "end": start + len(target),
        },
        retrieval_question=None,
        options={"bullet_count": 2, "audience": None, "target_language": None},
    )
    runtime, generator, workspace, scope = _planner_runtime(tmp_path, json.dumps(plan))
    _admit_planner_runtime(monkeypatch, workspace, scope)
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("transform invoked the old resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("transform invoked retrieval"),
    )
    observed: dict[str, Any] = {}

    def transform(_runtime: Any, **kwargs: Any) -> str:
        observed.update(kwargs)
        return "- Valve state: closed."

    monkeypatch.setattr(conversation_turn, "transform_conversation_text", transform)

    outcome = conversation_turn.run_conversation_turn(
        runtime, workspace_id="ws_test", question=question
    )

    assert generator.generate_calls == 1
    assert observed["target_text"] == target
    assert observed["instruction"] == "summarize in 2 bullets"
    assert outcome.status == "transformed"
    assert outcome.query_trace_id is None


def test_unselected_planner_source_mention_clarifies_without_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    question = "What does Maintenance Manual.pdf say?"
    mention = "Maintenance Manual.pdf"
    start = question.index(mention)
    plan = _wire_plan(
        retrieval_question="What does the maintenance manual say?",
        source_mentions=[{"start": start, "end": start + len(mention)}],
    )
    runtime, generator, workspace, scope = _planner_runtime(tmp_path, json.dumps(plan))
    workspace.sources = [
        SimpleNamespace(
            display_name=mention,
            source_id="src_not_selected",
            active=True,
        )
    ]
    _admit_planner_runtime(monkeypatch, workspace, scope)
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("planner invoked the old resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("unselected source reached retrieval"),
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime, workspace_id="ws_test", question=question
    )

    assert generator.generate_calls == 1
    assert outcome.status == "clarification_required"
    assert outcome.guidance_code == "source_reference_unavailable"
    trace = ConversationTraceStore(runtime.settings).get(outcome.conversation_trace_id)
    assert trace is not None
    assert trace.planner_reason_code == "source_reference_unavailable"


def test_invalid_planner_output_clarifies_without_downstream_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, generator, workspace, scope = _planner_runtime(tmp_path, "not json")
    _admit_planner_runtime(monkeypatch, workspace, scope)
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("invalid plan called the old resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("invalid plan invoked retrieval"),
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime, workspace_id="ws_test", question="PRIVATE malformed-plan question"
    )

    assert generator.generate_calls == 1
    assert outcome.status == "clarification_required"
    assert outcome.guidance_code == "planner_plan_invalid"
    trace = ConversationTraceStore(runtime.settings).get(outcome.conversation_trace_id)
    assert trace is not None
    assert trace.planner_validation == "rejected"
    assert trace.planner_reason_code == "planner_plan_invalid"
    assert "PRIVATE malformed-plan question" not in trace.model_dump_json()


def test_preplanner_cancellation_records_zero_call_failure_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_plan = json.dumps(_wire_plan())
    runtime, generator, workspace, scope = _planner_runtime(tmp_path, valid_plan)
    _admit_planner_runtime(monkeypatch, workspace, scope)

    class CancelAtPlanner:
        def checkpoint(self, stage: str) -> None:
            if stage == "pre_planner":
                raise AppError(ErrorCode.REQUEST_CANCELLED)

    with pytest.raises(AppError) as exc:
        conversation_turn.run_conversation_turn(
            runtime,
            workspace_id="ws_test",
            question="What does the report say?",
            control=CancelAtPlanner(),
        )

    assert exc.value.code is ErrorCode.REQUEST_CANCELLED
    assert generator.generate_calls == 0
    trace_paths = list(
        (runtime.settings.paths.traces / "conversation").glob("trace_*.json")
    )
    assert len(trace_paths) == 1
    trace = ConversationTraceStore(runtime.settings).get(trace_paths[0].stem)
    assert trace is not None
    assert trace.schema_version == PLANNER_CONVERSATION_TRACE_SCHEMA_VERSION
    assert trace.status == "cancelled"
    assert trace.planner_validation == "cancelled"
    assert trace.planner_model_call_count == 0


@pytest.mark.parametrize(
    ("failure_reason", "expected_trace_reason", "expected_error"),
    [
        (
            "context_window_exceeded",
            "planner_context_limit",
            ErrorCode.GENERATION_FAILED,
        ),
        ("timeout", "planner_timeout", ErrorCode.GENERATION_TIMEOUT),
        (
            "transport_error",
            "planner_transport_error",
            ErrorCode.GENERATION_UNAVAILABLE,
        ),
    ],
)
def test_planner_provider_failure_is_safe_and_traced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_reason: str,
    expected_trace_reason: str,
    expected_error: ErrorCode,
) -> None:
    runtime, _generator, workspace, scope = _planner_runtime(tmp_path, "unused")
    error = OpenAICompatibleGeneratorError(
        "provider text includes private details", failure_reason=failure_reason
    )
    runtime.resources.generator_client = FakeGenerator(raise_on_generate=error)
    _admit_planner_runtime(monkeypatch, workspace, scope)
    with pytest.raises(AppError) as exc:
        conversation_turn.run_conversation_turn(
            runtime,
            workspace_id="ws_test",
            question="PRIVATE provider failure question",
        )

    assert exc.value.code is expected_error
    trace_paths = list(
        (runtime.settings.paths.traces / "conversation").glob("trace_*.json")
    )
    assert len(trace_paths) == 1
    trace_text = trace_paths[0].read_text(encoding="utf-8")
    assert expected_trace_reason in trace_text
    assert "provider text includes private details" not in trace_text
    assert "PRIVATE provider failure question" not in trace_text


@pytest.mark.parametrize(
    "schema_version",
    [CONVERSATION_TRACE_SCHEMA_VERSION, "offline-rag-conversation-trace-v1"],
)
def test_legacy_trace_versions_reject_planner_failure_status(
    schema_version: str,
) -> None:
    from offline_rag.app.conversation.traces import allocate_conversation_trace_id

    with pytest.raises(ValueError):
        ConversationTraceRecord(
            schema_version=schema_version,
            conversation_trace_id=allocate_conversation_trace_id(),
            created_at=datetime.now(UTC),
            workspace_id="ws_test",
            workspace_revision=1,
            snapshot_id="snap_test",
            product_mode_id="grounded-v1",
            source_scope=ProductTraceSourceScope(
                workspace_id="ws_test",
                workspace_revision=1,
                mode="all_active",
                source_ids=[],
                document_ids=[],
            ),
            question_sha256="a" * 64,
            question_char_count=5,
            prior_turn_count=0,
            resolver_invoked=False,
            resolver_outcome="bypassed",
            context_used=False,
            status="failed",
        )
