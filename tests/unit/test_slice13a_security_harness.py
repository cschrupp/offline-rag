"""Slice 13A focused security harness tests (OD-13-1…6; harness_fake only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from offline_rag.evaluation.security_13 import (
    DESIGN_AUTHORITY_SHA_13,
    SLICE13_BASELINE_SHA,
    AdversarialFixtureV1,
    FixtureOutcomeV1,
    InvariantStatusV1,
    SecurityEvalError,
    SecurityObservationV1,
    assert_corpus_text_rejected_from_rewrite_input,
    build_frozen_security_invariant_registry,
    build_recovery_boundary_observation,
    compute_fixture_identity_hash,
    evaluate_adversarial_fixture,
    load_adversarial_fixture,
    validate_adversarial_fixture,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO / "eval" / "fixtures" / "security"


def _policy() -> dict:
    return {
        "allow_shell_tools": False,
        "allow_filesystem_tools": False,
        "allow_network_tools": False,
        "approved_models": ["local-only"],
    }


def _holding_observation(fixture: AdversarialFixtureV1) -> SecurityObservationV1:
    benign_ids = [
        unit.evidence_id for unit in fixture.evidence if unit.role == "benign"
    ]
    kwargs: dict = {
        "configured_corpus_scope": "ics_modules",
        "observed_corpus_scope": "ics_modules",
        "observed_original_query": fixture.user_query,
        "configured_security_policy": _policy(),
        "observed_security_policy": _policy(),
        "capability_invocations": [],
        "emitted_citation_ids": [],
        "product_default_recovery_enabled": False,
        "recovery_execution_mode": "disabled",
        "recovery_components_entered": [],
    }
    if "retry_budget_immutable_v1" in fixture.expected_invariant_ids:
        kwargs["configured_retry_budget"] = 1
        kwargs["observed_retry_budget"] = 1
    if "evidence_surface_preserved_v1" in fixture.expected_invariant_ids:
        kwargs["required_evidence_surface_ids"] = list(benign_ids)
        kwargs["observed_evidence_surface_ids"] = list(benign_ids)
    if "protected_prompt_canary_non_disclosure_v1" in fixture.expected_invariant_ids:
        kwargs["protected_prompt_canary"] = "CANARY_SLICE13A_PROMPT_TOKEN"
        kwargs["generated_output_text"] = "The operating limit is 3000 psi."
    if "rewriter_input_isolation_v1" in fixture.expected_invariant_ids:
        kwargs["rewriter_surface_texts"] = [fixture.user_query, "typed-diagnostics-only"]
    return SecurityObservationV1(**kwargs)


def test_frozen_registry_hash_stable_and_nine_invariants() -> None:
    registry = build_frozen_security_invariant_registry()
    again = build_frozen_security_invariant_registry()
    assert registry.registry_hash == again.registry_hash
    assert registry.registry_hash.startswith("secinv_")
    assert len(registry.invariants) == 9


def test_all_eight_unit_fixtures_load_and_pass_with_holding_observations() -> None:
    paths = sorted(FIXTURE_DIR.glob("*.json"))
    assert len(paths) == 8
    for path in paths:
        fixture = load_adversarial_fixture(path)
        if fixture.path_under_test == "recovery_path":
            observation = build_recovery_boundary_observation(fixture)
        else:
            observation = _holding_observation(fixture)
        result = evaluate_adversarial_fixture(fixture, observation)
        assert result.outcome == FixtureOutcomeV1.PASS, path.name
        assert result.failure_kind is None
        assert result.registry_hash.startswith("secinv_")


def test_extra_field_rejected() -> None:
    path = FIXTURE_DIR / "secfx_ignore_001_query.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "nope"
    with pytest.raises(SecurityEvalError, match="schema validation failed"):
        validate_adversarial_fixture(payload)


def test_audit_shas_excluded_from_semantic_identity() -> None:
    fixture = load_adversarial_fixture(FIXTURE_DIR / "secfx_ignore_001_query.json")
    mutated = fixture.model_copy(
        update={
            "slice13_baseline_sha": "0" * 40,
            "design_authority_sha": "1" * 40,
        }
    )
    assert compute_fixture_identity_hash(mutated) == fixture.fixture_identity_hash


def test_identity_changes_when_semantic_field_changes() -> None:
    fixture = load_adversarial_fixture(FIXTURE_DIR / "secfx_ignore_001_query.json")
    mutated = fixture.model_copy(update={"user_query": "Different query?"})
    assert compute_fixture_identity_hash(mutated) != fixture.fixture_identity_hash


def test_wrong_declared_hash_fails_closed() -> None:
    path = FIXTURE_DIR / "secfx_ignore_001_query.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["fixture_identity_hash"] = "advfx_" + ("ab" * 32)
    with pytest.raises(SecurityEvalError, match="fixture_identity_hash mismatch"):
        validate_adversarial_fixture(payload)


def test_unknown_invariant_id_fails_closed() -> None:
    path = FIXTURE_DIR / "secfx_ignore_001_query.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["expected_invariant_ids"] = ["not_a_real_invariant_v1"]
    # Recompute hash for schema path that still validates IDs before hash.
    with pytest.raises(SecurityEvalError, match="unknown invariant"):
        validate_adversarial_fixture(payload)


def test_missing_observation_is_unevaluable_fail() -> None:
    fixture = load_adversarial_fixture(FIXTURE_DIR / "secfx_ignore_001_query.json")
    observation = SecurityObservationV1(
        product_default_recovery_enabled=False,
        recovery_execution_mode="disabled",
    )
    result = evaluate_adversarial_fixture(fixture, observation)
    assert result.outcome == FixtureOutcomeV1.FAIL
    assert result.failure_kind == "invariant_unevaluable"
    assert any(
        row.status == InvariantStatusV1.UNEVALUABLE for row in result.invariant_outcomes
    )


def test_individual_violation_fails() -> None:
    fixture = load_adversarial_fixture(FIXTURE_DIR / "secfx_citation_001_query.json")
    observation = _holding_observation(fixture).model_copy(
        update={"emitted_citation_ids": ["ev_fabricated_not_allowed"]}
    )
    result = evaluate_adversarial_fixture(fixture, observation)
    assert result.outcome == FixtureOutcomeV1.FAIL
    assert result.failure_kind == "invariant_violation"
    citation = next(
        row
        for row in result.invariant_outcomes
        if row.invariant_id == "citation_scope_v1"
    )
    assert citation.status == InvariantStatusV1.VIOLATED


def test_recovery_probe_rejects_corpus_field_and_isolates_surface() -> None:
    fixture = load_adversarial_fixture(
        FIXTURE_DIR / "secfx_rewrite_isolation_001_recovery.json"
    )
    assert_corpus_text_rejected_from_rewrite_input(
        original_query=fixture.user_query,
        illicit_corpus_text="CORPUS_LEAK_MARKER_13A",
    )
    observation = build_recovery_boundary_observation(fixture)
    assert observation.recovery_execution_mode == "harness_fake"
    assert observation.product_default_recovery_enabled is False
    assert observation.recovery_components_entered == [
        "rewriter_input",
        "recovery_rewriter",
    ]
    result = evaluate_adversarial_fixture(fixture, observation)
    assert result.outcome == FixtureOutcomeV1.PASS
    assert "CORPUS_LEAK_MARKER_13A" not in "\n".join(
        observation.rewriter_surface_texts or []
    )


def test_recovery_components_entered_recorded_on_result() -> None:
    fixture = load_adversarial_fixture(
        FIXTURE_DIR / "secfx_rewrite_isolation_001_recovery.json"
    )
    observation = build_recovery_boundary_observation(fixture)
    result = evaluate_adversarial_fixture(fixture, observation)
    assert result.recovery_components_entered == [
        "rewriter_input",
        "recovery_rewriter",
    ]
    assert result.recovery_execution_mode == "harness_fake"


def test_fixture_provenance_matches_locked_authority() -> None:
    fixture = load_adversarial_fixture(FIXTURE_DIR / "secfx_shell_001_query.json")
    assert fixture.slice13_baseline_sha == SLICE13_BASELINE_SHA
    assert fixture.design_authority_sha == DESIGN_AUTHORITY_SHA_13


def test_prompt_canary_leak_fails() -> None:
    fixture = load_adversarial_fixture(
        FIXTURE_DIR / "secfx_prompt_extract_001_query.json"
    )
    observation = _holding_observation(fixture).model_copy(
        update={
            "protected_prompt_canary": "CANARY_SLICE13A_PROMPT_TOKEN",
            "generated_output_text": "leak CANARY_SLICE13A_PROMPT_TOKEN here",
        }
    )
    result = evaluate_adversarial_fixture(fixture, observation)
    assert result.outcome == FixtureOutcomeV1.FAIL
    assert result.failure_kind == "invariant_violation"
