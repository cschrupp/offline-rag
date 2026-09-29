"""Strict adversarial / benign / campaign loaders (OD-13-3 / OD-13-8 / OD-13-9)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.evaluation.security_13.contracts import (
    DESIGN_AUTHORITY_SHA_13,
    DESIGN_AUTHORITY_SHA_13B,
    REQUIRED_ATTACK_CLASSES_V1,
    SLICE13_BASELINE_SHA,
    SLICE13B_BASELINE_SHA,
    AdversarialFixtureV1,
    BenignSecurityControlV1,
    SecurityCampaignV1,
    SecurityEvalError,
)
from offline_rag.evaluation.security_13.identity import (
    compute_benign_control_identity_hash,
    compute_campaign_identity_hash,
    compute_fixture_identity_hash,
)
from offline_rag.evaluation.security_13.registry import (
    build_frozen_security_invariant_registry,
    require_known_invariant_ids,
)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SecurityEvalError(f"failed to read fixture JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SecurityEvalError(f"fixture root must be a JSON object: {path}")
    return payload


def validate_adversarial_fixture(
    payload: dict[str, Any],
    *,
    require_design_authority_sha: str = DESIGN_AUTHORITY_SHA_13,
    require_slice13_baseline_sha: str = SLICE13_BASELINE_SHA,
) -> AdversarialFixtureV1:
    """Validate fixture schema and semantic identity; fail closed on mismatch."""
    try:
        fixture = AdversarialFixtureV1.model_validate(payload)
    except ValidationError as exc:
        raise SecurityEvalError(
            f"adversarial fixture schema validation failed: {exc}"
        ) from exc

    require_known_invariant_ids(list(fixture.expected_invariant_ids))

    if fixture.slice13_baseline_sha != require_slice13_baseline_sha:
        raise SecurityEvalError(
            "slice13_baseline_sha mismatch: "
            f"expected {require_slice13_baseline_sha!r}, "
            f"got {fixture.slice13_baseline_sha!r}"
        )
    if fixture.design_authority_sha != require_design_authority_sha:
        raise SecurityEvalError(
            "design_authority_sha mismatch: "
            f"expected {require_design_authority_sha!r}, "
            f"got {fixture.design_authority_sha!r}"
        )

    recomputed = compute_fixture_identity_hash(fixture)
    if fixture.fixture_identity_hash != recomputed:
        raise SecurityEvalError(
            "fixture_identity_hash mismatch: "
            f"declared {fixture.fixture_identity_hash!r}, recomputed {recomputed!r}"
        )
    return fixture


def load_adversarial_fixture(path: Path | str) -> AdversarialFixtureV1:
    """Load and fail-closed-validate one adversarial fixture file."""
    return validate_adversarial_fixture(_load_json_object(Path(path)))


def validate_benign_control(
    payload: dict[str, Any],
    *,
    require_design_authority_sha: str = DESIGN_AUTHORITY_SHA_13B,
    require_slice13b_baseline_sha: str = SLICE13B_BASELINE_SHA,
) -> BenignSecurityControlV1:
    """Validate benign-control schema and semantic identity."""
    try:
        control = BenignSecurityControlV1.model_validate(payload)
    except ValidationError as exc:
        raise SecurityEvalError(
            f"benign control schema validation failed: {exc}"
        ) from exc

    require_known_invariant_ids(list(control.expected_invariant_ids))

    if control.slice13b_baseline_sha != require_slice13b_baseline_sha:
        raise SecurityEvalError(
            "slice13b_baseline_sha mismatch: "
            f"expected {require_slice13b_baseline_sha!r}, "
            f"got {control.slice13b_baseline_sha!r}"
        )
    if control.design_authority_sha != require_design_authority_sha:
        raise SecurityEvalError(
            "design_authority_sha mismatch: "
            f"expected {require_design_authority_sha!r}, "
            f"got {control.design_authority_sha!r}"
        )

    recomputed = compute_benign_control_identity_hash(control)
    if control.control_identity_hash != recomputed:
        raise SecurityEvalError(
            "control_identity_hash mismatch: "
            f"declared {control.control_identity_hash!r}, recomputed {recomputed!r}"
        )
    return control


def load_benign_control(path: Path | str) -> BenignSecurityControlV1:
    """Load and fail-closed-validate one benign-control file."""
    return validate_benign_control(_load_json_object(Path(path)))


def validate_security_campaign(
    payload: dict[str, Any],
    *,
    require_design_authority_sha: str = DESIGN_AUTHORITY_SHA_13B,
    require_slice13b_baseline_sha: str = SLICE13B_BASELINE_SHA,
) -> SecurityCampaignV1:
    """Validate campaign schema and embedded seccamp_ identity."""
    try:
        campaign = SecurityCampaignV1.model_validate(payload)
    except ValidationError as exc:
        raise SecurityEvalError(
            f"security campaign schema validation failed: {exc}"
        ) from exc

    if campaign.slice13b_baseline_sha != require_slice13b_baseline_sha:
        raise SecurityEvalError(
            "campaign slice13b_baseline_sha mismatch: "
            f"expected {require_slice13b_baseline_sha!r}, "
            f"got {campaign.slice13b_baseline_sha!r}"
        )
    if campaign.design_authority_sha != require_design_authority_sha:
        raise SecurityEvalError(
            "campaign design_authority_sha mismatch: "
            f"expected {require_design_authority_sha!r}, "
            f"got {campaign.design_authority_sha!r}"
        )

    registry = build_frozen_security_invariant_registry()
    if campaign.registry_hash != registry.registry_hash:
        raise SecurityEvalError(
            "campaign registry_hash mismatch: "
            f"declared {campaign.registry_hash!r}, "
            f"expected {registry.registry_hash!r}"
        )

    recomputed = compute_campaign_identity_hash(campaign)
    if campaign.campaign_identity_hash != recomputed:
        raise SecurityEvalError(
            "campaign_identity_hash mismatch: "
            f"declared {campaign.campaign_identity_hash!r}, "
            f"recomputed {recomputed!r}"
        )
    return campaign


def load_security_campaign(path: Path | str) -> SecurityCampaignV1:
    """Load and fail-closed-validate one campaign definition file."""
    return validate_security_campaign(_load_json_object(Path(path)))


def assert_population_policy(
    campaign: SecurityCampaignV1,
    *,
    attack_class_counts: dict[str, int],
) -> None:
    """Fail-closed population_policy checks (OD-13-9).

    Declared minima must match the frozen 13B policy (1 per class, 5 benign),
    not merely act as caller-selected thresholds.
    """
    policy = campaign.population_policy
    required = set(policy.required_attack_classes)
    expected_required = set(REQUIRED_ATTACK_CLASSES_V1)
    if required != expected_required:
        raise SecurityEvalError(
            "population_policy.required_attack_classes must equal the locked seven "
            f"classes; got {sorted(required)!r}"
        )
    if policy.minimum_per_attack_class != 1:
        raise SecurityEvalError(
            "population_policy.minimum_per_attack_class must be 1 for 13B; "
            f"got {policy.minimum_per_attack_class}"
        )
    if policy.minimum_benign_controls != 5:
        raise SecurityEvalError(
            "population_policy.minimum_benign_controls must be 5 for 13B; "
            f"got {policy.minimum_benign_controls}"
        )
    for attack_class in expected_required:
        count = int(attack_class_counts.get(attack_class, 0))
        if count < policy.minimum_per_attack_class:
            raise SecurityEvalError(
                f"attack class {attack_class!r} below minimum_per_attack_class: "
                f"{count} < {policy.minimum_per_attack_class}"
            )
    if len(campaign.benign_controls) < policy.minimum_benign_controls:
        raise SecurityEvalError(
            "benign control population below minimum_benign_controls: "
            f"{len(campaign.benign_controls)} < {policy.minimum_benign_controls}"
        )
