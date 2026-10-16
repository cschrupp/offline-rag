"""Lexical searchable-unit eligibility (exclude-zero-term-v1)."""

from __future__ import annotations

from offline_rag.core.ids import LEXICAL_EXCLUDE_ZERO_TERM_V1
from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer


def lexical_searchable_units_contract() -> str:
    """Hardwired product/CLI lexical eligibility contract wire value."""
    return LEXICAL_EXCLUDE_ZERO_TERM_V1


def is_analyzer_empty_v1(terms: list[str]) -> bool:
    """Return True iff technical-v1 produced zero indexable terms."""
    return len(terms) == 0


def classify_lexical_terms(
    terms: list[str],
) -> str:
    """Return ``eligible`` or ``excluded`` under exclude-zero-term-v1."""
    if is_analyzer_empty_v1(terms):
        return "excluded"
    return "eligible"


def analyze_and_classify(
    analyzer: TechnicalLexicalAnalyzer,
    lexical_text: str,
) -> tuple[list[str], str]:
    """Analyze ranking text and classify under the frozen eligibility policy."""
    terms = analyzer.analyze(lexical_text)
    return terms, classify_lexical_terms(terms)
