"""Cross-encoder reranking package (Slice 6)."""

from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.cross_encoder import (
    CrossEncoderReranker,
    CrossEncoderRerankerError,
)
from offline_rag.rerank.evaluate import HybridRerankRetrievalEvaluator
from offline_rag.rerank.fake import (
    FakeReranker,
    FakeRerankerError,
    fake_rerank_digest_score,
)
from offline_rag.rerank.input_builder import PairInputError, PlainPairInputBuilder
from offline_rag.rerank.protocol import Reranker, RerankerPair
from offline_rag.rerank.provision import (
    RerankerArtifactStatus,
    RerankerArtifactsUnavailableError,
    RerankerReadiness,
    default_reranker_model_dir,
    provision_reranker_model,
    require_reranker_artifacts,
    resolve_reranker_model_dir,
    validate_reranker_artifacts,
)
from offline_rag.rerank.retrieve import (
    HybridRerankRetrievalError,
    HybridRerankRetriever,
)
from offline_rag.rerank.status import (
    describe_hybrid_rerank_status,
    hybrid_rerank_status_for_corpus,
    reranker_artifact_status,
)

__all__ = [
    "CrossEncoderReranker",
    "CrossEncoderRerankerError",
    "FakeReranker",
    "FakeRerankerError",
    "HybridRerankRetrievalError",
    "HybridRerankRetrievalEvaluator",
    "HybridRerankRetriever",
    "PairInputError",
    "PlainPairInputBuilder",
    "Reranker",
    "RerankerArtifactStatus",
    "RerankerArtifactsUnavailableError",
    "RerankerPair",
    "RerankerReadiness",
    "build_reranker_config_hash",
    "default_reranker_model_dir",
    "describe_hybrid_rerank_status",
    "fake_rerank_digest_score",
    "hybrid_rerank_status_for_corpus",
    "provision_reranker_model",
    "require_reranker_artifacts",
    "reranker_artifact_status",
    "resolve_reranker_model_dir",
    "validate_reranker_artifacts",
]
