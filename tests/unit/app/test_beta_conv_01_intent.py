"""BETA-CONV-01 deterministic intent and transform-contract regressions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from offline_rag.app.conversation import turn as conversation_turn
from offline_rag.app.conversation.intent import route_conversation_intent
from offline_rag.app.conversation.prior_turns import PriorTurn
from offline_rag.app.conversation.traces import (
    LEGACY_CONVERSATION_TRACE_SCHEMA_VERSION,
    ConversationTraceRecord,
    ConversationTraceStore,
    allocate_conversation_trace_id,
)
from offline_rag.app.conversation.transform import (
    TRANSFORM_PROMPT_CONTRACT_ID,
    build_transform_request,
    parse_transform_response,
)
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.traces import ProductTraceSourceScope
from offline_rag.app.workspace.models import WorkspaceStatus
from offline_rag.config import load_settings
from offline_rag.generation.fake import FakeGenerator


def test_explicit_inline_simplification_routes_to_current_text() -> None:
    route = route_conversation_intent(
        "Simplify this for a beginner: “The system aggregates measurements.”", ()
    )

    assert route.kind == "conversation_transform"
    assert route.operation == "simplify"
    assert route.source == "current_message"
    assert route.target_text == "The system aggregates measurements."
    assert route.instruction == "simplify for beginner"


def test_prior_assistant_transform_uses_exact_validated_turn() -> None:
    turns = (
        PriorTurn(role="user", text="What does the report say?"),
        PriorTurn(role="assistant", text="The report describes two pumps."),
    )
    route = route_conversation_intent(
        "Summarize your previous answer in three bullets.", turns
    )

    assert route.kind == "conversation_transform"
    assert route.source == "prior_assistant_turn"
    assert route.source_role == "assistant"
    assert route.source_turn_ordinal == 2
    assert route.target_text == "The report describes two pumps."
    assert route.instruction == "summarize in 3 bullets"


@pytest.mark.parametrize(
    ("question", "expected_role", "expected_operation", "expected_instruction"),
    [
        (
            "Summarize your previous answer about the report in three bullets.",
            "assistant",
            "summarize",
            "summarize in 3 bullets",
        ),
        (
            "Translate your previous answer about the maintenance manual into Spanish.",
            "assistant",
            "translate",
            "translate into Spanish",
        ),
        (
            "Rewrite my previous question about chapter 2 for a beginner.",
            "user",
            "rewrite",
            "rewrite for beginner",
        ),
    ],
)
def test_named_prior_turn_transform_wins_over_topic_source_words(
    question: str,
    expected_role: str,
    expected_operation: str,
    expected_instruction: str,
) -> None:
    turns = (
        PriorTurn(role="user", text="What does chapter 2 say?"),
        PriorTurn(role="assistant", text="The report describes the maintenance plan."),
    )
    route = route_conversation_intent(question, turns)

    assert route.kind == "conversation_transform"
    assert route.source_role == expected_role
    assert route.operation == expected_operation
    assert route.instruction == expected_instruction
    assert route.target_text == (
        turns[0].text if expected_role == "user" else turns[1].text
    )


def test_inline_translation_extracts_language_and_delimited_text() -> None:
    route = route_conversation_intent(
        "Translate this paragraph into Spanish: `The valve is closed.`", ()
    )

    assert route.kind == "conversation_transform"
    assert route.operation == "translate"
    assert route.instruction == "translate into Spanish"
    assert route.target_text == "The valve is closed."


@pytest.mark.parametrize(
    "question",
    [
        "Summarize section 4 of the maintenance manual.",
        "Summarize chapter 2 of the quarterly report.",
        "Summarize the inspection report.",
        "Summarize [Maintenance Manual](https://example.org/manual).",
        "Summarize the title of the maintenance manual.",
    ],
)
def test_source_titles_and_document_sections_remain_grounded(question: str) -> None:
    assert route_conversation_intent(question, ()).kind == "grounded_query"


def test_source_words_inside_explicit_transform_target_do_not_change_route() -> None:
    route = route_conversation_intent(
        'Summarize this: "The report describes a maintenance section."', ()
    )

    assert route.kind == "conversation_transform"
    assert route.target_text == "The report describes a maintenance section."


@pytest.mark.parametrize(
    ("question", "expected_target"),
    [
        (
            'Summarize the following report excerpt: "The pump stopped at noon."',
            "The pump stopped at noon.",
        ),
        (
            'Translate this section into Spanish: "The pump is ready."',
            "The pump is ready.",
        ),
        (
            'Summarize this: "The text contains [instructions](https://example.org/guide)."',
            "The text contains [instructions](https://example.org/guide).",
        ),
    ],
)
def test_supplied_report_section_or_markdown_text_is_transformed(
    question: str, expected_target: str
) -> None:
    route = route_conversation_intent(question, ())

    assert route.kind == "conversation_transform"
    assert route.target_text == expected_target


def test_target_words_cannot_supply_operation_options() -> None:
    route = route_conversation_intent(
        'Translate this into Spanish: "The phrase into French is in the text."',
        (),
    )

    assert route.kind == "conversation_transform"
    assert route.instruction == "translate into Spanish"
    assert route.target_text == "The phrase into French is in the text."


def test_explain_transform_requires_a_specified_audience() -> None:
    unsupported = route_conversation_intent('Explain this: "A device state."', ())
    audience = route_conversation_intent(
        'Explain this for a beginner: "A device state."', ()
    )

    assert unsupported.kind == "clarification_required"
    assert unsupported.clarification_reason == "transform_request_unsupported"
    assert audience.kind == "conversation_transform"
    assert audience.operation == "simplify"
    assert audience.instruction == "simplify for beginner"


@pytest.mark.parametrize(
    "question",
    [
        "Summarize what document A says about the pump.",
        "Summarize what the report says about chapter 2.",
        "Verify your previous answer against the report.",
        "Summarize your previous answer and verify it against the report.",
        "Update your previous answer with facts from the report.",
        "Explain that finding in more detail.",
        "Translate the paragraph on page 4 of document A into Spanish.",
    ],
)
def test_source_questions_remain_grounded(question: str) -> None:
    assert route_conversation_intent(question, ()).kind == "grounded_query"


def test_ambiguous_transform_does_not_guess_prior_target() -> None:
    turns = (
        PriorTurn(role="user", text="My first question."),
        PriorTurn(role="assistant", text="First answer."),
    )
    route = route_conversation_intent("Summarize that.", turns)

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_target_ambiguous"


@pytest.mark.parametrize(
    ("question", "expected_target"),
    [
        (
            'Translate into Spanish:\n\n```text\nShe said "hello".\n```',
            'She said "hello".',
        ),
        (
            "Translate into Spanish:\n\n```text\nReturn [1, 2].\n```",
            "Return [1, 2].",
        ),
        ('Translate into Spanish: `She said "hello".`', 'She said "hello".'),
        ("Translate this into Spanish: `[1, 2]`", "[1, 2]"),
    ],
)
def test_nested_delimiters_produce_one_outer_target(
    question: str, expected_target: str
) -> None:
    route = route_conversation_intent(question, ())

    assert route.kind == "conversation_transform"
    assert route.target_text == expected_target


@pytest.mark.parametrize(
    ("question", "expected_target"),
    [
        (
            'Rewrite John\'s note:\n"The pump was stopped."',
            "The pump was stopped.",
        ),
        (
            'Translate today\'s alert into Spanish:\n"Pump is ready."',
            "Pump is ready.",
        ),
        (
            'Rewrite this: \'unfinished quote\n"The pump was stopped."',
            "The pump was stopped.",
        ),
        (
            'Rewrite this: ```unfinished fence\n"The pump was stopped."',
            "The pump was stopped.",
        ),
    ],
)
def test_apostrophes_and_malformed_delimiters_do_not_hide_targets(
    question: str, expected_target: str
) -> None:
    route = route_conversation_intent(question, ())

    assert route.kind == "conversation_transform"
    assert route.target_text == expected_target


def test_named_prior_target_takes_precedence_over_quoted_format_phrase() -> None:
    turns = (PriorTurn(role="assistant", text="The pump was restarted."),)
    route = route_conversation_intent(
        'Summarize your previous answer in "three bullets".', turns
    )

    assert route.kind == "conversation_transform"
    assert route.source == "prior_assistant_turn"
    assert route.target_text == "The pump was restarted."
    assert route.instruction == "summarize in 3 bullets"


def test_explicit_target_conflicting_with_named_prior_turn_clarifies() -> None:
    turns = (PriorTurn(role="assistant", text="The pump was restarted."),)
    route = route_conversation_intent(
        'Summarize your previous answer as "a different statement".', turns
    )

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_target_ambiguous"


def test_multiple_delimited_targets_clarify_instead_of_guessing() -> None:
    route = route_conversation_intent(
        'Summarize "the first statement" and "the second statement".', ()
    )

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_target_ambiguous"


def test_named_missing_prior_turn_clarifies_without_target() -> None:
    route = route_conversation_intent("Rewrite my previous question.", ())

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_target_missing"


def test_unsupported_output_format_fails_closed() -> None:
    route = route_conversation_intent('Summarize this as a poem: "Exact text."', ())

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_request_unsupported"


@pytest.mark.parametrize(
    "question",
    [
        "Summarize your previous answer in exactly two sentences.",
        'Summarize your previous answer in "exactly two sentences".',
        "Rewrite your previous answer with a friendly tone.",
        "Rewrite your previous answer with a sarcastic tone.",
        "Summarize your previous answer for a beginner.",
        "Summarize your previous answer in a calm voice.",
        "Summarize your previous answer as a numbered list.",
        "Summarize your previous answer in 100 bullets.",
    ],
)
def test_unsupported_options_are_not_silently_dropped(question: str) -> None:
    turns = (PriorTurn(role="assistant", text="The pump was restarted."),)
    route = route_conversation_intent(question, turns)

    assert route.kind == "clarification_required"
    assert route.clarification_reason == "transform_request_unsupported"


def test_transform_request_contains_only_target_and_allowlisted_instruction() -> None:
    request = build_transform_request(
        target_text="Private target text",
        instruction="summarize in 3 bullets",
        operation="summarize",
        model="local-test-model",
        max_output_tokens=200,
    )
    message_text = "\n".join(message.content for message in request.messages)

    assert request.metadata["prompt_contract"] == TRANSFORM_PROMPT_CONTRACT_ID
    assert request.temperature == 0.0
    assert "Private target text" in message_text
    assert "unrelated previous turn" not in message_text
    assert request.response_format is not None
    assert request.response_format["json_schema"]["strict"] is True


def test_transform_response_requires_exact_nonempty_schema() -> None:
    assert (
        parse_transform_response(
            json.dumps({"transformed_text": "A concise summary."}),
            max_output_tokens=100,
        )
        == "A concise summary."
    )
    invalid = (
        "{}",
        '{"transformed_text":" "}',
        '{"transformed_text":"ok","citation":"invented"}',
        '{"transformed_text":"a","transformed_text":"b"}',
        "not-json",
    )
    for content in invalid:
        with pytest.raises(AppError) as error:
            parse_transform_response(content, max_output_tokens=100)
        assert error.value.code is ErrorCode.RESPONSE_PARSE_ERROR


def test_trace_store_reads_v1_without_rewriting_historical_record(
    tmp_path: Path,
) -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_DATA_DIR": str(tmp_path / "data")},
    )
    trace_id = allocate_conversation_trace_id()
    record = ConversationTraceRecord(
        schema_version=LEGACY_CONVERSATION_TRACE_SCHEMA_VERSION,
        conversation_trace_id=trace_id,
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
        question_char_count=10,
        prior_turn_count=0,
        resolver_invoked=False,
        resolver_outcome="bypassed",
        context_used=False,
        status="answered",
        query_trace_id=None,
    )
    store = ConversationTraceStore(settings)
    store._root.mkdir(parents=True, exist_ok=True)
    path = store._path(trace_id)
    original = record.model_dump_json()
    path.write_text(original, encoding="utf-8")

    loaded = store.get(trace_id)

    assert loaded is not None
    assert loaded.schema_version == LEGACY_CONVERSATION_TRACE_SCHEMA_VERSION
    assert path.read_text(encoding="utf-8") == original


def _direct_runtime(tmp_path: Path, response: str = '{"transformed_text":"Done."}'):
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_DATA_DIR": str(tmp_path / "data")},
    )
    generator = FakeGenerator(default_response=response)
    workspace = SimpleNamespace(
        status=WorkspaceStatus.ACTIVE,
        revision=4,
        current_snapshot_id="snap_frozen",
        backing_corpus_name="workspace_test",
    )
    runtime = SimpleNamespace(
        settings=settings,
        resources=SimpleNamespace(generator_client=generator),
        publication=SimpleNamespace(
            resolve_snapshot=lambda *_args: object(),
        ),
        require_ready=lambda: None,
    )
    return runtime, generator, workspace


@pytest.mark.parametrize(
    "question",
    [
        'Rewrite this for a beginner: "TARGET_SECRET device is operational."',
        'Summarize the following report excerpt: "The pump stopped at noon."',
        'Translate this section into Spanish: "The pump is ready."',
        'Summarize this: "The text contains [instructions](https://example.org/guide)."',
    ],
)
def test_orchestration_transform_skips_resolver_and_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, question: str
) -> None:
    runtime, generator, workspace = _direct_runtime(tmp_path)
    scope = ProductTraceSourceScope(
        workspace_id="ws_test",
        workspace_revision=4,
        mode="all_active",
        source_ids=[],
        document_ids=[],
    )
    monkeypatch.setattr(
        conversation_turn.WorkspaceStore,
        "get",
        lambda _self, _workspace_id: workspace,
    )
    monkeypatch.setattr(
        conversation_turn,
        "_resolve_workspace_source_scope",
        lambda *_args, **_kwargs: (scope, [], []),
    )
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("transform called the resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("transform called retrieval"),
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime,
        workspace_id="ws_test",
        question=question,
    )

    assert outcome.response_kind == "conversation_transform"
    assert outcome.status == "transformed"
    assert outcome.query_trace_id is None
    assert outcome.response_kind == "conversation_transform"
    assert generator.generate_calls == 1
    trace = ConversationTraceStore(runtime.settings).get(outcome.conversation_trace_id)
    assert trace is not None
    assert trace.resolver_invoked is False
    assert trace.retrieval_question_sha256 is None
    assert trace.query_trace_id is None
    assert "TARGET_SECRET" not in trace.model_dump_json()


def test_orchestration_clarification_skips_generator_and_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, generator, workspace = _direct_runtime(tmp_path)
    scope = ProductTraceSourceScope(
        workspace_id="ws_test",
        workspace_revision=4,
        mode="all_active",
        source_ids=[],
        document_ids=[],
    )
    monkeypatch.setattr(
        conversation_turn.WorkspaceStore,
        "get",
        lambda _self, _workspace_id: workspace,
    )
    monkeypatch.setattr(
        conversation_turn,
        "_resolve_workspace_source_scope",
        lambda *_args, **_kwargs: (scope, [], []),
    )
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("clarification called the resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("clarification called retrieval"),
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime, workspace_id="ws_test", question="Translate this."
    )

    assert outcome.response_kind == "clarification"
    assert outcome.status == "clarification_required"
    assert outcome.query_trace_id is None
    assert generator.generate_calls == 0


def test_named_prior_transform_skips_resolver_and_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, generator, workspace = _direct_runtime(tmp_path)
    scope = ProductTraceSourceScope(
        workspace_id="ws_test",
        workspace_revision=4,
        mode="all_active",
        source_ids=[],
        document_ids=[],
    )
    monkeypatch.setattr(
        conversation_turn.WorkspaceStore,
        "get",
        lambda _self, _workspace_id: workspace,
    )
    monkeypatch.setattr(
        conversation_turn,
        "_resolve_workspace_source_scope",
        lambda *_args, **_kwargs: (scope, [], []),
    )
    monkeypatch.setattr(
        conversation_turn,
        "resolve_conversation_context",
        lambda *_args, **_kwargs: pytest.fail("prior transform called the resolver"),
    )
    monkeypatch.setattr(
        conversation_turn,
        "run_bound_snapshot_query",
        lambda *_args, **_kwargs: pytest.fail("prior transform called retrieval"),
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime,
        workspace_id="ws_test",
        question="Summarize your previous answer about the report in three bullets.",
        prior_turns=[
            {"role": "user", "text": "What happened to the pump?"},
            {"role": "assistant", "text": "The report says the pump restarted."},
        ],
    )

    assert outcome.response_kind == "conversation_transform"
    assert outcome.status == "transformed"
    assert outcome.transformation_source == "prior_assistant_turn"
    assert outcome.query_trace_id is None
    assert generator.generate_calls == 1
    trace = ConversationTraceStore(runtime.settings).get(outcome.conversation_trace_id)
    assert trace is not None
    assert trace.transform_source_kind == "prior_assistant_turn"
    assert trace.resolver_invoked is False
    assert trace.query_trace_id is None


@pytest.mark.parametrize(
    ("question", "with_prior_history"),
    [
        ("What does the selected report say about the pump?", False),
        ("Summarize what the report says about chapter 2.", False),
        ("Verify your previous answer against the report.", True),
        ("Summarize your previous answer and verify it against the report.", True),
        ("Summarize your previous answer based on the report.", True),
        ("Update your previous answer with facts from the report.", True),
        ("Summarize section 4 of the maintenance manual.", False),
        ('Summarize the report: "The pump stopped at noon."', False),
        (
            'Summarize section 4 of the maintenance manual: "Supplied excerpt."',
            False,
        ),
        (
            'Summarize the supplied excerpt from the report: "Quoted text."',
            False,
        ),
        ("Summarize [Maintenance Manual](https://example.org/manual).", False),
    ],
)
def test_source_oriented_request_stays_on_grounded_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    with_prior_history: bool,
) -> None:
    runtime, _generator, workspace = _direct_runtime(tmp_path)
    scope = ProductTraceSourceScope(
        workspace_id="ws_test",
        workspace_revision=4,
        mode="all_active",
        source_ids=[],
        document_ids=[],
    )
    calls = {"resolver": 0, "query": 0}
    observed = {"resolver_question": None}

    def resolver(_runtime, *, current_question, **_kwargs):
        calls["resolver"] += 1
        observed["resolver_question"] = current_question
        return SimpleNamespace(
            outcome="resolved",
            retrieval_question=current_question,
            context_used=False,
            resolver_invoked=False,
        )

    def query(*_args, **_kwargs):
        calls["query"] += 1
        return SimpleNamespace(
            status="answered",
            citations=[],
            binding=SimpleNamespace(
                product_mode_id="grounded-v1", snapshot_id="snap_frozen"
            ),
            answer_blocks=[{"text": "Grounded answer.", "citation_refs": ["c1"]}],
            trace_id="trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            abstention_reason=None,
            answer="Grounded answer.",
        )

    monkeypatch.setattr(
        conversation_turn.WorkspaceStore,
        "get",
        lambda _self, _workspace_id: workspace,
    )
    monkeypatch.setattr(
        conversation_turn,
        "_resolve_workspace_source_scope",
        lambda *_args, **_kwargs: (scope, [], []),
    )
    monkeypatch.setattr(conversation_turn, "resolve_conversation_context", resolver)
    monkeypatch.setattr(conversation_turn, "run_bound_snapshot_query", query)
    monkeypatch.setattr(
        conversation_turn,
        "_enrich_workspace_citations",
        lambda citations, **_kwargs: citations,
    )

    outcome = conversation_turn.run_conversation_turn(
        runtime,
        workspace_id="ws_test",
        question=question,
        prior_turns=(
            [
                {"role": "user", "text": "What happened to the pump?"},
                {"role": "assistant", "text": "The report says it restarted."},
            ]
            if with_prior_history
            else None
        ),
    )

    assert calls == {"resolver": 1, "query": 1}
    assert observed["resolver_question"] == question
    assert outcome.status == "answered"
    assert outcome.response_kind == "grounded_answer"
    assert outcome.query_trace_id == "trace_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
