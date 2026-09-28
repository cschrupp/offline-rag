"""Canonical serialization / identity helpers for Slice 13A / 13B."""

from __future__ import annotations

from typing import Any

from offline_rag.core.ids import (
    adversarial_fixture_hash,
    benign_security_control_hash,
    security_campaign_hash,
    security_invariant_registry_hash,
)
from offline_rag.evaluation.security_13.contracts import (
    ADVERSARIAL_FIXTURE_V1,
    BENIGN_SECURITY_CONTROL_V1,
    SECURITY_CAMPAIGN_V1,
    SECURITY_INVARIANT_REGISTRY_V1,
    AdversarialFixtureV1,
    BenignSecurityControlV1,
    SecurityCampaignV1,
    SecurityInvariantRegistryV1,
)

# Explicitly excluded from semantic fixture identity (audit provenance only).
_FIXTURE_AUDIT_ONLY_FIELDS = frozenset(
    {
        "slice13_baseline_sha",
        "design_authority_sha",
        "fixture_identity_hash",
    }
)

_BENIGN_AUDIT_ONLY_FIELDS = frozenset(
    {
        "slice13b_baseline_sha",
        "design_authority_sha",
        "control_identity_hash",
    }
)

_CAMPAIGN_AUDIT_ONLY_FIELDS = frozenset(
    {
        "slice13b_baseline_sha",
        "design_authority_sha",
        "campaign_identity_hash",
    }
)


def fixture_semantic_payload(fixture: AdversarialFixtureV1) -> dict[str, Any]:
    """Build the identity-bearing fixture payload (excludes audit SHAs)."""
    raw = fixture.model_dump(mode="json")
    payload = {key: value for key, value in raw.items() if key not in _FIXTURE_AUDIT_ONLY_FIELDS}
    payload["contract"] = ADVERSARIAL_FIXTURE_V1
    return payload


def compute_fixture_identity_hash(fixture: AdversarialFixtureV1) -> str:
    """Return ``advfx_`` semantic identity for a validated fixture body."""
    return adversarial_fixture_hash(fixture_semantic_payload(fixture))


def benign_control_semantic_payload(control: BenignSecurityControlV1) -> dict[str, Any]:
    """Build the identity-bearing benign-control payload (excludes audit SHAs)."""
    raw = control.model_dump(mode="json")
    payload = {
        key: value for key, value in raw.items() if key not in _BENIGN_AUDIT_ONLY_FIELDS
    }
    payload["contract"] = BENIGN_SECURITY_CONTROL_V1
    return payload


def compute_benign_control_identity_hash(control: BenignSecurityControlV1) -> str:
    """Return ``benc_`` semantic identity for a validated benign control."""
    return benign_security_control_hash(benign_control_semantic_payload(control))


def campaign_semantic_payload(campaign: SecurityCampaignV1) -> dict[str, Any]:
    """Build the identity-bearing campaign payload (excludes audit SHAs)."""
    raw = campaign.model_dump(mode="json")
    payload = {
        key: value for key, value in raw.items() if key not in _CAMPAIGN_AUDIT_ONLY_FIELDS
    }
    payload["contract"] = SECURITY_CAMPAIGN_V1
    # Stable ordering for membership lists (identity-bearing).
    payload["adversarial_cases"] = sorted(
        payload["adversarial_cases"], key=lambda row: row["fixture_id"]
    )
    payload["benign_controls"] = sorted(
        payload["benign_controls"], key=lambda row: row["control_id"]
    )
    payload["population_policy"]["required_attack_classes"] = sorted(
        payload["population_policy"]["required_attack_classes"]
    )
    return payload


def compute_campaign_identity_hash(campaign: SecurityCampaignV1) -> str:
    """Return ``seccamp_`` semantic identity for a validated campaign body."""
    return security_campaign_hash(campaign_semantic_payload(campaign))


def registry_semantic_payload(registry: SecurityInvariantRegistryV1) -> dict[str, Any]:
    """Build the identity-bearing registry payload (excludes registry_hash)."""
    return {
        "contract": SECURITY_INVARIANT_REGISTRY_V1,
        "invariants": [
            {"invariant_id": item.invariant_id, "property": item.property}
            for item in sorted(registry.invariants, key=lambda row: row.invariant_id)
        ],
    }


def compute_registry_hash(registry: SecurityInvariantRegistryV1) -> str:
    """Return ``secinv_`` identity for a registry body."""
    return security_invariant_registry_hash(registry_semantic_payload(registry))
