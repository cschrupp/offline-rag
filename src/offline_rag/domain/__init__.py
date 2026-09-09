"""Project-owned domain schemas.

These models must remain free of Docling, Qdrant, LangChain, Ollama, or other
infrastructure types. Adapters translate external objects into these contracts.
"""

from offline_rag.domain.documents import Chunk, Document
from offline_rag.domain.evaluation import EvaluationResult, ExperimentConfig
from offline_rag.domain.generation import Citation
from offline_rag.domain.retrieval import RetrievalCandidate, RetrievalResult
from offline_rag.domain.traces import QueryTrace

__all__ = [
    "Chunk",
    "Citation",
    "Document",
    "EvaluationResult",
    "ExperimentConfig",
    "QueryTrace",
    "RetrievalCandidate",
    "RetrievalResult",
]
