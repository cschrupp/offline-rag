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
GENERATION_SEMANTIC_METRICS_V1 = "generation-semantic-metrics-v1"

LabelCohort = Literal["human_reviewed", "assistant_only"]
CohortKey = Literal["full", "human_reviewed", "assistant_only"]
JudgeStatus = Literal[
    "disabled",
    "not_applicable",
    "succeeded",
    "judge_unavailable",
    "judge_failed",
]
JudgeFailureReason = Literal[
    "timeout",
    "transport_error",
    "http_error",
    "empty_response",
    "invalid_json",
    "schema_invalid",
    "redirect_not_allowed",
    "authentication_error",
    "prompt_build_error",
    "provider_error",
]
AnswerCorrectness = Literal["fully_correct", "partially_correct", "incorrect"]
Faithfulness = Literal["fully_supported", "partially_supported", "unsupported"]
Completeness = Literal["complete", "partial", "incomplete"]
CitationCoverage = Literal["complete", "partial", "unsupported"]
CitationUsefulness = Literal["all_useful", "some_irrelevant", "mostly_irrelevant"]


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


class GenerationSemanticJudgeCaseResultV1(BaseModel):
    """Per-case Layer-2 judge outcome (null fields unless succeeded)."""

    model_config = ConfigDict(extra="forbid")

    judge_status: JudgeStatus
    judge_failure_reason: JudgeFailureReason | None = None
    answer_correctness: AnswerCorrectness | None = None
    faithfulness: Faithfulness | None = None
    completeness: Completeness | None = None
    citation_coverage: CitationCoverage | None = None
    citation_usefulness: CitationUsefulness | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_key_points: list[str] = Field(default_factory=list)
    irrelevant_citation_ids: list[str] = Field(default_factory=list)
    rationale: str | None = None
    judge_latency_ms: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _semantic_only_when_succeeded(
        self,
    ) -> GenerationSemanticJudgeCaseResultV1:
        semantic_set = any(
            value is not None
            for value in (
                self.answer_correctness,
                self.faithfulness,
                self.completeness,
                self.citation_coverage,
                self.citation_usefulness,
                self.rationale,
            )
        ) or bool(
            self.unsupported_claims
            or self.missing_key_points
            or self.irrelevant_citation_ids
        )
        if self.judge_status == "succeeded":
            if self.judge_failure_reason is not None:
                raise ValueError("succeeded judge_result cannot have failure_reason")
            required = (
                self.answer_correctness,
                self.faithfulness,
                self.completeness,
                self.citation_coverage,
                self.citation_usefulness,
                self.rationale,
            )
            if any(item is None for item in required):
                raise ValueError("succeeded judge_result requires all rubric fields")
            return self
        if semantic_set:
            raise ValueError(
                "semantic judge fields must be null/empty unless judge_status=succeeded"
            )
        if self.judge_status == "judge_failed" and self.judge_failure_reason is None:
            raise ValueError("judge_failed requires judge_failure_reason")
        return self


class GenerationSemanticJudgeProvenanceV1(BaseModel):
    """Typed judge provenance for offline-rag-generation-semantic-eval-result-v1."""

    model_config = ConfigDict(extra="forbid")

    judge_requested: bool = False
    judge_available: bool = False
    judge_config_hash: NonEmptyStr | None = None
    provider: NonEmptyStr | None = None
    normalized_endpoint: NonEmptyStr | None = None
    model: str | None = None
    adapter_contract: NonEmptyStr | None = None
    prompt_contract: NonEmptyStr | None = None
    output_contract: NonEmptyStr | None = None
    reasoning_contract: NonEmptyStr | None = None
    network_policy: NonEmptyStr | None = None
    same_model_self_judge: bool | None = None
    same_endpoint_as_generator: bool | None = None
    preflight_status: NonEmptyStr | None = None
    preflight_reason: str | None = None
    preflight_kind: str | None = None


class GenerationSemanticDimensionCountsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    counts: dict[str, NonNegativeInt] = Field(default_factory=dict)


class GenerationSemanticCohortAggregateV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort: CohortKey
    case_count: NonNegativeInt = 0
    answered_count: NonNegativeInt = 0
    eligible_answered_cases: NonNegativeInt = 0
    judge_succeeded: NonNegativeInt = 0
    judge_failed: NonNegativeInt = 0
    judge_unavailable: NonNegativeInt = 0
    answer_correctness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    faithfulness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    completeness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    citation_coverage: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    citation_usefulness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    fully_correct_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    fully_supported_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    complete_answer_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    complete_citation_coverage_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    all_citations_useful_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )


class GenerationSemanticAggregatesV1(BaseModel):
    """Layer-2 semantic aggregates over answered + successful judgments."""

    model_config = ConfigDict(extra="forbid")

    metric_contract: NonEmptyStr = GENERATION_SEMANTIC_METRICS_V1
    eligible_answered_cases: NonNegativeInt = 0
    judge_succeeded: NonNegativeInt = 0
    judge_failed: NonNegativeInt = 0
    judge_unavailable: NonNegativeInt = 0
    answer_correctness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    faithfulness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    completeness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    citation_coverage: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    citation_usefulness: GenerationSemanticDimensionCountsV1 = Field(
        default_factory=GenerationSemanticDimensionCountsV1
    )
    fully_correct_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    fully_supported_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    complete_answer_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    complete_citation_coverage_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    all_citations_useful_rate: GenerationMetricValueV1 = Field(
        default_factory=GenerationMetricValueV1
    )
    cohorts: dict[str, GenerationSemanticCohortAggregateV1] = Field(
        default_factory=dict
    )


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
    judge_result: GenerationSemanticJudgeCaseResultV1 | None = None

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
    judge_provenance: GenerationSemanticJudgeProvenanceV1 | None = None

    population: GenerationSemanticPopulationV1 = Field(
        default_factory=GenerationSemanticPopulationV1
    )
    deterministic_aggregates: GenerationDeterministicAggregatesV1 = Field(
        default_factory=GenerationDeterministicAggregatesV1
    )
    semantic_aggregates: GenerationSemanticAggregatesV1 | None = None
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
