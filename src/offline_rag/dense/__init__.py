"""Dense indexing and retrieval package (Slice 3)."""

from offline_rag.dense.backend import (
    DenseIndexBackend,
    DensePointRecord,
    DenseSearchHit,
)
from offline_rag.dense.cache import (
    embedding_artifact_path,
    load_embedding_artifact,
    try_load_reusable_embedding_artifact,
    write_embedding_artifact,
)
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import (
    FakeEmbedder,
    SentenceTransformersEmbedder,
    make_embedder,
)
from offline_rag.dense.evaluate import (
    DenseEvaluationError,
    DenseRetrievalEvaluator,
    load_retrieval_eval_dataset,
    mean_reciprocal_rank,
    recall_at_k,
)
from offline_rag.dense.pipeline import IndexingError, run_indexing
from offline_rag.dense.points import (
    DENSE_POINT_SCHEMA_VERSION,
    build_dense_payload,
    build_dense_point,
)
from offline_rag.dense.provision import (
    EMBEDDING_MANIFEST_NAME,
    EmbeddingReadiness,
    provision_embedding_model,
    validate_embedding_artifacts,
)
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.retrieve import DenseRetrievalError, DenseRetriever
from offline_rag.dense.status import indexing_status_for_corpus
from offline_rag.dense.text import (
    EmbeddingTextBuilder,
    PlainEmbeddingTextBuilder,
    TitleSectionEmbeddingTextBuilder,
)

__all__ = [
    "DENSE_POINT_SCHEMA_VERSION",
    "EMBEDDING_MANIFEST_NAME",
    "DenseEvaluationError",
    "DenseIndexBackend",
    "DensePointRecord",
    "DenseRetrievalError",
    "DenseRetrievalEvaluator",
    "DenseRetriever",
    "DenseSearchHit",
    "EmbeddingReadiness",
    "EmbeddingTextBuilder",
    "FakeEmbedder",
    "IndexingError",
    "PlainEmbeddingTextBuilder",
    "QdrantLocalBackend",
    "SentenceTransformersEmbedder",
    "TitleSectionEmbeddingTextBuilder",
    "build_dense_payload",
    "build_dense_point",
    "build_embedding_config_hash",
    "build_index_config_hash",
    "embedding_artifact_path",
    "indexing_status_for_corpus",
    "load_embedding_artifact",
    "load_retrieval_eval_dataset",
    "make_embedder",
    "mean_reciprocal_rank",
    "provision_embedding_model",
    "recall_at_k",
    "run_indexing",
    "try_load_reusable_embedding_artifact",
    "validate_embedding_artifacts",
    "write_embedding_artifact",
]
