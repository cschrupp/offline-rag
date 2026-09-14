"""Offline gold-authoring subsystem (Slices 9A–9E)."""

from offline_rag.gold_authoring.config_hash import (
    build_authoring_config_hash,
    build_authoring_semantic_payload,
)
from offline_rag.gold_authoring.contracts import (
    ADAPTER_CONTRACT,
    ATTEMPT_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    BLIND_ORDER_CONTRACT,
    CONTEXT_CONTRACT,
    JUDGE_CONTEXT_CONTRACT,
    POOLING_CONTRACT,
    PRELABEL_AGREEMENT_CONTRACT,
    QUALITY_GATE_CONTRACT,
    QUESTION_PROPOSAL_CONTRACT,
    RELEVANCE_PRELABEL_CONTRACT,
    SAMPLING_CONTRACT,
)
from offline_rag.gold_authoring.finalize import FinalizePreRunError, run_gold_finalize
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    ProposalAttempt,
    ProposalAttemptStatus,
    SilverCase,
)
from offline_rag.gold_authoring.pool import PoolPreRunError, run_gold_pool
from offline_rag.gold_authoring.prelabel import PrelabelPreRunError, run_gold_prelabel
from offline_rag.gold_authoring.privacy import (
    AuthoringAuthReason,
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.propose import ProposePreRunError, run_gold_propose
from offline_rag.gold_authoring.readiness import (
    AuthoringReadiness,
    authoring_status_label,
    evaluate_authoring_readiness,
)
from offline_rag.gold_authoring.review_models import HumanReview, HumanReviewStatus

__all__ = [
    "ADAPTER_CONTRACT",
    "ATTEMPT_CONTRACT",
    "AUTHORING_ARTIFACT_CONTRACT",
    "BLIND_ORDER_CONTRACT",
    "CONTEXT_CONTRACT",
    "AuthoringAuthReason",
    "AuthoringPrivacyError",
    "AuthoringReadiness",
    "FinalizePreRunError",
    "GoldAuthoringRun",
    "HumanReview",
    "HumanReviewStatus",
    "JUDGE_CONTEXT_CONTRACT",
    "POOLING_CONTRACT",
    "PRELABEL_AGREEMENT_CONTRACT",
    "PoolPreRunError",
    "PrelabelPreRunError",
    "ProposalAttempt",
    "ProposalAttemptStatus",
    "ProposePreRunError",
    "QUALITY_GATE_CONTRACT",
    "QUESTION_PROPOSAL_CONTRACT",
    "RELEVANCE_PRELABEL_CONTRACT",
    "SAMPLING_CONTRACT",
    "SilverCase",
    "authorize_authoring_endpoint",
    "authoring_status_label",
    "build_authoring_config_hash",
    "build_authoring_semantic_payload",
    "evaluate_authoring_readiness",
    "run_gold_finalize",
    "run_gold_pool",
    "run_gold_prelabel",
    "run_gold_propose",
]
