"""Slice 10 generation-semantic evaluation artifact contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt, PositiveInt, Score
from offline_rag.gold_authoring.contracts import RETRIEVER_HYBRID_RERANK_V1

GENERATION_EVIDENCE_SET_V1 = "offline-rag-generation-evidence-set-v1"
GENERATION_SEMANTIC_EVAL_RESULT_V1 = "offline-rag-generation-semantic-eval-result-v1"
GENERATION_SEMANTIC_EVAL_COMPARISON_V1 = (
    "offline-rag-generation-semantic-eval-comparison-v1"
)
GENERATION_SEMANTIC_DETERMINISTIC_V1 = "generation-semantic-deterministic-v1"
GENERATION_ABSTENTION_DETERMINISTIC_V1 = "generation-abstention-deterministic-v1"
GENERATION_COHORT_MAP_V1 = "offline-rag-generation-cohort-map-v1"
GENERATION_SEMANTIC_METRICS_V1 = "generation-semantic-metrics-v1"

GOLD_EVIDENCE_V1 = "gold-evidence-v1"
HUMAN_GRADE0_HARD_NEGATIVE_V1 = "human-grade0-hard-negative-v1"
HARD_NEGATIVE_N_V1 = 5
HARD_NEGATIVE_RETRIEVER_V1 = RETRIEVER_HYBRID_RERANK_V1

LabelCohort = Literal["human_reviewed", "assistant_only"]
CohortKey = Literal["full", "human_reviewed", "assistant_only"]
ExpectedBehavior = Literal["answer", "abstain"]
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


class GenerationHardNegativeSelectedCandidateV1(BaseModel):
    """One selected human grade-0 hard-negative candidate (provenance only)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    human_relevance: Literal[0] = 0
    retriever: NonEmptyStr = HARD_NEGATIVE_RETRIEVER_V1
    rank: PositiveInt

    @model_validator(mode="after")
    def _selection_hit_invariants(
        self,
    ) -> GenerationHardNegativeSelectedCandidateV1:
        if self.human_relevance != 0:
            raise ValueError("selected hard-negative human_relevance must be 0")
        if self.retriever != HARD_NEGATIVE_RETRIEVER_V1:
            raise ValueError(
                f"selected hard-negative retriever must be "
                f"{HARD_NEGATIVE_RETRIEVER_V1!r}"
            )
        if self.rank < 1:
            raise ValueError("selected hard-negative rank must be >= 1")
        return self


class GenerationHardNegativeSelectionV1(BaseModel):
    """Case-level hard-negative selection provenance (Slice 10D)."""

    model_config = ConfigDict(extra="forbid")

    selection_contract: NonEmptyStr = HUMAN_GRADE0_HARD_NEGATIVE_V1
    authoring_run_id: NonEmptyStr
    source_silver_case_id: NonEmptyStr
    grade_basis_query: NonEmptyStr
    retriever: NonEmptyStr = HARD_NEGATIVE_RETRIEVER_V1
    requested_count: PositiveInt = HARD_NEGATIVE_N_V1
    selected_candidates: list[GenerationHardNegativeSelectedCandidateV1] = Field(
        default_factory=list
    )
    candidate_pool_size: NonNegativeInt | None = None
    eligible_grade0_hard_candidate_count: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _selection_contract_invariants(
        self,
    ) -> GenerationHardNegativeSelectionV1:
        if self.selection_contract != HUMAN_GRADE0_HARD_NEGATIVE_V1:
            raise ValueError(
                f"selection_contract must be {HUMAN_GRADE0_HARD_NEGATIVE_V1!r}"
            )
        if self.retriever != HARD_NEGATIVE_RETRIEVER_V1:
            raise ValueError(
                f"hard-negative retriever must be {HARD_NEGATIVE_RETRIEVER_V1!r}"
            )
        if self.requested_count != HARD_NEGATIVE_N_V1:
            raise ValueError(
                f"hard-negative requested_count must be {HARD_NEGATIVE_N_V1}"
            )
        if len(self.selected_candidates) != HARD_NEGATIVE_N_V1:
            raise ValueError(
                f"hard-negative selection requires exactly {HARD_NEGATIVE_N_V1} "
                f"candidates; got {len(self.selected_candidates)}"
            )
        seen: set[str] = set()
        for candidate in self.selected_candidates:
            if candidate.chunk_id in seen:
                raise ValueError(
                    f"duplicate selected hard-negative chunk_id: {candidate.chunk_id}"
                )
            seen.add(candidate.chunk_id)
        return self


class GenerationEvidenceCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    label_cohort: LabelCohort
    expected_behavior: ExpectedBehavior = "answer"
    evidence_units: list[EvidenceUnit] = Field(default_factory=list)
    gold_judgments: list[GoldEvidenceJudgmentV1] = Field(default_factory=list)
    hard_negative_selection: GenerationHardNegativeSelectionV1 | None = None

    @field_validator("query")
    @classmethod
    def _query_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must be non-empty")
        return value

    @model_validator(mode="after")
    def _expected_behavior_coherence(self) -> GenerationEvidenceCaseV1:
        if self.expected_behavior == "abstain":
            if self.hard_negative_selection is None:
                raise ValueError(
                    "expected_behavior=abstain requires hard_negative_selection"
                )
        elif self.hard_negative_selection is not None:
            raise ValueError(
                "hard_negative_selection is only valid when expected_behavior=abstain"
            )
        return self


class GenerationEvidenceSetV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_EVIDENCE_SET_V1
    evidence_set_id: NonEmptyStr
    evidence_contract: NonEmptyStr
    expected_behavior: ExpectedBehavior = "answer"
    source_gold_dataset_id: NonEmptyStr
    chunk_set_id: NonEmptyStr
    corpus_id: NonEmptyStr
    corpus_name: NonEmptyStr
    source_name_by_document_id: dict[str, str] = Field(default_factory=dict)
    cases: list[GenerationEvidenceCaseV1] = Field(default_factory=list)
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _unique_case_ids_and_contract(self) -> GenerationEvidenceSetV1:
        seen: set[str] = set()
        for case in self.cases:
            if case.case_id in seen:
                raise ValueError(f"duplicate case_id in evidence set: {case.case_id}")
            seen.add(case.case_id)
            if case.expected_behavior != self.expected_behavior:
                raise ValueError(
                    f"case {case.case_id} expected_behavior="
                    f"{case.expected_behavior!r} mismatches set "
                    f"{self.expected_behavior!r}"
                )

        if self.evidence_contract == GOLD_EVIDENCE_V1:
            if self.expected_behavior != "answer":
                raise ValueError(
                    f"{GOLD_EVIDENCE_V1} requires expected_behavior='answer'"
                )
            for case in self.cases:
                if case.hard_negative_selection is not None:
                    raise ValueError(
                        f"{GOLD_EVIDENCE_V1} case {case.case_id} must not carry "
                        "hard_negative_selection"
                    )
        elif self.evidence_contract == HUMAN_GRADE0_HARD_NEGATIVE_V1:
            if self.expected_behavior != "abstain":
                raise ValueError(
                    f"{HUMAN_GRADE0_HARD_NEGATIVE_V1} requires "
                    "expected_behavior='abstain'"
                )
            for case in self.cases:
                if case.label_cohort != "human_reviewed":
                    raise ValueError(
                        f"{HUMAN_GRADE0_HARD_NEGATIVE_V1} requires "
                        f"human_reviewed cohort; case {case.case_id} is "
                        f"{case.label_cohort}"
                    )
                if case.hard_negative_selection is None:
                    raise ValueError(
                        f"{HUMAN_GRADE0_HARD_NEGATIVE_V1} case {case.case_id} "
                        "requires hard_negative_selection"
                    )
                selected_ids = {
                    item.chunk_id
                    for item in case.hard_negative_selection.selected_candidates
                }
                evidence_ids = {unit.source_chunk_id for unit in case.evidence_units}
                if evidence_ids != selected_ids:
                    raise ValueError(
                        f"case {case.case_id}: evidence_units source_chunk_ids "
                        "must equal hard_negative_selection selected chunk_ids"
                    )
                if len(case.evidence_units) != HARD_NEGATIVE_N_V1:
                    raise ValueError(
                        f"case {case.case_id}: hard-negative evidence must have "
                        f"exactly {HARD_NEGATIVE_N_V1} units"
                    )
                gold_positive_ids = {j.chunk_id for j in case.gold_judgments}
                leaked = evidence_ids & gold_positive_ids
                if leaked:
                    raise ValueError(
                        f"case {case.case_id}: positive gold chunk(s) leaked into "
                        f"hard-negative evidence: {sorted(leaked)}"
                    )
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


class GenerationAbstentionCohortAggregateV1(BaseModel):
    """Cohort slice of label-defined hard-negative abstention metrics."""

    model_config = ConfigDict(extra="forbid")

    cohort: CohortKey
    case_count: NonNegativeInt = 0
    correct_abstention_rate: float | None = None
    false_answer_rate: float | None = None
    generation_failed_rate: float | None = None
    citation_invalid_rate: float | None = None
    empty_context_rate: float | None = None
    latency: GenerationLatencySummaryV1 = Field(
        default_factory=GenerationLatencySummaryV1
    )


class GenerationAbstentionAggregatesV1(BaseModel):
    """Typed Layer-1 abstention aggregates for human-grade0-hard-negative-v1."""

    model_config = ConfigDict(extra="forbid")

    metric_contract: NonEmptyStr = GENERATION_ABSTENTION_DETERMINISTIC_V1
    total_cases: NonNegativeInt = 0
    correct_abstention_rate: float | None = None
    false_answer_rate: float | None = None
    generation_failed_rate: float | None = None
    citation_invalid_rate: float | None = None
    empty_context_rate: float | None = None
    latency: GenerationLatencySummaryV1 = Field(
        default_factory=GenerationLatencySummaryV1
    )
    cohorts: dict[str, GenerationAbstentionCohortAggregateV1] = Field(
        default_factory=dict
    )


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
    expected_behavior: ExpectedBehavior = "answer"
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
    abstention_aggregates: GenerationAbstentionAggregatesV1 | None = None

    cases: list[GenerationSemanticEvalCaseResultV1] = Field(default_factory=list)

    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _behavior_contract_coherence(self) -> GenerationSemanticEvalResultV1:
        if self.evidence_contract == GOLD_EVIDENCE_V1:
            if self.expected_behavior != "answer":
                raise ValueError(
                    f"{GOLD_EVIDENCE_V1} result requires expected_behavior='answer'"
                )
            if self.abstention_aggregates is not None:
                raise ValueError(
                    f"{GOLD_EVIDENCE_V1} result must have abstention_aggregates=null"
                )
        elif self.evidence_contract == HUMAN_GRADE0_HARD_NEGATIVE_V1:
            if self.expected_behavior != "abstain":
                raise ValueError(
                    f"{HUMAN_GRADE0_HARD_NEGATIVE_V1} result requires "
                    "expected_behavior='abstain'"
                )
            if self.abstention_aggregates is None:
                raise ValueError(
                    f"{HUMAN_GRADE0_HARD_NEGATIVE_V1} result requires "
                    "abstention_aggregates"
                )
        return self


class GenerationSemanticEvalComparisonV1(BaseModel):
    """offline-rag-generation-semantic-eval-comparison-v1 (artifact-only; 10E)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_SEMANTIC_EVAL_COMPARISON_V1
    comparison_id: NonEmptyStr

    gold_dataset_id: NonEmptyStr
    evidence_set_id: NonEmptyStr
    evidence_contract: NonEmptyStr
    expected_behavior: ExpectedBehavior
    semantic_metric_contract: NonEmptyStr

    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None

    a_run_id: NonEmptyStr
    b_run_id: NonEmptyStr
    a_generation_config_hash: NonEmptyStr
    b_generation_config_hash: NonEmptyStr
    a_prompt_contract: NonEmptyStr
    b_prompt_contract: NonEmptyStr
    a_judge_config_hash: NonEmptyStr | None = None
    b_judge_config_hash: NonEmptyStr | None = None

    compatibility: GenerationCompareCompatibilityV1
    positive_aggregates: GenerationPositiveCompareAggregatesV1 | None = None
    negative_aggregates: GenerationNegativeCompareAggregatesV1 | None = None
    semantic_transitions: GenerationSemanticTransitionSummaryV1 | None = None
    cases: list[GenerationCompareCaseV1] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationCompareCompatibilityV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_gold_dataset_id: bool
    same_evidence_set_id: bool
    same_evidence_contract: bool
    same_expected_behavior: bool
    same_corpus_id: bool
    same_chunk_set_id: bool
    same_case_set: bool
    same_queries: bool
    same_cohort_labels: bool
    same_semantic_metric_contract: bool
    same_generation_semantics_except_prompt: bool
    same_judge_contract: bool
    prompt_pair_accepted: bool
    a_prompt_contract: NonEmptyStr
    b_prompt_contract: NonEmptyStr


class MetricDeltaV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: float | None = None
    b: float | None = None
    delta: float | None = None
    a_applicable_count: NonNegativeInt | None = None
    b_applicable_count: NonNegativeInt | None = None


class CountDeltaV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a: NonNegativeInt | None = None
    b: NonNegativeInt | None = None
    delta: int | None = None


class GenerationPositiveCohortCompareV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohort: CohortKey
    case_count: NonNegativeInt = 0
    answer_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    false_abstention_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    generation_failed_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    citation_invalid_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    mean_gold_citation_recall: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    grade2_citation_hit_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    fully_correct_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    fully_supported_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    complete_answer_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    complete_citation_coverage_rate: MetricDeltaV1 = Field(
        default_factory=MetricDeltaV1
    )
    all_citations_useful_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    latency_mean_ms: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    eligible_answered_cases: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    judge_succeeded: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    judge_failed: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    judge_unavailable: CountDeltaV1 = Field(default_factory=CountDeltaV1)


class GenerationPositiveCompareAggregatesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohorts: dict[str, GenerationPositiveCohortCompareV1] = Field(default_factory=dict)


class GenerationNegativeCompareAggregatesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_cases: NonNegativeInt = 0
    correct_abstention_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    false_answer_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    generation_failed_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    citation_invalid_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    empty_context_rate: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    latency_mean_ms: MetricDeltaV1 = Field(default_factory=MetricDeltaV1)
    false_answers_judged: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    false_answers_fully_supported: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    false_answers_fully_correct: CountDeltaV1 = Field(default_factory=CountDeltaV1)
    abstention_outcome_transitions: dict[str, NonNegativeInt] = Field(
        default_factory=dict
    )


SemanticTransitionKind = Literal["improved", "unchanged", "regressed", "not_comparable"]
NegativeLayer1Outcome = Literal[
    "correct_abstention",
    "false_answer",
    "generation_failed",
    "citation_invalid",
    "empty_context",
    "other",
]


class DimensionTransitionCountsV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    improved: NonNegativeInt = 0
    unchanged: NonNegativeInt = 0
    regressed: NonNegativeInt = 0
    not_comparable: NonNegativeInt = 0


class GenerationSemanticTransitionSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_correctness: DimensionTransitionCountsV1 = Field(
        default_factory=DimensionTransitionCountsV1
    )
    faithfulness: DimensionTransitionCountsV1 = Field(
        default_factory=DimensionTransitionCountsV1
    )
    completeness: DimensionTransitionCountsV1 = Field(
        default_factory=DimensionTransitionCountsV1
    )
    citation_coverage: DimensionTransitionCountsV1 = Field(
        default_factory=DimensionTransitionCountsV1
    )
    citation_usefulness: DimensionTransitionCountsV1 = Field(
        default_factory=DimensionTransitionCountsV1
    )


class GenerationCompareCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    label_cohort: LabelCohort | None = None
    query: NonEmptyStr | None = None

    a_status: str | None = None
    b_status: str | None = None
    status_transition: str | None = None

    a_layer1_outcome: str | None = None
    b_layer1_outcome: str | None = None
    layer1_outcome_transition: str | None = None

    a_citation_ids: list[str] = Field(default_factory=list)
    b_citation_ids: list[str] = Field(default_factory=list)
    a_citation_count: NonNegativeInt = 0
    b_citation_count: NonNegativeInt = 0

    a_gold_citation_recall: float | None = None
    b_gold_citation_recall: float | None = None
    gold_citation_recall_delta: float | None = None

    a_grade2_citation_hit: bool | None = None
    b_grade2_citation_hit: bool | None = None

    a_judge_status: str | None = None
    b_judge_status: str | None = None

    a_answer_correctness: str | None = None
    b_answer_correctness: str | None = None
    answer_correctness_transition: SemanticTransitionKind | None = None

    a_faithfulness: str | None = None
    b_faithfulness: str | None = None
    faithfulness_transition: SemanticTransitionKind | None = None

    a_completeness: str | None = None
    b_completeness: str | None = None
    completeness_transition: SemanticTransitionKind | None = None

    a_citation_coverage: str | None = None
    b_citation_coverage: str | None = None
    citation_coverage_transition: SemanticTransitionKind | None = None

    a_citation_usefulness: str | None = None
    b_citation_usefulness: str | None = None
    citation_usefulness_transition: SemanticTransitionKind | None = None

    a_latency_ms: NonNegativeInt | None = None
    b_latency_ms: NonNegativeInt | None = None
    latency_delta_ms: int | None = None

    negative_fixture_review_signal: bool = False


# Forward-reference resolution for comparison model field types defined above.
GenerationSemanticEvalComparisonV1.model_rebuild()


class GenerationCohortMapCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    label_cohort: LabelCohort


class GenerationCohortMapV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_COHORT_MAP_V1
    gold_dataset_id: NonEmptyStr
    cases: list[GenerationCohortMapCaseV1] = Field(default_factory=list)
