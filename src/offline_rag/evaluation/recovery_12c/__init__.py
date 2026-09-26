"""Slice 12C recovery-vs-baseline evaluation harness (contracts + paired exec).

Design authority: docs/milestone6_agentic_recovery_security.md §16 (OD-12C-1…8).
Consumes accepted 12A/12B recovery contracts. No generation, judge, or LangGraph.
Does not enable ``retrieval_recovery`` in base config and does not run measure-once.
"""

from offline_rag.evaluation.recovery_12c.binding import (
    bind_cohort_map_for_gold,
    load_and_bind_cohort_map,
    load_frozen_gold_dataset,
    require_gold_lineage_compatible,
)
from offline_rag.evaluation.recovery_12c.conclusion import conclude_recovery_eval
from offline_rag.evaluation.recovery_12c.contracts import (
    FROZEN_GOLD_DATASET_ID_12C,
    NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES,
    PLACEHOLDER_REWRITER_MODEL,
    RECOVERY_EVAL_CONCLUSION_V1,
    RECOVERY_EVAL_V1,
    AttemptObservationV1,
    CohortAggregateV1,
    PresenceMatchingRuleV1,
    RecoveryAttemptRecordV1,
    RecoveryEvalAggregateV1,
    RecoveryEvalCaseClassV1,
    RecoveryEvalCaseRecordV1,
    RecoveryEvalConclusionV1,
    RecoveryEvalError,
    TriggerCensusV1,
    ranking_score_to_dict,
)
from offline_rag.evaluation.recovery_12c.evidence import (
    evidence_surface_chunk_ids_from_context,
    gold_positive_overlap,
    ranked_anchor_chunk_ids,
)
from offline_rag.evaluation.recovery_12c.harness import (
    CountingInitialAssembler,
    aggregate_recovery_eval,
    assert_single_initial_assemble,
    build_trigger_census,
    census_from_initial_attempts,
    classify_case,
    evaluate_paired_case,
    is_recovery_triggered,
    observe_attempt,
)
from offline_rag.evaluation.recovery_12c.identity import (
    build_recovery_eval_identity_hash,
    build_recovery_eval_semantic_payload,
)
from offline_rag.evaluation.recovery_12c.preflight import (
    RecoveryEvalPreflightResult,
    preflight_authoritative_recovery_eval,
    require_authoritative_recovery_preflight,
)

__all__ = [
    "FROZEN_GOLD_DATASET_ID_12C",
    "NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES",
    "PLACEHOLDER_REWRITER_MODEL",
    "RECOVERY_EVAL_CONCLUSION_V1",
    "RECOVERY_EVAL_V1",
    "AttemptObservationV1",
    "CohortAggregateV1",
    "CountingInitialAssembler",
    "PresenceMatchingRuleV1",
    "RecoveryAttemptRecordV1",
    "RecoveryEvalAggregateV1",
    "RecoveryEvalCaseClassV1",
    "RecoveryEvalCaseRecordV1",
    "RecoveryEvalConclusionV1",
    "RecoveryEvalError",
    "RecoveryEvalPreflightResult",
    "TriggerCensusV1",
    "aggregate_recovery_eval",
    "assert_single_initial_assemble",
    "bind_cohort_map_for_gold",
    "build_recovery_eval_identity_hash",
    "build_recovery_eval_semantic_payload",
    "build_trigger_census",
    "census_from_initial_attempts",
    "classify_case",
    "conclude_recovery_eval",
    "evaluate_paired_case",
    "evidence_surface_chunk_ids_from_context",
    "gold_positive_overlap",
    "is_recovery_triggered",
    "load_and_bind_cohort_map",
    "load_frozen_gold_dataset",
    "observe_attempt",
    "preflight_authoritative_recovery_eval",
    "ranked_anchor_chunk_ids",
    "ranking_score_to_dict",
    "require_authoritative_recovery_preflight",
    "require_gold_lineage_compatible",
]
