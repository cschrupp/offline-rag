"""Level-C passive instrumentation substrate unit tests (fakes only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from offline_rag.config.models import AppSettings
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.domain.indexing import (
    ContextAssemblyDiagnostics,
    EvidenceUnit,
    HybridRerankContextResult,
)
from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
from offline_rag.evaluation.performance_14.contracts import (
    DerivedLatencyStatsV1,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceGenerationTelemetryV1,
    PerformanceLevelCAttemptV1,
    PerformanceLevelCStageDispositionV1,
    PerformanceResourceObservationV1,
)
from offline_rag.evaluation.performance_14.identity import (
    case_semantic_payload,
    compute_case_identity_hash,
    compute_config_identity_hash,
    compute_run_identity_hash,
    compute_suite_identity_hash,
)
from offline_rag.evaluation.performance_14.level_c import (
    LevelCTimeline,
    PassiveHybridRerankRetrieverDelegate,
    PassiveLevelCExecutor,
    PassiveLevelCGenerator,
    build_generation_telemetry,
    build_level_c_attempt,
    classify_level_c_terminal,
    derive_level_c_stage_stats,
    execute_level_c_attempt,
    extract_completion_tokens,
)
from offline_rag.evaluation.performance_14.report import render_report_markdown
from offline_rag.evaluation.performance_14.suite_14c import (
    build_suite_plan_14c,
    effective_config_id_14c,
    scientific_config_payload_14c,
)
from offline_rag.generation.fake import FakeGenerator
from offline_rag.generation.orchestrate import (
    GroundedAnswerError,
    GroundedAnswerOrchestrator,
)
from offline_rag.generation.prompt import build_prompt_grounded_v1
from offline_rag.generation.protocol import GeneratorRequest, GeneratorResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_PERFSUITE = (
    "perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba"
)
LOCKED_PERFCFG = (
    "perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d"
)
ACCEPTED_14C_RUN = (
    "perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca"
)


class _FakeClock:
    def __init__(self, start: float = 100.0, step: float = 0.5) -> None:
        self._t = start
        self._step = step

    def __call__(self) -> float:
        value = self._t
        self._t += self._step
        return value


def _disp(status: str, reason: str | None = None) -> PerformanceLevelCStageDispositionV1:
    return PerformanceLevelCStageDispositionV1(
        status=status, reason=reason
    )  # type: ignore[arg-type]


def _obs(
    stage_id: str,
    status: str,
    *,
    duration: float | None = 0.1,
    is_warmup: bool = False,
    failure_reason: str | None = None,
    exclusion_reason: str | None = None,
) -> PerformanceBenchmarkObservationV1:
    return PerformanceBenchmarkObservationV1(
        observation_status=status,  # type: ignore[arg-type]
        stage_id=stage_id,
        duration_seconds=duration,
        is_warmup=is_warmup,
        failure_reason=failure_reason,
        exclusion_reason=exclusion_reason,
    )


def _full_dispositions(**overrides: PerformanceLevelCStageDispositionV1):
    base = {
        "context_assembly": _disp("valid"),
        "generation": _disp("valid"),
        "citation_validation": _disp("valid"),
        "end_to_end": _disp("valid"),
    }
    base.update(overrides)
    return base


def _answered_attempt(
    *,
    attempt_index: int = 0,
    is_warmup: bool = False,
    duration: float = 0.2,
) -> PerformanceLevelCAttemptV1:
    return PerformanceLevelCAttemptV1(
        attempt_index=attempt_index,
        is_warmup=is_warmup,
        subject_identity="q1",
        terminal_status="answered",
        generator_invoked=True,
        stage_dispositions=_full_dispositions(),
        context_assembly_observation=_obs(
            "context_assembly", "valid", duration=duration
        ),
        generation_observation=_obs("generation", "valid", duration=duration),
        citation_validation_observation=_obs(
            "citation_validation", "valid", duration=duration
        ),
        end_to_end_observation=_obs("end_to_end", "valid", duration=duration * 4),
        generation_telemetry=build_generation_telemetry(
            generator_invoked=True, usage={"completion_tokens": 7}
        ),
    )


def _settings() -> AppSettings:
    return AppSettings().model_copy(
        update={
            "generation": AppSettings().generation.model_copy(
                update={
                    "enabled": True,
                    "model": "test-model",
                    "approved_models": ["test-model"],
                    "approved_endpoints": ["http://127.0.0.1:11434/v1"],
                    "base_url": "http://127.0.0.1:11434/v1",
                }
            )
        }
    )


def _unit(ev_id: str = "ev_A") -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=ev_id,
        source_chunk_id=f"chunk_{ev_id}",
        kind="child",
        text="max pressure is 100 psi",
        clipped=False,
        token_count=5,
        primary_anchor_chunk_id="anchor_1",
        contributing_anchor_chunk_ids=["anchor_1"],
        document_id="doc1",
        section_path=["Limits"],
        page_start=1,
        page_end=1,
    )


def _context(units: list[EvidenceUnit] | None = None) -> HybridRerankContextResult:
    units = units if units is not None else [_unit()]
    assembled = "\n\n".join(u.text for u in units)
    return HybridRerankContextResult(
        query="pressure?",
        evidence_units=units,
        assembled_text=assembled,
        context_token_count=len(assembled.split()),
        max_context_tokens=6000,
        context_config_hash="ctxcfg_test",
        anchors=[],
        dense_index_id="dense_x",
        lexical_index_id="lex_x",
        fusion_config_hash="fuscfg_x",
        reranker_config_hash="rrkcfg_x",
        diagnostics=ContextAssemblyDiagnostics(
            requested_anchor_k=5,
            actual_anchor_count=1,
            evidence_unit_count=len(units),
            context_token_count=len(assembled.split()),
            stop_reason="completed",
        ),
        metadata={"chunk_set_id": "chunkset_test", "latency_ms": {"total": 1}},
    )


def _result(**overrides: Any) -> GroundedAnswerResult:
    payload: dict[str, Any] = {
        "method": "query",
        "query": "pressure?",
        "status": "answered",
        "answer_text": "100 psi",
        "citations": [],
        "generator_invoked": True,
        "attempt_count": 1,
        "generation_config_hash": "gencfg_test",
        "diagnostics": {},
        "metadata": {},
    }
    payload.update(overrides)
    return GroundedAnswerResult(**payload)


@pytest.mark.parametrize(
    ("usage", "availability", "count"),
    [
        ({"completion_tokens": 12}, "available", 12),
        ({"completion_tokens": 0}, "available", 0),
        ({"completion_tokens": True}, "unavailable", None),
        ({"completion_tokens": -1}, "unavailable", None),
        ({"completion_tokens": 1.5}, "unavailable", None),
        ({"completion_tokens": "3"}, "unavailable", None),
        ({"completion_tokens": None}, "unavailable", None),
        ({}, "unavailable", None),
        ({"prompt_tokens": 9, "total_tokens": 12}, "unavailable", None),
        (None, "unavailable", None),
    ],
)
def test_extract_completion_tokens(usage, availability, count) -> None:
    got_av, got_count, source = extract_completion_tokens(usage)
    assert got_av == availability
    assert got_count == count
    assert source == (
        "provider_usage_completion_tokens"
        if availability == "available"
        else "unavailable"
    )


def test_generation_telemetry_rejects_fabricated_ttft() -> None:
    with pytest.raises(ValidationError):
        PerformanceGenerationTelemetryV1(
            generator_invoked=True,
            ttft_availability="unevaluable",
            ttft_seconds=0.1,
            decode_availability="unevaluable",
            decode_seconds=None,
            output_token_count_availability="unavailable",
            output_token_count=None,
            output_token_count_source="unavailable",
            tokens_per_second_availability="unevaluable",
            tokens_per_second=None,
        )


def test_retriever_delegate_passivity() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    result = object()
    inner = MagicMock()
    inner.retrieve.return_value = result
    delegate = PassiveHybridRerankRetrieverDelegate(inner, timeline)
    out = delegate.retrieve(query="q", corpus_name="c", top_k=3)
    assert out is result
    inner.retrieve.assert_called_once_with(query="q", corpus_name="c", top_k=3)
    assert timeline.t1 is not None


def test_generator_proxy_passivity_and_single_call() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    request = build_prompt_grounded_v1(
        query="q",
        evidence_units=[_unit()],
        model="test-model",
        temperature=0.0,
        max_output_tokens=10,
    )
    response = GeneratorResponse(
        content='{"abstain":true,"answer":null,"citation_ids":[]}'
    )
    inner = MagicMock()
    inner.generate.return_value = response
    proxy = PassiveLevelCGenerator(inner, timeline)
    out = proxy.generate(request)
    assert out is response
    assert proxy.call_count == 1
    assert proxy.last_request is request
    assert timeline.t3 is not None and timeline.t4 is not None
    assert timeline.t4 > timeline.t3
    inner.generate.assert_called_once_with(request)


def test_generator_proxy_preserves_exception_without_t4() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    inner = MagicMock()
    inner.generate.side_effect = RuntimeError("boom")
    proxy = PassiveLevelCGenerator(inner, timeline)
    req = GeneratorRequest(
        messages=(),
        model="m",
        temperature=0.0,
        max_output_tokens=1,
    )
    with pytest.raises(RuntimeError, match="boom"):
        proxy.generate(req)
    assert timeline.t3 is not None
    assert timeline.t4 is None
    assert proxy.time_to_error_seconds is not None


def test_executor_request_passthrough() -> None:
    settings = _settings()
    timeline = LevelCTimeline(clock=_FakeClock())
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "ok", "citation_ids": ["ev_A"]}
        )
    )
    proxy = PassiveLevelCGenerator(fake, timeline)
    executor = PassiveLevelCExecutor(settings, generator=proxy, timeline=timeline)
    units = [_unit()]
    req1 = executor._build_generator_request(
        query="pressure?", corpus_name="default", evidence_units=units
    )
    plain = PassiveLevelCExecutor(
        settings, generator=fake, timeline=LevelCTimeline(clock=_FakeClock(200.0))
    )
    req2 = plain._build_generator_request(
        query="pressure?", corpus_name="default", evidence_units=units
    )
    assert req1.model == req2.model
    assert req1.temperature == req2.temperature
    assert req1.max_output_tokens == req2.max_output_tokens
    assert req1.messages == req2.messages


def test_orchestrator_result_unchanged_with_instrumentation() -> None:
    settings = _settings()
    timeline = LevelCTimeline(clock=_FakeClock())
    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": ["ev_A"]}
        )
    )
    proxy = PassiveLevelCGenerator(fake, timeline)
    executor = PassiveLevelCExecutor(settings, generator=proxy, timeline=timeline)
    assembler = MagicMock()
    assembler.assemble.return_value = _context()
    orch = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, executor=executor
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]
    attempt = execute_level_c_attempt(
        orch,
        timeline,
        query="pressure?",
        corpus_name="default",
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        generator_proxy=proxy,
    )
    assert attempt.terminal_status == "answered"
    assert attempt.generator_invoked is True
    assert proxy.call_count == 1
    assert attempt.stage_dispositions["generation"].status == "valid"
    assert attempt.stage_dispositions["citation_validation"].status == "valid"
    assert attempt.end_to_end_observation is not None
    assert attempt.generation_observation is not None


def test_timeline_duration_formulas_answered() -> None:
    clock = _FakeClock(start=10.0, step=1.0)
    timeline = LevelCTimeline(clock=clock)
    timeline.mark_t0()
    timeline.mark_t1()
    timeline.mark_t2()
    timeline.mark_t3()
    timeline.mark_t4()
    timeline.mark_t5()
    timeline.mark_t6()
    assert timeline.duration(timeline.t1, timeline.t2) == 1.0
    assert timeline.duration(timeline.t3, timeline.t4) == 1.0
    assert timeline.duration(timeline.t4, timeline.t5) == 1.0
    assert timeline.duration(timeline.t0, timeline.t6) == 6.0
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(),
        usage={"completion_tokens": 3},
    )
    assert attempt.context_assembly_observation.duration_seconds == 1.0
    assert attempt.generation_observation.duration_seconds == 1.0
    assert attempt.citation_validation_observation.duration_seconds == 1.0
    assert attempt.end_to_end_observation.duration_seconds == 6.0


def test_missing_t2_prevents_valid_context_assembly() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    timeline.mark_t0()
    timeline.mark_t1()
    timeline.t3 = timeline.clock()
    timeline.t4 = timeline.clock()
    timeline.t5 = timeline.clock()
    timeline.mark_t6()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(),
    )
    assert attempt.stage_dispositions["context_assembly"].status == (
        "excluded_instrumentation_error"
    )


def test_missing_t4_prevents_valid_generation() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    timeline.mark_t0()
    timeline.mark_t1()
    timeline.mark_t2()
    timeline.mark_t3()
    timeline.mark_generation_error()
    timeline.t5 = timeline.clock()
    timeline.mark_t6()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(
            status="generation_failed",
            answer_text=None,
            generation_failure_reason="timeout",
            generator_invoked=True,
        ),
        generation_time_to_error=0.25,
    )
    assert attempt.stage_dispositions["generation"].status == "failed"
    assert attempt.stage_dispositions["citation_validation"].status == "not_applicable"


def test_t5_alone_does_not_imply_citation_validation() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    for mark in (
        timeline.mark_t0,
        timeline.mark_t1,
        timeline.mark_t2,
        timeline.mark_t3,
        timeline.mark_t4,
        timeline.mark_t5,
        timeline.mark_t6,
    ):
        mark()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(
            status="insufficient_evidence",
            answer_text=None,
            abstention_reason="model_abstain",
            generator_invoked=True,
        ),
    )
    assert attempt.terminal_status == "model_abstain"
    assert attempt.stage_dispositions["citation_validation"].status == "not_applicable"
    assert attempt.citation_validation_observation is None


def test_warmup_excluded_from_percentiles() -> None:
    attempts = [
        _answered_attempt(attempt_index=0, is_warmup=True, duration=9.0),
        _answered_attempt(attempt_index=0, is_warmup=False, duration=1.0),
        _answered_attempt(attempt_index=1, is_warmup=False, duration=3.0),
    ]
    stats = derive_level_c_stage_stats(attempts, "generation")
    assert stats.warmup_count == 1
    assert stats.n == 2
    assert stats.min == 1.0
    assert stats.max == 3.0


def test_classify_terminal_variants() -> None:
    assert classify_level_c_terminal(_result())[0] == "answered"
    assert (
        classify_level_c_terminal(
            _result(
                status="insufficient_evidence",
                answer_text=None,
                abstention_reason="empty_context",
                generator_invoked=False,
            )
        )[0]
        == "insufficient_evidence"
    )
    assert (
        classify_level_c_terminal(
            _result(
                status="insufficient_evidence",
                answer_text=None,
                abstention_reason="model_abstain",
                generator_invoked=True,
            )
        )[0]
        == "model_abstain"
    )
    assert (
        classify_level_c_terminal(None, exception=GroundedAnswerError("ready fail"))[0]
        == "orchestration_failed"
    )


def test_pre_generator_insufficient_evidence_matrix() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    timeline.mark_t0()
    timeline.mark_t1()
    timeline.mark_t6()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(
            status="insufficient_evidence",
            answer_text=None,
            abstention_reason="empty_context",
            generator_invoked=False,
            attempt_count=0,
        ),
    )
    assert attempt.stage_dispositions["context_assembly"].status == "not_applicable"
    assert attempt.stage_dispositions["generation"].status == "not_applicable"
    assert attempt.stage_dispositions["citation_validation"].status == "not_applicable"
    assert attempt.stage_dispositions["end_to_end"].status == "valid"
    assert attempt.context_assembly_observation is None


def test_citation_invalid_matrix() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    for mark in (
        timeline.mark_t0,
        timeline.mark_t1,
        timeline.mark_t2,
        timeline.mark_t3,
        timeline.mark_t4,
        timeline.mark_t5,
        timeline.mark_t6,
    ):
        mark()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(status="citation_invalid", answer_text=None, citations=[]),
    )
    assert attempt.stage_dispositions["citation_validation"].status == "failed"
    assert attempt.citation_validation_observation.failure_reason == "citation_invalid"


def test_schema_invalid_after_response_matrix() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    for mark in (
        timeline.mark_t0,
        timeline.mark_t1,
        timeline.mark_t2,
        timeline.mark_t3,
        timeline.mark_t4,
        timeline.mark_t5,
        timeline.mark_t6,
    ):
        mark()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(
            status="generation_failed",
            answer_text=None,
            generation_failure_reason="output_schema_invalid",
            generator_invoked=True,
        ),
        usage={"completion_tokens": 4},
    )
    assert attempt.stage_dispositions["generation"].status == "valid"
    assert attempt.stage_dispositions["citation_validation"].status == "failed"
    assert (
        attempt.citation_validation_observation.failure_reason == "output_schema_invalid"
    )


def test_orchestration_failed_matrix() -> None:
    timeline = LevelCTimeline(clock=_FakeClock())
    timeline.mark_t0()
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=None,
        exception=GroundedAnswerError("not ready"),
    )
    assert attempt.terminal_status == "orchestration_failed"
    assert attempt.stage_dispositions["end_to_end"].status == "failed"
    assert attempt.stage_dispositions["generation"].status == "not_applicable"


def test_flc_d3_exclusion_not_failure_and_partition() -> None:
    valid = _answered_attempt(attempt_index=0, duration=1.0)
    failed = PerformanceLevelCAttemptV1(
        attempt_index=1,
        is_warmup=False,
        subject_identity="q1",
        terminal_status="generation_failed",
        generation_failure_reason="timeout",
        generator_invoked=True,
        stage_dispositions=_full_dispositions(
            generation=_disp("failed", "timeout"),
            citation_validation=_disp("not_applicable", "no_raw_generation_response"),
        ),
        context_assembly_observation=_obs("context_assembly", "valid", duration=0.1),
        generation_observation=_obs(
            "generation", "failed", duration=0.2, failure_reason="timeout"
        ),
        citation_validation_observation=None,
        end_to_end_observation=_obs("end_to_end", "valid", duration=1.0),
        generation_telemetry=build_generation_telemetry(generator_invoked=True),
    )
    excluded = PerformanceLevelCAttemptV1(
        attempt_index=2,
        is_warmup=False,
        subject_identity="q1",
        terminal_status="answered",
        generator_invoked=True,
        stage_dispositions=_full_dispositions(
            generation=_disp("excluded_instrumentation_error", "clock_fault"),
        ),
        context_assembly_observation=_obs("context_assembly", "valid", duration=0.1),
        generation_observation=_obs(
            "generation",
            "excluded_instrumentation_error",
            duration=None,
            exclusion_reason="clock_fault",
        ),
        citation_validation_observation=_obs(
            "citation_validation", "valid", duration=0.1
        ),
        end_to_end_observation=_obs("end_to_end", "valid", duration=1.0),
        generation_telemetry=build_generation_telemetry(generator_invoked=True),
    )
    na = PerformanceLevelCAttemptV1(
        attempt_index=3,
        is_warmup=False,
        subject_identity="q1",
        terminal_status="insufficient_evidence",
        abstention_reason="empty_context",
        generator_invoked=False,
        stage_dispositions={
            "context_assembly": _disp(
                "not_applicable", "generator_request_not_finalized"
            ),
            "generation": _disp("not_applicable", "generator_not_invoked"),
            "citation_validation": _disp(
                "not_applicable", "no_raw_generation_response"
            ),
            "end_to_end": _disp("valid"),
        },
        context_assembly_observation=None,
        generation_observation=None,
        citation_validation_observation=None,
        end_to_end_observation=_obs("end_to_end", "valid", duration=0.5),
        generation_telemetry=build_generation_telemetry(generator_invoked=False),
    )
    stats = derive_level_c_stage_stats([valid, failed, excluded, na], "generation")
    assert stats.valid_count == 1
    assert stats.failure_count == 1
    assert stats.instrumentation_exclusion_count == 1
    assert stats.not_applicable_count == 1
    assert stats.attempted_count == 3
    assert stats.attempted_count + stats.not_applicable_count == 4
    assert stats.n == 1
    assert stats.min == 1.0


def test_inconsistent_disposition_observation_fails() -> None:
    with pytest.raises(ValidationError):
        PerformanceLevelCAttemptV1(
            attempt_index=0,
            is_warmup=False,
            subject_identity="q1",
            terminal_status="answered",
            generator_invoked=True,
            stage_dispositions=_full_dispositions(
                generation=_disp("failed", "timeout"),
            ),
            context_assembly_observation=_obs("context_assembly", "valid"),
            generation_observation=_obs(
                "generation",
                "excluded_instrumentation_error",
                duration=None,
                exclusion_reason="x",
            ),
            citation_validation_observation=_obs("citation_validation", "valid"),
            end_to_end_observation=_obs("end_to_end", "valid"),
        )


def test_not_applicable_cannot_embed_observation() -> None:
    with pytest.raises(ValidationError):
        PerformanceLevelCAttemptV1(
            attempt_index=0,
            is_warmup=False,
            subject_identity="q1",
            terminal_status="insufficient_evidence",
            abstention_reason="empty_context",
            generator_invoked=False,
            stage_dispositions={
                "context_assembly": _disp(
                    "not_applicable", "generator_request_not_finalized"
                ),
                "generation": _disp("not_applicable", "generator_not_invoked"),
                "citation_validation": _disp(
                    "not_applicable", "no_raw_generation_response"
                ),
                "end_to_end": _disp("valid"),
            },
            context_assembly_observation=_obs(
                "context_assembly", "valid", duration=0.0
            ),
            generation_observation=None,
            citation_validation_observation=None,
            end_to_end_observation=_obs("end_to_end", "valid"),
        )


def test_level_c_attempts_excluded_from_case_identity() -> None:
    base = PerformanceBenchmarkCaseV1(
        case_id="c1",
        case_kind="end_to_end_query",
        benchmark_level="C",
        stage_or_path="end_to_end",
        subject_identity="q1",
        variant="end_to_end_warm",
        cold_warm="warm",
    )
    with_attempts = base.model_copy(update={"level_c_attempts": [_answered_attempt()]})
    assert compute_case_identity_hash(base) == compute_case_identity_hash(with_attempts)
    payload = case_semantic_payload(with_attempts)
    assert "level_c_attempts" not in payload
    assert "measured_observations" not in payload


def test_not_applicable_count_defaults_on_historical_stats() -> None:
    stats = DerivedLatencyStatsV1(
        attempted_count=2,
        valid_count=2,
        n=2,
        min=1.0,
        p50=1.0,
        p95=1.0,
        max=1.0,
        failure_count=0,
        warmup_count=0,
        instrumentation_exclusion_count=0,
    )
    assert stats.not_applicable_count == 0
    raw = stats.model_dump(mode="json")
    raw.pop("not_applicable_count", None)
    restored = DerivedLatencyStatsV1.model_validate(raw)
    assert restored.not_applicable_count == 0


def test_14c_identities_unchanged() -> None:
    plan = build_suite_plan_14c()
    assert compute_suite_identity_hash(plan.suite) == LOCKED_PERFSUITE
    assert (
        compute_config_identity_hash(scientific_config_payload_14c(plan))
        == effective_config_id_14c()
        == LOCKED_PERFCFG
    )


def test_accepted_14c_terminal_run_artifacts_readable() -> None:
    run_dir = None
    for path in (REPO_ROOT / "eval" / "results" / "performance_14").rglob(
        ACCEPTED_14C_RUN
    ):
        if path.is_dir():
            run_dir = path
            break
    assert run_dir is not None, "accepted 14C perfrun directory missing"
    manifest_path = run_dir / "run_manifest.json"
    assert manifest_path.is_file()
    manifest = PerformanceBenchmarkRunManifestV1.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    assert compute_run_identity_hash(manifest) == ACCEPTED_14C_RUN
    case_files = sorted((run_dir / "cases").glob("*.json"))
    assert case_files
    sample = PerformanceBenchmarkCaseV1.model_validate_json(
        case_files[0].read_text(encoding="utf-8")
    )
    assert sample.level_c_attempts == []
    assert compute_case_identity_hash(sample).startswith("perfcase_")


def test_build_run_aggregate_level_c_branch_and_report() -> None:
    case = PerformanceBenchmarkCaseV1(
        case_id="c1",
        case_kind="end_to_end_query",
        benchmark_level="C",
        stage_or_path="end_to_end",
        subject_identity="q1",
        variant="end_to_end_warm",
        cold_warm="warm",
        level_c_attempts=[
            _answered_attempt(attempt_index=0, is_warmup=True),
            _answered_attempt(attempt_index=0, is_warmup=False),
            _answered_attempt(attempt_index=1, is_warmup=False),
        ],
    )
    aggregate = build_run_aggregate(
        suite_id="suite_c",
        run_id="run_c",
        run_status="completed",
        benchmark_level="C",
        cases=[case],
    )
    stages = {item.stage_or_path: item.stats for item in aggregate.by_stage_or_path}
    assert set(stages) == {
        "context_assembly",
        "generation",
        "citation_validation",
        "end_to_end",
    }
    assert stages["generation"].n == 2
    assert stages["generation"].warmup_count == 1
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id="suite_c",
        executing_sha="0" * 40,
        machine_profile_id="perfhost_" + ("0" * 64),
        config_id="perfcfg_" + ("0" * 64),
        corpus_id="corpus",
        warmup_policy="1",
        start_timestamp="2026-01-01T00:00:00Z",
        execution_mode="level_c_substrate",
        run_identity_hash="perfrun_" + ("0" * 64),
    )
    text = render_report_markdown(
        run_id="run_c", manifest=manifest, aggregate=aggregate, cases=[case]
    )
    assert "TTFT: `UNEVALUABLE`" in text
    assert "not_applicable_count" in text
    assert "Level-C stages" in text


def test_14c_aggregate_path_unchanged_without_level_c_attempts() -> None:
    case = PerformanceBenchmarkCaseV1(
        case_id="c1",
        case_kind="retrieval_path",
        benchmark_level="B",
        stage_or_path="hybrid",
        subject_identity="q1",
        variant="hybrid",
        cold_warm="warm",
        measured_observations=[
            _obs("fusion", "valid", duration=0.5),
            _obs("fusion", "valid", duration=1.5),
        ],
    )
    aggregate = build_run_aggregate(
        suite_id="suite_b",
        run_id="run_b",
        run_status="completed",
        benchmark_level="B",
        cases=[case],
    )
    assert aggregate.by_stage_or_path[0].stage_or_path == "fusion"
    assert aggregate.by_stage_or_path[0].stats.n == 2
    assert aggregate.by_stage_or_path[0].stats.not_applicable_count == 0


def test_flc_i1_failed_attempt_does_not_inherit_prior_usage() -> None:
    """Success then failure on the same proxy must not leak completion_tokens."""
    timeline = LevelCTimeline(clock=_FakeClock())
    responses = [
        GeneratorResponse(
            content='{"abstain":true,"answer":null,"citation_ids":[]}',
            usage={"completion_tokens": 17},
        ),
        RuntimeError("transport boom"),
    ]

    class _Sequenced:
        def __init__(self) -> None:
            self.i = 0

        def generate(self, request: GeneratorRequest) -> GeneratorResponse:
            item = responses[self.i]
            self.i += 1
            if isinstance(item, Exception):
                raise item
            return item

        def probe(self):  # pragma: no cover
            raise AssertionError("probe not used")

    proxy = PassiveLevelCGenerator(_Sequenced(), timeline)
    req = build_prompt_grounded_v1(
        query="q",
        evidence_units=[_unit()],
        model="test-model",
        temperature=0.0,
        max_output_tokens=10,
    )
    first = proxy.generate(req)
    assert first.usage["completion_tokens"] == 17
    assert proxy.last_response is first

    with pytest.raises(RuntimeError, match="transport boom"):
        proxy.generate(req)
    assert proxy.last_response is None
    assert proxy.generation_error is not None

    # Build the failed attempt with marks reflecting this invocation only.
    fail_timeline = LevelCTimeline(clock=_FakeClock(start=50.0, step=1.0))
    fail_timeline.mark_t0()
    fail_timeline.mark_t1()
    fail_timeline.mark_t2()
    fail_timeline.mark_t3()
    # T4 absent (generator raised)
    fail_timeline.mark_generation_error()
    fail_timeline.t5 = fail_timeline.clock()
    fail_timeline.mark_t6()
    usage = proxy.last_response.usage if proxy.last_response is not None else None
    attempt = build_level_c_attempt(
        timeline=fail_timeline,
        subject_identity="q1",
        attempt_index=1,
        is_warmup=False,
        result=_result(
            status="generation_failed",
            answer_text=None,
            generation_failure_reason="transport_error",
            generator_invoked=True,
        ),
        usage=usage,
        generation_time_to_error=proxy.time_to_error_seconds,
    )
    assert attempt.generation_telemetry is not None
    assert attempt.generation_telemetry.output_token_count_availability == "unavailable"
    assert attempt.generation_telemetry.output_token_count is None
    assert attempt.generation_telemetry.output_token_count_source == "unavailable"
    assert attempt.stage_dispositions["generation"].status == "failed"


def test_flc_i2_rss_before_captured_before_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """RSS sample must precede T0; T0 must precede orchestrator.answer."""
    settings = _settings()
    timeline = LevelCTimeline(clock=_FakeClock())
    events: list[str] = []

    def _fake_capture(stage_id: str, **kwargs: Any):
        events.append("rss")
        return PerformanceResourceObservationV1(
            stage_id=stage_id,
            ram_availability="available",
            ram_rss_bytes_before=424242,
            ram_rss_bytes_peak=None,
            vram_availability="unavailable",
            vram_used_bytes_before=None,
            vram_used_bytes_peak=None,
            is_warmup=bool(kwargs.get("is_warmup", False)),
        )

    monkeypatch.setattr(
        "offline_rag.evaluation.performance_14.level_c.capture_resource_observation",
        _fake_capture,
    )

    original_mark_t0 = timeline.mark_t0

    def _tracked_mark_t0() -> float:
        events.append("t0")
        return original_mark_t0()

    timeline.mark_t0 = _tracked_mark_t0  # type: ignore[method-assign]

    fake = FakeGenerator(
        default_response=json.dumps(
            {"abstain": False, "answer": "100 psi", "citation_ids": ["ev_A"]}
        )
    )
    proxy = PassiveLevelCGenerator(fake, timeline)
    executor = PassiveLevelCExecutor(settings, generator=proxy, timeline=timeline)
    assembler = MagicMock()
    assembler.assemble.return_value = _context()
    orch = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, executor=executor
    )
    orch._require_ready = lambda _name: None  # type: ignore[method-assign]

    original_answer = orch.answer

    def _tracked_answer(**kwargs: Any):
        events.append("answer")
        return original_answer(**kwargs)

    orch.answer = _tracked_answer  # type: ignore[method-assign]

    attempt = execute_level_c_attempt(
        orch,
        timeline,
        query="pressure?",
        corpus_name="default",
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        generator_proxy=proxy,
        capture_ram=True,
    )
    assert events.index("rss") < events.index("t0") < events.index("answer")
    assert events.count("rss") == 1
    resource = attempt.end_to_end_observation.resource
    assert resource is not None
    assert resource.ram_rss_bytes_before == 424242
    assert resource.ram_rss_bytes_peak is None


def test_flc_i2_post_query_rss_not_used_as_before() -> None:
    """Explicit pre-query observation is attached; builder does not re-sample."""
    timeline = LevelCTimeline(clock=_FakeClock())
    for mark in (
        timeline.mark_t0,
        timeline.mark_t1,
        timeline.mark_t2,
        timeline.mark_t3,
        timeline.mark_t4,
        timeline.mark_t5,
        timeline.mark_t6,
    ):
        mark()
    pre = PerformanceResourceObservationV1(
        stage_id="end_to_end",
        ram_availability="available",
        ram_rss_bytes_before=111,
        ram_rss_bytes_peak=None,
        vram_availability="unavailable",
    )
    attempt = build_level_c_attempt(
        timeline=timeline,
        subject_identity="q1",
        attempt_index=0,
        is_warmup=False,
        result=_result(),
        usage={"completion_tokens": 1},
        e2e_resource_observation=pre,
    )
    assert attempt.end_to_end_observation.resource is pre
    assert attempt.end_to_end_observation.resource.ram_rss_bytes_before == 111


def test_flc_i3_duplicate_measured_attempt_index_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate Level-C attempt key"):
        PerformanceBenchmarkCaseV1(
            case_id="c1",
            case_kind="end_to_end_query",
            benchmark_level="C",
            stage_or_path="end_to_end",
            subject_identity="q1",
            variant="end_to_end_warm",
            cold_warm="warm",
            level_c_attempts=[
                _answered_attempt(attempt_index=2, is_warmup=False),
                _answered_attempt(attempt_index=2, is_warmup=False),
            ],
        )


def test_flc_i3_duplicate_warmup_attempt_index_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate Level-C attempt key"):
        PerformanceBenchmarkCaseV1(
            case_id="c1",
            case_kind="end_to_end_query",
            benchmark_level="C",
            stage_or_path="end_to_end",
            subject_identity="q1",
            variant="end_to_end_warm",
            cold_warm="warm",
            level_c_attempts=[
                _answered_attempt(attempt_index=0, is_warmup=True),
                _answered_attempt(attempt_index=0, is_warmup=True),
            ],
        )


def test_flc_i3_warmup_and_measured_index_zero_allowed() -> None:
    case = PerformanceBenchmarkCaseV1(
        case_id="c1",
        case_kind="end_to_end_query",
        benchmark_level="C",
        stage_or_path="end_to_end",
        subject_identity="q1",
        variant="end_to_end_warm",
        cold_warm="warm",
        level_c_attempts=[
            _answered_attempt(attempt_index=0, is_warmup=True),
            _answered_attempt(attempt_index=0, is_warmup=False),
        ],
    )
    assert len(case.level_c_attempts) == 2


def test_flc_i3_subject_mismatch_rejected() -> None:
    bad = _answered_attempt()
    bad = bad.model_copy(update={"subject_identity": "other_query"})
    with pytest.raises(ValidationError, match="subject_identity must match"):
        PerformanceBenchmarkCaseV1(
            case_id="c1",
            case_kind="end_to_end_query",
            benchmark_level="C",
            stage_or_path="end_to_end",
            subject_identity="q1",
            variant="end_to_end_warm",
            cold_warm="warm",
            level_c_attempts=[bad],
        )


def test_flc_i3_attempts_still_excluded_from_perfcase_identity() -> None:
    base = PerformanceBenchmarkCaseV1(
        case_id="c1",
        case_kind="end_to_end_query",
        benchmark_level="C",
        stage_or_path="end_to_end",
        subject_identity="q1",
        variant="end_to_end_warm",
        cold_warm="warm",
    )
    with_attempts = base.model_copy(
        update={
            "level_c_attempts": [
                _answered_attempt(attempt_index=0, is_warmup=True),
                _answered_attempt(attempt_index=0, is_warmup=False),
            ]
        }
    )
    assert compute_case_identity_hash(base) == compute_case_identity_hash(with_attempts)
    assert "level_c_attempts" not in case_semantic_payload(with_attempts)
