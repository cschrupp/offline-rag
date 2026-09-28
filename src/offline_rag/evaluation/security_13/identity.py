"""Canonical serialization / identity helpers for Slice 13A."""

from __future__ import annotations

from typing import Any

from offline_rag.core.ids import (
    adversarial_fixture_hash,
    security_invariant_registry_hash,
)
from offline_rag.evaluation.security_13.contracts import (
    ADVERSARIAL_FIXTURE_V1,
    SECURITY_INVARIANT_REGISTRY_V1,
    AdversarialFixtureV1,
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


def fixture_semantic_payload(fixture: AdversarialFixtureV1) -> dict[str, Any]:
    """Build the identity-bearing fixture payload (excludes audit SHAs)."""
    raw = fixture.model_dump(mode="json")
    payload = {key: value for key, value in raw.items() if key not in _FIXTURE_AUDIT_ONLY_FIELDS}
    payload["contract"] = ADVERSARIAL_FIXTURE_V1
    return payload


def compute_fixture_identity_hash(fixture: AdversarialFixtureV1) -> str:
    """Return ``advfx_`` semantic identity for a validated fixture body."""
    return adversarial_fixture_hash(fixture_semantic_payload(fixture))


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
