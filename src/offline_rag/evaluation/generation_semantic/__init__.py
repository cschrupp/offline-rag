"""Slice 10 generation-semantic evaluation contracts and builders."""

from offline_rag.evaluation.generation_semantic.evidence import (
    EVIDENCE_BUDGET_EXCEEDED,
    GOLD_EVIDENCE_V1,
    EvidenceBudgetExceeded,
    GoldEvidenceBuildError,
    build_gold_evidence_set_v1,
    compute_generation_evidence_set_id,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_EVIDENCE_SET_V1,
    GENERATION_SEMANTIC_EVAL_COMPARISON_V1,
    GENERATION_SEMANTIC_EVAL_RESULT_V1,
    GenerationEvidenceCaseV1,
    GenerationEvidenceSetV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticEvalComparisonV1,
    GenerationSemanticEvalResultV1,
    GoldEvidenceJudgmentV1,
    LabelCohort,
)

__all__ = [
    "EVIDENCE_BUDGET_EXCEEDED",
    "GENERATION_EVIDENCE_SET_V1",
    "GENERATION_SEMANTIC_EVAL_COMPARISON_V1",
    "GENERATION_SEMANTIC_EVAL_RESULT_V1",
    "GOLD_EVIDENCE_V1",
    "EvidenceBudgetExceeded",
    "GenerationEvidenceCaseV1",
    "GenerationEvidenceSetV1",
    "GenerationSemanticEvalCaseResultV1",
    "GenerationSemanticEvalComparisonV1",
    "GenerationSemanticEvalResultV1",
    "GoldEvidenceBuildError",
    "GoldEvidenceJudgmentV1",
    "LabelCohort",
    "build_gold_evidence_set_v1",
    "compute_generation_evidence_set_id",
]
