"""question-proposal-v1 output schema parse/normalize."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from offline_rag.domain.types import NonEmptyStr
from offline_rag.gold_authoring.models import ProposedQueryFields


class QuestionProposalParseError(ValueError):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class QuestionProposalV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: NonEmptyStr
    category: str | None
    tags: list[str] = Field(default_factory=list)
    rationale: str | None

    @field_validator("query", mode="before")
    @classmethod
    def _query(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("query must be a string")
        text = value.strip()
        if not text:
            raise ValueError("query must be nonempty after trim")
        return text

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("category must be a string or null")
        text = value.strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def _tags(cls, value: Any) -> list[str]:
        if value is None:
            raise ValueError("tags must be a list")
        if not isinstance(value, list):
            raise ValueError("tags must be a list")
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("tags items must be strings")
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out

    @field_validator("rationale", mode="before")
    @classmethod
    def _rationale(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("rationale must be a string or null")
        text = value.strip()
        return text or None


def parse_question_proposal_v1(content: str) -> ProposedQueryFields:
    if not isinstance(content, str) or not content.strip():
        raise QuestionProposalParseError(
            "empty proposal response content",
            reason="empty_response",
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise QuestionProposalParseError(
            f"invalid JSON: {exc}",
            reason="invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise QuestionProposalParseError(
            "proposal JSON must be an object",
            reason="schema_invalid",
        )
    required = {"query", "category", "tags", "rationale"}
    missing = required - set(payload.keys())
    if missing:
        raise QuestionProposalParseError(
            f"missing required keys: {sorted(missing)}",
            reason="schema_invalid",
        )
    try:
        parsed = QuestionProposalV1.model_validate(payload)
    except ValidationError as exc:
        raise QuestionProposalParseError(
            f"schema invalid: {exc}",
            reason="schema_invalid",
        ) from exc
    return ProposedQueryFields(
        query=parsed.query,
        category=parsed.category,
        tags=list(parsed.tags),
        rationale=parsed.rationale,
    )
