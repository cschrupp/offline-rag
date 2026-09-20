"""Slice 10 generation-semantic evaluation contracts and builders."""

from offline_rag.evaluation.generation_semantic.cohort import (
    CohortMapError,
    load_cohort_map,
    validate_cohort_map_for_gold,
)
from offline_rag.evaluation.generation_semantic.evidence import (
    EVIDENCE_BUDGET_EXCEEDED,
    GOLD_EVIDENCE_V1,
    EvidenceBudgetExceeded,
    GoldEvidenceBuildError,
    build_gold_evidence_set_v1,
    compute_generation_evidence_set_id,
)
from offline_rag.evaluation.generation_semantic.format import (
    format_generation_semantic_result_human,
)
from offline_rag.evaluation.generation_semantic.models import (
    GENERATION_COHORT_MAP_V1,
    GENERATION_EVIDENCE_SET_V1,
    GENERATION_SEMANTIC_DETERMINISTIC_V1,
    GENERATION_SEMANTIC_EVAL_COMPARISON_V1,
    GENERATION_SEMANTIC_EVAL_RESULT_V1,
    GenerationCohortMapV1,
    GenerationEvidenceCaseV1,
    GenerationEvidenceSetV1,
    GenerationSemanticEvalCaseResultV1,
    GenerationSemanticEvalComparisonV1,
    GenerationSemanticEvalResultV1,
    GoldEvidenceJudgmentV1,
    LabelCohort,
)
from offline_rag.evaluation.generation_semantic.runner import (
    GenerationSemanticEvaluationError,
    GenerationSemanticEvaluator,
    run_generation_semantic_evaluation,
)

__all__ = [
    "EVIDENCE_BUDGET_EXCEEDED",
    "GENERATION_COHORT_MAP_V1",
    "GENERATION_EVIDENCE_SET_V1",
    "GENERATION_SEMANTIC_DETERMINISTIC_V1",
    "GENERATION_SEMANTIC_EVAL_COMPARISON_V1",
    "GENERATION_SEMANTIC_EVAL_RESULT_V1",
    "GOLD_EVIDENCE_V1",
    "CohortMapError",
    "EvidenceBudgetExceeded",
    "GenerationCohortMapV1",
    "GenerationEvidenceCaseV1",
    "GenerationEvidenceSetV1",
    "GenerationSemanticEvalCaseResultV1",
    "GenerationSemanticEvalComparisonV1",
    "GenerationSemanticEvalResultV1",
    "GenerationSemanticEvaluationError",
    "GenerationSemanticEvaluator",
    "GoldEvidenceBuildError",
    "GoldEvidenceJudgmentV1",
    "LabelCohort",
    "build_gold_evidence_set_v1",
    "compute_generation_evidence_set_id",
    "format_generation_semantic_result_human",
    "load_cohort_map",
    "run_generation_semantic_evaluation",
    "validate_cohort_map_for_gold",
]
