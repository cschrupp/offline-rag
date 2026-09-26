"""Paired shared-initial Slice 12C evaluation harness (no measure-once runner).

Consumes accepted RecoveryCoordinator / sufficiency-v1 contracts. Ensures one
initial assemble per case; Arm A observes that attempt; Arm B may recover only
when initially insufficient.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import mean, median
from typing import Protocol

from offline_rag.config.models import AppSettings
from offline_rag.domain.indexing import HybridRerankContextResult
from offline_rag.evaluation.generation_semantic.models import LabelCohort
from offline_rag.evaluation.gold import GoldCase
from offline_rag.evaluation.metrics import RankingScore, macro_average, score_ranking
from offline_rag.evaluation.recovery_12c.conclusion import conclude_recovery_eval
from offline_rag.evaluation.recovery_12c.contracts import (
    NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES,
    AttemptObservationV1,
    CohortAggregateV1,
    LatencySummaryV1,
    RecoveryAttemptRecordV1,
    RecoveryEvalAggregateV1,
    RecoveryEvalCaseClassV1,
    RecoveryEvalCaseRecordV1,
    RecoveryEvalError,
    TriggerCensusV1,
    ranking_score_to_dict,
)
from offline_rag.evaluation.recovery_12c.evidence import (
    context_latency_ms,
    evidence_surface_chunk_ids_from_context,
    gold_positive_overlap,
    ranked_anchor_chunk_ids,
)
from offline_rag.recovery.coordinator import (
    RecoveryCoordinator,
    RecoveryCoordinatorResult,
    RecoveryRuntimeError,
)
from offline_rag.recovery.lineage import (
    RecoveryLineageV1,
    extract_recovery_lineage,
    lineage_stack_equal,
)
from offline_rag.recovery.rewrite_contracts import RecoveryRewriter
from offline_rag.sufficiency.policy import (
    SufficiencyPolicyDecisionV1,
    evaluate_sufficiency_policy_v1,
)


class InitialContextAssembler(Protocol):
    """Produces the shared initial context attempt (exactly once per case)."""

    def assemble_initial(self, query: str) -> HybridRerankContextResult: ...


@dataclass
class CountingInitialAssembler:
    """Wraps a callable and records how many times the initial attempt ran."""

    _assemble: Callable[[str], HybridRerankContextResult]
    call_count: int = 0
    queries: list[str] | None = None

    def __post_init__(self) -> None:
        if self.queries is None:
            self.queries = []

    def assemble_initial(self, query: str) -> HybridRerankContextResult:
        self.call_count += 1
        assert self.queries is not None
        self.queries.append(query)
        return self._assemble(query)


def is_recovery_triggered(sufficiency: SufficiencyPolicyDecisionV1) -> bool:
    """OD-12C-3: trigger iff sufficiency-v1 / empty_context_v1 (insufficient)."""
    return not sufficiency.sufficient


def observe_attempt(
    context: HybridRerankContextResult,
    *,
    gold_positive_chunk_ids: Sequence[str],
    sufficiency: SufficiencyPolicyDecisionV1 | None = None,
) -> AttemptObservationV1:
    decision = sufficiency or evaluate_sufficiency_policy_v1(
        evidence_units=context.evidence_units
    )
    surface = evidence_surface_chunk_ids_from_context(context)
    overlap, present = gold_positive_overlap(
        gold_positive_chunk_ids=gold_positive_chunk_ids,
        evidence_surface=surface,
    )
    lineage: RecoveryLineageV1 | None
    try:
        lineage = extract_recovery_lineage(context)
    except ValueError:
        lineage = None
    stop_reason = None
    if context.diagnostics is not None:
        stop_reason = context.diagnostics.stop_reason
    return AttemptObservationV1(
        sufficient=decision.sufficient,
        empty_context=decision.empty_context,
        evidence_unit_count=decision.evidence_unit_count,
        triggered_gates=list(decision.triggered_gates),
        evidence_surface_chunk_ids=sorted(surface),
        ranked_anchor_chunk_ids=ranked_anchor_chunk_ids(context.anchors),
        gold_positive_overlap_chunk_ids=present,
        gold_positive_overlap=overlap,
        lineage=lineage,
        stop_reason=stop_reason,
        latency_ms=context_latency_ms(context),
    )


def classify_case(
    *,
    triggered: bool,
    recovery_failed: bool,
    recovery_observation: AttemptObservationV1 | None,
) -> RecoveryEvalCaseClassV1:
    if not triggered:
        return RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
    if recovery_failed:
        return RecoveryEvalCaseClassV1.RECOVERY_FAILED
    if recovery_observation is None:
        return RecoveryEvalCaseClassV1.RECOVERY_FAILED
    if not recovery_observation.sufficient:
        return RecoveryEvalCaseClassV1.STILL_INSUFFICIENT
    if recovery_observation.gold_positive_overlap:
        return RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    return RecoveryEvalCaseClassV1.UNSUPPORTED_RECOVERY


def _ranking_for_case(
    case: GoldCase,
    ranked_ids: Sequence[str],
) -> dict[str, float | None] | None:
    if not case.quality_eligible:
        return None
    score: RankingScore = score_ranking(
        case,
        list(ranked_ids),
        requested_depth=max(len(ranked_ids), 10),
        hit_rate_30_applicable=False,
    )
    return ranking_score_to_dict(score)


def evaluate_paired_case(
    *,
    case: GoldCase,
    adjudication_cohort: LabelCohort,
    initial_assembler: InitialContextAssembler,
    recovery_settings: AppSettings,
    recovery_assembler: object,
    rewriter: RecoveryRewriter,
    corpus_name: str = "default",
    enable_recovery_arm: bool = True,
) -> RecoveryEvalCaseRecordV1:
    """Run Arm A + Arm B from one shared initial assemble.

    ``enable_recovery_arm`` should be True for experiment Arm B settings
    (recovery.enabled). When False, records baseline-only observation (still
    shares the single initial attempt).
    """
    initial_context = initial_assembler.assemble_initial(case.query)
    initial_sufficiency = evaluate_sufficiency_policy_v1(
        evidence_units=initial_context.evidence_units
    )
    gold_ids = sorted(case.positive_chunk_ids())
    initial_obs = observe_attempt(
        initial_context,
        gold_positive_chunk_ids=gold_ids,
        sufficiency=initial_sufficiency,
    )
    triggered = is_recovery_triggered(initial_sufficiency)

    rewrite_calls = 0
    recovery_retrievals = 0
    recovery_record: RecoveryAttemptRecordV1 | None = None
    recovery_failed = False
    happy_path_diverged = False

    if not triggered:
        # Happy path: Arm B must not rewrite / re-retrieve.
        if enable_recovery_arm and recovery_settings.retrieval_recovery.enabled:
            coordinator = RecoveryCoordinator(
                recovery_settings,
                context_assembler=recovery_assembler,  # type: ignore[arg-type]
                rewriter=rewriter,
            )
            try:
                result = coordinator.run(
                    original_query=case.query,
                    corpus_name=corpus_name,
                    initial_context=initial_context,
                    initial_sufficiency=initial_sufficiency,
                )
            finally:
                coordinator.close()
            rewrite_calls = result.rewrite_call_count
            recovery_retrievals = result.recovery_retrieval_attempt_count
            if (
                rewrite_calls != 0
                or recovery_retrievals != 0
                or result.recovery_invoked
            ):
                happy_path_diverged = True
        classification = classify_case(
            triggered=False,
            recovery_failed=False,
            recovery_observation=None,
        )
    else:
        if not enable_recovery_arm or not recovery_settings.retrieval_recovery.enabled:
            # Triggered but recovery arm not active: still_insufficient baseline.
            classification = RecoveryEvalCaseClassV1.STILL_INSUFFICIENT
            recovery_record = None
        else:
            coordinator = RecoveryCoordinator(
                recovery_settings,
                context_assembler=recovery_assembler,  # type: ignore[arg-type]
                rewriter=rewriter,
            )
            try:
                try:
                    result = coordinator.run(
                        original_query=case.query,
                        corpus_name=corpus_name,
                        initial_context=initial_context,
                        initial_sufficiency=initial_sufficiency,
                    )
                except RecoveryRuntimeError as exc:
                    recovery_failed = True
                    rewrite_calls = (
                        exc.trace.rewrite_call_count if exc.trace is not None else 0
                    )
                    recovery_retrievals = (
                        exc.trace.recovery_retrieval_attempt_count
                        if exc.trace is not None
                        else 0
                    )
                    recovery_record = RecoveryAttemptRecordV1(
                        rewritten_query=(
                            exc.trace.rewrite_provenance.rewritten_query
                            if exc.trace is not None
                            and exc.trace.rewrite_provenance is not None
                            else None
                        ),
                        rewriter_config_hash=(
                            exc.trace.rewrite_provenance.rewriter_config_hash
                            if exc.trace is not None
                            and exc.trace.rewrite_provenance is not None
                            else None
                        ),
                        rewrite_contract=(
                            exc.trace.rewrite_provenance.output_contract
                            if exc.trace is not None
                            and exc.trace.rewrite_provenance is not None
                            else None
                        ),
                        rewrite_call_count=rewrite_calls,
                        recovery_retrieval_attempt_count=recovery_retrievals,
                        terminal_outcome=(
                            exc.state.terminal_outcome
                            if exc.state is not None
                            else None
                        ),
                        failure_reason=exc.failure_reason,
                        observation=None,
                    )
                    result = None
            finally:
                coordinator.close()

            if not recovery_failed and result is not None:
                recovery_record = _record_successful_recovery_arm(
                    result=result,
                    gold_ids=gold_ids,
                    initial_lineage=initial_obs.lineage,
                )
                rewrite_calls = result.rewrite_call_count
                recovery_retrievals = result.recovery_retrieval_attempt_count

            classification = classify_case(
                triggered=True,
                recovery_failed=recovery_failed,
                recovery_observation=(
                    recovery_record.observation if recovery_record is not None else None
                ),
            )

    return RecoveryEvalCaseRecordV1(
        case_id=case.id,
        adjudication_cohort=adjudication_cohort,
        original_query=case.query,
        quality_eligible=case.quality_eligible,
        gold_positive_chunk_ids=gold_ids,
        initial=initial_obs,
        triggered=triggered,
        classification=classification,
        rewrite_call_count=rewrite_calls,
        recovery_retrieval_attempt_count=recovery_retrievals,
        happy_path_diverged=happy_path_diverged,
        recovery=recovery_record,
        initial_ranking=_ranking_for_case(case, initial_obs.ranked_anchor_chunk_ids),
        recovery_ranking=(
            _ranking_for_case(case, recovery_record.observation.ranked_anchor_chunk_ids)
            if recovery_record is not None and recovery_record.observation is not None
            else None
        ),
    )


def _record_successful_recovery_arm(
    *,
    result: RecoveryCoordinatorResult,
    gold_ids: Sequence[str],
    initial_lineage: RecoveryLineageV1 | None,
) -> RecoveryAttemptRecordV1:
    recovery_obs = observe_attempt(
        result.context,
        gold_positive_chunk_ids=gold_ids,
        sufficiency=result.sufficiency,
    )
    if (
        initial_lineage is not None
        and recovery_obs.lineage is not None
        and not lineage_stack_equal(initial_lineage, recovery_obs.lineage)
    ):
        raise RecoveryEvalError(
            "recovery attempt retrieval stack differs from shared initial attempt "
            "(only active_retrieval_query may differ)"
        )
    rewrite_latency = None
    rewriter_hash = None
    rewrite_contract = None
    rewritten_query = None
    terminal = None
    failure = None
    if result.trace is not None and result.trace.rewrite_provenance is not None:
        prov = result.trace.rewrite_provenance
        rewriter_hash = prov.rewriter_config_hash
        rewrite_contract = prov.output_contract
        rewritten_query = prov.rewritten_query
    if result.state is not None:
        terminal = result.state.terminal_outcome
        failure = result.state.failure_reason
    recovery_latency = recovery_obs.latency_ms
    incremental = float(recovery_latency) if recovery_latency is not None else None
    return RecoveryAttemptRecordV1(
        rewritten_query=rewritten_query,
        rewriter_config_hash=rewriter_hash,
        rewrite_contract=rewrite_contract,
        rewrite_call_count=result.rewrite_call_count,
        recovery_retrieval_attempt_count=result.recovery_retrieval_attempt_count,
        terminal_outcome=terminal,
        failure_reason=failure,
        observation=recovery_obs,
        rewrite_latency_ms=rewrite_latency,
        recovery_context_latency_ms=recovery_latency,
        incremental_recovery_latency_ms=incremental,
    )


def build_trigger_census(
    records: Sequence[RecoveryEvalCaseRecordV1],
) -> TriggerCensusV1:
    """Freeze T_H / T_A from shared-initial observations (before recovery results)."""
    human_ids = [
        r.case_id
        for r in records
        if r.triggered and r.adjudication_cohort == "human_reviewed"
    ]
    assistant_ids = [
        r.case_id
        for r in records
        if r.triggered and r.adjudication_cohort == "assistant_only"
    ]
    not_evaluable = len(human_ids) == 0
    return TriggerCensusV1(
        human_trigger_case_ids=sorted(human_ids),
        assistant_trigger_case_ids=sorted(assistant_ids),
        human_trigger_count=len(human_ids),
        assistant_trigger_count=len(assistant_ids),
        not_evaluable=not_evaluable,
        stop_reason=(
            NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES if not_evaluable else None
        ),
    )


def census_from_initial_attempts(
    *,
    cases: Sequence[GoldCase],
    cohort_by_case: Mapping[str, LabelCohort],
    initial_assembler: InitialContextAssembler,
) -> TriggerCensusV1:
    """Run shared-initial attempts only and freeze trigger membership."""
    records: list[RecoveryEvalCaseRecordV1] = []
    for case in cases:
        cohort = cohort_by_case.get(case.id)
        if cohort is None:
            raise RecoveryEvalError(f"missing cohort for case_id={case.id!r}")
        ctx = initial_assembler.assemble_initial(case.query)
        suff = evaluate_sufficiency_policy_v1(evidence_units=ctx.evidence_units)
        obs = observe_attempt(
            ctx,
            gold_positive_chunk_ids=sorted(case.positive_chunk_ids()),
            sufficiency=suff,
        )
        triggered = is_recovery_triggered(suff)
        records.append(
            RecoveryEvalCaseRecordV1(
                case_id=case.id,
                adjudication_cohort=cohort,
                original_query=case.query,
                quality_eligible=case.quality_eligible,
                gold_positive_chunk_ids=sorted(case.positive_chunk_ids()),
                initial=obs,
                triggered=triggered,
                classification=(
                    RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
                    if not triggered
                    else RecoveryEvalCaseClassV1.STILL_INSUFFICIENT
                ),
            )
        )
    return build_trigger_census(records)


def _latency_summary(values: Sequence[float | None]) -> LatencySummaryV1:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return LatencySummaryV1()
    return LatencySummaryV1(
        count=len(nums),
        mean_ms=float(mean(nums)),
        p50_ms=float(median(nums)),
        max_ms=float(max(nums)),
    )


def _macro_metric_dict(
    scores: Sequence[dict[str, float | None] | None],
) -> dict[str, float | None] | None:
    present = [s for s in scores if s is not None]
    if not present:
        return None
    keys = present[0].keys()
    out: dict[str, float | None] = {}
    for key in keys:
        avg, n = macro_average([s.get(key) for s in present])
        out[key] = avg if n > 0 else None
    return out


def _aggregate_cohort(
    records: Sequence[RecoveryEvalCaseRecordV1],
    *,
    cohort: LabelCohort | str,
) -> CohortAggregateV1:
    if cohort == "all":
        selected = list(records)
        label: str = "all"
    else:
        selected = [r for r in records if r.adjudication_cohort == cohort]
        label = cohort

    total = len(selected)
    trigger_count = sum(1 for r in selected if r.triggered)
    gold_pos = sum(
        1
        for r in selected
        if r.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED
    )
    unsupported = sum(
        1
        for r in selected
        if r.classification == RecoveryEvalCaseClassV1.UNSUPPORTED_RECOVERY
    )
    still = sum(
        1
        for r in selected
        if r.classification == RecoveryEvalCaseClassV1.STILL_INSUFFICIENT
    )
    failed = sum(
        1
        for r in selected
        if r.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED
    )
    recovered_sufficient = gold_pos + unsupported
    no_op = sum(
        1
        for r in selected
        if r.recovery is not None
        and r.recovery.rewritten_query is not None
        and r.recovery.rewritten_query == r.original_query
    )
    diverged = sum(1 for r in selected if r.happy_path_diverged)
    initial_sufficient = sum(1 for r in selected if not r.triggered)

    return CohortAggregateV1(
        cohort=label,  # type: ignore[arg-type]
        total_case_count=total,
        trigger_count=trigger_count,
        trigger_rate=(float(trigger_count) / float(total)) if total else None,
        recovered_sufficient_count=recovered_sufficient,
        gold_positive_recovery_count=gold_pos,
        still_insufficient_count=still,
        unsupported_recovery_count=unsupported,
        recovery_failure_count=failed,
        no_op_rewrite_count=no_op,
        happy_path_divergence_count=diverged,
        initial_sufficient_count=initial_sufficient,
        rewrite_latency=_latency_summary(
            [r.recovery.rewrite_latency_ms for r in selected if r.recovery is not None]
        ),
        recovery_context_latency=_latency_summary(
            [
                r.recovery.recovery_context_latency_ms
                for r in selected
                if r.recovery is not None
            ]
        ),
        incremental_recovery_latency=_latency_summary(
            [
                r.recovery.incremental_recovery_latency_ms
                for r in selected
                if r.recovery is not None
            ]
        ),
        ranking_metrics_initial=_macro_metric_dict(
            [r.initial_ranking for r in selected]
        ),
        ranking_metrics_recovery=_macro_metric_dict(
            [r.recovery_ranking for r in selected if r.triggered]
        ),
    )


def aggregate_recovery_eval(
    records: Sequence[RecoveryEvalCaseRecordV1],
    *,
    evaluation_identity_hash: str | None = None,
    rewriter_config_hash: str | None = None,
) -> RecoveryEvalAggregateV1:
    """Separate human-reviewed (authoritative) from assistant-only aggregates."""
    human = _aggregate_cohort(records, cohort="human_reviewed")
    assistant = _aggregate_cohort(records, cohort="assistant_only")
    conclusion = conclude_recovery_eval(
        human_trigger_count=human.trigger_count,
        gold_positive_recovery_count=human.gold_positive_recovery_count,
        unsupported_recovery_count=human.unsupported_recovery_count,
        recovery_failure_count=human.recovery_failure_count,
        happy_path_divergence_count=human.happy_path_divergence_count,
    )
    return RecoveryEvalAggregateV1(
        total_case_count=len(records),
        human_reviewed_count=human.total_case_count,
        assistant_only_count=assistant.total_case_count,
        human=human,
        assistant=assistant,
        conclusion=conclusion,
        evaluation_identity_hash=evaluation_identity_hash,
        rewriter_config_hash=rewriter_config_hash,
    )


def assert_single_initial_assemble(
    assembler: CountingInitialAssembler,
    *,
    expected_cases: int,
) -> None:
    """Fail closed if the harness accidentally re-ran initial retrieval."""
    if assembler.call_count != expected_cases:
        raise RecoveryEvalError(
            "shared-initial contract violated: expected "
            f"{expected_cases} initial assemble call(s), got {assembler.call_count}"
        )
