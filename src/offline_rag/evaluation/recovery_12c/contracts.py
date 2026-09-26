"""Slice 12C recovery evaluation contracts (``recovery-eval-v1``).

Evaluation-layer only. Consumes accepted 12A/12B recovery contracts; does not
redefine runtime recovery semantics. No generation, judge, or LangGraph.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class AttemptLatencyFieldsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_latency_ms: float | None = None
    rewrite_latency_ms: float | None = None
    recovery_context_latency_ms: float | None = None
    incremental_recovery_latency_ms: float | None = None


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


class RecoveryAttemptRecordV1(BaseModel):
    """Recovery arm fields when triggered; null when not triggered."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: ExactNonBlankStr | None = None
    rewriter_config_hash: ExactNonBlankStr | None = None
    rewrite_contract: ExactNonBlankStr | None = None
    rewrite_call_count: int = 0
    recovery_retrieval_attempt_count: int = 0
    terminal_outcome: RecoveryTerminalOutcomeV1 | None = None
    failure_reason: RecoveryFailureReasonV1 | None = None
    observation: AttemptObservationV1 | None = None
    rewrite_latency_ms: float | None = None
    recovery_context_latency_ms: float | None = None
    incremental_recovery_latency_ms: float | None = None


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


class LatencySummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int = 0
    mean_ms: float | None = None
    p50_ms: float | None = None
    max_ms: float | None = None


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
