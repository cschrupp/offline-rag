"""Slice 13A security evaluation package (OD-13-1…6; harness_fake only).

Design authority: docs/milestone6_agentic_recovery_security.md §29.
Does not enable product recovery, LangGraph, NeMo, or 13B/13C campaigns.
"""

from offline_rag.evaluation.security_13.contracts import (
    ADVERSARIAL_EVAL_RESULT_V1,
    ADVERSARIAL_FIXTURE_V1,
    DESIGN_AUTHORITY_SHA_13,
    LOCKED_INVARIANT_IDS_V1,
    SECURITY_INVARIANT_REGISTRY_V1,
    SLICE13_BASELINE_SHA,
    AdversarialEvalResultV1,
    AdversarialEvidenceUnitV1,
    AdversarialFixtureV1,
    FixtureOutcomeV1,
    InvariantOutcomeV1,
    InvariantStatusV1,
    SecurityEvalError,
    SecurityInvariantRegistryV1,
    SecurityObservationV1,
)
from offline_rag.evaluation.security_13.evaluate import evaluate_adversarial_fixture
from offline_rag.evaluation.security_13.identity import (
    compute_fixture_identity_hash,
    compute_registry_hash,
    fixture_semantic_payload,
    registry_semantic_payload,
)
from offline_rag.evaluation.security_13.loader import (
    load_adversarial_fixture,
    validate_adversarial_fixture,
)
from offline_rag.evaluation.security_13.recovery_probe import (
    assert_corpus_text_rejected_from_rewrite_input,
    build_recovery_boundary_observation,
)
from offline_rag.evaluation.security_13.registry import (
    build_frozen_security_invariant_registry,
    require_known_invariant_ids,
)

__all__ = [
    "ADVERSARIAL_EVAL_RESULT_V1",
    "ADVERSARIAL_FIXTURE_V1",
    "DESIGN_AUTHORITY_SHA_13",
    "LOCKED_INVARIANT_IDS_V1",
    "SECURITY_INVARIANT_REGISTRY_V1",
    "SLICE13_BASELINE_SHA",
    "AdversarialEvalResultV1",
    "AdversarialEvidenceUnitV1",
    "AdversarialFixtureV1",
    "FixtureOutcomeV1",
    "InvariantOutcomeV1",
    "InvariantStatusV1",
    "SecurityEvalError",
    "SecurityInvariantRegistryV1",
    "SecurityObservationV1",
    "assert_corpus_text_rejected_from_rewrite_input",
    "build_frozen_security_invariant_registry",
    "build_recovery_boundary_observation",
    "compute_fixture_identity_hash",
    "compute_registry_hash",
    "evaluate_adversarial_fixture",
    "fixture_semantic_payload",
    "load_adversarial_fixture",
    "registry_semantic_payload",
    "require_known_invariant_ids",
    "validate_adversarial_fixture",
]
