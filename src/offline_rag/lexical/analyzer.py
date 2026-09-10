"""Technical lexical analyzer (technical-v1)."""

from __future__ import annotations

import re
import unicodedata

from offline_rag.core.ids import TECHNICAL_ANALYZER_CONTRACT

# Optional leading '.', alphanumeric runs, internal/trailing technical separators.
_TOKEN_RE = re.compile(
    r"\.?[^\W_]+(?:[-_./+#]+[^\W_]+)*[-_./+#]*",
    re.UNICODE,
)


class TechnicalLexicalAnalyzer:
    """NFKC → casefold → technical tokenizer; no stopwords/stemming."""

    strategy = "technical"
    contract_version = TECHNICAL_ANALYZER_CONTRACT
    unicode_normalization = "NFKC"
    case_normalization = "casefold"
    stopwords = "none"
    stemming = "none"
    lemmatization = "none"

    def analyze(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        terms: list[str] = []
        for term in _TOKEN_RE.findall(normalized):
            if any(ch.isalnum() for ch in term):
                terms.append(term)
        return terms

    def analyze_query_terms(self, text: str) -> list[str]:
        """Return unique analyzed terms preserving first-seen order."""
        seen: set[str] = set()
        unique: list[str] = []
        for term in self.analyze(text):
            if term in seen:
                continue
            seen.add(term)
            unique.append(term)
        return unique
