"""Slice 10 generation-semantic evaluation artifact contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, Score

GENERATION_EVIDENCE_SET_V1 = "offline-rag-generation-evidence-set-v1"
GENERATION_SEMANTIC_EVAL_RESULT_V1 = "offline-rag-generation-semantic-eval-result-v1"
GENERATION_SEMANTIC_EVAL_COMPARISON_V1 = (
    "offline-rag-generation-semantic-eval-comparison-v1"
)
GENERATION_SEMANTIC_DETERMINISTIC_V1 = "generation-semantic-deterministic-v1"
GENERATION_COHORT_MAP_V1 = "offline-rag-generation-cohort-map-v1"

LabelCohort = Literal["human_reviewed", "assistant_only"]
CohortKey = Literal["full", "human_reviewed", "assistant_only"]


class GoldEvidenceJudgmentV1(BaseModel):
    """Evaluator-only gold judgment metadata (never prompted)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    relevance: Literal[1, 2]


class GenerationEvidenceCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    label_cohort: LabelCohort
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    gold_judgments: list[GoldEvidenceJudgmentV1] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _query_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be non-empty")
        return value


class GenerationEvidenceSetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_EVIDENCE_SET_V1
    evidence_set_id: NonEmptyStr
    evidence_contract: NonEmptyStr
    source_gold_dataset_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr
    corpus_name: NonEmptyStr
    source_name_by_document_id: dict[str, str] = Field(default_factory=dict)
    cases: list[GenerationEvidenceCaseV1] = Field(default_factory=list)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> GenerationEvidenceSetV1:
        seen: set[str] = set()
        for case in self.cases:
            if case.case_id in seen:
                raise ValueError(f"duplicate case_id in evidence set: {case.case_id}")
            seen.add(case.case_id)
        return self


class GenerationMetricValueV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    applicable_count: NonNegativeInt = 0


class GenerationLatencySummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean_ms: Score = 0.0
    p50_ms: Score = 0.0
    p95_ms: Score = 0.0
    executed_count: NonNegativeInt = 0
    generation_mean_ms: Score = 0.0


class GenerationSemanticPopulationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: NonNegativeInt = 0
    executed_cases: NonNegativeInt = 0
    human_reviewed_cases: NonNegativeInt = 0
    assistant_only_cases: NonNegativeInt = 0
    answered: NonNegativeInt = 0
    model_abstain: NonNegativeInt = 0
    generation_failed: NonNegativeInt = 0
    citation_invalid: NonNegativeInt = 0
    empty_context: NonNegativeInt = 0


class GenerationDeterministicCaseMetricsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gold_positive_count: NonNegativeInt = 0
    gold_grade2_count: NonNegativeInt = 0
    gold_grade1_count: NonNegativeInt = 0
    cited_evidence_count: NonNegativeInt = 0
    cited_gold_chunk_ids: list[str] = Field(default_factory=list)
    cited_gold_grade2_count: NonNegativeInt = 0
    cited_gold_grade1_count: NonNegativeInt = 0
    gold_citation_recall: float | None = None
    grade2_citation_hit: bool | None = None


class GenerationCohortAggregateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort: CohortKey
    case_count: NonNegativeInt = 0
    answer_rate: float | None = None
    false_abstention_rate: float | None = None
    generation_failed_rate: float | None = None
    citation_invalid_rate: float | None = None
    empty_context_rate: float | None = None
    mean_gold_citation_recall: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    grade2_citation_hit_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    latency: GenerationLatencySummaryV1 = Field(
        default_factory=GenerationLatencySummaryV1
    )


class GenerationDeterministicAggregatesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_contract: NonEmptyStr = GENERATION_SEMANTIC_DETERMINISTIC_V1
    answer_rate: float | None = None
    false_abstention_rate: float | None = None
    generation_failed_rate: float | None = None
    citation_invalid_rate: float | None = None
    empty_context_rate: float | None = None
    mean_gold_citation_recall: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    grade2_citation_hit_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    citation_count_mean: float | None = None
    citation_count_p50: float | None = None
    citation_count_p95: float | None = None
    latency: GenerationLatencySummaryV1 = Field(
        default_factory=GenerationLatencySummaryV1
    )
    cohorts: dict[str, GenerationCohortAggregateV1] = Field(default_factory=dict)


class GenerationSemanticEvalCaseResultV1(BaseModel):
    """Per-case semantic-eval row with Layer-1 deterministic diagnostics."""

    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    label_cohort: LabelCohort | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)

    status: NonEmptyStr | None = None
    abstention_reason: str | None = None
    generation_failure_reason: str | None = None
    answer_text: str | None = None
    citation_ids: list[str] = Field(default_factory=list)
    resolved_citation_source_chunk_ids: list[str] = Field(default_factory=list)

    generator_invoked: bool = False
    attempt_count: NonNegativeInt = 0
    generation_config_hash: NonEmptyStr | None = None
    prompt_contract: NonEmptyStr | None = None

    deterministic_metrics: GenerationDeterministicCaseMetricsV1 = Field(
        default_factory=GenerationDeterministicCaseMetricsV1
    )
    judge_result: dict[str, Any] | None = None

    latency_ms: NonNegativeInt | None = None
    generation_latency_ms: NonNegativeInt | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationSemanticEvalResultV1(BaseModel):
    """offline-rag-generation-semantic-eval-result-v1 envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_SEMANTIC_EVAL_RESULT_V1
    run_id: NonEmptyStr

    gold_dataset_id: NonEmptyStr
    evidence_set_id: NonEmptyStr
    evidence_contract: NonEmptyStr
    semantic_metric_contract: NonEmptyStr = GENERATION_SEMANTIC_DETERMINISTIC_V1

    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None

    generation_config_hash: NonEmptyStr
    generation_semantic_provenance: dict[str, Any] = Field(default_factory=dict)

    judge_enabled: bool = False
    judge_provenance: dict[str, Any] | None = None

    population: GenerationSemanticPopulationV1 = Field(
        default_factory=GenerationSemanticPopulationV1
    )
    deterministic_aggregates: GenerationDeterministicAggregatesV1 = Field(
        default_factory=GenerationDeterministicAggregatesV1
    )
    semantic_aggregates: dict[str, Any] | None = None
    abstention_aggregates: dict[str, Any] | None = None

    cases: list[GenerationSemanticEvalCaseResultV1] = Field(default_factory=list)

    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationSemanticEvalComparisonV1(BaseModel):
    """offline-rag-generation-semantic-eval-comparison-v1 (artifact-only; 10E)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_SEMANTIC_EVAL_COMPARISON_V1
    comparison_id: NonEmptyStr | None = None

    gold_dataset_id: NonEmptyStr
    evidence_set_id: NonEmptyStr
    semantic_metric_contract: NonEmptyStr

    a_run_id: NonEmptyStr
    b_run_id: NonEmptyStr
    a_generation_config_hash: NonEmptyStr | None = None
    b_generation_config_hash: NonEmptyStr | None = None
    a_prompt_contract: NonEmptyStr | None = None
    b_prompt_contract: NonEmptyStr | None = None

    compatibility: dict[str, Any] = Field(default_factory=dict)
    aggregates: dict[str, Any] = Field(default_factory=dict)
    cases: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationCohortMapCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    label_cohort: LabelCohort


class GenerationCohortMapV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_COHORT_MAP_V1
    gold_dataset_id: NonEmptyStr
    cases: list[GenerationCohortMapCaseV1] = Field(default_factory=list)
