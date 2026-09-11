"""grounded-answer-v1 parsing and invariant validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from offline_rag.generation.contracts import OUTPUT_CONTRACT


@dataclass(frozen=True)
class GroundedAnswerModelOutput:
    abstain: bool
    answer: str | None
    citation_ids: list[str]


@dataclass(frozen=True)
class ParseOutcome:
    ok: bool
    output: GroundedAnswerModelOutput | None = None
    failure_reason: str | None = None


def _is_ev_id(value: str) -> bool:
    return value.startswith("ev_") and len(value) > 3


def parse_grounded_answer_v1(raw: str) -> ParseOutcome:
    """Strictly parse raw model text into grounded-answer-v1."""
    text = raw if isinstance(raw, str) else ""
    stripped = text.strip()
    if not stripped:
        return ParseOutcome(ok=False, failure_reason="response_parse_error")
    if stripped.startswith("```"):
        return ParseOutcome(ok=False, failure_reason="response_parse_error")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return ParseOutcome(ok=False, failure_reason="response_parse_error")
    if not isinstance(payload, dict):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if set(payload.keys()) != {"abstain", "answer", "citation_ids"}:
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    abstain = payload["abstain"]
    answer = payload["answer"]
    citation_ids = payload["citation_ids"]
    if not isinstance(abstain, bool):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if answer is not None and not isinstance(answer, str):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if not isinstance(citation_ids, list) or any(not isinstance(item, str) for item in citation_ids):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if len(citation_ids) != len(set(citation_ids)):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if abstain:
        if answer is not None or citation_ids:
            return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
        return ParseOutcome(
            ok=True,
            output=GroundedAnswerModelOutput(abstain=True, answer=None, citation_ids=[]),
        )
    if answer is None or not answer.strip():
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if not citation_ids:
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    if any(not _is_ev_id(item) for item in citation_ids):
        return ParseOutcome(ok=False, failure_reason="output_schema_invalid")
    return ParseOutcome(
        ok=True,
        output=GroundedAnswerModelOutput(
            abstain=False,
            answer=answer,
            citation_ids=list(citation_ids),
        ),
    )


def grounded_answer_schema_metadata() -> dict[str, Any]:
    return {"output_contract": OUTPUT_CONTRACT}
