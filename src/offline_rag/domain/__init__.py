"""Project-owned domain schemas.

These models must remain free of Docling, Qdrant, LangChain, Ollama, or other
infrastructure types. Adapters translate external objects into these contracts.
"""

from offline_rag.domain.blocks import (
    ContentBlock,
    ContentType,
    ParsedDocument,
    ParseWarning,
    SourceLocator,
    WarningCategory,
)
from offline_rag.domain.corpus import (
    CorpusDocumentEntry,
    CorpusManifest,
    CorpusSourceEntry,
    CorpusState,
)
from offline_rag.domain.documents import Chunk, Document
from offline_rag.domain.evaluation import EvaluationResult, ExperimentConfig
from offline_rag.domain.generation import Citation
from offline_rag.domain.ingestion import (
    FileIngestionResult,
    FileIngestionStatus,
    IngestionReport,
    IngestionStatus,
)
from offline_rag.domain.retrieval import RetrievalCandidate, RetrievalResult
from offline_rag.domain.traces import QueryTrace

__all__ = [
    "Chunk",
    "Citation",
    "ContentBlock",
    "ContentType",
    "CorpusDocumentEntry",
    "CorpusManifest",
    "CorpusSourceEntry",
    "CorpusState",
    "Document",
    "EvaluationResult",
    "ExperimentConfig",
    "FileIngestionResult",
    "FileIngestionStatus",
    "IngestionReport",
    "IngestionStatus",
    "ParseWarning",
    "ParsedDocument",
    "QueryTrace",
    "RetrievalCandidate",
    "RetrievalResult",
    "SourceLocator",
    "WarningCategory",
]
