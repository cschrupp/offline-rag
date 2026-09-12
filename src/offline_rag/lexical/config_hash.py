"""Deterministic lexical configuration hash."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, LexicalSettings
from offline_rag.core.ids import DOCUMENT_TITLE_V1, TITLE_SECTION_TEXT_V1, lexical_config_hash
from offline_rag.lexical.text import PlainLexicalTextBuilder, TitleSectionLexicalTextBuilder


def build_lexical_config_hash(settings: AppSettings | LexicalSettings) -> str:
    """Hash lexical-index-affecting semantics (excludes query-time top_k)."""
    lexical = settings.lexical if isinstance(settings, AppSettings) else settings
    payload: dict = {
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
    if (
        lexical.text.strategy == TitleSectionLexicalTextBuilder.strategy
        and lexical.text.contract_version == TitleSectionLexicalTextBuilder.contract_version
    ):
        payload["document_title_contract"] = DOCUMENT_TITLE_V1
        payload["ranking_text_contract"] = TITLE_SECTION_TEXT_V1
    elif not (
        lexical.text.strategy == PlainLexicalTextBuilder.strategy
        and lexical.text.contract_version == PlainLexicalTextBuilder.contract_version
    ):
        pass
    return lexical_config_hash(payload)
