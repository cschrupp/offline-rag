"""Fail-closed fixture / control evaluation (OD-13-1 / OD-13-6 / OD-13-11)."""

from __future__ import annotations

from offline_rag.evaluation.security_13.contracts import (
    AdversarialEvalResultV1,
    AdversarialFixtureV1,
    BenignControlEvalResultV1,
    BenignSecurityControlV1,
    FixtureOutcomeV1,
    InvariantStatusV1,
    SecurityEvalError,
    SecurityObservationV1,
)
from offline_rag.evaluation.security_13.evaluators import dispatch_invariant_evaluator
from offline_rag.evaluation.security_13.identity import (
    compute_benign_control_identity_hash,
    compute_fixture_identity_hash,
)
from offline_rag.evaluation.security_13.registry import (
    build_frozen_security_invariant_registry,
    require_known_invariant_ids,
)


def evaluate_adversarial_fixture(
    fixture: AdversarialFixtureV1,
    observation: SecurityObservationV1,
) -> AdversarialEvalResultV1:
    """Evaluate all expected invariants; never pass on unknown/unevaluable."""
    require_known_invariant_ids(list(fixture.expected_invariant_ids))
    recomputed = compute_fixture_identity_hash(fixture)
    if fixture.fixture_identity_hash != recomputed:
        raise SecurityEvalError(
            "fixture_identity_hash mismatch at evaluation time: "
            f"declared {fixture.fixture_identity_hash!r}, recomputed {recomputed!r}"
        )

    registry = build_frozen_security_invariant_registry()
    outcomes = [
        dispatch_invariant_evaluator(invariant_id, fixture, observation)
        for invariant_id in fixture.expected_invariant_ids
    ]

    violated = any(row.status == InvariantStatusV1.VIOLATED for row in outcomes)
    unevaluable = any(
        row.status == InvariantStatusV1.UNEVALUABLE for row in outcomes
    )
    all_hold = all(row.status == InvariantStatusV1.HOLDS for row in outcomes)

    if all_hold and not violated and not unevaluable:
        outcome = FixtureOutcomeV1.PASS
        failure_kind = None
    else:
        outcome = FixtureOutcomeV1.FAIL
        if violated:
            failure_kind = "invariant_violation"
        else:
            failure_kind = "invariant_unevaluable"

    return AdversarialEvalResultV1(
        fixture_id=fixture.fixture_id,
        fixture_identity_hash=fixture.fixture_identity_hash,
        registry_hash=registry.registry_hash,
        outcome=outcome,
        invariant_outcomes=outcomes,
        product_default_recovery_enabled=observation.product_default_recovery_enabled,
        recovery_execution_mode=observation.recovery_execution_mode,
        recovery_components_entered=list(observation.recovery_components_entered),
        failure_kind=failure_kind,
    )


def evaluate_benign_control(
    control: BenignSecurityControlV1,
    observation: SecurityObservationV1,
) -> BenignControlEvalResultV1:
    """Evaluate benign control invariants with the same OD-13-1 vocabulary."""
    require_known_invariant_ids(list(control.expected_invariant_ids))
    recomputed = compute_benign_control_identity_hash(control)
    if control.control_identity_hash != recomputed:
        raise SecurityEvalError(
            "control_identity_hash mismatch at evaluation time: "
            f"declared {control.control_identity_hash!r}, recomputed {recomputed!r}"
        )

    registry = build_frozen_security_invariant_registry()
    outcomes = [
        dispatch_invariant_evaluator(invariant_id, control, observation)
        for invariant_id in control.expected_invariant_ids
    ]

    violated = any(row.status == InvariantStatusV1.VIOLATED for row in outcomes)
    unevaluable = any(
        row.status == InvariantStatusV1.UNEVALUABLE for row in outcomes
    )
    all_hold = all(row.status == InvariantStatusV1.HOLDS for row in outcomes)

    if all_hold and not violated and not unevaluable:
        outcome = FixtureOutcomeV1.PASS
        failure_kind = None
    else:
        outcome = FixtureOutcomeV1.FAIL
        if violated:
            failure_kind = "invariant_violation"
        else:
            failure_kind = "invariant_unevaluable"

    return BenignControlEvalResultV1(
        control_id=control.control_id,
        control_identity_hash=control.control_identity_hash,
        registry_hash=registry.registry_hash,
        outcome=outcome,
        invariant_outcomes=outcomes,
        product_default_recovery_enabled=observation.product_default_recovery_enabled,
        recovery_execution_mode=observation.recovery_execution_mode,
        recovery_components_entered=list(observation.recovery_components_entered),
        failure_kind=failure_kind,
    )
