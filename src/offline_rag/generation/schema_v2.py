"""grounded_answer_v2 parsing and invariant validation (A2-D12)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from offline_rag.core.ids import GROUNDED_ANSWER_V2
from offline_rag.generation.evidence_handles import is_valid_handle_syntax

MODEL_ABSTENTION_REASONS = frozenset(
    {"insufficient_support", "conflicting_evidence", "model_declined"}
)
APPLICATION_ONLY_ABSTENTION_REASONS = frozenset({"no_evidence", "ambiguous_request"})


@dataclass(frozen=True)
class GroundedAnswerV2Block:
    text: str
    evidence_handles: list[str]


@dataclass(frozen=True)
class GroundedAnswerV2ModelOutput:
    abstain: bool
    blocks: list[GroundedAnswerV2Block]
    abstention_reason: str | None


@dataclass(frozen=True)
class ParseV2Outcome:
    ok: bool
    output: GroundedAnswerV2ModelOutput | None = None
    failure_reason: str | None = None


def _fail(reason: str = "output_schema_invalid") -> ParseV2Outcome:
    return ParseV2Outcome(ok=False, failure_reason=reason)


def parse_grounded_answer_v2(
    raw: str,
    *,
    allowed_handles: set[str],
) -> ParseV2Outcome:
    """Strictly parse raw model text into grounded_answer_v2."""
    text = raw if isinstance(raw, str) else ""
    stripped = text.strip()
    if not stripped:
        return _fail("response_parse_error")
    if stripped.startswith("```"):
        return _fail("response_parse_error")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return _fail("response_parse_error")
    if not isinstance(payload, dict):
        return _fail()
    if set(payload.keys()) != {"abstain", "blocks", "abstention_reason"}:
        return _fail()

    abstain = payload["abstain"]
    blocks_raw = payload["blocks"]
    reason = payload["abstention_reason"]
    if not isinstance(abstain, bool):
        return _fail()
    if not isinstance(blocks_raw, list):
        return _fail()
    if reason is not None and not isinstance(reason, str):
        return _fail()

    if abstain:
        if blocks_raw:
            return _fail()
        if reason is None:
            return _fail()
        if reason in APPLICATION_ONLY_ABSTENTION_REASONS:
            return _fail()
        if reason not in MODEL_ABSTENTION_REASONS:
            return _fail()
        return ParseV2Outcome(
            ok=True,
            output=GroundedAnswerV2ModelOutput(
                abstain=True, blocks=[], abstention_reason=reason
            ),
        )

    if reason is not None:
        return _fail()
    if not blocks_raw:
        return _fail()

    blocks: list[GroundedAnswerV2Block] = []
    for item in blocks_raw:
        if not isinstance(item, dict):
            return _fail()
        if set(item.keys()) != {"text", "evidence_handles"}:
            return _fail()
        block_text = item["text"]
        handles = item["evidence_handles"]
        if not isinstance(block_text, str) or not block_text.strip():
            return _fail()
        if not isinstance(handles, list) or not handles:
            return _fail()
        if any(not isinstance(h, str) for h in handles):
            return _fail()
        if len(handles) != len(set(handles)):
            return _fail()
        for handle in handles:
            if not is_valid_handle_syntax(handle):
                return _fail()
            if handle not in allowed_handles:
                return ParseV2Outcome(ok=False, failure_reason="citation_invalid")
        blocks.append(
            GroundedAnswerV2Block(text=block_text, evidence_handles=list(handles))
        )

    return ParseV2Outcome(
        ok=True,
        output=GroundedAnswerV2ModelOutput(
            abstain=False, blocks=blocks, abstention_reason=None
        ),
    )


def grounded_answer_v2_schema_metadata() -> dict[str, Any]:
    return {"output_contract": GROUNDED_ANSWER_V2}
