"""HumanReview durable schema for Slice 9E (offline-rag-gold-authoring-v1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.domain.types import NonEmptyStr


class HumanReviewStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class HumanJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: NonEmptyStr
    relevance: Literal[0, 1, 2]

    @field_validator("chunk_id")
    @classmethod
    def _chunk_id_strip(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("chunk_id must be non-empty")
        return text


class CategoryOverride(BaseModel):
    """Tri-state category override: no override vs override-to-value (incl. null)."""

    model_config = ConfigDict(extra="forbid")

    is_overridden: bool = False
    value: str | None = None

    @model_validator(mode="after")
    def _coherence(self) -> CategoryOverride:
        if not self.is_overridden and self.value is not None:
            raise ValueError(
                "category_override.value must be null when is_overridden is false"
            )
        if self.is_overridden and self.value is not None:
            text = self.value.strip()
            object.__setattr__(self, "value", text or None)
        return self


class HumanReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HumanReviewStatus = HumanReviewStatus.PENDING
    judgments: list[HumanJudgment] = Field(default_factory=list)
    query_override: str | None = None
    category_override: CategoryOverride = Field(default_factory=CategoryOverride)
    tags_override: list[str] | None = None
    grade_basis_query: str | None = None

    @field_validator("query_override", mode="before")
    @classmethod
    def _normalize_query_override(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("query_override must be a string or null")
        text = value.strip()
        return text or None

    @field_validator("grade_basis_query", mode="before")
    @classmethod
    def _normalize_basis(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("grade_basis_query must be a string or null")
        text = value.strip()
        return text or None

    @field_validator("tags_override", mode="before")
    @classmethod
    def _normalize_tags_override(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("tags_override must be a list or null")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("tags_override items must be strings")
            label = item.strip()
            if not label:
                continue
            if label in seen:
                raise ValueError(f"duplicate tag after normalization: {label}")
            seen.add(label)
            normalized.append(label)
        return normalized

    @model_validator(mode="after")
    def _judgment_and_basis_invariants(self) -> HumanReview:
        seen: set[str] = set()
        for judgment in self.judgments:
            if judgment.chunk_id in seen:
                raise ValueError(
                    f"duplicate human judgment chunk_id: {judgment.chunk_id}"
                )
            seen.add(judgment.chunk_id)

        if not self.judgments:
            if self.grade_basis_query is not None:
                raise ValueError(
                    "grade_basis_query must be null when human judgments are empty"
                )
        elif self.grade_basis_query is None:
            raise ValueError(
                "grade_basis_query is required when human judgments are nonempty"
            )
        return self


def canonicalize_query(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ValueError("query must be non-empty after trim")
    return stripped


def canonicalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("category must be a string or null")
    text = value.strip()
    return text or None


def canonicalize_tags(tags: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    if tags is None:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in tags:
        if not isinstance(item, str):
            raise ValueError("tags must be strings")
        label = item.strip()
        if not label:
            continue
        if label in seen:
            raise ValueError(f"duplicate tag after normalization: {label}")
        seen.add(label)
        normalized.append(label)
    return tuple(normalized)


def tags_equal(
    left: list[str] | tuple[str, ...] | None,
    right: list[str] | tuple[str, ...] | None,
) -> bool:
    return set(canonicalize_tags(left)) == set(canonicalize_tags(right))


class ReviewError(ValueError):
    """Domain-level human-review mutation/validation error."""

    def __init__(self, message: str, *, code: str = "review_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
