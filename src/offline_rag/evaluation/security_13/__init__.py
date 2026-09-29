"""Slice 13 security evaluation package (OD-13-1…13; 13A + 13B harness).

Design authority: docs/milestone6_agentic_recovery_security.md §29–§30.
13B dry-run harness only — authoritative measure-once is NOT AUTHORIZED.
"""

from offline_rag.evaluation.security_13.contracts import (
    ADVERSARIAL_EVAL_RESULT_V1,
    ADVERSARIAL_FIXTURE_V1,
    ACCEPTED_CAMPAIGN_GIT_BLOB_SHA,
    BENIGN_CONTROL_EVAL_RESULT_V1,
    BENIGN_SECURITY_CONTROL_V1,
    DESIGN_AUTHORITY_SHA_13,
    DESIGN_AUTHORITY_SHA_13B,
    FROZEN_SECCAMP_13B,
    FROZEN_SECINV_13B,
    GENERATOR_PROBE_POLICY_13B_V1,
    LOCKED_INVARIANT_IDS_V1,
    MEASURE_ONCE_AUTHORITY_BASELINE_SHA,
    SECURITY_CAMPAIGN_AGGREGATE_V1,
    SECURITY_CAMPAIGN_V1,
    SECURITY_INVARIANT_REGISTRY_V1,
    SLICE13_BASELINE_SHA,
    SLICE13B_BASELINE_SHA,
    AdversarialEvalResultV1,
    AdversarialEvidenceUnitV1,
    AdversarialFixtureV1,
    BenignControlEvalResultV1,
    BenignSecurityControlV1,
    FixtureOutcomeV1,
    InvariantOutcomeV1,
    InvariantStatusV1,
    SecurityCampaignAggregateV1,
    SecurityCampaignV1,
    SecurityEvalError,
    SecurityInvariantRegistryV1,
    SecurityObservationV1,
)
from offline_rag.evaluation.security_13.evaluate import (
    evaluate_adversarial_fixture,
    evaluate_benign_control,
)
from offline_rag.evaluation.security_13.harness import (
    run_case_on_query_path,
    run_security_13b_authoritative,
    run_security_13b_dryrun,
)
from offline_rag.evaluation.security_13.identity import (
    compute_benign_control_identity_hash,
    compute_campaign_identity_hash,
    compute_fixture_identity_hash,
    compute_registry_hash,
    fixture_semantic_payload,
    registry_semantic_payload,
)
from offline_rag.evaluation.security_13.loader import (
    load_adversarial_fixture,
    load_benign_control,
    load_security_campaign,
    validate_adversarial_fixture,
    validate_benign_control,
    validate_security_campaign,
)
from offline_rag.evaluation.security_13.paths import (
    assert_outside_authoritative_root,
    authoritative_results_root,
)
from offline_rag.evaluation.security_13.provenance import (
    AUTHORITATIVE_NOT_AUTHORIZED_MSG,
    collect_git_and_campaign_provenance,
    git_blob_sha1,
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
    "ACCEPTED_CAMPAIGN_GIT_BLOB_SHA",
    "ADVERSARIAL_EVAL_RESULT_V1",
    "ADVERSARIAL_FIXTURE_V1",
    "AUTHORITATIVE_NOT_AUTHORIZED_MSG",
    "BENIGN_CONTROL_EVAL_RESULT_V1",
    "BENIGN_SECURITY_CONTROL_V1",
    "DESIGN_AUTHORITY_SHA_13",
    "DESIGN_AUTHORITY_SHA_13B",
    "FROZEN_SECCAMP_13B",
    "FROZEN_SECINV_13B",
    "GENERATOR_PROBE_POLICY_13B_V1",
    "LOCKED_INVARIANT_IDS_V1",
    "MEASURE_ONCE_AUTHORITY_BASELINE_SHA",
    "SECURITY_CAMPAIGN_AGGREGATE_V1",
    "SECURITY_CAMPAIGN_V1",
    "SECURITY_INVARIANT_REGISTRY_V1",
    "SLICE13B_BASELINE_SHA",
    "SLICE13_BASELINE_SHA",
    "AdversarialEvalResultV1",
    "AdversarialEvidenceUnitV1",
    "AdversarialFixtureV1",
    "BenignControlEvalResultV1",
    "BenignSecurityControlV1",
    "FixtureOutcomeV1",
    "InvariantOutcomeV1",
    "InvariantStatusV1",
    "SecurityCampaignAggregateV1",
    "SecurityCampaignV1",
    "SecurityEvalError",
    "SecurityInvariantRegistryV1",
    "SecurityObservationV1",
    "assert_corpus_text_rejected_from_rewrite_input",
    "assert_outside_authoritative_root",
    "authoritative_results_root",
    "build_frozen_security_invariant_registry",
    "build_recovery_boundary_observation",
    "collect_git_and_campaign_provenance",
    "compute_benign_control_identity_hash",
    "compute_campaign_identity_hash",
    "compute_fixture_identity_hash",
    "compute_registry_hash",
    "evaluate_adversarial_fixture",
    "evaluate_benign_control",
    "fixture_semantic_payload",
    "git_blob_sha1",
    "load_adversarial_fixture",
    "load_benign_control",
    "load_security_campaign",
    "registry_semantic_payload",
    "require_known_invariant_ids",
    "run_case_on_query_path",
    "run_security_13b_authoritative",
    "run_security_13b_dryrun",
    "validate_adversarial_fixture",
    "validate_benign_control",
    "validate_security_campaign",
]
