"""Offline gold-authoring subsystem (Slice 9A contracts and privacy boundary)."""

from offline_rag.gold_authoring.config_hash import (
    build_authoring_config_hash,
    build_authoring_semantic_payload,
)
from offline_rag.gold_authoring.contracts import (
    ADAPTER_CONTRACT,
    AUTHORING_ARTIFACT_CONTRACT,
    QUESTION_PROPOSAL_CONTRACT,
    RELEVANCE_PRELABEL_CONTRACT,
)
from offline_rag.gold_authoring.models import (
    GoldAuthoringRun,
    HumanReviewStatus,
    SilverCase,
)
from offline_rag.gold_authoring.privacy import (
    AuthoringAuthReason,
    AuthoringPrivacyError,
    authorize_authoring_endpoint,
)
from offline_rag.gold_authoring.readiness import (
    AuthoringReadiness,
    authoring_status_label,
    evaluate_authoring_readiness,
)

__all__ = [
    "ADAPTER_CONTRACT",
    "AUTHORING_ARTIFACT_CONTRACT",
    "AuthoringAuthReason",
    "AuthoringPrivacyError",
    "AuthoringReadiness",
    "GoldAuthoringRun",
    "HumanReviewStatus",
    "QUESTION_PROPOSAL_CONTRACT",
    "RELEVANCE_PRELABEL_CONTRACT",
    "SilverCase",
    "authorize_authoring_endpoint",
    "authoring_status_label",
    "build_authoring_config_hash",
    "build_authoring_semantic_payload",
    "evaluate_authoring_readiness",
]
