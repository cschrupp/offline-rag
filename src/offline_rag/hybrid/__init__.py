"""Hybrid retrieval package (Slice 5)."""

from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.evaluate import HybridRetrievalEvaluator
from offline_rag.hybrid.fusion import FusedHit, RankedBranchHit, ReciprocalRankFusion
from offline_rag.hybrid.retrieve import HybridRetrievalError, HybridRetriever
from offline_rag.hybrid.status import describe_hybrid_status, hybrid_status_for_corpus

__all__ = [
    "FusedHit",
    "HybridRetrievalError",
    "HybridRetrievalEvaluator",
    "HybridRetriever",
    "RankedBranchHit",
    "ReciprocalRankFusion",
    "build_fusion_config_hash",
    "describe_hybrid_status",
    "hybrid_status_for_corpus",
]
