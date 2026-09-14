"""relevance-prelabel-v1 output schema parse/normalize."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from offline_rag.gold_authoring.contracts import RATIONALE_MAX_CHARS


class RelevancePrelabelParseError(ValueError):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class RelevancePrelabelV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: Literal[0, 1, 2]
    rationale: str

    @field_validator("grade", mode="before")
    @classmethod
    def _grade(cls, value: Any) -> int:
        # Reject bool explicitly (bool is a subclass of int).
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("grade must be a JSON integer 0, 1, or 2")
        if value not in {0, 1, 2}:
            raise ValueError("grade must be exactly 0, 1, or 2")
        return value

    @field_validator("rationale", mode="before")
    @classmethod
    def _rationale(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("rationale must be a string")
        text = value.strip()
        if not text:
            raise ValueError("rationale must be nonempty after strip")
        if len(text) > RATIONALE_MAX_CHARS:
            raise ValueError(
                f"rationale exceeds {RATIONALE_MAX_CHARS} characters"
            )
        return text


def parse_relevance_prelabel_v1(content: str) -> RelevancePrelabelV1:
    if not isinstance(content, str) or not content.strip():
        raise RelevancePrelabelParseError(
            "empty prelabel response content",
            reason="empty_response",
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RelevancePrelabelParseError(
            f"invalid JSON: {exc}",
            reason="invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise RelevancePrelabelParseError(
            "prelabel JSON must be an object",
            reason="schema_invalid",
        )
    required = {"grade", "rationale"}
    missing = required - set(payload.keys())
    if missing:
        raise RelevancePrelabelParseError(
            f"missing required keys: {sorted(missing)}",
            reason="schema_invalid",
        )
    try:
        return RelevancePrelabelV1.model_validate(payload)
    except ValidationError as exc:
        raise RelevancePrelabelParseError(
            f"schema invalid: {exc}",
            reason="schema_invalid",
        ) from exc
