"""Server-side prior_turns validation (A2-D07) — before admission/resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails

MAX_PRIOR_ROLE_TURNS = 12
MAX_PRIOR_PAIRS = 6
MAX_PRIOR_TEXT_CHARS = 12_000

Role = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class PriorTurn:
    role: Role
    text: str


def normalize_turn_text(text: object) -> str:
    if not isinstance(text, str):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turn_text_invalid"),
        )
    trimmed = text.strip()
    if not trimmed:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turn_text_empty"),
        )
    return trimmed


def validate_prior_turns(raw: object) -> tuple[PriorTurn, ...]:
    """Validate and normalize prior_turns. Empty is valid (first turn).

    Fail closed on over-bound or malformed sequences. Does not silently truncate.
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turns_invalid"),
        )
    if len(raw) > MAX_PRIOR_ROLE_TURNS:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turns_too_many"),
        )
    if len(raw) % 2 != 0:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turns_incomplete_pair"),
        )

    turns: list[PriorTurn] = []
    total_chars = 0
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="prior_turn_invalid"),
            )
        role = item.get("role")
        if role not in ("user", "assistant"):
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="prior_turn_role_invalid"),
            )
        expected: Role = "user" if index % 2 == 0 else "assistant"
        if role != expected:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="prior_turns_sequence_invalid"),
            )
        text = normalize_turn_text(item.get("text"))
        total_chars += len(text)
        if total_chars > MAX_PRIOR_TEXT_CHARS:
            raise AppError(
                ErrorCode.REQUEST_INVALID,
                details=SafeErrorDetails(reason="prior_turns_too_long"),
            )
        turns.append(PriorTurn(role=role, text=text))

    if len(turns) // 2 > MAX_PRIOR_PAIRS:
        raise AppError(
            ErrorCode.REQUEST_INVALID,
            details=SafeErrorDetails(reason="prior_turns_too_many_pairs"),
        )
    return tuple(turns)


def prior_turns_as_dicts(turns: tuple[PriorTurn, ...]) -> list[dict[str, Any]]:
    return [{"role": t.role, "text": t.text} for t in turns]
