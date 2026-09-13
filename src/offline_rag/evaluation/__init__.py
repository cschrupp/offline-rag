"""Slice 9 retrieval evaluation package."""

from offline_rag.evaluation.compare import (
    CompareError,
    compare_retrieval_results,
    load_retrieval_eval_result,
)
from offline_rag.evaluation.gold import (
    GOLD_SCHEMA_V1,
    GoldCase,
    GoldDatasetError,
    LoadedGoldDataset,
    compute_gold_dataset_id,
    load_gold_dataset,
)
from offline_rag.evaluation.result import RetrievalEvaluationResultV1
from offline_rag.evaluation.runner import EvaluationError

__all__ = [
    "CompareError",
    "EvaluationError",
    "GOLD_SCHEMA_V1",
    "GoldCase",
    "GoldDatasetError",
    "LoadedGoldDataset",
    "RetrievalEvaluationResultV1",
    "compare_retrieval_results",
    "compute_gold_dataset_id",
    "load_gold_dataset",
    "load_retrieval_eval_result",
]
