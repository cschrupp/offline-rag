"""generation-semantic-judge-output-v1 schema and validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr
from offline_rag.evaluation.generation_semantic.judge_contracts import (
    DIAGNOSTIC_MAX_CHARS,
    DIAGNOSTIC_MAX_ITEMS,
    OUTPUT_CONTRACT,
    RATIONALE_MAX_CHARS,
)

AnswerCorrectness = Literal["fully_correct", "partially_correct", "incorrect"]
Faithfulness = Literal["fully_supported", "partially_supported", "unsupported"]
Completeness = Literal["complete", "partial", "incomplete"]
CitationCoverage = Literal["complete", "partial", "unsupported"]
CitationUsefulness = Literal["all_useful", "some_irrelevant", "mostly_irrelevant"]


class GenerationSemanticJudgeOutputV1(BaseModel):
    """Strict structured judge response (generation-semantic-judge-output-v1)."""

    model_config = ConfigDict(extra="forbid")

    answer_correctness: AnswerCorrectness
    faithfulness: Faithfulness
    completeness: Completeness
    citation_coverage: CitationCoverage
    citation_usefulness: CitationUsefulness
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_key_points: list[str] = Field(default_factory=list)
    irrelevant_citation_ids: list[str] = Field(default_factory=list)
    rationale: NonEmptyStr

    @field_validator("unsupported_claims", "missing_key_points")
    @classmethod
    def _bounded_string_lists(cls, value: list[str]) -> list[str]:
        if len(value) > DIAGNOSTIC_MAX_ITEMS:
            raise ValueError(f"at most {DIAGNOSTIC_MAX_ITEMS} items allowed")
        for item in value:
            if not isinstance(item, str):
                raise TypeError("diagnostic items must be strings")
            if len(item) > DIAGNOSTIC_MAX_CHARS:
                raise ValueError(
                    f"diagnostic item exceeds {DIAGNOSTIC_MAX_CHARS} characters"
                )
        return value

    @field_validator("irrelevant_citation_ids")
    @classmethod
    def _bounded_citation_ids(cls, value: list[str]) -> list[str]:
        if len(value) > DIAGNOSTIC_MAX_ITEMS:
            raise ValueError(f"at most {DIAGNOSTIC_MAX_ITEMS} items allowed")
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("irrelevant_citation_ids must be non-empty strings")
        return value

    @field_validator("rationale")
    @classmethod
    def _rationale_bound(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("rationale must be non-empty")
        if len(text) > RATIONALE_MAX_CHARS:
            raise ValueError(f"rationale exceeds {RATIONALE_MAX_CHARS} characters")
        return text


def parse_generation_semantic_judge_output_v1(
    raw: object,
    *,
    allowed_citation_ids: list[str] | set[str],
) -> GenerationSemanticJudgeOutputV1:
    """Parse and validate judge JSON; enforce citation ID membership."""
    if not isinstance(raw, dict):
        raise TypeError("judge output must be a JSON object")
    parsed = GenerationSemanticJudgeOutputV1.model_validate(raw)
    allowed = {item.strip() for item in allowed_citation_ids}
    unknown = [
        cid for cid in parsed.irrelevant_citation_ids if cid.strip() not in allowed
    ]
    if unknown:
        raise ValueError(
            "irrelevant_citation_ids contains unknown citation id(s): "
            + ", ".join(sorted(unknown))
        )
    return parsed


def output_contract_id() -> str:
    return OUTPUT_CONTRACT
