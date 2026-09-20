"""Slice 10 generation-semantic evaluation artifact contracts (10A)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.domain.types import NonEmptyStr, NonNegativeInt

GENERATION_EVIDENCE_SET_V1 = "offline-rag-generation-evidence-set-v1"
GENERATION_SEMANTIC_EVAL_RESULT_V1 = "offline-rag-generation-semantic-eval-result-v1"
GENERATION_SEMANTIC_EVAL_COMPARISON_V1 = (
    "offline-rag-generation-semantic-eval-comparison-v1"
)

LabelCohort = Literal["human_reviewed", "assistant_only"]


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


class GenerationSemanticEvalCaseResultV1(BaseModel):
    """Per-case semantic-eval row (forward-compatible; 10B+ populates diagnostics)."""

    model_config = ConfigDict(extra="forbid")

    case_id: NonEmptyStr
    query: NonEmptyStr
    label_cohort: LabelCohort | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)

    status: NonEmptyStr | None = None
    answer_text: str | None = None
    citation_ids: list[str] = Field(default_factory=list)
    resolved_citation_ids: list[str] = Field(default_factory=list)

    deterministic_diagnostics: dict[str, Any] = Field(default_factory=dict)
    judge_result: dict[str, Any] | None = None

    latency_ms: NonNegativeInt | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationSemanticEvalResultV1(BaseModel):
    """offline-rag-generation-semantic-eval-result-v1 envelope (contracts only in 10A)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = GENERATION_SEMANTIC_EVAL_RESULT_V1
    run_id: NonEmptyStr

    gold_dataset_id: NonEmptyStr
    evidence_set_id: NonEmptyStr
    evidence_contract: NonEmptyStr

    corpus_id: NonEmptyStr | None = None
    chunk_set_id: NonEmptyStr | None = None

    generation_config_hash: NonEmptyStr
    generation_semantic_provenance: dict[str, Any] = Field(default_factory=dict)

    judge_enabled: bool = False
    judge_provenance: dict[str, Any] | None = None

    population: dict[str, Any] = Field(default_factory=dict)

    deterministic_aggregates: dict[str, Any] = Field(default_factory=dict)
    semantic_aggregates: dict[str, Any] | None = None
    abstention_aggregates: dict[str, Any] | None = None

    cases: list[GenerationSemanticEvalCaseResultV1] = Field(default_factory=list)

    started_at: datetime
    completed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerationSemanticEvalComparisonV1(BaseModel):
    """offline-rag-generation-semantic-eval-comparison-v1 (artifact-only; 10E executes)."""

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
