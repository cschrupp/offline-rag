"""Lean silver/run models for offline-rag-gold-authoring-v1 (Slice 9A)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonEmptyStr
from offline_rag.gold_authoring.contracts import AUTHORING_ARTIFACT_CONTRACT


class HumanReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class SourceSeed(BaseModel):
    """Minimal structural provenance; expanded in Slice 9B."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    document_id: NonEmptyStr | None = None


class CandidateRef(BaseModel):
    """Minimal candidate placeholder; pooling diagnostics arrive in 9C."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr


class ModelJudgmentPlaceholder(BaseModel):
    """Minimal judgment placeholder; prelabel semantics arrive in 9D."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr | None = None
    relevance: Literal[0, 1, 2] | None = None
    pass_id: NonEmptyStr | None = None
    rationale: str | None = None


class SilverCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_case_id: NonEmptyStr
    human_status: HumanReviewStatus = HumanReviewStatus.PENDING
    proposed_query: str | None = None
    source_seed: SourceSeed | None = None
    candidates: list[CandidateRef] = Field(default_factory=list)
    model_judgments: list[ModelJudgmentPlaceholder] = Field(default_factory=list)

    @field_validator("proposed_query", mode="before")
    @classmethod
    def _normalize_query(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("proposed_query must be a string or null")
        text = value.strip()
        return text or None


class GoldAuthoringRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: NonEmptyStr = AUTHORING_ARTIFACT_CONTRACT
    authoring_run_id: NonEmptyStr
    authorcfg_id: NonEmptyStr
    network_policy: Literal["localhost_only", "private_network"]
    effective_endpoint: str | None = None
    corpus_id: str | None = None
    chunk_set_id: str | None = None
    created_at: datetime
    cases: list[SilverCase] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_must_be_authoring_v1(cls, value: str) -> str:
        if value != AUTHORING_ARTIFACT_CONTRACT:
            raise ValueError(
                f"unsupported authoring schema_version: {value!r}; "
                f"expected {AUTHORING_ARTIFACT_CONTRACT!r}"
            )
        return value

    @field_validator("authorcfg_id")
    @classmethod
    def _authorcfg_prefix(cls, value: str) -> str:
        text = value.strip()
        if not text.startswith("authorcfg_"):
            raise ValueError("authorcfg_id must start with authorcfg_")
        return text
