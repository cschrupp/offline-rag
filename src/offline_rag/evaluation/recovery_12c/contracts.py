"""Slice 12C recovery evaluation contracts (``recovery-eval-v1``).

Evaluation-layer only. Consumes accepted 12A/12B recovery contracts; does not
redefine runtime recovery semantics. No generation, judge, or LangGraph.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from offline_rag.evaluation.generation_semantic.models import LabelCohort
from offline_rag.evaluation.metrics import RankingScore
from offline_rag.recovery.contracts import (
    RecoveryFailureReasonV1,
    RecoveryTerminalOutcomeV1,
)
from offline_rag.recovery.lineage import RecoveryLineageV1
from offline_rag.sufficiency.contracts import ExactNonBlankStr
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1, SUFFICIENCY_POLICY_V1

RECOVERY_EVAL_V1 = "recovery-eval-v1"
RECOVERY_EVAL_CONCLUSION_V1 = "recovery-eval-conclusion-v1"
RECOVERY_EVAL_PRESENCE_RULE_ID = "evidence-surface-chunk-id-overlap-v1"
RECOVERY_EVAL_PRESENCE_RULE_VERSION = "v1"
FROZEN_GOLD_DATASET_ID_12C = (
    "gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172"
)
PLACEHOLDER_REWRITER_MODEL = "REPLACE_WITH_APPROVED_LOCAL_MODEL"

_SUCCESS_RECOVERY_TERMINALS = frozenset(
    {
        RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT,
        RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY,
    }
)
_FAILURE_RECOVERY_TERMINAL = (
    RecoveryTerminalOutcomeV1.RECOVERY_PREPARATION_OR_EXECUTION_FAILED
)


class RecoveryEvalError(RuntimeError):
    """Fail-closed 12C evaluation harness error."""


class RecoveryEvalCaseClassV1(str, Enum):
    """Deterministic per-case classification."""

    INITIAL_SUFFICIENT_NO_RECOVERY = "initial_sufficient_no_recovery"
    GOLD_POSITIVE_RECOVERED = "gold_positive_recovered"
    UNSUPPORTED_RECOVERY = "unsupported_recovery"
    STILL_INSUFFICIENT = "still_insufficient"
    RECOVERY_FAILED = "recovery_failed"


class RecoveryEvalConclusionV1(str, Enum):
    """Predeclared OD-12C-6 conclusion states."""

    INSUFFICIENT_EVIDENCE_FOR_RECOVERY_EFFICACY = (
        "insufficient_evidence_for_recovery_efficacy"
    )
    RETAIN_DISABLED_NO_MEASURED_BENEFIT = "retain_disabled_no_measured_benefit"
    RETAIN_DISABLED_RECOVERY_REGRESSION = "retain_disabled_recovery_regression"
    PROMOTION_CANDIDATE = "promotion_candidate"


# Trigger-census stop before measurement (maps to insufficient-evidence family).
NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES = (
    "not_evaluable_no_human_recovery_opportunities"
)


class PresenceMatchingRuleV1(BaseModel):
    """Same 11B evidence-surface chunk-ID overlap rule (exact IDs only)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: Literal["evidence-surface-chunk-id-overlap-v1"] = (
        RECOVERY_EVAL_PRESENCE_RULE_ID
    )
    version: Literal["v1"] = RECOVERY_EVAL_PRESENCE_RULE_VERSION
    description: str = (
        "A Gold-positive chunk is present when its chunk_id appears in the "
        "evidence surface: union of anchors[].chunk_id, "
        "evidence_units[].source_chunk_id, and "
        "evidence_units[].primary_anchor_chunk_id. Exact chunk_id overlap only."
    )


class AttemptObservationV1(BaseModel):
    """Shared-initial or recovery attempt observation (IDs only; no body text)."""

    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    empty_context: bool
    evidence_unit_count: int
    triggered_gates: list[ExactNonBlankStr] = Field(default_factory=list)
    evidence_surface_chunk_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    ranked_anchor_chunk_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    gold_positive_overlap_chunk_ids: list[ExactNonBlankStr] = Field(
        default_factory=list
    )
    gold_positive_overlap: bool = False
    lineage: RecoveryLineageV1 | None = None
    stop_reason: ExactNonBlankStr | None = None
    latency_ms: float | None = None
    policy_contract: Literal["sufficiency-v1"] = SUFFICIENCY_POLICY_V1
    gate_contract: Literal["empty_context_v1"] = EMPTY_CONTEXT_GATE_V1

    @field_validator("evidence_unit_count")
    @classmethod
    def _nonneg_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("evidence_unit_count must be >= 0")
        return value

    @field_validator("latency_ms")
    @classmethod
    def _nonneg_latency(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("latency_ms must be >= 0")
        return value

    @model_validator(mode="after")
    def _sufficiency_v1_consistency(self) -> AttemptObservationV1:
        overlap_ids = list(self.gold_positive_overlap_chunk_ids)
        if bool(overlap_ids) != bool(self.gold_positive_overlap):
            raise ValueError(
                "gold_positive_overlap must equal "
                "(len(gold_positive_overlap_chunk_ids) > 0)"
            )
        if self.sufficient:
            if self.empty_context:
                raise ValueError("sufficient attempt cannot have empty_context=true")
            if self.evidence_unit_count <= 0:
                raise ValueError("sufficient attempt requires evidence_unit_count > 0")
            if list(self.triggered_gates):
                raise ValueError("sufficient attempt requires triggered_gates == []")
        else:
            if not self.empty_context:
                raise ValueError("insufficient attempt requires empty_context=true")
            if self.evidence_unit_count != 0:
                raise ValueError(
                    "insufficient attempt requires evidence_unit_count == 0"
                )
            if list(self.triggered_gates) != [EMPTY_CONTEXT_GATE_V1]:
                raise ValueError(
                    "insufficient attempt requires "
                    f"triggered_gates == [{EMPTY_CONTEXT_GATE_V1!r}]"
                )
        return self


class RecoveryAttemptRecordV1(BaseModel):
    """Recovery arm fields when triggered; null on the case when not triggered."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: ExactNonBlankStr | None = None
    rewriter_config_hash: ExactNonBlankStr | None = None
    adapter_contract: ExactNonBlankStr | None = None
    prompt_contract: ExactNonBlankStr | None = None
    output_contract: ExactNonBlankStr | None = None
    rewrite_call_count: int = 0
    recovery_retrieval_attempt_count: int = 0
    terminal_outcome: RecoveryTerminalOutcomeV1 | None = None
    failure_reason: RecoveryFailureReasonV1 | None = None
    observation: AttemptObservationV1 | None = None
    rewrite_latency_ms: float | None = None
    recovery_context_latency_ms: float | None = None
    incremental_recovery_latency_ms: float | None = None

    @field_validator(
        "rewrite_call_count",
        "recovery_retrieval_attempt_count",
    )
    @classmethod
    def _bounded_counts(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("attempt counts must be in {0,1}")
        return value

    @field_validator(
        "rewrite_latency_ms",
        "recovery_context_latency_ms",
        "incremental_recovery_latency_ms",
    )
    @classmethod
    def _nonneg_latencies(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("latency fields must be >= 0")
        return value

    @model_validator(mode="after")
    def _bounded_recovery_invariants(self) -> RecoveryAttemptRecordV1:
        terminal = self.terminal_outcome
        if terminal is None:
            raise ValueError("recovery attempt requires terminal_outcome")

        if terminal in _SUCCESS_RECOVERY_TERMINALS:
            if self.failure_reason is not None:
                raise ValueError(
                    "successful recovery terminal cannot carry failure_reason"
                )
            if (
                self.rewrite_call_count != 1
                or self.recovery_retrieval_attempt_count != 1
            ):
                raise ValueError(
                    "successful recovery terminal requires exactly one rewrite "
                    "and one recovery retrieval"
                )
            if self.observation is None:
                raise ValueError("successful recovery terminal requires observation")
            if self.observation.lineage is None:
                raise ValueError(
                    "successful recovery requires non-null recovery lineage"
                )
            if (
                terminal == RecoveryTerminalOutcomeV1.RECOVERED_EVIDENCE_SUFFICIENT
                and not self.observation.sufficient
            ):
                raise ValueError(
                    "RECOVERED_EVIDENCE_SUFFICIENT requires sufficient observation"
                )
            if (
                terminal
                == RecoveryTerminalOutcomeV1.INSUFFICIENT_AFTER_BOUNDED_RECOVERY
                and self.observation.sufficient
            ):
                raise ValueError(
                    "INSUFFICIENT_AFTER_BOUNDED_RECOVERY requires "
                    "insufficient observation"
                )
            return self

        if terminal == _FAILURE_RECOVERY_TERMINAL:
            if self.failure_reason is None:
                raise ValueError("failure terminal requires failure_reason")
            if (
                self.failure_reason
                == RecoveryFailureReasonV1.REWRITE_PREPARATION_FAILED
            ):
                if self.recovery_retrieval_attempt_count != 0:
                    raise ValueError(
                        "preparation failure cannot claim a recovery retrieval"
                    )
                if self.rewrite_call_count not in (0, 1):
                    raise ValueError(
                        "preparation failure rewrite_call_count must be 0 or 1"
                    )
            elif (
                self.failure_reason == RecoveryFailureReasonV1.RECOVERY_EXECUTION_FAILED
            ):
                if self.rewrite_call_count != 1:
                    raise ValueError(
                        "execution failure requires rewrite_call_count == 1"
                    )
                if self.recovery_retrieval_attempt_count != 1:
                    raise ValueError(
                        "execution failure requires recovery_retrieval_attempt_count == 1"
                    )
            return self

        raise ValueError(f"unsupported recovery terminal_outcome: {terminal}")


class RecoveryEvalCaseRecordV1(BaseModel):
    """Per-case paired shared-initial evaluation record."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-v1"] = RECOVERY_EVAL_V1
    case_id: ExactNonBlankStr
    adjudication_cohort: LabelCohort
    original_query: ExactNonBlankStr
    quality_eligible: bool
    gold_positive_chunk_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    initial: AttemptObservationV1
    triggered: bool
    classification: RecoveryEvalCaseClassV1
    rewrite_call_count: int = 0
    recovery_retrieval_attempt_count: int = 0
    happy_path_diverged: bool = False
    recovery: RecoveryAttemptRecordV1 | None = None
    initial_ranking: dict[str, float | None] | None = None
    recovery_ranking: dict[str, float | None] | None = None

    @field_validator("rewrite_call_count", "recovery_retrieval_attempt_count")
    @classmethod
    def _bounded_top_counts(cls, value: int) -> int:
        if value not in (0, 1):
            raise ValueError("attempt counts must be in {0,1}")
        return value

    @model_validator(mode="after")
    def _case_invariants(self) -> RecoveryEvalCaseRecordV1:
        expected_triggered = not self.initial.sufficient
        if self.triggered != expected_triggered:
            raise ValueError("triggered must equal (not initial.sufficient)")

        if self.initial.lineage is None:
            raise ValueError("authoritative case requires non-null initial lineage")

        if not self.triggered:
            if (
                self.classification
                != RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
            ):
                raise ValueError(
                    "non-trigger case must classify as initial_sufficient_no_recovery"
                )
            if (
                self.rewrite_call_count != 0
                or self.recovery_retrieval_attempt_count != 0
            ):
                raise ValueError(
                    "non-trigger case requires zero rewrite/recovery calls"
                )
            if self.recovery is not None:
                raise ValueError("non-trigger case must not carry a recovery record")
            return self

        # Triggered.
        if self.recovery is None:
            raise ValueError("triggered case requires a recovery attempt record")
        if self.rewrite_call_count != self.recovery.rewrite_call_count:
            raise ValueError("top-level rewrite_call_count must match recovery record")
        if (
            self.recovery_retrieval_attempt_count
            != self.recovery.recovery_retrieval_attempt_count
        ):
            raise ValueError(
                "top-level recovery_retrieval_attempt_count must match recovery record"
            )

        obs = self.recovery.observation
        terminal = self.recovery.terminal_outcome
        if self.classification == RecoveryEvalCaseClassV1.RECOVERY_FAILED:
            if terminal != _FAILURE_RECOVERY_TERMINAL:
                raise ValueError("recovery_failed requires failure terminal")
            return self

        if terminal == _FAILURE_RECOVERY_TERMINAL:
            raise ValueError("failure terminal must classify as recovery_failed")

        if obs is None:
            raise ValueError("non-failure triggered case requires recovery observation")
        if obs.lineage is None:
            raise ValueError("successful recovery requires non-null recovery lineage")

        if self.classification == RecoveryEvalCaseClassV1.GOLD_POSITIVE_RECOVERED:
            if not (obs.sufficient and obs.gold_positive_overlap):
                raise ValueError(
                    "gold_positive_recovered requires recovered sufficient + Gold overlap"
                )
        elif self.classification == RecoveryEvalCaseClassV1.UNSUPPORTED_RECOVERY:
            if not (obs.sufficient and not obs.gold_positive_overlap):
                raise ValueError(
                    "unsupported_recovery requires recovered sufficient + no Gold overlap"
                )
        elif self.classification == RecoveryEvalCaseClassV1.STILL_INSUFFICIENT:
            if obs.sufficient:
                raise ValueError("still_insufficient requires recovered insufficient")
        elif (
            self.classification
            == RecoveryEvalCaseClassV1.INITIAL_SUFFICIENT_NO_RECOVERY
        ):
            raise ValueError("triggered case cannot classify as initial_sufficient")
        else:
            raise ValueError(
                f"unexpected classification for triggered case: {self.classification}"
            )
        return self


class TriggerCensusV1(BaseModel):
    """OD-12C-3 trigger membership before any rewrite/recovery result."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-v1"] = RECOVERY_EVAL_V1
    human_trigger_case_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    assistant_trigger_case_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    human_trigger_count: int = 0
    assistant_trigger_count: int = 0
    not_evaluable: bool = False
    stop_reason: ExactNonBlankStr | None = None

    @model_validator(mode="after")
    def _census_invariants(self) -> TriggerCensusV1:
        human_ids = list(self.human_trigger_case_ids)
        assistant_ids = list(self.assistant_trigger_case_ids)
        if len(human_ids) != len(set(human_ids)):
            raise ValueError("human_trigger_case_ids must be unique")
        if len(assistant_ids) != len(set(assistant_ids)):
            raise ValueError("assistant_trigger_case_ids must be unique")
        if set(human_ids) & set(assistant_ids):
            raise ValueError("human and assistant trigger sets must be disjoint")
        if self.human_trigger_count != len(human_ids):
            raise ValueError(
                "human_trigger_count must equal len(human_trigger_case_ids)"
            )
        if self.assistant_trigger_count != len(assistant_ids):
            raise ValueError(
                "assistant_trigger_count must equal len(assistant_trigger_case_ids)"
            )
        if self.human_trigger_count < 0 or self.assistant_trigger_count < 0:
            raise ValueError("trigger counts must be >= 0")
        expected_not_evaluable = self.human_trigger_count == 0
        if self.not_evaluable != expected_not_evaluable:
            raise ValueError("not_evaluable must equal (human_trigger_count == 0)")
        if self.not_evaluable:
            if self.stop_reason != NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES:
                raise ValueError(
                    "not_evaluable requires stop_reason "
                    f"== {NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES!r}"
                )
        elif self.stop_reason is not None:
            raise ValueError("stop_reason must be null when evaluable")
        return self


class LatencySummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 0
    mean_ms: float | None = None
    p50_ms: float | None = None
    max_ms: float | None = None

    @field_validator("count")
    @classmethod
    def _nonneg(cls, value: int) -> int:
        if value < 0:
            raise ValueError("count must be >= 0")
        return value


class CohortAggregateV1(BaseModel):
    """Aggregate counts for one adjudication cohort (or combined descriptive)."""

    model_config = ConfigDict(extra="forbid")

    cohort: Literal["human_reviewed", "assistant_only", "all"]
    total_case_count: int = 0
    trigger_count: int = 0
    trigger_rate: float | None = None
    recovered_sufficient_count: int = 0
    gold_positive_recovery_count: int = 0
    still_insufficient_count: int = 0
    unsupported_recovery_count: int = 0
    recovery_failure_count: int = 0
    no_op_rewrite_count: int = 0
    happy_path_divergence_count: int = 0
    initial_sufficient_count: int = 0
    rewrite_latency: LatencySummaryV1 = Field(default_factory=LatencySummaryV1)
    recovery_context_latency: LatencySummaryV1 = Field(default_factory=LatencySummaryV1)
    incremental_recovery_latency: LatencySummaryV1 = Field(
        default_factory=LatencySummaryV1
    )
    ranking_metrics_initial: dict[str, float | None] | None = None
    ranking_metrics_recovery: dict[str, float | None] | None = None

    @model_validator(mode="after")
    def _cohort_arithmetic(self) -> CohortAggregateV1:
        for name in (
            "total_case_count",
            "trigger_count",
            "recovered_sufficient_count",
            "gold_positive_recovery_count",
            "still_insufficient_count",
            "unsupported_recovery_count",
            "recovery_failure_count",
            "no_op_rewrite_count",
            "happy_path_divergence_count",
            "initial_sufficient_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        if self.trigger_count > self.total_case_count:
            raise ValueError("trigger_count cannot exceed total_case_count")
        if self.initial_sufficient_count != self.total_case_count - self.trigger_count:
            raise ValueError(
                "initial_sufficient_count must equal total_case_count - trigger_count"
            )
        if self.recovered_sufficient_count != (
            self.gold_positive_recovery_count + self.unsupported_recovery_count
        ):
            raise ValueError(
                "recovered_sufficient_count must equal "
                "gold_positive_recovery_count + unsupported_recovery_count"
            )
        partitioned = (
            self.gold_positive_recovery_count
            + self.unsupported_recovery_count
            + self.still_insufficient_count
            + self.recovery_failure_count
        )
        if partitioned != self.trigger_count:
            raise ValueError(
                "triggered classifications must partition the trigger population"
            )
        return self


class RecoveryEvalAggregateV1(BaseModel):
    """Authoritative human aggregates + descriptive assistant aggregates."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-v1"] = RECOVERY_EVAL_V1
    conclusion_contract: Literal["recovery-eval-conclusion-v1"] = (
        RECOVERY_EVAL_CONCLUSION_V1
    )
    total_case_count: int = 0
    human_reviewed_count: int = 0
    assistant_only_count: int = 0
    human: CohortAggregateV1
    assistant: CohortAggregateV1
    conclusion: RecoveryEvalConclusionV1
    presence_rule: PresenceMatchingRuleV1 = Field(
        default_factory=PresenceMatchingRuleV1
    )
    evaluation_identity_hash: ExactNonBlankStr | None = None
    rewriter_config_hash: ExactNonBlankStr | None = None
    experimental_limitation: str = (
        "Current Gold fixture does not provide authoritative "
        "unanswerable/negative truth; 12C cannot establish false-recovery "
        "rate on genuinely unanswerable questions."
    )

    @model_validator(mode="after")
    def _aggregate_invariants(self) -> RecoveryEvalAggregateV1:
        if self.total_case_count < 0:
            raise ValueError("total_case_count must be >= 0")
        if self.human.cohort != "human_reviewed":
            raise ValueError("human aggregate cohort must be human_reviewed")
        if self.assistant.cohort != "assistant_only":
            raise ValueError("assistant aggregate cohort must be assistant_only")
        if self.human_reviewed_count != self.human.total_case_count:
            raise ValueError("human_reviewed_count must match human.total_case_count")
        if self.assistant_only_count != self.assistant.total_case_count:
            raise ValueError(
                "assistant_only_count must match assistant.total_case_count"
            )
        if (
            self.human_reviewed_count + self.assistant_only_count
            != self.total_case_count
        ):
            raise ValueError(
                "human + assistant totals must equal aggregate total_case_count"
            )
        # Local import avoids circular import with conclusion module.
        from offline_rag.evaluation.recovery_12c.conclusion import (
            conclude_recovery_eval,
        )

        expected = conclude_recovery_eval(
            human_trigger_count=self.human.trigger_count,
            gold_positive_recovery_count=self.human.gold_positive_recovery_count,
            unsupported_recovery_count=self.human.unsupported_recovery_count,
            recovery_failure_count=self.human.recovery_failure_count,
            happy_path_divergence_count=self.human.happy_path_divergence_count,
        )
        if self.conclusion != expected:
            raise ValueError(
                f"stored conclusion {self.conclusion} mismatches recomputed {expected}"
            )
        return self


def ranking_score_to_dict(score: RankingScore) -> dict[str, float | None]:
    """Flatten RankingScore into a stable metric dict (existing semantics)."""
    return {
        "recall_at_1": score.recall.get(1),
        "recall_at_5": score.recall.get(5),
        "recall_at_10": score.recall.get(10),
        "precision_at_1": score.precision.get(1),
        "precision_at_5": score.precision.get(5),
        "precision_at_10": score.precision.get(10),
        "hit_rate_at_1": score.hit_rate.get(1),
        "hit_rate_at_5": score.hit_rate.get(5),
        "hit_rate_at_10": score.hit_rate.get(10),
        "mrr": score.mrr,
        "ndcg_at_1": score.ndcg.get(1),
        "ndcg_at_5": score.ndcg.get(5),
        "ndcg_at_10": score.ndcg.get(10),
    }
