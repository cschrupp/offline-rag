"""Deterministic lexical configuration hash."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, LexicalSettings
from offline_rag.core.ids import lexical_config_hash


def build_lexical_config_hash(settings: AppSettings | LexicalSettings) -> str:
    """Hash lexical-index-affecting semantics (excludes query-time top_k)."""
    lexical = settings.lexical if isinstance(settings, AppSettings) else settings
    return lexical_config_hash(
        {
            "text_strategy": lexical.text.strategy,
            "text_contract": lexical.text.contract_version,
            "analyzer_strategy": lexical.analyzer.strategy,
            "analyzer_contract": lexical.analyzer.contract_version,
            "unicode_normalization": lexical.analyzer.unicode_normalization,
            "case_normalization": lexical.analyzer.case_normalization,
            "stopwords": lexical.analyzer.stopwords,
            "stemming": lexical.analyzer.stemming,
            "lemmatization": lexical.analyzer.lemmatization,
            "bm25_contract": lexical.bm25.contract_version,
            "k1": lexical.bm25.k1,
            "b": lexical.bm25.b,
            "idf": lexical.bm25.idf,
            "query_tf": lexical.bm25.query_tf,
            "backend": lexical.backend,
            "backend_contract": lexical.backend_contract,
            "method": lexical.method,
        }
    )
