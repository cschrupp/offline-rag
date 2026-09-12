"""Lexical indexing and retrieval package (Slice 4)."""

from offline_rag.lexical.analyzer import TechnicalLexicalAnalyzer
from offline_rag.lexical.backend import (
    LexicalDocumentInput,
    LexicalIndexBackend,
    LexicalSearchHit,
    LocalInvertedIndexBackend,
)
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.evaluate import (
    LexicalEvaluationError,
    LexicalRetrievalEvaluator,
)
from offline_rag.lexical.pipeline import (
    LexicalIndexingError,
    make_lexical_analyzer,
    make_lexical_text_builder,
    run_lexical_indexing,
)
from offline_rag.lexical.retrieve import LexicalRetrievalError, LexicalRetriever
from offline_rag.lexical.scoring import BM25OkapiV1Scorer, idf, score_document
from offline_rag.lexical.status import (
    describe_lexical_indexing_status,
    lexical_indexing_status_for_corpus,
)
from offline_rag.lexical.text import (
    LexicalTextBuilder,
    PlainLexicalTextBuilder,
    TitleSectionLexicalTextBuilder,
)

__all__ = [
    "BM25OkapiV1Scorer",
    "LexicalDocumentInput",
    "LexicalEvaluationError",
    "LexicalIndexBackend",
    "LexicalIndexingError",
    "LexicalRetrievalError",
    "LexicalRetrievalEvaluator",
    "LexicalRetriever",
    "LexicalSearchHit",
    "LexicalTextBuilder",
    "LocalInvertedIndexBackend",
    "PlainLexicalTextBuilder",
    "TechnicalLexicalAnalyzer",
    "TitleSectionLexicalTextBuilder",
    "build_lexical_config_hash",
    "describe_lexical_indexing_status",
    "idf",
    "lexical_indexing_status_for_corpus",
    "make_lexical_analyzer",
    "make_lexical_text_builder",
    "run_lexical_indexing",
    "score_document",
]
