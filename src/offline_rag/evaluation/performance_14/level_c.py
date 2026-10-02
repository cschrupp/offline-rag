"""Level-C passive instrumentation substrate (evaluation-layer only).

Implements accepted T0–T6 timing, attempt provenance, stage dispositions, and
generation telemetry without modifying the production query path.

This module is measurement substrate only. It does not freeze suites/configs,
select queries/models, persist authoritative runs, or invoke real generators
in tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.evaluation.performance_14.contracts import (
    LEVEL_C_STAGE_IDS_V1,
    STATISTICS_SEMANTICS_VERSION_V1,
    DerivedLatencyStatsV1,
    LevelCStageIdV1,
    LevelCTerminalStatusV1,
    Performance14Error,
    PerformanceBenchmarkObservationV1,
    PerformanceGenerationTelemetryV1,
    PerformanceLevelCAttemptV1,
    PerformanceLevelCStageDispositionV1,
    PerformanceResourceObservationV1,
    PerformanceStageStatsV1,
)
from offline_rag.evaluation.performance_14.resources import capture_resource_observation
from offline_rag.evaluation.performance_14.statistics import linear_percentile
from offline_rag.generation.executor import GroundedGenerationExecutor
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.generation.protocol import (
    Generator,
    GeneratorProbeResult,
    GeneratorRequest,
    GeneratorResponse,
)
from offline_rag.rerank.retrieve import HybridRerankRetriever

Clock = Callable[[], float]


@dataclass
class LevelCTimeline:
    """Harness-owned monotonic marks for one Level-C attempt."""

    clock: Clock = time.perf_counter
    t0: float | None = None
    t1: float | None = None
    t2: float | None = None
    t3: float | None = None
    t4: float | None = None
    t5: float | None = None
    t6: float | None = None
    generation_error_at: float | None = None

    def clear(self) -> None:
        self.t0 = self.t1 = self.t2 = self.t3 = None
        self.t4 = self.t5 = self.t6 = None
        self.generation_error_at = None

    def mark_t0(self) -> float:
        self.t0 = self.clock()
        return self.t0

    def mark_t1(self) -> float:
        self.t1 = self.clock()
        return self.t1

    def mark_t2(self) -> float:
        self.t2 = self.clock()
        return self.t2

    def mark_t3(self) -> float:
        self.t3 = self.clock()
        return self.t3

    def mark_t4(self) -> float:
        self.t4 = self.clock()
        return self.t4

    def mark_t5(self) -> float:
        self.t5 = self.clock()
        return self.t5

    def mark_t6(self) -> float:
        self.t6 = self.clock()
        return self.t6

    def mark_generation_error(self) -> float:
        self.generation_error_at = self.clock()
        return self.generation_error_at

    def duration(self, start: float | None, end: float | None) -> float | None:
        if start is None or end is None:
            return None
        return float(end - start)


@dataclass
class PassiveHybridRerankRetrieverDelegate:
    """Record T1 after accepted retrieve; return the exact result object."""

    inner: HybridRerankRetriever
    timeline: LevelCTimeline
    last_kwargs: dict[str, Any] = field(default_factory=dict)
    last_result: Any = None

    def retrieve(
        self,
        *,
        query: str,
        corpus_name: str = "default",
        top_k: int | None = None,
    ) -> Any:
        self.last_kwargs = {
            "query": query,
            "corpus_name": corpus_name,
            "top_k": top_k,
        }
        result = self.inner.retrieve(
            query=query, corpus_name=corpus_name, top_k=top_k
        )
        self.last_result = result
        self.timeline.mark_t1()
        return result

    def close(self) -> None:
        self.inner.close()


class PassiveLevelCGenerator:
    """Record T3/T4 around accepted generate; preserve request/response/exceptions."""

    def __init__(self, inner: Generator, timeline: LevelCTimeline) -> None:
        self._inner = inner
        self._timeline = timeline
        self.last_request: GeneratorRequest | None = None
        self.last_response: GeneratorResponse | None = None
        self.call_count = 0
        self.generation_error: BaseException | None = None
        self.time_to_error_seconds: float | None = None

    def generate(self, request: GeneratorRequest) -> GeneratorResponse:
        self.call_count += 1
        # Clear prior-attempt state so failed calls cannot inherit stale usage.
        self.last_response = None
        self.last_request = request
        self.generation_error = None
        self.time_to_error_seconds = None
        self._timeline.mark_t3()
        try:
            response = self._inner.generate(request)
        except Exception as exc:
            self.generation_error = exc
            self._timeline.mark_generation_error()
            if self._timeline.t3 is not None and self._timeline.generation_error_at is not None:
                self.time_to_error_seconds = (
                    self._timeline.generation_error_at - self._timeline.t3
                )
            raise
        self._timeline.mark_t4()
        self.last_response = response
        return response

    def probe(self) -> GeneratorProbeResult:
        return self._inner.probe()


class PassiveLevelCExecutor(GroundedGenerationExecutor):
    """Record T2 after request finalize and T5 after execute returns."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        generator: Generator,
        timeline: LevelCTimeline,
    ) -> None:
        super().__init__(settings, generator=generator)
        self._timeline = timeline
        self.last_request: GeneratorRequest | None = None
        self.last_result: GroundedAnswerResult | None = None

    def _build_generator_request(self, **kwargs: Any) -> GeneratorRequest:
        request = super()._build_generator_request(**kwargs)
        self.last_request = request
        self._timeline.mark_t2()
        return request

    def execute(self, **kwargs: Any) -> GroundedAnswerResult:
        result = super().execute(**kwargs)
        self.last_result = result
        self._timeline.mark_t5()
        return result


def extract_completion_tokens(
    usage: Mapping[str, Any] | None,
) -> tuple[str, int | None, str]:
    """Exact provider completion_tokens only; otherwise unavailable."""
    unavailable = ("unavailable", None, "unavailable")
    if not isinstance(usage, Mapping) or "completion_tokens" not in usage:
        return unavailable
    value = usage["completion_tokens"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return unavailable
    return ("available", value, "provider_usage_completion_tokens")


def build_generation_telemetry(
    *,
    generator_invoked: bool,
    usage: Mapping[str, Any] | None = None,
) -> PerformanceGenerationTelemetryV1:
    availability, count, source = extract_completion_tokens(usage)
    return PerformanceGenerationTelemetryV1(
        generator_invoked=generator_invoked,
        ttft_availability="unevaluable",
        ttft_seconds=None,
        decode_availability="unevaluable",
        decode_seconds=None,
        output_token_count_availability=availability,  # type: ignore[arg-type]
        output_token_count=count,
        output_token_count_source=source,  # type: ignore[arg-type]
        tokens_per_second_availability="unevaluable",
        tokens_per_second=None,
    )


def classify_level_c_terminal(
    result: GroundedAnswerResult | None,
    *,
    exception: BaseException | None = None,
) -> tuple[LevelCTerminalStatusV1, str | None, str | None, bool]:
    """Map repository result/exception to Level-C terminal classification."""
    if exception is not None or result is None:
        reason = type(exception).__name__ if exception is not None else "no_terminal_result"
        detail = str(exception) if exception is not None else "no_terminal_result"
        return ("orchestration_failed", None, f"{reason}:{detail}"[:500], False)

    abstention = result.abstention_reason
    failure = result.generation_failure_reason
    invoked = bool(result.generator_invoked)
    if result.status == "answered":
        return ("answered", None, None, invoked)
    if result.status == "citation_invalid":
        return ("citation_invalid", None, failure, invoked)
    if result.status == "generation_failed":
        return ("generation_failed", None, failure, invoked)
    if result.status == "insufficient_evidence":
        if abstention == "model_abstain":
            return ("model_abstain", "model_abstain", failure, invoked)
        return ("insufficient_evidence", abstention, failure, invoked)
    raise Performance14Error(f"unsupported GroundedAnswerResult.status={result.status!r}")


def _disp(
    status: str, reason: str | None = None
) -> PerformanceLevelCStageDispositionV1:
    return PerformanceLevelCStageDispositionV1(status=status, reason=reason)  # type: ignore[arg-type]


def _obs(
    *,
    stage_id: str,
    status: str,
    duration: float | None,
    is_warmup: bool,
    failure_reason: str | None = None,
    exclusion_reason: str | None = None,
    resource: Any = None,
) -> PerformanceBenchmarkObservationV1:
    return PerformanceBenchmarkObservationV1(
        observation_status=status,  # type: ignore[arg-type]
        stage_id=stage_id,
        duration_seconds=duration,
        is_warmup=is_warmup,
        failure_reason=failure_reason,
        exclusion_reason=exclusion_reason,
        resource=resource,
    )


def _excluded(
    stage_id: str, reason: str, *, is_warmup: bool
) -> tuple[PerformanceLevelCStageDispositionV1, PerformanceBenchmarkObservationV1]:
    return (
        _disp("excluded_instrumentation_error", reason),
        _obs(
            stage_id=stage_id,
            status="excluded_instrumentation_error",
            duration=None,
            is_warmup=is_warmup,
            exclusion_reason=reason,
        ),
    )


def build_level_c_attempt(
    *,
    timeline: LevelCTimeline,
    subject_identity: str,
    attempt_index: int,
    is_warmup: bool,
    result: GroundedAnswerResult | None,
    exception: BaseException | None = None,
    usage: Mapping[str, Any] | None = None,
    generation_time_to_error: float | None = None,
    e2e_exclusion_reason: str | None = None,
    e2e_resource_observation: PerformanceResourceObservationV1 | None = None,
) -> PerformanceLevelCAttemptV1:
    """Build a validated attempt from timeline marks and terminal outcome."""
    terminal, abstention, gen_failure, invoked = classify_level_c_terminal(
        result, exception=exception
    )

    context_disp: PerformanceLevelCStageDispositionV1
    gen_disp: PerformanceLevelCStageDispositionV1
    cite_disp: PerformanceLevelCStageDispositionV1
    e2e_disp: PerformanceLevelCStageDispositionV1
    context_obs: PerformanceBenchmarkObservationV1 | None
    gen_obs: PerformanceBenchmarkObservationV1 | None
    cite_obs: PerformanceBenchmarkObservationV1 | None
    e2e_obs: PerformanceBenchmarkObservationV1 | None

    ca_dur = timeline.duration(timeline.t1, timeline.t2)
    gen_dur = timeline.duration(timeline.t3, timeline.t4)
    cite_dur = timeline.duration(timeline.t4, timeline.t5)
    e2e_dur = timeline.duration(timeline.t0, timeline.t6)

    # --- context_assembly / generation / citation by terminal matrix ---
    if terminal == "answered":
        if ca_dur is None:
            context_disp, context_obs = _excluded(
                "context_assembly", "missing_t1_or_t2", is_warmup=is_warmup
            )
        else:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        if gen_dur is None:
            gen_disp, gen_obs = _excluded(
                "generation", "missing_t3_or_t4", is_warmup=is_warmup
            )
        else:
            gen_disp, gen_obs = (
                _disp("valid"),
                _obs(
                    stage_id="generation",
                    status="valid",
                    duration=gen_dur,
                    is_warmup=is_warmup,
                ),
            )
        if cite_dur is None:
            cite_disp, cite_obs = _excluded(
                "citation_validation", "missing_t4_or_t5", is_warmup=is_warmup
            )
        else:
            cite_disp, cite_obs = (
                _disp("valid"),
                _obs(
                    stage_id="citation_validation",
                    status="valid",
                    duration=cite_dur,
                    is_warmup=is_warmup,
                ),
            )
    elif terminal == "insufficient_evidence" and not invoked and timeline.t2 is None:
        context_disp = _disp("not_applicable", "generator_request_not_finalized")
        context_obs = None
        gen_disp = _disp("not_applicable", "generator_not_invoked")
        gen_obs = None
        cite_disp = _disp("not_applicable", "no_raw_generation_response")
        cite_obs = None
    elif terminal == "model_abstain":
        if ca_dur is None:
            context_disp, context_obs = _excluded(
                "context_assembly", "missing_t1_or_t2", is_warmup=is_warmup
            )
        else:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        if gen_dur is None:
            gen_disp, gen_obs = _excluded(
                "generation", "missing_t3_or_t4", is_warmup=is_warmup
            )
        else:
            gen_disp, gen_obs = (
                _disp("valid"),
                _obs(
                    stage_id="generation",
                    status="valid",
                    duration=gen_dur,
                    is_warmup=is_warmup,
                ),
            )
        cite_disp = _disp("not_applicable", "model_abstain_no_citation_validation")
        cite_obs = None
    elif terminal == "citation_invalid":
        if ca_dur is None:
            context_disp, context_obs = _excluded(
                "context_assembly", "missing_t1_or_t2", is_warmup=is_warmup
            )
        else:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        if gen_dur is None:
            gen_disp, gen_obs = _excluded(
                "generation", "missing_t3_or_t4", is_warmup=is_warmup
            )
        else:
            gen_disp, gen_obs = (
                _disp("valid"),
                _obs(
                    stage_id="generation",
                    status="valid",
                    duration=gen_dur,
                    is_warmup=is_warmup,
                ),
            )
        cite_disp = _disp("failed", "citation_invalid")
        cite_obs = _obs(
            stage_id="citation_validation",
            status="failed",
            duration=cite_dur,
            is_warmup=is_warmup,
            failure_reason="citation_invalid",
        )
    elif terminal == "generation_failed" and timeline.t4 is not None:
        # Schema/output invalid after complete response (or similar post-response fail).
        failure_reason = gen_failure or "generation_failed"
        if ca_dur is None:
            context_disp, context_obs = _excluded(
                "context_assembly", "missing_t1_or_t2", is_warmup=is_warmup
            )
        else:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        if gen_dur is None:
            gen_disp, gen_obs = _excluded(
                "generation", "missing_t3_or_t4", is_warmup=is_warmup
            )
        else:
            gen_disp, gen_obs = (
                _disp("valid"),
                _obs(
                    stage_id="generation",
                    status="valid",
                    duration=gen_dur,
                    is_warmup=is_warmup,
                ),
            )
        cite_reason = (
            "output_schema_invalid"
            if (failure_reason == "output_schema_invalid")
            or (failure_reason is not None and "schema" in failure_reason)
            else failure_reason
        )
        cite_disp = _disp("failed", cite_reason)
        cite_obs = _obs(
            stage_id="citation_validation",
            status="failed",
            duration=cite_dur,
            is_warmup=is_warmup,
            failure_reason=cite_reason,
        )
    elif terminal == "generation_failed" and invoked and timeline.t2 is not None:
        # Provider/transport/timeout: T3 set, T4 absent.
        failure_reason = gen_failure or "provider_error"
        if ca_dur is None:
            context_disp, context_obs = _excluded(
                "context_assembly", "missing_t1_or_t2", is_warmup=is_warmup
            )
        else:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        gen_disp = _disp("failed", failure_reason)
        gen_obs = _obs(
            stage_id="generation",
            status="failed",
            duration=generation_time_to_error,
            is_warmup=is_warmup,
            failure_reason=failure_reason,
        )
        cite_disp = _disp("not_applicable", "no_raw_generation_response")
        cite_obs = None
    elif terminal == "generation_failed" and timeline.t2 is None:
        # Request construction failure before generator.
        context_disp = _disp("not_applicable", "generator_request_not_finalized")
        context_obs = None
        gen_disp = _disp("not_applicable", "generator_not_invoked")
        gen_obs = None
        cite_disp = _disp("not_applicable", "no_raw_generation_response")
        cite_obs = None
    elif terminal == "orchestration_failed":
        if timeline.t2 is not None and ca_dur is not None:
            context_disp, context_obs = (
                _disp("valid"),
                _obs(
                    stage_id="context_assembly",
                    status="valid",
                    duration=ca_dur,
                    is_warmup=is_warmup,
                ),
            )
        elif timeline.t2 is None and timeline.t1 is None:
            context_disp = _disp("not_applicable", "generator_request_not_finalized")
            context_obs = None
        else:
            context_disp, context_obs = _excluded(
                "context_assembly", "incomplete_context_assembly_marks", is_warmup=is_warmup
            )
        if timeline.t3 is not None and timeline.t4 is None:
            failure_reason = gen_failure or "provider_error"
            gen_disp = _disp("failed", failure_reason)
            gen_obs = _obs(
                stage_id="generation",
                status="failed",
                duration=generation_time_to_error,
                is_warmup=is_warmup,
                failure_reason=failure_reason,
            )
            cite_disp = _disp("not_applicable", "no_raw_generation_response")
            cite_obs = None
        elif timeline.t3 is None:
            gen_disp = _disp("not_applicable", "generator_not_invoked")
            gen_obs = None
            cite_disp = _disp("not_applicable", "no_raw_generation_response")
            cite_obs = None
        else:
            gen_disp, gen_obs = _excluded(
                "generation", "incomplete_generation_marks", is_warmup=is_warmup
            )
            cite_disp = _disp("not_applicable", "no_raw_generation_response")
            cite_obs = None
    else:
        raise Performance14Error(
            f"unhandled Level-C terminal matrix branch: {terminal!r} "
            f"invoked={invoked} t2={timeline.t2 is not None} t4={timeline.t4 is not None}"
        )

    # --- end_to_end ---
    if e2e_exclusion_reason is not None:
        e2e_disp, e2e_obs = _excluded(
            "end_to_end", e2e_exclusion_reason, is_warmup=is_warmup
        )
    elif terminal == "orchestration_failed":
        e2e_disp = _disp("failed", gen_failure or "orchestration_failed")
        e2e_obs = _obs(
            stage_id="end_to_end",
            status="failed",
            duration=timeline.duration(timeline.t0, timeline.generation_error_at)
            if timeline.t6 is None
            else e2e_dur,
            is_warmup=is_warmup,
            failure_reason=gen_failure or "orchestration_failed",
            resource=e2e_resource_observation,
        )
    elif e2e_dur is None:
        e2e_disp, e2e_obs = _excluded(
            "end_to_end", "missing_t0_or_t6", is_warmup=is_warmup
        )
        if e2e_resource_observation is not None and e2e_obs is not None:
            e2e_obs = e2e_obs.model_copy(
                update={"resource": e2e_resource_observation}
            )
    else:
        e2e_disp = _disp("valid")
        e2e_obs = _obs(
            stage_id="end_to_end",
            status="valid",
            duration=e2e_dur,
            is_warmup=is_warmup,
            # Pre-query RSS captured at E2E start (before answer), never post-T6.
            resource=e2e_resource_observation,
        )

    telemetry = build_generation_telemetry(
        generator_invoked=invoked,
        usage=usage if invoked else None,
    )

    return PerformanceLevelCAttemptV1(
        attempt_index=attempt_index,
        is_warmup=is_warmup,
        subject_identity=subject_identity,
        terminal_status=terminal,
        abstention_reason=abstention,  # type: ignore[arg-type]
        generation_failure_reason=gen_failure,
        generator_invoked=invoked,
        stage_dispositions={
            "context_assembly": context_disp,
            "generation": gen_disp,
            "citation_validation": cite_disp,
            "end_to_end": e2e_disp,
        },
        context_assembly_observation=context_obs,
        generation_observation=gen_obs,
        citation_validation_observation=cite_obs,
        end_to_end_observation=e2e_obs,
        generation_telemetry=telemetry,
    )


def build_instrumented_orchestrator(
    settings: AppSettings,
    *,
    timeline: LevelCTimeline,
    retriever: HybridRerankRetriever,
    generator: Generator,
) -> tuple[
    GroundedAnswerOrchestrator,
    PassiveLevelCGenerator,
    PassiveLevelCExecutor,
    PassiveHybridRerankRetrieverDelegate,
]:
    """Wire evaluation-layer proxies into a persistent orchestrator."""
    retriever_delegate = PassiveHybridRerankRetrieverDelegate(retriever, timeline)
    assembler = HybridRerankContextAssembler(
        settings,
        retriever=retriever_delegate,  # type: ignore[arg-type]
    )
    gen_proxy = PassiveLevelCGenerator(generator, timeline)
    executor = PassiveLevelCExecutor(settings, generator=gen_proxy, timeline=timeline)
    orch = GroundedAnswerOrchestrator(
        settings, context_assembler=assembler, executor=executor
    )
    return orch, gen_proxy, executor, retriever_delegate


def execute_level_c_attempt(
    orchestrator: GroundedAnswerOrchestrator,
    timeline: LevelCTimeline,
    *,
    query: str,
    corpus_name: str,
    subject_identity: str,
    attempt_index: int,
    is_warmup: bool,
    generator_proxy: PassiveLevelCGenerator | None = None,
    capture_ram: bool = False,
) -> PerformanceLevelCAttemptV1:
    """Run one Level-C attempt against a persistent instrumented orchestrator."""
    timeline.clear()
    # Pre-query RSS is harness evidence and must NOT sit inside T0→T6.
    e2e_resource = None
    if capture_ram:
        try:
            e2e_resource = capture_resource_observation(
                stage_id="end_to_end",
                is_warmup=is_warmup,
            )
        except Exception:  # noqa: BLE001 - resource failure must not alter query path
            e2e_resource = None

    result: GroundedAnswerResult | None = None
    error: BaseException | None = None

    # Locked Level-C E2E boundary begins immediately before query invocation.
    timeline.mark_t0()
    try:
        result = orchestrator.answer(query=query, corpus_name=corpus_name)
    except Exception as exc:  # noqa: BLE001 - classify orchestration_failed
        error = exc
        timeline.mark_generation_error()
    else:
        timeline.mark_t6()

    usage = None
    time_to_error = None
    if generator_proxy is not None:
        if generator_proxy.last_response is not None:
            usage = generator_proxy.last_response.usage
        time_to_error = generator_proxy.time_to_error_seconds
        if usage is None and result is not None:
            diagnostics = result.diagnostics or {}
            raw_usage = diagnostics.get("usage")
            if isinstance(raw_usage, Mapping):
                usage = raw_usage

    return build_level_c_attempt(
        timeline=timeline,
        subject_identity=subject_identity,
        attempt_index=attempt_index,
        is_warmup=is_warmup,
        result=result,
        exception=error,
        usage=usage,
        generation_time_to_error=time_to_error,
        e2e_resource_observation=e2e_resource,
    )


def _observation_for_stage(
    attempt: PerformanceLevelCAttemptV1, stage_id: LevelCStageIdV1
) -> PerformanceBenchmarkObservationV1 | None:
    return {
        "context_assembly": attempt.context_assembly_observation,
        "generation": attempt.generation_observation,
        "citation_validation": attempt.citation_validation_observation,
        "end_to_end": attempt.end_to_end_observation,
    }[stage_id]


def derive_level_c_stage_stats(
    attempts: Sequence[PerformanceLevelCAttemptV1],
    stage_id: LevelCStageIdV1,
) -> DerivedLatencyStatsV1:
    """Aggregate one Level-C stage from structurally owned attempt observations."""
    valid_durations: list[float] = []
    failure_count = 0
    exclusion_count = 0
    not_applicable_count = 0
    warmup_count = 0

    for attempt in attempts:
        disposition = attempt.stage_dispositions[stage_id]
        observation = _observation_for_stage(attempt, stage_id)
        if attempt.is_warmup:
            warmup_count += 1
            continue
        if disposition.status == "not_applicable":
            if observation is not None:
                raise Performance14Error(
                    f"{stage_id}: N/A disposition with observation present"
                )
            not_applicable_count += 1
            continue
        if observation is None:
            raise Performance14Error(
                f"{stage_id}: disposition {disposition.status} missing observation"
            )
        if observation.observation_status != disposition.status:
            raise Performance14Error(
                f"{stage_id}: disposition/observation status mismatch"
            )
        if disposition.status == "valid":
            if observation.duration_seconds is None:
                raise Performance14Error(f"{stage_id}: valid missing duration")
            valid_durations.append(float(observation.duration_seconds))
        elif disposition.status == "failed":
            failure_count += 1
        elif disposition.status == "excluded_instrumentation_error":
            exclusion_count += 1
        else:
            raise Performance14Error(f"unknown disposition {disposition.status!r}")

    valid_count = len(valid_durations)
    attempted_count = valid_count + failure_count + exclusion_count
    if not valid_durations:
        return DerivedLatencyStatsV1(
            statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
            attempted_count=attempted_count,
            valid_count=0,
            n=0,
            min=None,
            p50=None,
            p95=None,
            max=None,
            failure_count=failure_count,
            warmup_count=warmup_count,
            instrumentation_exclusion_count=exclusion_count,
            not_applicable_count=not_applicable_count,
        )
    ordered = sorted(valid_durations)
    return DerivedLatencyStatsV1(
        statistics_semantics_version=STATISTICS_SEMANTICS_VERSION_V1,
        attempted_count=attempted_count,
        valid_count=valid_count,
        n=valid_count,
        min=ordered[0],
        p50=linear_percentile(ordered, 50.0),
        p95=linear_percentile(ordered, 95.0),
        max=ordered[-1],
        failure_count=failure_count,
        warmup_count=warmup_count,
        instrumentation_exclusion_count=exclusion_count,
        not_applicable_count=not_applicable_count,
    )


def build_level_c_stage_aggregates(
    attempts: Sequence[PerformanceLevelCAttemptV1],
) -> list[PerformanceStageStatsV1]:
    return [
        PerformanceStageStatsV1(
            stage_or_path=stage_id,
            stats=derive_level_c_stage_stats(attempts, stage_id),
        )
        for stage_id in LEVEL_C_STAGE_IDS_V1
    ]
