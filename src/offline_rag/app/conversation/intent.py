"""Deterministic intent routing for bounded conversation text operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from offline_rag.app.conversation.prior_turns import (
    MAX_PRIOR_TEXT_CHARS,
    PriorTurn,
)
from offline_rag.app.query import MAX_QUESTION_CHARS

INTENT_ROUTER_CONTRACT_ID = "conversation_intent_router_v1"

TransformOperation = Literal["summarize", "rewrite", "simplify", "translate"]
TransformSource = Literal[
    "current_message",
    "prior_user_turn",
    "prior_assistant_turn",
]
TransformRole = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class ConversationRoute:
    kind: Literal["grounded_query", "conversation_transform", "clarification_required"]
    operation: TransformOperation | None = None
    source: TransformSource | None = None
    source_role: TransformRole | None = None
    source_turn_ordinal: int | None = None
    target_text: str | None = None
    instruction: str | None = None
    clarification_reason: (
        Literal[
            "transform_target_missing",
            "transform_target_ambiguous",
            "transform_request_unsupported",
        ]
        | None
    ) = None


_OPERATION_RE = re.compile(
    r"^\s*(summari[sz]e|summary|rewrite|rephrase|simplify|translate|explain)\b",
    re.IGNORECASE,
)
_SOURCE_REQUEST_RE = re.compile(
    r"\b(document|documents|source|sources|file|files|page\s+\d+|"
    r"selected sources|evidence|citation|citations)\b|"
    r"\b(?:true|accurate|supported)\b|"
    r"\bcompare\b|\bverify\b|\bfact.?check\b",
    re.IGNORECASE,
)
_PRIOR_ASSISTANT_RE = re.compile(
    r"\b(?:your|seneca's|the)\s+(?:previous|last|prior)\s+"
    r"(?:answer|response|explanation)\b|\bprevious answer\b",
    re.IGNORECASE,
)
_PRIOR_USER_RE = re.compile(
    r"\b(?:my|the)\s+(?:previous|last|prior)\s+(?:question|prompt)\b",
    re.IGNORECASE,
)
_QUOTED_TARGETS = (
    re.compile(r"```(?:text)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL),
    re.compile(r"“(.*?)”", re.DOTALL),
    re.compile(r"‘(.*?)’", re.DOTALL),
    re.compile(r'"([^"\n]+)"', re.DOTALL),
    re.compile(r"'([^'\n]+)'", re.DOTALL),
    re.compile(r"`([^`\n]+)`", re.DOTALL),
    re.compile(r"\[([^\[\]]+)\]", re.DOTALL),
)
_BULLET_COUNT_RE = re.compile(
    r"\b(?:in|as)\s+(one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|\d{1,2})\s+bullet(?:s|\s+points?)?\b",
    re.IGNORECASE,
)
_AUDIENCE_RE = re.compile(r"\bfor\s+(?:a|an|the)?\s*([\w -]{2,60})", re.IGNORECASE)
_LANGUAGE_RE = re.compile(
    r"\b(?:to|into)\s+([A-Za-z][A-Za-z -]{1,39}?)(?:\s*:|\s*[,.;]|$)", re.IGNORECASE
)
_UNSUPPORTED_FORMAT_RE = re.compile(
    r"\b(?:exactly\s+\d+\s+words?|as\s+(?:a\s+)?(?:poem|table|json|yaml)|"
    r"in\s+(?:json|yaml|csv|a\s+table)|as\s+(?:a\s+)?(?:list|email|letter)|"
    r"with\s+(?:headings|subheadings|a\s+title))\b",
    re.IGNORECASE,
)


def _without_delimited_targets(question: str) -> str:
    routing_text = question
    for pattern in _QUOTED_TARGETS:
        routing_text = pattern.sub(" ", routing_text)
    return routing_text


def _source_request(question: str) -> bool:
    """Prefer factual/source-oriented intent over a transform verb."""
    routing_text = _without_delimited_targets(question)
    if _SOURCE_REQUEST_RE.search(routing_text):
        return True
    return bool(
        re.search(
            r"\bwhat\s+(?:does|do|did)\s+(?:the\s+)?"
            r"(?:document|source|file)\b",
            routing_text,
            re.IGNORECASE,
        )
    )


def _operation(question: str) -> TransformOperation | None:
    match = _OPERATION_RE.match(question)
    if not match:
        return None
    value = match.group(1).lower()
    if value in {"summarize", "summarise", "summary"}:
        return "summarize"
    if value in {"rewrite", "rephrase"}:
        return "rewrite"
    if value in {"simplify", "explain"}:
        return "simplify"
    if value == "translate":
        return "translate"
    return None


def _target(question: str) -> str | None:
    matches: list[str] = []
    for pattern in _QUOTED_TARGETS:
        matches.extend(match.group(1) for match in pattern.finditer(question))
    matches = [value for value in matches if value.strip()]
    if len(matches) == 1:
        return matches[0]
    return None


def _target_count(question: str) -> int:
    matches: list[str] = []
    for pattern in _QUOTED_TARGETS:
        matches.extend(match.group(1).strip() for match in pattern.finditer(question))
    return sum(bool(value) for value in matches)


def _prior_target(
    question: str, prior_turns: tuple[PriorTurn, ...]
) -> tuple[TransformSource, TransformRole, int, str] | None:
    role: TransformRole | None = None
    if _PRIOR_ASSISTANT_RE.search(question):
        role = "assistant"
    elif _PRIOR_USER_RE.search(question):
        role = "user"
    if role is None:
        return None
    for index in range(len(prior_turns) - 1, -1, -1):
        turn = prior_turns[index]
        if turn.role == role:
            source: TransformSource = (
                "prior_user_turn" if role == "user" else "prior_assistant_turn"
            )
            return source, role, index + 1, turn.text
    return None


def _clarify(
    reason: Literal[
        "transform_target_missing",
        "transform_target_ambiguous",
        "transform_request_unsupported",
    ],
) -> ConversationRoute:
    return ConversationRoute(kind="clarification_required", clarification_reason=reason)


def route_conversation_intent(
    question: str, prior_turns: tuple[PriorTurn, ...]
) -> ConversationRoute:
    """Route only high-precision text transformations away from grounding."""
    if _source_request(question):
        return ConversationRoute(kind="grounded_query")

    operation = _operation(question)
    if operation is None:
        return ConversationRoute(kind="grounded_query")

    operation_text = _without_delimited_targets(question)
    has_audience = bool(_AUDIENCE_RE.search(operation_text))
    leading_operation = _OPERATION_RE.match(question)
    is_explain = (
        leading_operation is not None
        and leading_operation.group(1).lower() == "explain"
    )
    if is_explain and not has_audience:
        if _target(question) is None:
            # Plain contextual explanations remain grounded follow-ups.
            return ConversationRoute(kind="grounded_query")
        return _clarify("transform_request_unsupported")
    if operation == "simplify" and not has_audience and _target(question) is None:
        # Plain contextual requests such as “explain that finding” stay grounded.
        return ConversationRoute(kind="grounded_query")

    if _UNSUPPORTED_FORMAT_RE.search(operation_text):
        return _clarify("transform_request_unsupported")

    target_text = _target(question)
    source: TransformSource = "current_message"
    source_role: TransformRole | None = "user"
    source_ordinal: int | None = None
    if target_text is None:
        if _target_count(question) > 1:
            return _clarify("transform_target_ambiguous")
        prior = _prior_target(operation_text, prior_turns)
        if prior is not None:
            source, source_role, source_ordinal, target_text = prior
        elif re.search(r"\b(?:that|it|this)\b", operation_text, re.IGNORECASE):
            return _clarify("transform_target_ambiguous")
        else:
            return _clarify("transform_target_missing")

    target_limit = (
        MAX_QUESTION_CHARS if source == "current_message" else MAX_PRIOR_TEXT_CHARS
    )
    if not target_text or len(target_text) > target_limit:
        return _clarify("transform_request_unsupported")

    options: list[str] = []
    if operation == "summarize":
        bullets = _BULLET_COUNT_RE.search(operation_text)
        if bullets:
            count_text = bullets.group(1).lower()
            count = {
                "one": 1,
                "two": 2,
                "three": 3,
                "four": 4,
                "five": 5,
                "six": 6,
                "seven": 7,
                "eight": 8,
                "nine": 9,
                "ten": 10,
                "eleven": 11,
                "twelve": 12,
            }.get(count_text, int(count_text) if count_text.isdigit() else 0)
            if count < 1 or count > 12:
                return _clarify("transform_request_unsupported")
            options.append(f"in {count} bullets")
    if operation in {"rewrite", "simplify"}:
        audience = _AUDIENCE_RE.search(operation_text)
        if audience:
            value = audience.group(1).strip().rstrip(".:;,")
            value = re.split(r"\b(?:using|with|from)\b", value, maxsplit=1)[0].strip()
            if not value or len(value) > 60:
                return _clarify("transform_request_unsupported")
            options.append(f"for {value}")
    if operation == "translate":
        language = _LANGUAGE_RE.search(operation_text)
        if language is None:
            return _clarify("transform_request_unsupported")
        options.append(f"into {language.group(1).strip()}")

    instruction = operation
    if options:
        instruction = f"{instruction} {' '.join(options)}"

    return ConversationRoute(
        kind="conversation_transform",
        operation=operation,
        source=source,
        source_role=source_role,
        source_turn_ordinal=source_ordinal,
        target_text=target_text,
        instruction=instruction,
    )
