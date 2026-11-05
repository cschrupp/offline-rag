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


@dataclass(frozen=True, slots=True)
class _DelimitedTarget:
    text: str
    start: int
    end: int


_OPERATION_RE = re.compile(
    r"^\s*(summari[sz]e|summary|rewrite|rephrase|simplify|translate|explain)\b",
    re.IGNORECASE,
)
_SOURCE_REQUEST_RE = re.compile(
    r"\b(document|documents|source|sources|file|files|report|reports|"
    r"manual|manuals|chapter|chapters|section|sections|article|articles|"
    r"page\s+\d+|selected sources|evidence|citation|citations|"
    r"source title|document title|file title)\b|"
    r"\b(?:true|accurate|supported)\b|"
    r"\bcompare\b|\bverify\b|\bfact.?check\b",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]+\]\([^\s)]+(?:\s+[^)]*)?\)")
_INLINE_TEXT_LABEL_RE = re.compile(
    r"\b(?:(?:the|a|an)\s+)?(?:this|that|following|provided|pasted|quoted|the)\s+"
    r"(?:(?:the|a|an)\s+)?(?:report|manual|chapter|section|document|source|"
    r"file|paragraph)?\s*(?:excerpt|passage|text|section|paragraph)\b",
    re.IGNORECASE,
)
_LOCATED_SOURCE_REFERENCE_RE = re.compile(
    r"\b(?:from|in|inside|using|against|according\s+to|based\s+on)\s+"
    r"(?:(?:the|this|that|selected)\s+)?(?:[\w-]+\s+){0,3}"
    r"(?:document|source|file|report|manual|chapter|section|page)\b|"
    r"\b(?:page|section|chapter)\s+\d+\s+(?:of|in)\s+"
    r"(?:(?:the|a)\s+)?(?:[\w-]+\s+){0,3}"
    r"(?:document|source|file|report|manual)\b",
    re.IGNORECASE,
)
_FACTUAL_SOURCE_REQUEST_RE = re.compile(
    r"\b(?:true|accurate|supported)\b|\bcompare\b|\bverify\b|"
    r"\bfact.?check\b|\bwhat\s+(?:does|do|did)\s+(?:the\s+)?"
    r"(?:document|source|file|report|manual|chapter|section)\b",
    re.IGNORECASE,
)
_SOURCE_UPDATE_ACTION_RE = re.compile(
    r"\b(?:update|re-?answer|answer\s+again|refresh|add\s+facts?)\b|"
    r"\bcorrect\s+(?:the\s+)?(?:facts?|factual\s+claims?|information|data)\b",
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
_FORMATTER_TARGET_RE = re.compile(
    r"^(?:(?:exactly\s+)?(?:one|two|three|four|five|six|seven|eight|nine|"
    r"ten|eleven|twelve|\d+)\s+)?"
    r"(?:bullets?|bullet\s+points?|sentences?|paragraphs?|words?|lines?|"
    r"characters?|poems?|tables?|json|yaml|csv|lists?|emails?|letters?)$",
    re.IGNORECASE,
)
_BULLET_COUNT_RE = re.compile(
    r"\b(?:in|as)\s+(one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|\d+)\s+bullet(?:s|\s+points?)?\b",
    re.IGNORECASE,
)
_AUDIENCE_RE = re.compile(r"\bfor\s+(?:a|an|the)?\s*([\w -]{2,60})", re.IGNORECASE)
_LANGUAGE_RE = re.compile(
    r"\b(?:to|into)\s+([A-Za-z][A-Za-z -]{1,39}?)(?:\s*:|\s*[,.;]|$)", re.IGNORECASE
)
_UNSUPPORTED_FORMAT_RE = re.compile(
    r"\b(?:exactly\s+(?:\d+|one|two|three|four|five|six|seven|eight|"
    r"nine|ten|eleven|twelve)\s+(?:words?|sentences?|paragraphs?|lines?|"
    r"characters?)|(?:in|as)\s+(?:exactly\s+)?(?:\d+|one|two|three|four|"
    r"five|six|seven|eight|nine|ten|eleven|twelve)\s+"
    r"(?:sentences?|paragraphs?|words?|lines?|characters?)|"
    r"as\s+(?:a\s+)?(?:poem|table|json|yaml|list|email|letter)|"
    r"as\s+(?:a\s+)?(?:bullet|numbered)\s+list|"
    r"in\s+(?:json|yaml|csv|a\s+table)|"
    r"(?:in|as)\s+(?:a\s+|an\s+)?[\w-]+\s+"
    r"(?:tone|style|voice|format)\b|"
    r"with\s+(?:headings|subheadings|a\s+title)|"
    r"(?:at\s+least|at\s+most|no\s+more\s+than|under|fewer\s+than)\s+"
    r"\d+\s+(?:words?|sentences?|paragraphs?|lines?|characters?)|"
    r"(?:with|without|keep|preserve|include|exclude|avoid|maintain|use|make)\b|"
    r"\bcorrect\s+(?:its|the|their)\s+(?:grammar|wording|style|spelling)\b|"
    r"\b(?:a\s+|the\s+)?(?:friendly|formal|casual|technical|humorous)\s+"
    r"(?:tone|style|voice)\b)",
    re.IGNORECASE,
)


def _closing_quote(text: str, start: int, closing: str) -> int:
    index = start
    while index < len(text):
        if text[index] == closing and (index == 0 or text[index - 1] != "\\"):
            if (
                closing == "'"
                and index > 0
                and index + 1 < len(text)
                and text[index - 1].isalnum()
                and text[index + 1].isalnum()
            ):
                index += 1
                continue
            return index
        index += 1
    return -1


def _apostrophe_inside_word(text: str, index: int) -> bool:
    return (
        text[index] == "'"
        and index > 0
        and index + 1 < len(text)
        and text[index - 1].isalnum()
        and text[index + 1].isalnum()
    )


def _closing_bracket(text: str, start: int) -> int:
    depth = 1
    index = start
    while index < len(text):
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _delimited_targets(question: str) -> tuple[_DelimitedTarget, ...]:
    """Read non-overlapping explicit targets from supported delimiters."""
    targets: list[_DelimitedTarget] = []
    index = 0
    while index < len(question):
        if question.startswith("```", index):
            opening_end = question.find("\n", index + 3)
            content_start = index + 3 if opening_end < 0 else opening_end + 1
            closing = question.find("```", content_start)
            if closing < 0:
                index += 3
                continue
            value = question[content_start:closing].strip()
            if value:
                targets.append(_DelimitedTarget(value, index, closing + 3))
            index = closing + 3
            continue

        if question[index] == "`":
            closing = _closing_quote(question, index + 1, "`")
            if closing < 0:
                index += 1
                continue
            value = question[index + 1 : closing].strip()
            if value:
                targets.append(_DelimitedTarget(value, index, closing + 1))
            index = closing + 1
            continue

        quote_pairs = {"“": "”", "‘": "’", '"': '"', "'": "'"}
        if _apostrophe_inside_word(question, index):
            index += 1
            continue
        closing_quote = quote_pairs.get(question[index])
        if closing_quote is not None:
            closing = _closing_quote(question, index + 1, closing_quote)
            if closing < 0:
                index += 1
                continue
            value = question[index + 1 : closing].strip()
            if value:
                targets.append(_DelimitedTarget(value, index, closing + 1))
            index = closing + 1
            continue

        if question[index] == "[":
            closing = _closing_bracket(question, index + 1)
            if closing < 0:
                index += 1
                continue
            if closing + 1 < len(question) and question[closing + 1] == "(":
                link_end = question.find(")", closing + 2)
                index = len(question) if link_end < 0 else link_end + 1
                continue
            value = question[index + 1 : closing].strip()
            if value:
                targets.append(_DelimitedTarget(value, index, closing + 1))
            index = closing + 1
            continue

        index += 1
    return tuple(targets)


def _is_formatting_target(target: _DelimitedTarget, question: str) -> bool:
    prefix = question[: target.start].rstrip()
    if not re.search(r"\b(?:in|as)$", prefix, re.IGNORECASE):
        return False
    value = target.text.strip().strip(".!?`*_\"'“”‘’")
    return bool(_FORMATTER_TARGET_RE.fullmatch(value))


def _remove_targets(question: str, targets: tuple[_DelimitedTarget, ...]) -> str:
    parts: list[str] = []
    previous_end = 0
    for target in targets:
        parts.extend((question[previous_end : target.start], " "))
        previous_end = target.end
    parts.append(question[previous_end:])
    return " ".join(parts)


def _without_delimited_targets(question: str) -> str:
    return _remove_targets(question, _delimited_targets(question))


def _option_text(
    question: str,
    targets: tuple[_DelimitedTarget, ...],
    formatting_targets: tuple[_DelimitedTarget, ...],
) -> str:
    """Keep formatter phrases visible while excluding actual target text."""
    replacements = {
        (target.start, target.end): target.text for target in formatting_targets
    }
    removed = {(target.start, target.end) for target in targets}
    all_targets = sorted((*targets, *formatting_targets), key=lambda item: item.start)
    parts: list[str] = []
    previous_end = 0
    for target in all_targets:
        parts.append(question[previous_end : target.start])
        span = (target.start, target.end)
        parts.append(" " if span in removed else replacements[span])
        previous_end = target.end
    parts.append(question[previous_end:])
    return " ".join(parts)


def _source_request(
    question: str, *, has_inline_target: bool, has_prior_target: bool
) -> bool:
    """Prefer factual/source-oriented intent over a transform verb."""
    routing_text = _without_delimited_targets(question)
    if _FACTUAL_SOURCE_REQUEST_RE.search(routing_text) or (
        _SOURCE_UPDATE_ACTION_RE.search(routing_text)
        and _SOURCE_REQUEST_RE.search(routing_text)
    ):
        return True
    if _MARKDOWN_LINK_RE.search(routing_text):
        return True
    if has_prior_target:
        # Source terms may describe the topic of the explicitly named prior
        # turn. A located reference still asks for source material.
        return bool(_LOCATED_SOURCE_REFERENCE_RE.search(routing_text))
    if has_inline_target:
        # A uniquely delimited current-message target is the explicit input.
        # Supplied-text labels describe it; other source terms retain grounding.
        if _LOCATED_SOURCE_REFERENCE_RE.search(routing_text):
            return True
        if _INLINE_TEXT_LABEL_RE.search(routing_text):
            return False
        return bool(_SOURCE_REQUEST_RE.search(routing_text))
    return bool(_SOURCE_REQUEST_RE.search(routing_text))


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
    operation = _operation(question)
    if operation is None:
        return ConversationRoute(kind="grounded_query")

    all_targets = _delimited_targets(question)
    formatting_targets = tuple(
        target for target in all_targets if _is_formatting_target(target, question)
    )
    explicit_targets = tuple(
        target for target in all_targets if target not in formatting_targets
    )
    option_text = _option_text(question, explicit_targets, formatting_targets)
    operation_text = _without_delimited_targets(question)
    has_audience = bool(_AUDIENCE_RE.search(option_text))
    has_bullet_count = bool(_BULLET_COUNT_RE.search(option_text))
    has_language = bool(_LANGUAGE_RE.search(option_text))
    has_prior_reference = bool(
        _PRIOR_ASSISTANT_RE.search(option_text) or _PRIOR_USER_RE.search(option_text)
    )
    if explicit_targets and has_prior_reference:
        return _clarify("transform_target_ambiguous")
    if _source_request(
        question,
        has_inline_target=bool(explicit_targets),
        has_prior_target=has_prior_reference,
    ):
        return ConversationRoute(kind="grounded_query")
    if has_audience and operation not in {"rewrite", "simplify"}:
        return _clarify("transform_request_unsupported")
    if has_bullet_count and operation != "summarize":
        return _clarify("transform_request_unsupported")
    if has_language and operation != "translate":
        return _clarify("transform_request_unsupported")
    leading_operation = _OPERATION_RE.match(question)
    is_explain = (
        leading_operation is not None
        and leading_operation.group(1).lower() == "explain"
    )
    if is_explain and not has_audience:
        if not explicit_targets and not has_prior_reference:
            # Plain contextual explanations remain grounded follow-ups.
            return ConversationRoute(kind="grounded_query")
        return _clarify("transform_request_unsupported")
    if (
        operation == "simplify"
        and not has_audience
        and not explicit_targets
        and not has_prior_reference
    ):
        # Plain contextual requests such as “explain that finding” stay grounded.
        return ConversationRoute(kind="grounded_query")

    if _UNSUPPORTED_FORMAT_RE.search(option_text):
        return _clarify("transform_request_unsupported")

    if len(explicit_targets) > 1 or (explicit_targets and has_prior_reference):
        return _clarify("transform_target_ambiguous")

    target_text = explicit_targets[0].text if explicit_targets else None
    source: TransformSource = "current_message"
    source_role: TransformRole | None = "user"
    source_ordinal: int | None = None
    if target_text is None:
        prior = _prior_target(option_text, prior_turns)
        if prior is not None:
            source, source_role, source_ordinal, target_text = prior
        elif has_prior_reference:
            return _clarify("transform_target_missing")
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
        bullets = _BULLET_COUNT_RE.search(option_text)
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
        audience = _AUDIENCE_RE.search(option_text)
        if audience:
            value = audience.group(1).strip().rstrip(".:;,")
            value = re.split(r"\b(?:using|with|from)\b", value, maxsplit=1)[0].strip()
            if not value or len(value) > 60:
                return _clarify("transform_request_unsupported")
            options.append(f"for {value}")
    if operation == "translate":
        language = _LANGUAGE_RE.search(option_text)
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
