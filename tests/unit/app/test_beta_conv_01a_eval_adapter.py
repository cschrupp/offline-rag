from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
import scripts.beta_conv_01a_eval_adapter as adapter_module
from scripts.beta_conv_01a_eval_adapter import (
    ConversationApiEvidenceAdapter,
    EvaluationInstrumentation,
    SourceAliasMap,
)

from offline_rag.app.conversation.planner import PLANNER_CONTRACT_ID
from offline_rag.core.ids import GROUNDED_ANSWER_V2


def _case(case_id: str, request: dict[str, object]) -> dict[str, object]:
    canonical = json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "case_id": case_id,
        "request": request,
        "request_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _aliases() -> SourceAliasMap:
    return SourceAliasMap.from_active_sources(
        {"source_manual": "manual.txt", "source_report": "report.txt"},
        [
            {"source_id": "live-manual", "display_name": "manual.txt", "active": True},
            {"source_id": "live-report", "display_name": "report.txt", "active": True},
        ],
    )


class _JsonResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {
            "conversation_trace_id": "private-conversation-trace-id",
            "query_trace_id": "private-query-trace-id",
            "snapshot_id": "private-snapshot-id",
            "status": "answered",
            "response_kind": "grounded_answer",
            "citations": [
                {"source_id": "live-manual", "evidence_unit_id": "evidence-1"}
            ],
        }


class _EvidenceClient:
    def __init__(self, instrumentation: EvaluationInstrumentation) -> None:
        self.instrumentation = instrumentation
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(
        self, url: str, *, json: dict[str, object], timeout: float
    ) -> _JsonResponse:
        self.calls.append((url, json))
        self.instrumentation.record_generator_call(PLANNER_CONTRACT_ID)
        self.instrumentation.record_generator_duration(PLANNER_CONTRACT_ID, 20.0)
        self.instrumentation._increment("retrieval_calls")
        self.instrumentation.record_generator_call(GROUNDED_ANSWER_V2)
        return _JsonResponse()


def test_source_alias_map_requires_exact_active_one_to_one_population() -> None:
    active = [
        {"source_id": "live-manual", "display_name": "manual.txt", "active": True},
        {"source_id": "live-report", "display_name": "report.txt", "active": True},
    ]

    with pytest.raises(ValueError, match="exactly one active source"):
        SourceAliasMap.from_active_sources(
            {"source_manual": "missing.txt", "source_report": "report.txt"},
            active,
        )
    with pytest.raises(ValueError, match="population differs"):
        SourceAliasMap.from_active_sources({"source_manual": "manual.txt"}, active)
    with pytest.raises(ValueError, match="distinct created source IDs"):
        SourceAliasMap.from_active_sources(
            {"source_manual": "manual.txt", "source_report": "manual.txt"},
            [active[0]],
        )


def test_source_alias_map_accepts_api_active_source_projection() -> None:
    aliases = SourceAliasMap.from_active_sources(
        {"source_manual": "manual.txt", "source_report": "report.txt"},
        [
            {"source_id": "live-manual", "display_name": "manual.txt"},
            {"source_id": "live-report", "display_name": "report.txt"},
        ],
    )
    assert set(aliases.alias_to_source_id.values()) == {
        "live-manual",
        "live-report",
    }


def test_source_alias_map_rejects_invalid_scopes_and_unknown_citations() -> None:
    aliases = _aliases()
    assert aliases.translate_request_scope(None) is None
    assert aliases.translate_request_scope(["source_report"]) == ["live-report"]
    assert aliases.normalize_citations(
        [{"source_id": "live-manual"}, {"source_id": "live-report"}]
    ) == (["source_manual", "source_report"], True)
    assert aliases.normalize_citations([{"source_id": "unexpected-live-id"}]) == (
        [],
        False,
    )
    with pytest.raises(ValueError, match="nonempty alias list"):
        aliases.translate_request_scope([])
    with pytest.raises(ValueError, match="duplicate aliases"):
        aliases.translate_request_scope(["source_manual", "source_manual"])
    with pytest.raises(ValueError, match="unknown alias"):
        aliases.translate_request_scope(["source_unknown"])


class _TimeoutClient:
    def __init__(self, instrumentation: EvaluationInstrumentation) -> None:
        self.instrumentation = instrumentation

    def post(self, url: str, *, json: dict[str, object], timeout: float) -> object:
        self.instrumentation.record_generator_call("seneca_conversation_task_plan_v1")
        self.instrumentation.record_generator_duration(
            "seneca_conversation_task_plan_v1", 123.0
        )
        raise httpx.ReadTimeout("private request detail")


def test_adapter_retains_timeout_and_planner_stage_timing_without_sensitive_text() -> (
    None
):
    instrumentation = EvaluationInstrumentation(runtime=object())
    adapter = ConversationApiEvidenceAdapter(
        client=_TimeoutClient(instrumentation),
        runtime=SimpleNamespace(
            settings=SimpleNamespace(
                conversation=SimpleNamespace(router_mode="planner")
            )
        ),
        workspace_id="workspace-private-id",
        source_aliases=_aliases(),
        instrumentation=instrumentation,
    )

    observation = adapter.execute(
        _case(
            "timeout-case",
            {
                "question": "What does the maintenance manual say?",
                "source_ids": ["source_manual"],
                "prior_turns": [],
            },
        ),
        arm="planner",
        repeat=1,
        measurement_phase="warm_interactive",
        timeout=1,
    )

    assert observation["terminal_state"] == "timeout"
    assert observation["reason_code"] == "request_timeout"
    assert observation["planner_calls"] == 1
    assert observation["planner_elapsed_ms"] == 123.0
    assert observation["planner_validation"] == "unavailable"
    assert len(observation["request_sha256"]) == 64
    assert "private" not in repr(observation)
    assert "workspace-private-id" not in repr(observation)


def test_adapter_rejects_arm_that_differs_from_application_configuration() -> None:
    instrumentation = EvaluationInstrumentation(runtime=object())
    adapter = ConversationApiEvidenceAdapter(
        client=object(),
        runtime=SimpleNamespace(
            settings=SimpleNamespace(
                conversation=SimpleNamespace(router_mode="planner")
            )
        ),
        workspace_id="workspace-id",
        source_aliases=_aliases(),
        instrumentation=instrumentation,
    )

    with pytest.raises(ValueError, match="does not match"):
        adapter.execute(
            _case(
                "case",
                {
                    "question": "What does the maintenance manual say?",
                    "source_ids": None,
                    "prior_turns": [],
                },
            ),
            arm="legacy",
            repeat=1,
            measurement_phase="cold_start",
            timeout=1,
        )


def test_adapter_normalizes_successful_canonical_response_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_trace = SimpleNamespace(
        snapshot_id="private-snapshot-id",
        source_scope=SimpleNamespace(mode="selected", source_ids=["live-manual"]),
        planner_operation="grounded_query",
        planner_validation="valid",
        planner_reason_code=None,
        planner_duration_ms=20,
        query_trace_id="private-query-trace-id",
        transform_source_kind=None,
        transform_source_role=None,
        transform_source_turn_ordinal=None,
        transform_target_sha256=None,
        transform_target_char_count=None,
        transform_operation=None,
    )
    query_trace = SimpleNamespace(
        snapshot_id="private-snapshot-id",
        execution=SimpleNamespace(citation_evidence_unit_ids=["evidence-1"]),
    )

    class _ConversationTraceStore:
        def __init__(self, _settings: object) -> None:
            pass

        def get(self, _trace_id: str) -> object:
            return conversation_trace

    class _ProductTraceStore:
        def __init__(self, _settings: object) -> None:
            pass

        def get(self, _trace_id: str) -> object:
            return query_trace

    monkeypatch.setattr(
        adapter_module, "ConversationTraceStore", _ConversationTraceStore
    )
    monkeypatch.setattr(adapter_module, "ProductTraceStore", _ProductTraceStore)
    instrumentation = EvaluationInstrumentation(runtime=object())
    client = _EvidenceClient(instrumentation)
    adapter = ConversationApiEvidenceAdapter(
        client=client,
        runtime=SimpleNamespace(
            settings=SimpleNamespace(
                conversation=SimpleNamespace(router_mode="planner")
            )
        ),
        workspace_id="private-workspace-id",
        source_aliases=_aliases(),
        instrumentation=instrumentation,
    )

    observation = adapter.execute(
        _case(
            "grounded-case",
            {
                "question": "What does the maintenance manual say?",
                "source_ids": ["source_manual"],
                "prior_turns": [],
            },
        ),
        arm="planner",
        repeat=1,
        measurement_phase="warm_interactive",
        timeout=1,
    )

    assert client.calls[0][0].endswith(
        "/v1/workspaces/private-workspace-id/conversation/turn"
    )
    assert client.calls[0][1]["source_ids"] == ["live-manual"]
    assert observation["response_status"] == "answered"
    assert observation["citation_source_ids"] == ["source_manual"]
    assert observation["citations_valid"] is True
    assert observation["snapshot_consistent"] is True
    assert observation["source_scope_consistent"] is True
    assert observation["query_trace_present"] is True
    assert observation["query_trace_link_consistent"] is True
    assert observation["planner_validation"] == "valid"
    assert observation["planner_elapsed_ms"] == 20
    assert observation["answer_generation_calls"] == 1
    assert observation["source_alias_mapping_sha256"] == adapter._source_aliases.sha256
    assert "live-manual" not in repr(observation)
    assert "private-workspace-id" not in repr(observation)


def test_adapter_rejects_dataset_request_hash_mismatch_before_api_call() -> None:
    instrumentation = EvaluationInstrumentation(runtime=object())
    client = _EvidenceClient(instrumentation)
    adapter = ConversationApiEvidenceAdapter(
        client=client,
        runtime=SimpleNamespace(
            settings=SimpleNamespace(
                conversation=SimpleNamespace(router_mode="planner")
            )
        ),
        workspace_id="private-workspace-id",
        source_aliases=_aliases(),
        instrumentation=instrumentation,
    )

    case = _case(
        "wrong-request-hash",
        {
            "question": "What does the maintenance manual say?",
            "source_ids": ["source_manual"],
            "prior_turns": [],
        },
    )
    case["request_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="does not match dataset record"):
        adapter.execute(
            case,
            arm="planner",
            repeat=1,
            measurement_phase="warm_interactive",
            timeout=1,
        )
    assert client.calls == []


def test_adapter_rejects_query_trace_id_not_linked_from_conversation_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation_trace = SimpleNamespace(
        snapshot_id="private-snapshot-id",
        query_trace_id="different-query-trace-id",
        source_scope=SimpleNamespace(mode="selected", source_ids=["live-manual"]),
        planner_operation="grounded_query",
        planner_validation="valid",
        planner_reason_code=None,
        planner_duration_ms=20,
        transform_source_kind=None,
        transform_source_role=None,
        transform_source_turn_ordinal=None,
        transform_target_sha256=None,
        transform_target_char_count=None,
        transform_operation=None,
    )
    query_trace = SimpleNamespace(
        snapshot_id="private-snapshot-id",
        execution=SimpleNamespace(citation_evidence_unit_ids=["evidence-1"]),
    )

    class _ConversationTraceStore:
        def __init__(self, _settings: object) -> None:
            pass

        def get(self, _trace_id: str) -> object:
            return conversation_trace

    class _ProductTraceStore:
        def __init__(self, _settings: object) -> None:
            pass

        def get(self, _trace_id: str) -> object:
            return query_trace

    monkeypatch.setattr(
        adapter_module, "ConversationTraceStore", _ConversationTraceStore
    )
    monkeypatch.setattr(adapter_module, "ProductTraceStore", _ProductTraceStore)
    instrumentation = EvaluationInstrumentation(runtime=object())
    adapter = ConversationApiEvidenceAdapter(
        client=_EvidenceClient(instrumentation),
        runtime=SimpleNamespace(
            settings=SimpleNamespace(
                conversation=SimpleNamespace(router_mode="planner")
            )
        ),
        workspace_id="private-workspace-id",
        source_aliases=_aliases(),
        instrumentation=instrumentation,
    )
    observation = adapter.execute(
        _case(
            "query-trace-mismatch",
            {
                "question": "What does the maintenance manual say?",
                "source_ids": ["source_manual"],
                "prior_turns": [],
            },
        ),
        arm="planner",
        repeat=1,
        measurement_phase="warm_interactive",
        timeout=1,
    )

    assert observation["query_trace_present"] is True
    assert observation["query_trace_link_consistent"] is False
    assert observation["adapter_error_category"] == "query_trace_link_mismatch"
