"""Deterministic proposal quality gates (proposal-quality-gates-v1)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from offline_rag.gold_authoring.contracts import QUALITY_GATE_CONTRACT
from offline_rag.gold_authoring.models import ProposalFailureReason, ProposedQueryFields

_WHITESPACE = re.compile(r"\s+", flags=re.UNICODE)
_DEICTIC_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(phrase)}\b", flags=re.IGNORECASE)
    for phrase in (
        "the passage above",
        "the text above",
        "the provided passage",
        "the provided text",
        "the provided context",
        "the context above",
        "this passage",
        "this text",
        "this context",
        "according to the passage",
        "according to the provided text",
        "according to the provided context",
        "based on the passage above",
        "based on the provided context",
    )
)


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    ok: bool
    reason: ProposalFailureReason | None = None


def _collapse_ws(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip())


def _normalize_for_quote(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = _collapse_ws(folded)
    # Drop surrounding punctuation on tokens for comparison only.
    tokens: list[str] = []
    for raw in folded.split(" "):
        token = raw.strip(".,;:!?\"'`()[]{}")
        if token:
            tokens.append(token)
    return tokens


def _normalize_for_dedupe(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = _collapse_ws(folded)
    folded = folded.rstrip("?").strip()
    folded = folded.replace("\u2019", "'")
    return folded


def _token_set(text: str) -> set[str]:
    tokens = _normalize_for_quote(text)
    return set(tokens)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _longest_common_run(query_tokens: list[str], seed_tokens: list[str]) -> int:
    if not query_tokens or not seed_tokens:
        return 0
    seed_joined = f" {' '.join(seed_tokens)} "
    best = 0
    n = len(query_tokens)
    max_len = min(n, len(seed_tokens))
    for length in range(max_len, 0, -1):
        for start in range(0, n - length + 1):
            span = f" {' '.join(query_tokens[start : start + length])} "
            if span in seed_joined:
                return length
        # Continue only while we have not found any match yet for this length.
        if best:
            break
    return best


def check_deictic(query: str) -> QualityGateResult:
    normalized = _collapse_ws(query)
    for pattern in _DEICTIC_PATTERNS:
        if pattern.search(normalized):
            return QualityGateResult(False, ProposalFailureReason.DEICTIC_QUERY)
    return QualityGateResult(True)


def check_seed_quote_overlap(*, query: str, seed_text: str) -> QualityGateResult:
    q_tokens = _normalize_for_quote(query)
    s_tokens = _normalize_for_quote(seed_text)
    if not q_tokens:
        return QualityGateResult(True)
    run = _longest_common_run(q_tokens, s_tokens)
    if run >= 12 and (run / len(q_tokens)) >= 0.50:
        return QualityGateResult(False, ProposalFailureReason.SEED_QUOTE_OVERLAP)
    if len(q_tokens) >= 10:
        overlap = sum(1 for t in q_tokens if t in set(s_tokens)) / len(q_tokens)
        if overlap >= 0.80:
            return QualityGateResult(False, ProposalFailureReason.SEED_QUOTE_OVERLAP)
    return QualityGateResult(True)


def check_same_run_duplicate(
    *,
    query: str,
    accepted_queries: list[str],
) -> QualityGateResult:
    normalized = _normalize_for_dedupe(query)
    q_tokens = _normalize_for_quote(query)
    q_set = _token_set(query)
    for prior in accepted_queries:
        if _normalize_for_dedupe(prior) == normalized:
            return QualityGateResult(False, ProposalFailureReason.DUPLICATE_QUERY_EXACT)
        if len(q_tokens) >= 5:
            if _jaccard(q_set, _token_set(prior)) >= 0.90:
                return QualityGateResult(False, ProposalFailureReason.DUPLICATE_QUERY_NEAR)
    return QualityGateResult(True)


def apply_proposal_quality_gates(
    proposal: ProposedQueryFields,
    *,
    seed_text: str,
    accepted_queries: list[str],
) -> QualityGateResult:
    result = check_deictic(proposal.query)
    if not result.ok:
        return result
    result = check_seed_quote_overlap(query=proposal.query, seed_text=seed_text)
    if not result.ok:
        return result
    return check_same_run_duplicate(
        query=proposal.query,
        accepted_queries=accepted_queries,
    )


def quality_gate_contract_id() -> str:
    return QUALITY_GATE_CONTRACT
